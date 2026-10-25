"""Turn tracked players and a ball into possession events for one selected player.

A click picks the track under the cursor. When that track ends, it may continue
as a new same-team track that appears within a second and one and a half box
heights. Possession is the player whose feet are nearest the ball.
"""

from __future__ import annotations

import math

from app.scout.discover import Event
from app.scout.identity import Box, Det, Point, Correction, center, feet, iou

NEAR_HEIGHTS = 1.3
RELINK_MS = 1000
RELINK_HEIGHTS = 1.5
MIN_SEGMENT_FRAMES = 2
MERGE_GAP_MS = 600
CARRY_MS = 1500
CARRY_HEIGHTS = 2.0
PASS_TRAVEL_HEIGHTS = 6.0
UNCLEAR_MS = 2000
REFEREE = 3


def _height(box: Box) -> float:
    return max(box[3], 0.02)


def _feet_distance(a: Box, b: Box) -> float:
    return math.hypot(feet(a)[0] - feet(b)[0], feet(a)[1] - feet(b)[1])


def select_track(frames: list[dict], t_ms: int, box: Box) -> int | None:
    if not frames:
        return None
    frame = min(frames, key=lambda item: abs(item["t"] - t_ms))
    best_id = None
    best = 0.0
    for player in frame["players"]:
        if player["cls"] == REFEREE:
            continue
        score = iou(tuple(player["box"]), box)
        if score > best:
            best = score
            best_id = int(player["id"])
    return best_id if best > 0.05 else None


def _player(frame: dict, track_id: int) -> dict | None:
    for player in frame["players"]:
        if int(player["id"]) == track_id:
            return player
    return None


def _relink(frames: list[dict], index: int, last: dict) -> int | None:
    started = frames[index]["t"]
    previous_ids = {int(player["id"]) for player in frames[index - 1]["players"]} if index else set()
    last_box = tuple(last["box"])
    for frame in frames[index:]:
        if frame["t"] - started > RELINK_MS:
            break
        for player in frame["players"]:
            if int(player["id"]) in previous_ids or player["cls"] == REFEREE:
                continue
            if player["team"] is None or player["team"] != last["team"]:
                continue
            if _feet_distance(tuple(player["box"]), last_box) <= RELINK_HEIGHTS * _height(last_box):
                return int(player["id"])
    return None


def follow_track(frames: list[dict], track_id: int, start_ms: int) -> tuple[list[Point], list[Correction], set[int]]:
    """Points cover the whole clip. Identity is the selected track and its re-links."""
    points: list[Point] = []
    corrections: list[Correction] = []
    identity = {track_id}
    current = track_id
    lost = False
    begin = next((index for index, frame in enumerate(frames) if frame["t"] >= start_ms - 100), 0)
    last = None
    for index, frame in enumerate(frames):
        if index < begin:
            points.append(Point(frame["t"], "skipped", None, None, None))
            continue
        if lost:
            points.append(Point(frame["t"], "lost", None, None, _ball(frame)))
            continue
        player = _player(frame, current)
        if player is None and last is not None:
            linked = _relink(frames, index, last)
            if linked is not None:
                current = linked
                identity.add(linked)
                player = _player(frame, current)
        if player is None:
            lost = True
            nearby = [
                Det(int(item["id"]), tuple(item["box"]), kind="person")
                for item in frame["players"]
                if item["cls"] != REFEREE
            ]
            corrections.append(Correction(
                frame["t"],
                "The track was lost here. Click the selected player to continue.",
                nearby[:8],
            ))
            points.append(Point(frame["t"], "lost", None, None, _ball(frame)))
            continue
        last = player
        points.append(Point(frame["t"], "tracked", tuple(player["box"]), int(player["id"]), _ball(frame)))
    return points, corrections, identity


def _ball(frame: dict) -> Box | None:
    ball = frame.get("ball")
    return tuple(ball) if ball else None


def _owner(frame: dict) -> dict | None:
    ball = _ball(frame)
    if ball is None:
        return None
    best = None
    best_distance = 1e9
    for player in frame["players"]:
        if player["cls"] == REFEREE:
            continue
        distance = math.hypot(center(ball)[0] - feet(tuple(player["box"]))[0], center(ball)[1] - feet(tuple(player["box"]))[1])
        limit = NEAR_HEIGHTS * _height(tuple(player["box"]))
        if distance <= limit and distance < best_distance:
            best = player
            best_distance = distance
    return best


def possession_segments(frames: list[dict]) -> list[dict]:
    raw: list[dict] = []
    for frame in frames:
        owner = _owner(frame)
        raw.append({"t": frame["t"], "id": None if owner is None else int(owner["id"]), "team": None if owner is None else owner["team"], "box": None if owner is None else tuple(owner["box"]), "ball": _ball(frame)})
    segments: list[dict] = []
    for row in raw:
        if row["id"] is None:
            continue
        if segments and segments[-1]["id"] == row["id"] and row["t"] - segments[-1]["end"] <= MERGE_GAP_MS:
            segments[-1]["end"] = row["t"]
            segments[-1]["boxes"].append(row["box"])
            segments[-1]["balls"].append(row["ball"])
            continue
        segments.append({"id": row["id"], "team": row["team"], "start": row["t"], "end": row["t"], "boxes": [row["box"]], "balls": [row["ball"]]})
    return [segment for segment in segments if len(segment["boxes"]) >= MIN_SEGMENT_FRAMES]


def events_along(path: list[tuple[int, Box]], frames: list[dict]) -> list[Event]:
    """Possession for a clicked path. The ball has to be near that box."""
    rows = []
    for t_ms, box in path:
        frame = min(frames, key=lambda item: abs(item["t"] - t_ms), default=None)
        ball = _ball(frame) if frame is not None and abs(frame["t"] - t_ms) <= 180 else None
        owns = False
        if ball is not None:
            distance = math.hypot(center(ball)[0] - feet(box)[0], center(ball)[1] - feet(box)[1])
            owns = distance <= NEAR_HEIGHTS * _height(box)
        rows.append({"t": t_ms, "owns": owns, "box": box})
    segments: list[dict] = []
    for row in rows:
        if not row["owns"]:
            continue
        if segments and row["t"] - segments[-1]["end"] <= MERGE_GAP_MS:
            segments[-1]["end"] = row["t"]
            segments[-1]["boxes"].append(row["box"])
            continue
        segments.append({"start": row["t"], "end": row["t"], "boxes": [row["box"]]})
    found: list[Event] = []
    for segment in segments:
        if len(segment["boxes"]) < MIN_SEGMENT_FRAMES:
            continue
        start, end = int(segment["start"]), int(segment["end"])
        found.append(_event("receive", "controlled", start, min(end, start + 800), "Receives the ball"))
        moved = _feet_distance(segment["boxes"][0], segment["boxes"][-1])
        if end - start >= CARRY_MS and moved >= CARRY_HEIGHTS * _height(segment["boxes"][0]):
            found.append(_event("carry", "retained", start, end, "Carries the ball"))
        later = [row["t"] for row in rows if row["t"] > end and not row["owns"]]
        if later and later[-1] - end >= UNCLEAR_MS:
            found.append(_event("loss", "unclear", end, end + 400, "The ball leaves and the next owner is not clear"))
    return found


def events_for(frames: list[dict], identity: set[int]) -> list[Event]:
    segments = possession_segments(frames)
    found: list[Event] = []
    for index, segment in enumerate(segments):
        if segment["id"] not in identity:
            continue
        start, end = int(segment["start"]), int(segment["end"])
        found.append(_event("receive", "controlled", start, min(end, start + 800), "Receives the ball"))
        moved = _feet_distance(segment["boxes"][0], segment["boxes"][-1])
        if end - start >= CARRY_MS and moved >= CARRY_HEIGHTS * _height(segment["boxes"][0]):
            found.append(_event("carry", "retained", start, end, "Carries the ball"))
        nxt = _next_owner(segments, index)
        if nxt is None:
            if _gap_after(frames, end) >= UNCLEAR_MS:
                found.append(_event("loss", "unclear", end, end + 400, "The ball leaves and the next owner is not clear"))
            continue
        travel = _ball_travel(segment, nxt)
        same_team = segment["team"] is not None and segment["team"] == nxt["team"] and segment["id"] != nxt["id"]
        if same_team:
            found.append(_event("pass", "completed", max(start, end - 400), nxt["start"], "Plays the ball to a teammate"))
        elif travel >= PASS_TRAVEL_HEIGHTS * _height(segment["boxes"][-1]):
            found.append(_event("pass", "intercepted", max(start, end - 400), nxt["start"], "Plays the ball and an opponent takes it"))
        else:
            found.append(_event("loss", "lost", max(start, end - 400), nxt["start"], "Loses the ball to an opponent"))
    return found


def _next_owner(segments: list[dict], index: int) -> dict | None:
    current = segments[index]
    for nxt in segments[index + 1:]:
        if nxt["start"] - current["end"] > UNCLEAR_MS:
            return None
        if nxt["id"] != current["id"]:
            return nxt
    return None


def _gap_after(frames: list[dict], t_ms: int) -> int:
    later = [frame["t"] for frame in frames if frame["t"] > t_ms]
    if not later:
        return UNCLEAR_MS
    return later[-1] - t_ms


def _ball_travel(segment: dict, nxt: dict) -> float:
    start = next((ball for ball in reversed(segment["balls"]) if ball), None)
    end = next((ball for ball in nxt["balls"] if ball), None)
    if start is None or end is None:
        return 0.0
    return math.hypot(center(start)[0] - center(end)[0], center(start)[1] - center(end)[1])


def _event(action: str, outcome: str, start: int, end: int, text: str) -> Event:
    return Event(
        action=action,
        outcome=outcome,
        start_ms=start,
        end_ms=max(end, start + 100),
        frame_ids=(f"t{start}",),
        evidence_status="observable",
        visible_action=text,
        identity_status="clear_in_cited_frames",
        limitations=(),
    )
