"""Track, find candidate involvements, and send only those to the model."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.budget import estimate_usd
from app.config import Settings
from app.db import Database
from app.schemas import ScoutReport
from app.scout.calls import decide_batch, finish_batch
from app.scout.chunks import chunk_ranges, stitch
from app.scout.discover import Event, coverage, dedupe, discover
from app.scout.frames import context_jpeg, iter_frames, scaled_size, scene_cut, torso_hue, video_size
from app.scout.identity import Box, Det, FrameObs, Point, follow
from app.scout.validate import validate_scout
from app.versions import SCOUT_PROMPT_VERSION, SCOUT_SCHEMA_VERSION, TRACKER_VERSION

PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "scout_v1.md").read_text(encoding="utf-8")

CATEGORY = {
    "receive": "first_touch",
    "pass": "passing_action",
    "carry": "carrying_action",
    "loss": "loss_of_possession",
}
VISIBLE_OUTCOME = {
    "completed": "completed_visible",
    "controlled": "completed_visible",
    "retained": "completed_visible",
    "intercepted": "unsuccessful_visible",
    "out_of_play": "unsuccessful_visible",
    "miscontrolled": "unsuccessful_visible",
    "lost": "unsuccessful_visible",
    "unclear": "not_observable",
}


def follow_anchors(frames: list[FrameObs], anchors: list[tuple[int, Box]]) -> tuple[list[Point], list]:
    """Each anchor resumes identity. Tracking does not continue through a later anchor."""
    ordered = sorted(anchors, key=lambda item: item[0])
    points: list[Point] = []
    corrections = []
    for index, (t_ms, box) in enumerate(ordered):
        end = ordered[index + 1][0] if index + 1 < len(ordered) else None
        segment = [frame for frame in frames if frame.t_ms >= t_ms - 50 and (end is None or frame.t_ms < end)]
        seg_points, seg_corrections = follow(segment, t_ms, box)
        points.extend(seg_points)
        if end is None:
            corrections.extend(seg_corrections)
    return stitch([points]), corrections


def _cache_file(root: Path, sha: str, start_ms: int, end_ms: int) -> Path:
    return root / "tracks" / sha / TRACKER_VERSION / f"{start_ms}_{end_ms}.json"


def _load_frames(path: Path) -> list[FrameObs]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    frames = []
    for item in raw["frames"]:
        frames.append(
            FrameObs(
                item["t_ms"],
                [Det(person["track_id"], tuple(person["box"]), person.get("confidence", 1), "person", tuple(person["hue"]) if person.get("hue") else None) for person in item["people"]],
                [Det(0, tuple(ball["box"]), ball.get("confidence", 1), "ball") for ball in item.get("balls", [])],
                item.get("cut", False),
            )
        )
    return frames


def _dump_frame(frame: FrameObs) -> dict:
    return {
        "t_ms": frame.t_ms,
        "cut": frame.cut,
        "people": [
            {"track_id": person.track_id, "box": list(person.box), "confidence": person.confidence, "hue": list(person.hue) if person.hue else None}
            for person in frame.people
        ],
        "balls": [{"box": list(ball.box), "confidence": ball.confidence} for ball in frame.balls],
    }


def track_interval(video: Path, sha: str, start_ms: int, end_ms: int, root: Path, tracker, on_chunk) -> list[FrameObs]:
    width, height = scaled_size(*video_size(video))
    ranges = chunk_ranges(start_ms, end_ms)
    chunks: list[list[FrameObs]] = []
    for index, (chunk_start, chunk_end) in enumerate(ranges):
        path = _cache_file(root, sha, chunk_start, chunk_end)
        if path.exists():
            chunks.append(_load_frames(path))
        else:
            tracker.reset()
            previous = None
            frames: list[FrameObs] = []
            for t_ms, image in iter_frames(video, chunk_start, chunk_end, 10, width, height):
                cut, previous = scene_cut(previous, image)
                people = []
                for person in tracker.track_people(image):
                    people.append(Det(person.track_id, person.box, person.confidence, "person", torso_hue(image, person.box)))
                frames.append(FrameObs(t_ms, people, [], cut))
            # A second pass finds the ball near every detected person only after identity is known.
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"frames": [_dump_frame(frame) for frame in frames]}), encoding="utf-8")
            chunks.append(frames)
        on_chunk(index + 1, len(ranges))
    return stitch_frames(chunks)


def stitch_frames(chunks: list[list[FrameObs]]) -> list[FrameObs]:
    merged: list[FrameObs] = []
    seen: set[int] = set()
    for chunk in chunks:
        for frame in chunk:
            if frame.t_ms in seen:
                continue
            seen.add(frame.t_ms)
            merged.append(frame)
    merged.sort(key=lambda frame: frame.t_ms)
    return merged


def attach_balls(video: Path, frames: list[FrameObs], points: list[Point], tracker) -> list[FrameObs]:
    """Detect the ball on a crop around the followed player. One nearby ball is stored."""
    wanted = {point.t_ms: point.box for point in points if point.state == "tracked" and point.box and point.ball is None}
    if not wanted:
        return frames
    by_time = {frame.t_ms: frame for frame in frames}
    width, height = scaled_size(*video_size(video))
    groups = _runs(sorted(wanted))
    for start, end in groups:
        for t_ms, image in iter_frames(video, start, end, 10, width, height):
            box = wanted.get(t_ms)
            frame = by_time.get(t_ms)
            if box is None or frame is None or frame.balls:
                continue
            frame.balls = tracker.balls_in_crop(image, box)[:1]
    return frames


def _runs(times: list[int]) -> list[tuple[int, int]]:
    if not times:
        return []
    runs = [[times[0], times[0]]]
    for t_ms in times[1:]:
        if t_ms - runs[-1][1] <= 400:
            runs[-1][1] = t_ms
        else:
            runs.append([t_ms, t_ms])
    return [(start, end + 100) for start, end in runs]


def event_payload(event: Event, index: int) -> dict:
    detail = event.outcome
    return {
        "key": f"sc_{event.action}_{event.start_ms}_{event.end_ms}",
        "category": CATEGORY[event.action],
        "action": event.action,
        "outcomeDetail": detail,
        "startMs": event.start_ms,
        "endMs": event.end_ms,
        "seekMs": event.start_ms,
        "frameIds": list(event.frame_ids),
        "visibleAction": event.visible_action,
        "outcome": VISIBLE_OUTCOME.get(detail, "not_observable"),
        "evidenceStatus": event.evidence_status,
        "identityStatus": event.identity_status,
        "limitations": list(event.limitations),
        "attributionHold": event.identity_status != "clear_in_cited_frames",
        "holdReason": None if event.identity_status == "clear_in_cited_frames" else "The selected player is not clear in the cited frames.",
        "holdFrameId": None,
    }


def inspect_candidates(
    db: Database,
    settings: Settings,
    *,
    job_id: str,
    video: Path,
    points: list[Point],
    candidates,
    model,
    stop,
    on_events=None,
) -> tuple[list[Event], str]:
    """Returns accepted events and a stop reason: ok, budget, cancel, or unknown."""
    width, height = scaled_size(*video_size(video))
    events: list[Event] = []
    reason = "ok"
    notes: list[str] = []
    inspected = 0
    batch: list = []

    def flush() -> str:
        nonlocal reason
        if not batch:
            return "ok"
        images = []
        windows = {}
        frames_by_id = {}
        content = [{"type": "text", "text": f"schema_version={SCOUT_SCHEMA_VERSION}\nQuestion: what does the selected player do when receiving and moving the ball?"}]
        number = 0
        for candidate, rendered in batch:
            windows[candidate_id(candidate)] = (candidate.start_ms, candidate.end_ms)
            content.append({"type": "text", "text": f"candidate_id={candidate_id(candidate)} touch {candidate.touch_start_ms}-{candidate.touch_end_ms}"})
            for t_ms, jpeg in rendered:
                number += 1
                frame_id = f"f{number:02d}"
                frames_by_id[frame_id] = t_ms
                content.append({"type": "text", "text": f"frame_id={frame_id} source_t_ms={t_ms}"})
                content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _b64(jpeg)}})
                images.append(jpeg)
        fingerprint = hashlib.sha256(b"".join(images) + SCOUT_PROMPT_VERSION.encode()).hexdigest()
        batch_key = fingerprint[:16]
        amount = _estimate(model, content)
        decision = decide_batch(db, settings, job_id=job_id, batch_key=batch_key, fingerprint=fingerprint, amount=amount)
        if decision.action == "skip_budget":
            reason = "budget"
            return reason
        if decision.action in {"skip_unknown", "skip_failed"}:
            notes.append(decision.action)
            batch.clear()
            return "ok"
        if decision.action == "cache" and decision.response_json:
            report = ScoutReport.model_validate_json(decision.response_json)
        else:
            try:
                report, usage = model.interpret(PROMPT, [{"role": "user", "content": content}])
            except Exception as exc:
                from app.providers.base import ProviderError

                definite = isinstance(exc, ProviderError) and not exc.billed
                finish_batch(
                    db, settings, job_id=job_id, batch_key=batch_key, fingerprint=fingerprint,
                    reservation_id=decision.reservation_id or "", amount=amount,
                    outcome="failed" if definite else "unknown",
                    usage=getattr(exc, "usage", None),
                )
                reason = "ok" if definite and getattr(exc, "retryable", False) else ("failed" if definite else "unknown")
                batch.clear()
                return "ok" if reason == "ok" else reason
            body = report.model_dump_json()
            finish_batch(
                db, settings, job_id=job_id, batch_key=batch_key, fingerprint=fingerprint,
                reservation_id=decision.reservation_id or "", amount=amount, outcome="succeeded",
                response_json=body, usage=usage,
            )
            report = ScoutReport.model_validate_json(body)
        checked = validate_scout(report, windows=windows, frames_by_id=frames_by_id)
        events.extend(checked.events)
        if checked.events and on_events:
            on_events(list(checked.events))
        batch.clear()
        return "ok"

    for candidate in candidates:
        if stop():
            return dedupe(events), "cancel"
        rendered = _render_candidate(video, candidate, points, width, height)
        if not rendered:
            continue
        batch.append((candidate, rendered))
        inspected += 1
        if len(batch) == 3:
            if flush() in {"budget", "failed"}:
                break
    if reason == "ok":
        flush()
    return dedupe(events), reason


def candidate_id(candidate) -> str:
    return f"c{candidate.touch_start_ms}"


def _render_candidate(video, candidate, points, width, height):
    tracked = [point for point in points if point.state == "tracked" and point.box and candidate.start_ms <= point.t_ms <= candidate.end_ms]
    if not tracked:
        return []
    span = max(1, candidate.end_ms - candidate.start_ms)
    fps = max(1, min(8, int(12 * 1000 / span)))
    rendered = []
    nearest = {point.t_ms: point.box for point in tracked}
    for t_ms, image in iter_frames(video, candidate.start_ms, candidate.end_ms, fps, width, height):
        box = min(nearest, key=lambda item: abs(item - t_ms), default=None)
        if box is None or abs(box - t_ms) > 500:
            continue
        rendered.append((t_ms, context_jpeg(image, nearest[box])))
        if len(rendered) >= 12:
            break
    return rendered


def _b64(jpeg: bytes) -> str:
    import base64

    return base64.b64encode(jpeg).decode("ascii")


def _estimate(model, content) -> float:
    try:
        tokens = model.count_tokens(PROMPT, [{"role": "user", "content": content}])
    except Exception:
        tokens = 1500 * sum(1 for item in content if isinstance(item, dict) and item.get("type") == "image")
    return estimate_usd(model.settings, tokens)


class ClaudeScout:
    """The live model. Tests pass a fake with the same two methods."""

    def __init__(self, settings: Settings) -> None:
        from app.providers.anthropic import AnthropicProvider

        self.settings = settings
        self.provider = AnthropicProvider(
            settings.anthropic_api_key,
            settings.anthropic_model,
            settings.provider_timeout_seconds,
            settings.max_output_tokens,
        )

    def count_tokens(self, system: str, messages: list[dict]) -> int:
        return self.provider.count_tokens(system, messages)

    def interpret(self, system: str, messages: list[dict]):
        from app.providers.anthropic import _usage

        response = self.provider.client.messages.parse(
            model=self.provider.model,
            max_tokens=self.provider.max_output_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            output_format=ScoutReport,
        )
        parsed = response.parsed_output
        if parsed is None:
            from app.providers.base import ProviderError

            raise ProviderError("malformed_output", "The model response did not match the scouting schema.", billed=True, usage=_usage(response.usage))
        return parsed, _usage(response.usage)


def narrate_findings(db, settings, job_id: str, events: list[Event], model) -> list[dict]:
    """One text-only call. A finding is kept only when every cited event is real."""
    if not events or model is None or not getattr(model, "provider", None):
        return []
    listing = [
        {"id": event_payload(event, index)["key"], "action": event.action, "outcome": event.outcome, "text": event.visible_action, "start_ms": event.start_ms}
        for index, event in enumerate(events)
    ]
    known = {item["id"] for item in listing}
    fingerprint = hashlib.sha256(json.dumps(listing, sort_keys=True).encode()).hexdigest()
    amount = estimate_usd(settings, 800)
    decision = decide_batch(db, settings, job_id=job_id, batch_key="brief", fingerprint=fingerprint, amount=amount)
    if decision.action == "cache" and decision.response_json:
        return _accepted_findings(decision.response_json, known)
    if decision.action != "send" or decision.reservation_id is None:
        return []
    system = (
        "You write a coach's briefing from a list of events that were already detected. "
        "Use only those events. Return at most 3 findings. Copy event ids exactly. "
        "Do not rate the player, rank them, or invent an action. "
        f"Set schema_version to {SCOUT_SCHEMA_VERSION}."
    )
    try:
        from app.providers.anthropic import _usage

        response = model.provider.client.messages.parse(
            model=model.provider.model,
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": json.dumps({"events": listing})}],
            output_format=NarratedBrief,
        )
        parsed = response.parsed_output
        usage = _usage(response.usage)
        if parsed is None or parsed.schema_version != SCOUT_SCHEMA_VERSION:
            finish_batch(db, settings, job_id=job_id, batch_key="brief", fingerprint=fingerprint, reservation_id=decision.reservation_id, amount=amount, outcome="failed", usage=usage)
            return []
        kept = [finding for finding in parsed.findings if finding.event_ids and set(finding.event_ids) <= known][:3]
        body = json.dumps([{"text": finding.text, "eventIds": finding.event_ids} for finding in kept])
        finish_batch(db, settings, job_id=job_id, batch_key="brief", fingerprint=fingerprint, reservation_id=decision.reservation_id, amount=amount, outcome="succeeded", response_json=body, usage=usage)
        return json.loads(body)
    except Exception:
        log_brief = __import__("logging").getLogger("secondlook.scout")
        log_brief.warning("brief call failed")
        finish_batch(db, settings, job_id=job_id, batch_key="brief", fingerprint=fingerprint, reservation_id=decision.reservation_id, amount=amount, outcome="unknown")
        return []


def _accepted_findings(raw: str, known: set[str]) -> list[dict]:
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [row for row in rows if isinstance(row, dict) and set(row.get("eventIds") or []) <= known][:3]


def run_scout(db, settings, *, video: Path, sha: str, start_ms: int, end_ms: int, anchors: list[tuple[int, Box]], job_id: str, tracker, model, progress, stop, on_events=None) -> dict:
    """Read the upload-time tracks, follow the clicked player, and publish possession events."""
    del tracker
    from app.scout.possession import events_for, follow_track, select_track
    from app.scout.roboflow import load_tracks

    document = load_tracks(settings.data_path, sha)
    if document is None:
        return {"state": "failed", "events": [], "corrections": [], "note": "Player tracking has not finished for this clip.", "coverage": {}, "candidates": 0, "narrative": []}
    frames = [frame for frame in document["frames"] if start_ms - 100 <= frame["t"] <= end_ms]
    progress({"phase": "tracking", "chunksDone": 1, "chunksTotal": 1, "message": "Using the saved tracks"})
    if stop():
        return {"state": "cancelled", "events": [], "corrections": [], "note": "Cancelled.", "coverage": {}, "candidates": 0, "narrative": []}
    box = anchors[0][1] if anchors else (0.5, 0.5, 0.04, 0.1)
    anchor_t = anchors[0][0] if anchors else start_ms
    track_id = select_track(frames, anchor_t, box)
    if track_id is None:
        return {"state": "failed", "events": [], "corrections": [], "note": "The click did not land on a tracked player. Click the player again.", "coverage": {}, "candidates": 0, "narrative": []}
    points, corrections, identity = follow_track(frames, track_id, anchor_t)
    events = events_for(frames, identity)
    progress({"phase": "inspecting", "candidates": len(events), "message": f"{len(events)} possession events"})
    narrative = []
    if events and not stop():
        narrative = narrate_findings(db, settings, job_id, events, model)
    if on_events and events:
        on_events(events)
    tracked = _state_ms(points, "tracked")
    lost = _state_ms(points, "lost")
    note = f"Tracked {tracked / 1000:.1f}s and lost the player for {lost / 1000:.1f}s. {len(events)} possession events."
    return {
        "state": "succeeded",
        "events": [event_payload(event, index) for index, event in enumerate(events)],
        "corrections": corrections,
        "note": note,
        "coverage": {"tracked_ms": tracked, "lost_ms": lost},
        "candidates": len(events),
        "narrative": narrative,
    }


def _state_ms(points: list[Point], state: str) -> int:
    total = 0
    for index, point in enumerate(points[:-1]):
        if point.state == state:
            total += max(0, points[index + 1].t_ms - point.t_ms)
    return total


class NarratedFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=280)
    event_ids: list[str] = Field(min_length=1, max_length=8)


class NarratedBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    findings: list[NarratedFinding] = Field(default_factory=list, max_length=3)


def coverage_note(points: list[Point], candidates, inspected_reason: str, inspected: int) -> str:
    totals = coverage(points)
    partial = ""
    if inspected_reason == "budget":
        partial = f" Inspected part of {len(candidates)} candidates; the cost limit was reached."
    elif inspected_reason == "cancel":
        partial = " Analysis was cancelled. Completed findings are kept."
    elif inspected_reason == "unknown":
        partial = " One model call ended without a stored result and was not repeated."
    return (
        f"Tracked {totals['tracked_ms'] / 1000:.1f}s, lost the player for {totals['lost_ms'] / 1000:.1f}s, "
        f"and did not see the ball for {totals['ball_unseen_ms'] / 1000:.0f}s of the tracked time."
        + partial
    )
