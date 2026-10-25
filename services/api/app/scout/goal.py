"""Follow the scorer from a click after the goal.

The click is the calibration: that box is the player who just scored, so the
goal is there. Walking away from the click, the ring stays on the detected
player nearest the ball when the ball is still by that goal. A ball that jumps
across the frame is ignored.
"""

from __future__ import annotations

import math

BEFORE_MS = 8000
AFTER_MS = 2000
GOAL_REACH = 0.30
BALL_JUMP = 0.15
STEP_REACH = 0.18
HOLD_MS = 400


def _feet(box: tuple[float, float, float, float]) -> tuple[float, float]:
    return box[0] + box[2] / 2, box[1] + box[3]


def _ball_center(ball: list[float] | tuple[float, ...]) -> tuple[float, float]:
    return ball[0] + ball[2] / 2, ball[1] + ball[3] / 2


def _trusted_balls(frames: list[dict], goal: tuple[float, float]) -> dict[int, tuple[float, float]]:
    found: dict[int, tuple[float, float]] = {}
    previous: tuple[float, float] | None = None
    previous_t = 0
    for frame in frames:
        ball = frame.get("ball")
        if not ball:
            continue
        center = _ball_center(ball)
        if math.hypot(center[0] - goal[0], center[1] - goal[1]) > GOAL_REACH:
            continue
        if previous is not None and frame["t"] - previous_t < 700 and math.hypot(center[0] - previous[0], center[1] - previous[1]) > BALL_JUMP:
            continue
        found[int(frame["t"])] = center
        previous = center
        previous_t = int(frame["t"])
    return found


def _choose(frame: dict, last: tuple[float, float, float, float], ball: tuple[float, float] | None, goal: tuple[float, float]):
    last_feet = _feet(last)
    near = []
    for player in frame.get("players") or []:
        if player.get("cls") == 3:
            continue
        box = tuple(player["box"])
        feet = _feet(box)
        if math.hypot(feet[0] - last_feet[0], feet[1] - last_feet[1]) > STEP_REACH:
            continue
        near.append((box, feet))
    if not near:
        return None
    if ball is not None:
        return min(near, key=lambda item: math.hypot(item[1][0] - ball[0], item[1][1] - ball[1]))[0]
    return min(near, key=lambda item: math.hypot(item[1][0] - goal[0], item[1][1] - goal[1]))[0]


def interpolate_marks(marks: list[tuple[int, tuple[float, float, float, float]]]) -> list[dict]:
    """A straight line of boxes between clicks, ten per second."""
    ordered = sorted(marks, key=lambda item: item[0])
    if not ordered:
        return []
    if len(ordered) == 1:
        t_ms, box = ordered[0]
        return [{"t": t_ms, "box": _rounded(box)}]
    path = []
    for (start, box0), (end, box1) in zip(ordered, ordered[1:]):
        steps = max(1, round((end - start) / 100))
        for step in range(steps):
            alpha = step / steps
            box = tuple(box0[index] + (box1[index] - box0[index]) * alpha for index in range(4))
            path.append({"t": int(start + (end - start) * alpha), "box": _rounded(box)})
    path.append({"t": ordered[-1][0], "box": _rounded(ordered[-1][1])})
    return path


def _rounded(box: tuple[float, float, float, float]) -> dict:
    return {"x": round(box[0], 4), "y": round(box[1], 4), "w": round(box[2], 4), "h": round(box[3], 4)}


def scorer_path(frames: list[dict], t_ms: int, box: tuple[float, float, float, float]) -> list[dict]:
    """Boxes for the player nearest the goal and the ball, locked to the click."""
    window = [frame for frame in frames if t_ms - BEFORE_MS <= int(frame["t"]) <= t_ms + AFTER_MS]
    if not window:
        return [{"t": t_ms, "box": {"x": box[0], "y": box[1], "w": box[2], "h": box[3]}}]
    goal = _feet(box)
    balls = _trusted_balls(window, goal)
    ordered = sorted(window, key=lambda frame: int(frame["t"]))
    anchor = min(range(len(ordered)), key=lambda index: abs(int(ordered[index]["t"]) - t_ms))
    chosen: dict[int, tuple[float, float, float, float]] = {anchor: box}

    def walk(step: int) -> None:
        last = box
        held_at: int | None = None
        index = anchor
        while True:
            index += step
            if index < 0 or index >= len(ordered):
                break
            frame = ordered[index]
            pick = _choose(frame, last, balls.get(int(frame["t"])), goal)
            if pick is None:
                if held_at is None:
                    held_at = int(frame["t"])
                if abs(int(frame["t"]) - held_at) > HOLD_MS:
                    break
                pick = last
            else:
                held_at = None
            last = pick
            chosen[index] = pick

    walk(-1)
    walk(1)
    path = []
    for index in sorted(chosen):
        item = chosen[index]
        when = t_ms if index == anchor else int(ordered[index]["t"])
        used = box if index == anchor else item
        path.append({"t": when, "box": {"x": round(used[0], 4), "y": round(used[1], 4), "w": round(used[2], 4), "h": round(used[3], 4)}})
    return path
