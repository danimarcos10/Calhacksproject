"""Bounded frame reads. Source timestamps come from ffmpeg, not from a frame index."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import cv2
import numpy as np

from app.scout.chunks import parse_showinfo_pts
from app.scout.identity import Box, Hue


def video_size(path: Path) -> tuple[int, int]:
    raw = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path),
        ],
        text=True,
    )
    width, height = raw.strip().split(",")[:2]
    return int(width), int(height)


def scaled_size(width: int, height: int, target: int = 960) -> tuple[int, int]:
    if width <= target:
        scaled_w, scaled_h = width, height
    else:
        scaled_w = target
        scaled_h = max(2, round(height * target / width))
    if scaled_w % 2:
        scaled_w -= 1
    if scaled_h % 2:
        scaled_h -= 1
    return max(2, scaled_w), max(2, scaled_h)


def iter_frames(video: Path, start_ms: int, end_ms: int, fps: int, width: int, height: int):
    """Yield (source_t_ms, bgr) and stop the decoder when the caller stops."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "info",
        "-ss", f"{start_ms / 1000:.3f}", "-to", f"{end_ms / 1000:.3f}",
        "-i", str(video),
        "-vf", f"fps={fps},scale={width}:{height}:flags=bilinear,showinfo",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    times: list[int] = []

    def read_times() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            parsed = parse_showinfo_pts(line.decode("utf-8", "ignore"))
            if parsed is not None:
                times.append(parsed)

    thread = threading.Thread(target=read_times, daemon=True)
    thread.start()
    frame_bytes = width * height * 3
    index = 0
    assert proc.stdout is not None
    try:
        while True:
            raw = proc.stdout.read(frame_bytes)
            if len(raw) < frame_bytes:
                break
            for _ in range(200):
                if index < len(times) or proc.poll() is not None:
                    break
                thread.join(0.01)
            # -ss before -i resets pts to the start of this chunk, so add the source offset.
            offset = times[index] if index < len(times) else 0
            t_ms = start_ms + offset
            index += 1
            yield t_ms, np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3).copy()
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        thread.join(timeout=1)


def torso_hue(frame: np.ndarray, box: Box) -> Hue | None:
    height, width = frame.shape[:2]
    x, y, w, h = box
    x0, x1 = int((x + w * 0.25) * width), int((x + w * 0.75) * width)
    y0, y1 = int(y * height), int((y + h * 0.45) * height)
    crop = frame[max(0, y0) : max(y0 + 1, y1), max(0, x0) : max(x0 + 1, x1)]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0], None, [8], [0, 180]).flatten()
    total = float(hist.sum()) or 1.0
    return tuple(float(value / total) for value in hist)


def scene_cut(previous: np.ndarray | None, frame: np.ndarray) -> tuple[bool, np.ndarray]:
    small = cv2.resize(frame, (32, 18))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [8, 8], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    if previous is None:
        return False, hist
    return float(cv2.compareHist(previous, hist, cv2.HISTCMP_CORREL)) < 0.35, hist


def context_jpeg(frame: np.ndarray, box: Box, *, heights: float = 6.0, max_side: int = 640) -> bytes:
    """A crop wide enough to show the ball and nearby players, with the player outlined."""
    image_h, image_w = frame.shape[:2]
    x, y, w, h = box
    cx, cy = (x + w / 2) * image_w, (y + h / 2) * image_h
    half = max(h * image_h, w * image_w, 8) * heights / 2
    x0, y0 = int(max(0, cx - half)), int(max(0, cy - half))
    x1, y1 = int(min(image_w, cx + half)), int(min(image_h, cy + half))
    crop = frame[y0:y1, x0:x1]
    if crop.size == 0:
        crop = frame
        x0, y0 = 0, 0
    scale = min(1.0, max_side / max(crop.shape[0], crop.shape[1]))
    if scale < 1:
        crop = cv2.resize(crop, (max(1, int(crop.shape[1] * scale)), max(1, int(crop.shape[0] * scale))))
    px0 = int((x * image_w - x0) * scale)
    py0 = int((y * image_h - y0) * scale)
    px1 = int(((x + w) * image_w - x0) * scale)
    py1 = int(((y + h) * image_h - y0) * scale)
    cv2.rectangle(crop, (px0, py0), (px1, py1), (0, 165, 255), 2)
    ok, encoded = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        raise RuntimeError("Could not encode a scout frame")
    return encoded.tobytes()
