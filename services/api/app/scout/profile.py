"""One text call that turns every finished clip into a single player profile."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.budget import actual_usd, estimate_usd
from app.jobs import model_name
from app.opportunities import NUMBER, _banned, summary_ok
from app.versions import PROFILE_PROMPT_VERSION, PROFILE_SCHEMA_VERSION

log = logging.getLogger("secondlook.profile")
PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "profile_v1.md").read_text(encoding="utf-8")

MATCHING = {
    "ball_security": {"loss"},
    "passing": {"pass"},
    "carrying": {"carry"},
    "involvement": {"receive", "pass", "carry", "loss"},
}
COMPLETED = {"completed", "completed_visible"}


class ProfileQualityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=280)
    event_ids: list[str] = Field(min_length=1, max_length=8)


class AbilityDimensionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["ball_security", "passing", "carrying", "involvement"]
    score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=240)
    event_ids: list[str] = Field(min_length=2, max_length=12)


class AbilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overall: int = Field(ge=0, le=100)
    dimensions: list[AbilityDimensionIn] = Field(default_factory=list, max_length=4)


class PlayerProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    summary: str = Field(min_length=1, max_length=600)
    qualities: list[ProfileQualityIn] = Field(default_factory=list, max_length=4)
    gaps: list[str] = Field(default_factory=list, max_length=6)
    ability: AbilityIn | None = None


def _fmt(value: float) -> str:
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def _counts(events: list[dict]) -> Counter:
    counts: Counter = Counter()
    for event in events:
        action = event.get("action") or ""
        counts[action] += 1
        if action == "pass" and event.get("outcome") in COMPLETED:
            counts["pass_completed"] += 1
    return counts


def _line(label: str, tracked_ms: int, counts: Counter) -> str:
    return (
        f"{label}: tracked {_fmt(tracked_ms / 1000)}s, receives {counts['receive']}, "
        f"passes {counts['pass_completed']} completed of {counts['pass']}, "
        f"carries {counts['carry']}, losses {counts['loss']}"
    )


def stats_table(clips: list[dict]) -> tuple[str, list[dict], dict[str, str]]:
    """Returns the table, the event listing, and id to action."""
    lines = []
    listing = []
    actions: dict[str, str] = {}
    total: Counter = Counter()
    tracked = 0
    for clip in clips:
        events = list(clip.get("events") or [])
        counts = _counts(events)
        total.update(counts)
        tracked_ms = int(clip.get("trackedMs") or 0)
        tracked += tracked_ms
        lines.append(_line(f"Clip {clip.get('order')}", tracked_ms, counts))
        for event in events:
            event_id = str(event.get("id") or "")
            action = str(event.get("action") or "")
            if not event_id or not action:
                continue
            actions[event_id] = action
            listing.append(
                {
                    "id": event_id,
                    "clip": clip.get("order"),
                    "action": action,
                    "outcome": event.get("outcome") or "",
                    "text": event.get("text") or "",
                    "start_ms": event.get("startMs") or 0,
                    "identity": "held" if event.get("held") else "clear",
                }
            )
    lines.append(_line(f"Total across {len(clips)} clips", tracked, total))
    return "\n".join(lines), listing, actions


def text_ok(text: str, table: str) -> bool:
    cleaned = " ".join(text.split())
    if not cleaned or _banned(cleaned):
        return False
    known = {float(token) for token in NUMBER.findall(table)}
    return all(float(token) in known for token in NUMBER.findall(cleaned))


def validate_profile(parsed: PlayerProfileIn, *, actions: dict[str, str], table: str) -> dict | None:
    """Drops qualities and dimensions that do not cite real events. A bad summary drops the profile."""
    if parsed.schema_version != PROFILE_SCHEMA_VERSION or not summary_ok(parsed.summary, table):
        return None
    known = set(actions)
    qualities = []
    for quality in parsed.qualities:
        if not set(quality.event_ids) <= known or not text_ok(quality.text, table):
            continue
        qualities.append({"text": " ".join(quality.text.split()), "eventIds": list(quality.event_ids)})
    gaps = [" ".join(gap.split()) for gap in parsed.gaps if text_ok(gap, table)]
    ability = _ability(parsed.ability, actions, table)
    body = {
        "eventIds": list(actions),
        "summary": " ".join(parsed.summary.split()),
        "qualities": qualities[:4],
        "gaps": gaps[:6],
    }
    if ability is not None:
        body["ability"] = ability
    return body


def _ability(ability: AbilityIn | None, actions: dict[str, str], table: str) -> dict | None:
    if ability is None:
        return None
    kept = []
    for dimension in ability.dimensions:
        if not set(dimension.event_ids) <= set(actions) or not text_ok(dimension.reason, table):
            continue
        matching = [event_id for event_id in dimension.event_ids if actions[event_id] in MATCHING[dimension.name]]
        if len(matching) < 2:
            continue
        kept.append(
            {
                "name": dimension.name,
                "score": dimension.score,
                "reason": " ".join(dimension.reason.split()),
                "eventIds": list(dimension.event_ids),
            }
        )
    if len(kept) < 2:
        return None
    return {"overall": ability.overall, "dimensions": kept}


def maybe_build_profile(app, client, request_id: str, job_id: str) -> None:
    settings = app.state.settings
    db = app.state.db
    if not settings.anthropic_api_key.strip():
        return
    secret = settings.convex_worker_secret
    payload = client.mutation("worker:profileInput", {"secret": secret, "requestId": request_id})
    if not payload or not payload.get("ready"):
        return
    table, listing, actions = stats_table(payload.get("clips") or [])
    if not listing:
        return
    message = json.dumps({"player": payload.get("playerName") or "", "stats": table, "events": listing}, sort_keys=True)
    fingerprint = hashlib.sha256(f"{PROFILE_PROMPT_VERSION}\n{message}".encode()).hexdigest()
    amount = estimate_usd(settings, 1500)
    from app.scout.calls import decide_batch, finish_batch

    decision = decide_batch(db, settings, job_id=job_id, batch_key="profile", fingerprint=fingerprint, amount=amount)
    if decision.action == "cache" and decision.response_json:
        _publish(client, secret, request_id, fingerprint, decision.response_json, None, "cached", settings)
        return
    if decision.action != "send" or decision.reservation_id is None:
        return
    try:
        from app.providers.anthropic import _usage
        from app.scout.pipeline import ClaudeScout

        model = ClaudeScout(settings)
        response = model.provider.client.messages.parse(
            model=model.provider.model,
            max_tokens=900,
            system=[{"type": "text", "text": PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": message}],
            output_format=PlayerProfileIn,
        )
        usage = _usage(response.usage)
        parsed = response.parsed_output
        body = validate_profile(parsed, actions=actions, table=table) if parsed is not None else None
        if body is None:
            finish_batch(
                db, settings, job_id=job_id, batch_key="profile", fingerprint=fingerprint,
                reservation_id=decision.reservation_id, amount=amount, outcome="failed", usage=usage,
            )
            return
        raw = json.dumps(body)
        finish_batch(
            db, settings, job_id=job_id, batch_key="profile", fingerprint=fingerprint,
            reservation_id=decision.reservation_id, amount=amount, outcome="succeeded",
            response_json=raw, usage=usage,
        )
        _publish(client, secret, request_id, fingerprint, raw, usage, "live", settings)
    except Exception:
        log.warning("profile call failed")
        finish_batch(
            db, settings, job_id=job_id, batch_key="profile", fingerprint=fingerprint,
            reservation_id=decision.reservation_id, amount=amount, outcome="unknown",
        )


def _publish(client, secret: str, request_id: str, fingerprint: str, raw: str, usage: dict | None, cache_status: str, settings) -> None:
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return
    payload = {
        "secret": secret,
        "requestId": request_id,
        "key": fingerprint,
        "eventIds": body.get("eventIds") or [],
        "summary": body.get("summary") or "",
        "qualities": body.get("qualities") or [],
        "gaps": body.get("gaps") or [],
        "model": model_name(settings),
        "promptVersion": PROFILE_PROMPT_VERSION,
        "costUsd": actual_usd(settings, usage) if usage else None,
        "inputTokens": int(usage.get("input_tokens") or 0) if usage else None,
        "outputTokens": int(usage.get("output_tokens") or 0) if usage else None,
        "cacheStatus": cache_status,
    }
    if body.get("ability"):
        payload["ability"] = body["ability"]
    client.mutation("worker:publishProfile", payload)
