"""Find candidate involvements from a followed track. A nearby ball is not possession."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.scout.identity import Box, Point, center, feet

NEAR_HEIGHTS = 1.2
MERGE_GAP_MS = 800
PAD_BEFORE_MS = 1000
PAD_AFTER_MS = 1500
MAX_TOUCH_MS = 8000


@dataclass(frozen=True)
class Candidate:
    start_ms: int
    end_ms: int
    touch_start_ms: int
    touch_end_ms: int


def ball_near_feet(player: Box, ball: Box, heights: float = NEAR_HEIGHTS) -> bool:
    fx, fy = feet(player)
    bx, by = center(ball)
    height = max(player[3], 0.02)
    return math.hypot(bx - fx, by - fy) / height <= heights


def discover(
    points: list[Point],
    *,
    bounds: tuple[int, int],
) -> tuple[list[Candidate], dict[str, int]]:
    tracked = [point for point in points if point.state == "tracked" and point.box is not None]
    contact: list[Point] = []
    seen: set[int] = set()
    for index, _point in enumerate(tracked):
        window = tracked[index : index + 3]
        if len(window) < 2 or window[-1].t_ms - window[0].t_ms > 700:
            continue
        near = [item for item in window if item.box is not None and item.ball is not None and ball_near_feet(item.box, item.ball)]
        if len(near) < 2:
            continue
        for item in near:
            if item.t_ms not in seen:
                seen.add(item.t_ms)
                contact.append(item)

    runs: list[list[Point]] = []
    for point in contact:
        if runs and point.t_ms - runs[-1][-1].t_ms <= MERGE_GAP_MS:
            runs[-1].append(point)
        else:
            runs.append([point])

    low, high = bounds
    candidates: list[Candidate] = []
    for run in runs:
        touch_start, touch_end = run[0].t_ms, run[-1].t_ms
        cursor = touch_start
        while cursor <= touch_end:
            piece_end = min(touch_end, cursor + MAX_TOUCH_MS)
            candidates.append(
                Candidate(
                    start_ms=max(low, cursor - PAD_BEFORE_MS),
                    end_ms=min(high, piece_end + PAD_AFTER_MS),
                    touch_start_ms=cursor,
                    touch_end_ms=piece_end,
                )
            )
            if piece_end == touch_end:
                break
            cursor = piece_end
    return candidates, coverage(points)


def coverage(points: list[Point]) -> dict[str, int]:
    totals = {"tracked_ms": 0, "lost_ms": 0, "ball_unseen_ms": 0}
    for earlier, later in zip(points, points[1:]):
        span = max(0, later.t_ms - earlier.t_ms)
        key = "tracked_ms" if earlier.state == "tracked" else "lost_ms"
        totals[key] += span
        if earlier.state == "tracked" and earlier.ball is None:
            totals["ball_unseen_ms"] += span
    return totals


@dataclass(frozen=True)
class Event:
    action: str
    outcome: str
    start_ms: int
    end_ms: int
    frame_ids: tuple[str, ...]
    evidence_status: str
    visible_action: str
    identity_status: str = "clear_in_cited_frames"
    limitations: tuple[str, ...] = ()


def dedupe(events: list[Event]) -> list[Event]:
    """Same action starting within 0.7s is one incident. Keep the clearer one."""
    kept: list[Event] = []
    for event in sorted(events, key=lambda item: item.start_ms):
        match = next(
            (
                index
                for index, prior in enumerate(kept)
                if prior.action == event.action and abs(prior.start_ms - event.start_ms) <= 700
            ),
            None,
        )
        if match is None:
            kept.append(event)
            continue
        if _rank(event) > _rank(kept[match]):
            kept[match] = event
    return sorted(kept, key=lambda item: item.start_ms)


def _rank(event: Event) -> tuple[int, int, int]:
    known = 0 if event.outcome == "unclear" else 2
    observable = 1 if event.evidence_status == "observable" else 0
    return known + observable, len(event.frame_ids), event.end_ms - event.start_ms
