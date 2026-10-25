import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from app.propagate import decode_window, proposals_for_frames
from tests.videos import build_vfr


def _bar(width: int, x: int, color: tuple[int, int, int] = (240, 240, 240)) -> np.ndarray:
    image = np.zeros((80, width, 3), dtype=np.uint8)
    x = max(0, min(width - 24, x))
    image[20:60, x : x + 24] = color
    return image


def _box(x: int, width: int = 200) -> dict:
    return {"x": round(x / width, 4), "y": 20 / 80, "w": 24 / width, "h": 40 / 80}


def test_one_moving_bar_is_estimated_between_anchors():
    width = 200
    frames = [_bar(width, 8 + index * 10) for index in range(8)]
    times = [index * 100 for index in range(8)]
    samples = [{"frame_id": f"f{index + 1:02d}", "source_t_ms": times[index]} for index in range(8)]
    anchors = [
        {"frame_id": "f01", "state": "located", "source": "manual", "box": _box(8), "explicit": False},
        {"frame_id": "f08", "state": "located", "source": "manual", "box": _box(8 + 7 * 10), "explicit": False},
    ]
    proposed = {item["frame_id"]: item for item in proposals_for_frames(frames, times, samples, anchors)}
    assert "f01" not in proposed
    middle = proposed["f04"]
    assert middle["state"] == "located"
    assert middle["source"] == "estimated"
    assert middle["method"] == "csrt-fb"
    assert abs(middle["box"]["x"] - _box(8 + 3 * 10)["x"]) < 0.08


def test_crossing_bars_are_uncertain():
    width = 220
    frames = []
    for index in range(8):
        image = np.zeros((80, width, 3), dtype=np.uint8)
        left = 10 + index * 18
        right = 170 - index * 18
        image[20:60, left : left + 22] = (230, 230, 230)
        image[20:60, right : right + 22] = (230, 230, 230)
        frames.append(image)
    times = [index * 100 for index in range(8)]
    samples = [{"frame_id": f"f{index + 1:02d}", "source_t_ms": times[index]} for index in range(8)]
    anchors = [
        {"frame_id": "f01", "state": "located", "source": "manual", "box": _box(10, width), "explicit": False},
        {"frame_id": "f08", "state": "located", "source": "manual", "box": _box(10 + 7 * 18, width), "explicit": False},
    ]
    proposed = {item["frame_id"]: item for item in proposals_for_frames(frames, times, samples, anchors)}
    assert proposed["f04"]["state"] == "uncertain"
    assert "disagree" in (proposed["f04"]["reason"] or "").lower() or "lost" in (proposed["f04"]["reason"] or "").lower()


def test_decoding_ignores_a_locked_earlier_decode(tmp_path):
    clip = tmp_path / "clip.mp4"
    build_vfr(clip)
    work = tmp_path / "proposals"
    earlier = work / "decode_earlier"
    earlier.mkdir(parents=True)
    with open(earlier / "0001.jpg", "wb") as held:
        held.write(b"held open, as a sync client does")
        frames, times = decode_window(clip, 1500, 3000, work)
    assert frames and len(frames) == len(times)
    assert times == sorted(times)
    assert [path.name for path in work.iterdir()] == ["decode_earlier"]
