"""FFmpeg ingest and timestamped sampling.

Source time is milliseconds from the first displayed video frame's decoded
presentation timestamp. It is never frame_index / fps.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from app.errors import MediaError
from app.versions import SAMPLER_VERSION

_decode = threading.BoundedSemaphore(1)
_PLAYBACK_SCALE = "scale=w=1280:h=1280:force_original_aspect_ratio=decrease:force_divisible_by=2"
_FRAME_SCALE = "scale=w=960:h=960:force_original_aspect_ratio=decrease:force_divisible_by=2"


@dataclass
class Probe:
    codec: str
    coded_width: int
    coded_height: int
    display_width: int
    display_height: int
    rotation: int
    duration_ms: int
    timeline_ms: int
    first_pts: float
    frame_count: int
    frame_rate: str
    format_name: str


def _run(args: list[str], timeout: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, capture_output=True, timeout=timeout, shell=False)


def _fail_process(proc: subprocess.CompletedProcess[bytes], code: str, message: str) -> None:
    if proc.returncode != 0:
        raise MediaError(code, message, 400)


def frame_pts(path: Path) -> list[float]:
    """Decoded presentation timestamps, in seconds, in display order."""
    with _decode:
        return _frame_pts(path)


def _frame_pts(path: Path) -> list[float]:
    proc = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "frame=best_effort_timestamp_time",
            "-of",
            "csv=p=0",
            str(path),
        ],
        timeout=90,
    )
    _fail_process(proc, "unreadable_video", "This file could not be read as a video. Export an MP4 or MOV and try again.")
    pts: list[float] = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        cleaned = line.strip().strip(",")
        if not cleaned or cleaned == "N/A":
            continue
        pts.append(float(cleaned))
    if not pts:
        raise MediaError(
            "no_frames",
            "No video frames could be decoded. Export the clip again as H.264 MP4.",
            400,
        )
    return pts


def _rotation(stream: dict) -> int:
    angle: float | None = None
    for side in stream.get("side_data_list") or []:
        if side.get("side_data_type") == "Display Matrix" and side.get("rotation") is not None:
            angle = float(side["rotation"])
            break
    if angle is None:
        tags = stream.get("tags") or {}
        if tags.get("rotate") not in (None, ""):
            angle = float(tags["rotate"])
    if angle is None:
        return 0
    turned = int(round(angle)) % 360
    if turned not in (0, 90, 180, 270):
        raise MediaError(
            "unknown_rotation",
            "This video's rotation is not 0, 90, 180, or 270 degrees. Export it with the picture already upright.",
            400,
        )
    return turned


def probe_video(path: Path, *, min_seconds: int, max_seconds: int) -> Probe:
    with _decode:
        info = _run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            timeout=60,
        )
        _fail_process(
            info,
            "unreadable_video",
            "This file could not be read as a video. Export an MP4 or MOV and try again.",
        )
        try:
            payload = json.loads(info.stdout.decode("utf-8", "replace") or "{}")
        except json.JSONDecodeError as exc:
            raise MediaError(
                "unreadable_video",
                "This file could not be read as a video. Export an MP4 or MOV and try again.",
                400,
            ) from exc
        streams = [
            stream
            for stream in payload.get("streams") or []
            if stream.get("codec_type") == "video" and not (stream.get("disposition") or {}).get("attached_pic")
        ]
        if not streams or not streams[0].get("width") or not streams[0].get("height"):
            raise MediaError("no_video_stream", "No video stream was found in that file.", 400)
        stream = streams[0]
        codec = stream.get("codec_name") or ""
        if not codec or codec == "none":
            raise MediaError("no_video_stream", "No video stream was found in that file.", 400)
        rotation = _rotation(stream)
        coded_w = int(stream["width"])
        coded_h = int(stream["height"])
        if rotation in (90, 270):
            display_w, display_h = coded_h, coded_w
        else:
            display_w, display_h = coded_w, coded_h
        if max(display_w, display_h) > 4096:
            raise MediaError(
                "resolution_too_high",
                "This video is over 4096 pixels on the long side. Export a smaller copy.",
                400,
            )
        duration = float((payload.get("format") or {}).get("duration") or 0)
        if duration <= 0:
            raise MediaError("bad_duration", "The video duration could not be read.", 400)
        if duration > max_seconds:
            raise MediaError(
                "video_too_long",
                f"Videos are limited to {max_seconds} seconds for this demo. Export a shorter clip.",
                400,
            )
        if duration < min_seconds:
            raise MediaError(
                "video_too_short",
                f"Use a clip of at least {min_seconds} seconds so a 6-8 second window fits.",
                400,
            )
        decode = _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-v",
                "error",
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-f",
                "null",
                "-",
            ],
            timeout=60,
        )
        if decode.returncode != 0:
            raise MediaError(
                "undecodable",
                "The video could not be decoded. Export it again as H.264 MP4.",
                400,
            )
        pts = _frame_pts(path)
        timeline_ms = int(round((pts[-1] - pts[0]) * 1000))
        return Probe(
            codec=codec,
            coded_width=coded_w,
            coded_height=coded_h,
            display_width=display_w,
            display_height=display_h,
            rotation=rotation,
            duration_ms=int(round(duration * 1000)),
            timeline_ms=timeline_ms,
            first_pts=pts[0],
            frame_count=len(pts),
            frame_rate=str(stream.get("avg_frame_rate") or ""),
            format_name=str((payload.get("format") or {}).get("format_name") or ""),
        )


def make_playback(src: Path, dest: Path) -> None:
    """H.264 copy for the browser. Display rotation is applied. Relative timing is kept."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.mp4")
    if tmp.exists():
        tmp.unlink()
    with _decode:
        proc = _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-y",
                "-i",
                str(src),
                "-map",
                "0:v:0",
                "-vf",
                _PLAYBACK_SCALE,
                "-fps_mode",
                "passthrough",
                "-bf",
                "0",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-an",
                "-movflags",
                "+faststart",
                str(tmp),
            ],
            timeout=180,
        )
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise MediaError(
            "transcode_failed",
            "A browser-playable copy could not be made. Export the clip as H.264 MP4 and try again.",
            400,
        )
    tmp.replace(dest)


def _choose(inside: list[tuple[float, int]], start_ms: int, end_ms: int, cap: int) -> list[tuple[float, int]]:
    count = min(cap, max(2, round(((end_ms - start_ms) / 1000) * 2)))
    if len(inside) <= count:
        return inside
    targets = [start_ms + i * (end_ms - start_ms) / (count - 1) for i in range(count)]
    chosen: list[tuple[float, int]] = []
    used: set[int] = set()
    for target in targets:
        index = min(range(len(inside)), key=lambda i: (abs(inside[i][1] - target), i))
        if index not in used:
            used.add(index)
            chosen.append(inside[index])
    chosen.sort(key=lambda item: item[0])
    return chosen


def sample_window(src: Path, dest_dir: Path, start_ms: int, end_ms: int, cap: int) -> list[dict]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with _decode:
        absolute = _frame_pts(src)
        first = absolute[0]
        inside: list[tuple[float, int]] = []
        for pts in absolute:
            source_ms = int(round((pts - first) * 1000))
            if start_ms <= source_ms <= end_ms:
                inside.append((pts, source_ms))
        if len(inside) < 2:
            raise MediaError(
                "window_too_sparse",
                "That window does not contain enough decoded frames. Choose another interval.",
                400,
            )
        chosen = _choose(inside, start_ms, end_ms, cap)
        for earlier, later in zip(chosen, chosen[1:]):
            if abs(later[0] - earlier[0]) < 0.003:
                raise MediaError(
                    "frames_too_close",
                    "Two sampled frames are too close to extract reliably. Choose another interval.",
                    400,
                )
        select = "+".join(f"between(t,{pts - 0.0015:.6f},{pts + 0.0015:.6f})" for pts, _ in chosen)
        pattern = dest_dir / "extract%02d.jpg"
        proc = _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-y",
                "-copyts",
                "-i",
                str(src),
                "-map",
                "0:v:0",
                "-vf",
                f"select='{select}',showinfo,{_FRAME_SCALE}",
                "-fps_mode",
                "passthrough",
                "-q:v",
                "3",
                str(pattern),
            ],
            timeout=120,
        )
        if proc.returncode != 0:
            raise MediaError(
                "sample_failed",
                "Frames could not be extracted for that window. Try a slightly different interval.",
                400,
            )
        stderr = proc.stderr.decode("utf-8", "replace")
        seen = _showinfo_pts(stderr)
        files = sorted(dest_dir.glob("extract*.jpg"))
        if len(files) != len(chosen) or len(seen) != len(chosen):
            for file in files:
                file.unlink(missing_ok=True)
            raise MediaError(
                "sample_mismatch",
                "The extracted frames did not match the source timestamps. Try the window again.",
                400,
            )
        for file, (pts, _), reported in zip(files, chosen, seen):
            if abs(reported - pts) > 0.02:
                for item in files:
                    item.unlink(missing_ok=True)
                raise MediaError(
                    "sample_mismatch",
                    "The extracted frames did not match the source timestamps. Try the window again.",
                    400,
                )
        frames: list[dict] = []
        for index, (file, (pts, source_ms)) in enumerate(zip(files, chosen), start=1):
            frame_id = f"f{index:02d}"
            target = dest_dir / f"{frame_id}.jpg"
            file.replace(target)
            with Image.open(target) as image:
                width, height = image.size
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            frames.append(
                {
                    "frame_id": frame_id,
                    "source_t_ms": source_ms,
                    "derivative_t_ms": source_ms - start_ms,
                    "source_pts": round(pts, 6),
                    "width": width,
                    "height": height,
                    "image_sha256": digest,
                    "file": target.name,
                    "sampler_version": SAMPLER_VERSION,
                }
            )
        manifest_path = dest_dir / "manifest.json"
        temporary = dest_dir / "manifest.json.tmp"
        temporary.write_text(json.dumps({"frames": frames}, indent=2), encoding="utf-8")
        temporary.replace(manifest_path)
        return frames


def format_duration_ms(path: Path) -> int:
    with _decode:
        proc = _run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            timeout=30,
        )
    _fail_process(proc, "transcode_failed", "The playable copy could not be inspected.")
    payload = json.loads(proc.stdout.decode("utf-8", "replace") or "{}")
    duration = float((payload.get("format") or {}).get("duration") or 0)
    if duration <= 0:
        raise MediaError("transcode_failed", "The playable copy has no duration.", 400)
    return int(round(duration * 1000))


def _showinfo_pts(stderr: str) -> list[float]:
    found: list[float] = []
    for line in stderr.splitlines():
        if "pts_time:" not in line or "showinfo" not in line:
            continue
        token = line.split("pts_time:", 1)[1].split()[0]
        found.append(float(token))
    return found
