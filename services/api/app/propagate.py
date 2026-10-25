"""Forward and backward CSRT proposals between manual anchors.

A proposal is an estimate until the user saves it. Frames the user already
located, or marked not visible on purpose, are left alone. One-direction
tracks past the last anchor are flagged for a check rather than presented
as a location.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import numpy as np

_decode = threading.BoundedSemaphore(1)


def _tracker():
    import cv2

    if hasattr(cv2, "TrackerCSRT_create"):
        return cv2.TrackerCSRT_create()
    legacy = getattr(cv2, "legacy", None)
    if legacy is not None and hasattr(legacy, "TrackerCSRT_create"):
        return legacy.TrackerCSRT_create()
    raise RuntimeError("CSRT is not available in this OpenCV build")


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _run_track(frames: list[np.ndarray], start: int, box: tuple[float, float, float, float], step: int) -> dict[int, tuple[float, float, float, float]]:
    import cv2

    height, width = frames[start].shape[:2]
    pixel = (
        int(round(box[0] * width)),
        int(round(box[1] * height)),
        max(2, int(round(box[2] * width))),
        max(2, int(round(box[3] * height))),
    )
    tracker = _tracker()
    try:
        tracker.init(frames[start], pixel)
    except Exception:
        return {}
    found = {start: box}
    index = start
    while True:
        index += step
        if index < 0 or index >= len(frames):
            break
        ok, updated = tracker.update(frames[index])
        if not ok:
            break
        x, y, w, h = (float(value) for value in updated)
        if w < 2 or h < 2:
            break
        found[index] = (
            max(0.0, x / width),
            max(0.0, y / height),
            min(1.0, w / width),
            min(1.0, h / height),
        )
    return found


def proposals_for_frames(
    frames: list[np.ndarray],
    times_ms: list[int],
    samples: list[dict],
    anchors: list[dict],
) -> list[dict]:
    """samples are {frame_id, source_t_ms}. anchors use normalized boxes."""
    if not frames or len(frames) != len(times_ms):
        return []
    located = [anchor for anchor in anchors if anchor.get("state") == "located" and anchor.get("source") != "estimated" and anchor.get("box")]
    protected = {
        anchor["frame_id"]
        for anchor in anchors
        if (anchor.get("state") == "located" and anchor.get("source") != "estimated") or (anchor.get("state") == "not_visible" and anchor.get("explicit"))
    }
    located.sort(key=lambda anchor: _sample_time(samples, anchor["frame_id"]))
    if not located:
        return []

    def nearest(time_ms: int) -> int:
        return min(range(len(times_ms)), key=lambda index: abs(times_ms[index] - time_ms))

    tracks: list[tuple[dict, dict[int, tuple[float, float, float, float]], dict[int, tuple[float, float, float, float]]]] = []
    for anchor in located:
        origin = nearest(_sample_time(samples, anchor["frame_id"]))
        box = (anchor["box"]["x"], anchor["box"]["y"], anchor["box"]["w"], anchor["box"]["h"])
        tracks.append((anchor, _run_track(frames, origin, box, 1), _run_track(frames, origin, box, -1)))

    proposals = []
    width = frames[0].shape[1]
    height = frames[0].shape[0]
    for sample in samples:
        if sample["frame_id"] in protected:
            continue
        index = nearest(sample["source_t_ms"])
        if abs(times_ms[index] - sample["source_t_ms"]) > 80:
            continue
        previous = [item for item in tracks if _sample_time(samples, item[0]["frame_id"]) <= sample["source_t_ms"]]
        following = [item for item in tracks if _sample_time(samples, item[0]["frame_id"]) >= sample["source_t_ms"]]
        forward = previous[-1][1].get(index) if previous else None
        backward = following[0][2].get(index) if following else None
        both_sides = bool(previous and following and previous[-1][0]["frame_id"] != following[0][0]["frame_id"])
        proposal = _decide(forward, backward, both_sides, width, height)
        if proposal is None:
            continue
        proposals.append({"frame_id": sample["frame_id"], **proposal})
    return proposals


def _sample_time(samples: list[dict], frame_id: str) -> int:
    for sample in samples:
        if sample["frame_id"] == frame_id:
            return int(sample["source_t_ms"])
    return 0


def _decide(forward, backward, both_sides: bool, width: int, height: int) -> dict | None:
    if forward is None and backward is None:
        return None
    if both_sides and forward is not None and backward is not None:
        if iou(forward, backward) >= 0.5 and _jump_ok(forward, backward, width, height):
            return {
                "state": "located",
                "source": "estimated",
                "box": _box(forward),
                "method": "csrt-fb",
                "reason": None,
                "explicit": False,
            }
        return {
            "state": "uncertain",
            "source": "estimated",
            "box": _box(forward),
            "method": "csrt-fb",
            "reason": "The forward and backward tracks disagree, so this may be a crossing, an occlusion, or a lost track.",
            "explicit": True,
        }
    if both_sides:
        return {
            "state": "uncertain",
            "source": "estimated",
            "box": _box(forward or backward),
            "method": "csrt-fb",
            "reason": "One of the two tracks was lost.",
            "explicit": True,
        }
    return {
        "state": "uncertain",
        "source": "estimated",
        "box": _box(forward or backward),
        "method": "csrt-fb",
        "reason": "Needs check: the track runs in only one direction beyond the manual anchors.",
        "explicit": True,
    }


def _jump_ok(a, b, width: int, height: int) -> bool:
    ax, ay = a[0] + a[2] / 2, a[1] + a[3] / 2
    bx, by = b[0] + b[2] / 2, b[1] + b[3] / 2
    distance = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
    scale = max(width, height) / max(width, 1)
    return distance * scale < 0.35


def _box(value: tuple[float, float, float, float]) -> dict:
    x, y, w, h = value
    w = min(w, 1 - x)
    h = min(h, 1 - y)
    return {"x": round(x, 4), "y": round(y, 4), "w": round(max(w, 0.02), 4), "h": round(max(h, 0.02), 4)}


def decode_window(video: Path, start_ms: int, end_ms: int, directory: Path) -> tuple[list[np.ndarray], list[int]]:
    directory.mkdir(parents=True, exist_ok=True)
    # Synced folders (OneDrive) can hold a lock on a previous decode, so every
    # call decodes into its own folder and removes it best-effort.
    work = Path(tempfile.mkdtemp(prefix="decode_", dir=directory))
    try:
        return _decode_into(video, start_ms, end_ms, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _decode_into(video: Path, start_ms: int, end_ms: int, directory: Path) -> tuple[list[np.ndarray], list[int]]:
    import cv2

    start = max(0, start_ms) / 1000
    end = end_ms / 1000
    with _decode:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-copyts",
                "-ss",
                f"{start:.3f}",
                "-to",
                f"{end:.3f}",
                "-i",
                str(video),
                "-an",
                "-vf",
                "scale=480:-2,showinfo",
                "-fps_mode",
                "passthrough",
                str(directory / "%04d.jpg"),
            ],
            capture_output=True,
            timeout=90,
            shell=False,
        )
    if proc.returncode != 0:
        raise RuntimeError("The window could not be decoded for proposals.")
    times = []
    for line in proc.stderr.decode("utf-8", "replace").splitlines():
        if "pts_time:" not in line:
            continue
        raw = line.split("pts_time:", 1)[1].split()[0]
        times.append(int(round(float(raw) * 1000)))
    paths = sorted(directory.glob("*.jpg"))
    frames = []
    kept = []
    for path, time_ms in zip(paths, times):
        image = cv2.imread(str(path))
        if image is None:
            continue
        frames.append(image)
        kept.append(time_ms)
    return frames, kept
