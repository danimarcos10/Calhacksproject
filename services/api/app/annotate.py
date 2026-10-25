import io
from pathlib import Path

from PIL import Image, ImageDraw


def annotated_jpeg(path: Path, box: dict | None) -> bytes:
    """Bytes actually sent to the model. A box is a manual coach anchor, not a track."""
    with Image.open(path) as image:
        frame = image.convert("RGB")
    if box is not None:
        width, height = frame.size
        x0 = round(box["x"] * width)
        y0 = round(box["y"] * height)
        x1 = round((box["x"] + box["w"]) * width)
        y1 = round((box["y"] + box["h"]) * height)
        draw = ImageDraw.Draw(frame)
        draw.rectangle([x0, y0, x1, y1], outline=(255, 176, 0), width=3)
        label_y = y0 - 14 if y0 >= 16 else min(y0 + 2, height - 12)
        draw.text((x0 + 2, label_y), "manual coach anchor", fill=(255, 176, 0))
    buffer = io.BytesIO()
    frame.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()
