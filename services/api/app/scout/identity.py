"""Follow one player through detections without silently changing identity.

The detector is injected. This module only decides which detection, if any, is
still the player who was identified at the anchor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

Box = tuple[float, float, float, float]
Hue = tuple[float, ...]

IOU_MIN = 0.3
LOST_MS = 3000
SIM_KEEP = 0.45
SIM_RELINK = 0.62
SIM_MARGIN = 0.15


@dataclass(frozen=True)
class Det:
    track_id: int
    box: Box
    confidence: float = 1.0
    kind: str = "person"
    hue: Hue | None = None


@dataclass
class FrameObs:
    t_ms: int
    people: list[Det] = field(default_factory=list)
    balls: list[Det] = field(default_factory=list)
    cut: bool = False


@dataclass(frozen=True)
class Point:
    t_ms: int
    state: str
    box: Box | None
    track_id: int | None
    ball: Box | None


@dataclass(frozen=True)
class Correction:
    t_ms: int
    reason: str
    boxes: list[Det]


def iou(a: Box, b: Box) -> float:
    ax2, ay2 = a[0] + a[2], a[1] + a[3]
    bx2, by2 = b[0] + b[2], b[1] + b[3]
    ix, iy = max(0.0, min(ax2, bx2) - max(a[0], b[0])), max(0.0, min(ay2, by2) - max(a[1], b[1]))
    inter = ix * iy
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def center(box: Box) -> tuple[float, float]:
    return box[0] + box[2] / 2, box[1] + box[3] / 2


def feet(box: Box) -> tuple[float, float]:
    return box[0] + box[2] / 2, box[1] + box[3]


def hue_similarity(a: Hue | None, b: Hue | None) -> float | None:
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return None
    return dot / (na * nb)


def _in_gate(box: Box, last: Box) -> bool:
    ax, ay = center(box)
    bx, by = center(last)
    reach = max(0.06, 1.8 * max(last[2], last[3]))
    return math.hypot(ax - bx, ay - by) <= reach


def _nearest_ball(box: Box, balls: list[Det]) -> Box | None:
    if not balls:
        return None
    fx, fy = feet(box)
    height = max(box[3], 0.02)

    def distance(ball: Det) -> float:
        bx, by = center(ball.box)
        return math.hypot(bx - fx, by - fy) / height

    ball = min(balls, key=distance)
    return ball.box if distance(ball) <= 4 else None


def _blend(model: list[float] | None, hue: Hue | None) -> list[float] | None:
    if hue is None:
        return model
    if model is None:
        return list(hue)
    return [0.8 * old + 0.2 * new for old, new in zip(model, hue)]


def follow(frames: list[FrameObs], anchor_t_ms: int, anchor_box: Box) -> tuple[list[Point], list[Correction]]:
    """Track forward from the anchor. A cut or an ambiguous relink ends the identity."""
    if not frames:
        return [], []
    start = min(range(len(frames)), key=lambda index: abs(frames[index].t_ms - anchor_t_ms))
    anchor = frames[start]
    window = [frame for frame in frames if abs(frame.t_ms - anchor_t_ms) <= 400]
    candidates = [(frame, person) for frame in window for person in frame.people if iou(person.box, anchor_box) >= IOU_MIN]
    chosen = max(candidates, key=lambda item: iou(item[1].box, anchor_box), default=None)
    if chosen is not None:
        anchor = chosen[0]
        start = frames.index(anchor)
        target = chosen[1]
    else:
        target = None
    if target is None:
        return [], [Correction(anchor.t_ms, "no_match", list(anchor.people[:8]))]

    points: list[Point] = []
    corrections: list[Correction] = []
    track_id: int | None = target.track_id
    last_box: Box = target.box
    model = list(target.hue) if target.hue else None
    lost_since: int | None = None
    reported = False
    # A cut ends this identity. A later correction starts a new follow() from its anchor.
    broken = False

    for index, frame in enumerate(frames[start:]):
        if frame.cut and index:
            broken = True
        person = None if broken else (_same_person(frame, track_id, model) if index else target)
        if person is None and index and not broken:
            person = _relink(frame, last_box, model)
        if person is None:
            if lost_since is None:
                lost_since = frame.t_ms
            track_id = None
            points.append(Point(frame.t_ms, "lost", None, None, None))
            if not reported and frame.t_ms - lost_since >= LOST_MS:
                lost_frame = next((item for item in frames[start:] if item.t_ms == lost_since), frame)
                corrections.append(Correction(lost_since, "track_lost", _nearby(lost_frame, last_box)))
                reported = True
                # The coach resumes from a new anchor. Do not adopt a later player in this pass.
                broken = True
            continue
        track_id = person.track_id
        last_box = person.box
        model = _blend(model, person.hue)
        lost_since = None
        reported = False
        points.append(Point(frame.t_ms, "tracked", person.box, person.track_id, _nearest_ball(person.box, frame.balls)))
    return points, corrections


def _same_person(frame: FrameObs, track_id: int | None, model: list[float] | None) -> Det | None:
    if track_id is None:
        return None
    person = next((item for item in frame.people if item.track_id == track_id), None)
    if person is None:
        return None
    similarity = hue_similarity(model, person.hue)
    if similarity is not None and similarity < SIM_KEEP:
        return None
    return person


def _relink(frame: FrameObs, last_box: Box, model: list[float] | None) -> Det | None:
    gated = [person for person in frame.people if _in_gate(person.box, last_box)]
    if not gated:
        return None
    scored = [(hue_similarity(model, person.hue), person) for person in gated]
    known = [item for item in scored if item[0] is not None]
    if not known:
        return gated[0] if len(gated) == 1 else None
    known.sort(key=lambda item: item[0] or 0, reverse=True)
    best, winner = known[0]
    second = known[1][0] if len(known) > 1 else None
    if best is None or best < SIM_RELINK:
        return None
    if second is not None and best - second < SIM_MARGIN:
        return None
    return winner


def _nearby(frame: FrameObs, last_box: Box) -> list[Det]:
    reach = max(0.12, 3 * max(last_box[2], last_box[3]))
    lx, ly = center(last_box)
    close = [
        person
        for person in frame.people
        if math.hypot(center(person.box)[0] - lx, center(person.box)[1] - ly) <= reach
    ]
    return (close or list(frame.people))[:8]
