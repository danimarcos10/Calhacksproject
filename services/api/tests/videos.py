import subprocess
from pathlib import Path

from PIL import Image, ImageDraw


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True, shell=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-2000:])


def build_vfr(path: Path, offset: float = 1.5) -> list[float]:
    """Variable-rate clip with a one-second gap and a start-time offset.

    A white bar's x position is round(t * 30), where t is the pre-offset timeline.
    """
    times = [round(i * 0.1, 3) for i in range(30)] + [round(4.0 + i * 0.1, 3) for i in range(40)]
    work = path.parent / f"{path.stem}-frames"
    work.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for index, timestamp in enumerate(times):
        image = Image.new("RGB", (320, 180), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        x = min(300, int(round(timestamp * 30)))
        draw.rectangle([x, 20, x + 6, 160], fill=(255, 255, 255))
        name = f"f{index:03d}.png"
        image.save(work / name)
        names.append(name)
    lines = ["ffconcat version 1.0"]
    for index, name in enumerate(names):
        duration = (times[index + 1] - times[index]) if index + 1 < len(times) else 0.1
        lines.append(f"file '{(work / name).as_posix()}'")
        lines.append(f"duration {duration:.3f}")
    lines.append(f"file '{(work / names[-1]).as_posix()}'")
    script = work / "list.txt"
    script.write_text("\n".join(lines), encoding="ascii")
    raw = work / "raw.mp4"
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(script),
            "-fps_mode",
            "passthrough",
            "-bf",
            "0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(raw),
        ]
    )
    _run(["ffmpeg", "-y", "-i", str(raw), "-c", "copy", "-output_ts_offset", str(offset), str(path)])
    return times


def build_rotated(path: Path) -> None:
    work = path.parent / f"{path.stem}-frames"
    work.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (320, 180), (20, 80, 180))
    image.save(work / "frame.png")
    lines = ["ffconcat version 1.0", f"file '{(work / 'frame.png').as_posix()}'", "duration 2.000", f"file '{(work / 'frame.png').as_posix()}'"]
    script = work / "list.txt"
    script.write_text("\n".join(lines), encoding="ascii")
    plain = work / "plain.mp4"
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(script),
            "-r",
            "10",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(plain),
        ]
    )
    _run(["ffmpeg", "-y", "-display_rotation", "90", "-i", str(plain), "-c", "copy", str(path)])
