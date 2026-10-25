"""Follow a clicked player from the picture when the detector drops them.

Optical flow starts at the click and runs backward and forward. It stops when
the patch is lost or jumps, instead of switching to another player.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

BEFORE_MS = 8000
AFTER_MS = 2000
MIN_POINTS = 4


def follow_click(video: Path, t_ms: int, box: tuple[float, float, float, float]) -> list[dict]:
    """Boxes from the click, about ten per second, covering the held stretch."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return []
    start = max(0, t_ms - BEFORE_MS)
    end = t_ms + AFTER_MS
    cap.set(cv2.CAP_PROP_POS_MSEC, start)
    grays: list[tuple[int, np.ndarray]] = []
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            ms = int(cap.get(cv2.CAP_PROP_POS_MSEC))
            if ms > end:
                break
            grays.append((ms, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)))
    finally:
        cap.release()
    if not grays:
        return []
    height, width = grays[0][1].shape[:2]
    seed = min(range(len(grays)), key=lambda index: abs(grays[index][0] - t_ms))
    found = track_grays([gray for _, gray in grays], seed, box, -1, width, height)
    found.update(track_grays([gray for _, gray in grays], seed, box, 1, width, height))
    found[seed] = box
    samples = []
    last = -10_000
    for index in sorted(found):
        ms = grays[index][0]
        if samples and ms - last < 90:
            continue
        x, y, w, h = found[index]
        samples.append({"t": ms, "box": {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}})
        last = ms
    return samples


def track_grays(
    grays: list[np.ndarray],
    seed: int,
    box: tuple[float, float, float, float],
    step: int,
    width: int | None = None,
    height: int | None = None,
) -> dict[int, tuple[float, float, float, float]]:
    if not grays or step == 0:
        return {}
    height = grays[seed].shape[0] if height is None else height
    width = grays[seed].shape[1] if width is None else width
    current = tuple(box)
    points = _features(grays[seed], current, width, height)
    found: dict[int, tuple[float, float, float, float]] = {}
    index = seed
    previous = grays[seed]
    jumps = max(24.0, 0.08 * width)
    while points is not None:
        index += step
        if index < 0 or index >= len(grays):
            break
        nxt, status, _err = cv2.calcOpticalFlowPyrLK(
            previous,
            grays[index],
            points,
            None,
            winSize=(21, 21),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
        )
        if nxt is None or status is None:
            break
        keep = status.reshape(-1) == 1
        good = nxt[keep]
        old = points[keep]
        if len(good) < MIN_POINTS:
            break
        shift = np.median(good - old, axis=0).reshape(-1)
        if float(np.hypot(shift[0], shift[1])) > jumps:
            break
        moved = (
            current[0] + float(shift[0]) / width,
            current[1] + float(shift[1]) / height,
            current[2],
            current[3],
        )
        if moved[0] < 0 or moved[1] < 0 or moved[0] + moved[2] > 1 or moved[1] + moved[3] > 1:
            break
        current = moved
        found[index] = current
        previous = grays[index]
        if abs(index - seed) % 5 == 0:
            points = _features(grays[index], current, width, height)
        else:
            points = good.reshape(-1, 1, 2)
    return found


def _features(gray: np.ndarray, box: tuple[float, float, float, float], width: int, height: int):
    x, y, w, h = box
    x0 = int((x + 0.15 * w) * width)
    y0 = int((y + 0.1 * h) * height)
    x1 = int((x + 0.85 * w) * width)
    y1 = int((y + 0.75 * h) * height)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, max(x0 + 2, x1)), min(height, max(y0 + 2, y1))
    roi = gray[y0:y1, x0:x1]
    if roi.size == 0:
        return None
    points = cv2.goodFeaturesToTrack(roi, 24, 0.05, 3)
    if points is None:
        return None
    points[:, :, 0] += x0
    points[:, :, 1] += y0
    return points
