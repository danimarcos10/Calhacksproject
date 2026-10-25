import io
from pathlib import Path

from PIL import Image, ImageDraw

_STYLES = {
    "manual": ((255, 176, 0), "manual selection", False),
    "estimated": ((0, 196, 210), "software estimate, unverified", True),
    "uncertain": ((220, 60, 60), "location uncertain", False),
}


def annotated_jpeg(path: Path, box: dict | None, kind: str = "manual") -> bytes:
    """Bytes actually sent to the model. The label says how the box was made."""
    with Image.open(path) as image:
        frame = image.convert("RGB")
    if box is not None:
        width, height = frame.size
        x0 = round(box["x"] * width)
        y0 = round(box["y"] * height)
        x1 = round((box["x"] + box["w"]) * width)
        y1 = round((box["y"] + box["h"]) * height)
        color, label, dashed = _STYLES.get(kind, _STYLES["manual"])
        draw = ImageDraw.Draw(frame)
        if dashed:
            _dashed(draw, x0, y0, x1, y1, color)
        else:
            draw.rectangle([x0, y0, x1, y1], outline=color, width=3)
        label_y = y0 - 14 if y0 >= 16 else min(y0 + 2, height - 12)
        draw.text((x0 + 2, label_y), label, fill=color)
    buffer = io.BytesIO()
    frame.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def _dashed(draw: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
    edges = [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]
    dash, gap = 8, 6
    for xa, ya, xb, yb in edges:
        length = max(abs(xb - xa), abs(yb - ya))
        if length == 0:
            continue
        travelled = 0
        while travelled < length:
            start = travelled / length
            end = min(length, travelled + dash) / length
            draw.line(
                [(xa + (xb - xa) * start, ya + (yb - ya) * start), (xa + (xb - xa) * end, ya + (yb - ya) * end)],
                fill=color,
                width=3,
            )
            travelled += dash + gap
