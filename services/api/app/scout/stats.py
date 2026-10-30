"""Team and player counts from the picture. No learned action model.

The nearest player within about one body-height keeps the ball. That spell
counts only if the ball actually reaches their feet, within half a body-height.
A player who is only nearby does not get possession, a pass or a completion. Pitch centimetres are used only for shots, on the 120m by 70m pitch
from the Roboflow soccer example. A frame with no ball, or with nobody that
close to it, is not possession.
"""

from __future__ import annotations

import math

PITCH_LENGTH = 12000
PITCH_WIDTH = 7000
PENALTY_LENGTH = 2015
PENALTY_WIDTH = 4100
ASPECT = 16 / 9
TOUCH_HEIGHTS = 1.2
CONTROL_HEIGHTS = 0.5
DRIBBLE_RUN = 1.0
DRIBBLE_CLOSE = 2.0
DRIBBLE_AHEAD = 0.4
MERGE_GAP_MS = 600
MIN_FRAMES = 2
NEXT_OWNER_MS = 2000
SHOT_WINDOW_MS = 1200
SHOT_SPEED_CM_S = 800
SHOT_MIN_DX = 300
MIN_BOX = 0.02
REFEREE = 3

PENALTY_Y0 = (PITCH_WIDTH - PENALTY_WIDTH) / 2
PENALTY_Y1 = (PITCH_WIDTH + PENALTY_WIDTH) / 2
RIGHT_GOAL_X = PITCH_LENGTH - PENALTY_LENGTH


def summarise(frames: list[dict]) -> dict:
    teams = _stable_teams(frames)
    rows = [_row(frame, teams) for frame in frames]
    segments = _segments(rows)
    for segment in segments:
        segment["controlled"] = _reached(segment, frames)
    owned = [row for row in rows if _covers(segments, row)]
    passes, intercepted, shots = _events(segments, frames)
    players = _players(frames, segments, passes, shots, teams)
    return {
        "teams": [_team(team, owned, passes, intercepted, shots) for team in (0, 1)],
        "players": players,
    }


def _team(team: int, owned: list[dict], passes: dict, intercepted: dict, shots: dict) -> dict:
    total = len(owned)
    ours = sum(1 for row in owned if row["team"] == team)
    completed = sum(passes[key] for key in passes if _team_of(key) == team)
    missed = sum(intercepted[key] for key in intercepted if _team_of(key) == team)
    attempts = completed + missed
    return {
        "team": team,
        "possession": round(ours / total, 3) if total else 0,
        "passes": completed,
        "pass_completion": round(completed / attempts, 3) if attempts else None,
        "shots": sum(shots[key] for key in shots if _team_of(key) == team),
    }


def _players(frames: list[dict], segments: list[dict], passes: dict, shots: dict, teams: dict[int, int | None]) -> list[dict]:
    found = []
    for track_id in sorted(teams):
        team = teams[track_id]
        own = [segment for segment in segments if segment["id"] == track_id and segment.get("controlled")]
        dribbles = sum(_dribble_count(segment, frames, teams) for segment in own)
        key = (track_id, team)
        found.append({
            "id": track_id,
            "team": team,
            "passes": passes.get(key, 0),
            "dribbles": dribbles,
            "shots": shots.get(key, 0),
            "touches": len(own),
        })
    return found


def _events(segments: list[dict], frames: list[dict]) -> tuple[dict, dict, dict]:
    passes: dict[tuple, int] = {}
    intercepted: dict[tuple, int] = {}
    shots: dict[tuple, int] = {}
    for index, segment in enumerate(segments):
        if segment["team"] is None or not segment.get("controlled"):
            continue
        key = (segment["id"], segment["team"])
        nxt = _next_other(segments, index)
        if nxt is not None and not nxt.get("controlled"):
            nxt = None
        if nxt is not None and nxt["team"] is not None and nxt["id"] != segment["id"]:
            if nxt["team"] == segment["team"]:
                passes[key] = passes.get(key, 0) + 1
            else:
                intercepted[key] = intercepted.get(key, 0) + 1
        if _is_shot(segment, frames, nxt):
            shots[key] = shots.get(key, 0) + 1
    return passes, intercepted, shots


def _is_shot(segment: dict, frames: list[dict], nxt: dict | None) -> bool:
    release = next((point for point in reversed(segment["balls"]) if point), None)
    if release is None:
        return False
    flight = []
    for frame in frames:
        t_ms = int(frame["t"])
        if t_ms <= segment["end"] or t_ms > segment["end"] + SHOT_WINDOW_MS:
            continue
        ball = _point(frame.get("ball_pitch"))
        if ball is not None:
            flight.append((t_ms, ball))
    if not flight:
        return False
    dx = flight[-1][1][0] - release[0]
    if abs(dx) < SHOT_MIN_DX:
        return False
    side = "right" if dx > 0 else "left"
    if _in_penalty(release, side):
        return False
    entered = next(((t_ms, ball) for t_ms, ball in flight if _in_penalty(ball, side)), None)
    if entered is None:
        return False
    if nxt is not None and nxt["team"] == segment["team"]:
        return False
    distance = _distance(release, entered[1])
    seconds = max(0.05, (entered[0] - segment["end"]) / 1000)
    return distance / seconds >= SHOT_SPEED_CM_S


def _in_penalty(point: tuple[float, float], side: str) -> bool:
    x, y = point
    if y < PENALTY_Y0 or y > PENALTY_Y1:
        return False
    if side == "left":
        return 0 <= x <= PENALTY_LENGTH
    return RIGHT_GOAL_X <= x <= PITCH_LENGTH


def _dribble_count(segment: dict, frames: list[dict], teams: dict[int, int | None]) -> int:
    """How many opponents this spell leaves behind while the carrier still has the ball."""
    samples = []
    for frame in frames:
        t_ms = int(frame["t"])
        if t_ms < segment["start"] or t_ms > segment["end"]:
            continue
        carrier = None
        others = []
        for player in frame.get("players") or []:
            if int(player.get("cls", 2)) == REFEREE:
                continue
            parsed = _box(player.get("box"))
            if parsed is None:
                continue
            feet, height = _feet(parsed)
            if int(player["id"]) == segment["id"]:
                carrier = (feet, height)
                continue
            team = teams.get(int(player["id"]))
            if team is None or team == segment["team"]:
                continue
            others.append((int(player["id"]), feet))
        if carrier is not None:
            samples.append({"feet": carrier[0], "height": carrier[1], "others": others})
    if len(samples) < 2:
        return 0
    height = samples[0]["height"]
    start = samples[0]["feet"]
    end = samples[-1]["feet"]
    run = _heights(start, end, height)
    if run < DRIBBLE_RUN:
        return 0
    dx = (end[0] - start[0]) * ASPECT / height
    dy = (end[1] - start[1]) / height
    length = math.hypot(dx, dy)
    if length == 0:
        return 0
    ux, uy = dx / length, dy / length
    beaten = 0
    opponents = {opp_id for sample in samples for opp_id, _feet in sample["others"]}
    for opp_id in opponents:
        signed = []
        for sample in samples:
            found = next((feet for oid, feet in sample["others"] if oid == opp_id), None)
            if found is None:
                continue
            if _heights(found, sample["feet"], sample["height"]) > DRIBBLE_CLOSE:
                continue
            ox = (found[0] - sample["feet"][0]) * ASPECT / sample["height"]
            oy = (found[1] - sample["feet"][1]) / sample["height"]
            signed.append(ox * ux + oy * uy)
        if len(signed) >= 2 and signed[0] >= DRIBBLE_AHEAD and signed[-1] <= -DRIBBLE_AHEAD:
            beaten += 1
    return beaten


def _reached(segment: dict, frames: list[dict]) -> bool:
    """True when the ball gets to this player's feet during the spell."""
    for frame in frames:
        t_ms = int(frame["t"])
        if t_ms < segment["start"] or t_ms > segment["end"]:
            continue
        ball = _box(frame.get("ball"))
        if ball is None:
            continue
        center = _center(ball)
        for player in frame.get("players") or []:
            if int(player["id"]) != segment["id"]:
                continue
            parsed = _box(player.get("box"))
            if parsed is None:
                continue
            feet, height = _feet(parsed)
            if _heights(feet, center, height) <= CONTROL_HEIGHTS:
                return True
    return False


def _covers(segments: list[dict], row: dict) -> bool:
    if row["id"] is None:
        return False
    return any(
        segment.get("controlled") and segment["id"] == row["id"] and segment["start"] <= row["t"] <= segment["end"]
        for segment in segments
    )


def _segments(rows: list[dict]) -> list[dict]:
    segments: list[dict] = []
    for row in rows:
        if row["id"] is None:
            continue
        if segments and segments[-1]["id"] == row["id"] and row["t"] - segments[-1]["end"] <= MERGE_GAP_MS:
            segments[-1]["end"] = row["t"]
            segments[-1]["pitches"].append(row["pitch"])
            segments[-1]["balls"].append(row["ball"])
            continue
        segments.append({
            "id": row["id"],
            "team": row["team"],
            "start": row["t"],
            "end": row["t"],
            "pitches": [row["pitch"]],
            "balls": [row["ball"]],
        })
    return [segment for segment in segments if len(segment["balls"]) >= MIN_FRAMES]


def _row(frame: dict, teams: dict[int, int | None]) -> dict:
    owner = _owner(frame, teams)
    ball = _point(frame.get("ball_pitch"))
    if owner is None:
        return {"t": int(frame["t"]), "id": None, "team": None, "pitch": None, "ball": ball}
    track_id = int(owner["id"])
    return {
        "t": int(frame["t"]),
        "id": track_id,
        "team": teams.get(track_id),
        "pitch": _point(owner.get("pitch")),
        "ball": ball,
    }


def _owner(frame: dict, teams: dict[int, int | None]) -> dict | None:
    ball_box = _box(frame.get("ball"))
    if ball_box is None:
        return None
    ball = _center(ball_box)
    best = None
    best_distance = TOUCH_HEIGHTS
    for player in frame.get("players") or []:
        if int(player.get("cls", 2)) == REFEREE:
            continue
        track_id = int(player["id"])
        if teams.get(track_id) is None:
            continue
        parsed = _box(player.get("box"))
        if parsed is None:
            continue
        feet, height = _feet(parsed)
        distance = _heights(feet, ball, height)
        if distance <= best_distance:
            best = player
            best_distance = distance
    return best


def _stable_teams(frames: list[dict]) -> dict[int, int | None]:
    seen: dict[int, list[int]] = {}
    for frame in frames:
        for player in frame.get("players") or []:
            if int(player.get("cls", 2)) == REFEREE:
                continue
            track_id = int(player["id"])
            seen.setdefault(track_id, [])
            if player.get("team") is not None:
                seen[track_id].append(int(player["team"]))
    return {track_id: max(set(labels), key=labels.count) if labels else None for track_id, labels in seen.items()}


def _next_other(segments: list[dict], index: int) -> dict | None:
    current = segments[index]
    for nxt in segments[index + 1 :]:
        if nxt["start"] - current["end"] > NEXT_OWNER_MS:
            return None
        if nxt["id"] != current["id"]:
            return nxt
    return None


def _box(value) -> tuple[float, float, float, float] | None:
    if not value or len(value) < 4:
        return None
    x, y, w, h = (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
    if h <= 0 or w <= 0 or not all(math.isfinite(part) for part in (x, y, w, h)):
        return None
    return (x, y, w, h)


def _feet(box: tuple[float, float, float, float]) -> tuple[tuple[float, float], float]:
    x, y, w, h = box
    return (x + w / 2, y + h), h


def _center(box: tuple[float, float, float, float]) -> tuple[float, float]:
    x, y, w, h = box
    return (x + w / 2, y + h / 2)


def _heights(a: tuple[float, float], b: tuple[float, float], height: float) -> float:
    if height < MIN_BOX:
        return math.inf
    dx = (a[0] - b[0]) * ASPECT / height
    dy = (a[1] - b[1]) / height
    return math.hypot(dx, dy)


def _point(value) -> tuple[float, float] | None:
    if not value or len(value) < 2:
        return None
    x, y = float(value[0]), float(value[1])
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return (x, y)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _team_of(key: tuple) -> int:
    return int(key[1])
