import io

from PIL import Image

from app.annotate import annotated_jpeg
from app.media import frame_pts
from tests.conftest import make_client
from tests.videos import build_rotated, build_vfr


def _upload(client, path):
    with path.open("rb") as handle:
        response = client.post(
            "/api/videos",
            files={"file": (path.name, handle, "video/mp4")},
            data={"rights_note": "test clip"},
        )
    assert response.status_code == 201, response.text
    return response.json()


def test_vfr_timestamps_follow_presentation_time_not_frame_rate(client, tmp_path):
    test_client, application = client
    source = tmp_path / "vfr.mp4"
    build_vfr(source)
    video = _upload(test_client, source)
    original = application.state.settings.data_path / "videos" / video["id"] / "original.mp4"
    playback = application.state.settings.data_path / "videos" / video["id"] / "playback.mp4"
    original_pts = frame_pts(original)
    playback_pts = frame_pts(playback)
    assert abs(playback_pts[0]) < 0.05
    original_deltas = [b - a for a, b in zip(original_pts, original_pts[1:])]
    playback_deltas = [b - a for a, b in zip(playback_pts, playback_pts[1:])]
    assert len(playback_deltas) == len(original_deltas)
    assert all(abs(left - right) < 0.02 for left, right in zip(original_deltas, playback_deltas))
    assumed_wrong = any(abs((pts - original_pts[0]) - (index / 10)) > 0.5 for index, pts in enumerate(original_pts))
    assert assumed_wrong

    end_ms = min(7000, video["duration_ms"])
    sampled = test_client.post(f"/api/videos/{video['id']}/samples", json={"start_ms": 0, "end_ms": end_ms})
    assert sampled.status_code == 200, sampled.text
    frames = sampled.json()["frames"]
    assert frames
    for frame in frames:
        assert frame["derivative_t_ms"] == frame["source_t_ms"] - 0
        image = Image.open(io.BytesIO(test_client.get(frame["url"]).content))
        bright = None
        pixels = image.load()
        for x in range(image.width):
            red, green, blue = pixels[x, 80]
            if red > 200 and green > 200 and blue > 200:
                bright = x
                break
        assert bright is not None
        scale = image.width / 320
        expected = min(image.width - 1, int(round((frame["source_t_ms"] / 1000) * 30 * scale)))
        assert abs(bright - expected) <= 12
        nearest = min(original_pts, key=lambda pts: abs(int(round((pts - original_pts[0]) * 1000)) - frame["source_t_ms"]))
        assert abs(int(round((nearest - original_pts[0]) * 1000)) - frame["source_t_ms"]) <= 1


def test_rotation_is_applied_to_display_and_frames(client, tmp_path):
    test_client, _application = client
    source = tmp_path / "rotated.mp4"
    build_rotated(source)
    video = _upload(test_client, source)
    assert video["rotation"] == 90
    assert video["width"] == 180
    assert video["height"] == 320
    end_ms = min(1500, video["duration_ms"])
    sampled = test_client.post(f"/api/videos/{video['id']}/samples", json={"start_ms": 0, "end_ms": end_ms})
    assert sampled.status_code == 200, sampled.text
    frame = sampled.json()["frames"][0]
    image = Image.open(io.BytesIO(test_client.get(frame["url"]).content))
    assert image.height > image.width


def test_upload_rejects_bad_files_and_media_supports_range(client, tmp_path):
    test_client, application = client
    text = tmp_path / "notes.mp4"
    text.write_text("not a video", encoding="utf-8")
    with text.open("rb") as handle:
        rejected = test_client.post("/api/videos", files={"file": ("notes.mp4", handle, "video/mp4")})
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "unreadable_video"
    assert "request_id" in rejected.json()

    source = tmp_path / "clip.mp4"
    build_vfr(source, offset=0)
    video = _upload(test_client, source)
    ranged = test_client.get(video["media_url"], headers={"Range": "bytes=0-99"})
    assert ranged.status_code == 206
    assert ranged.headers["content-range"].startswith("bytes 0-99/")
    assert len(ranged.content) == 100

    too_long_client, _app = make_client(tmp_path / "long", max_video_seconds=2, scout_max_video_seconds=2)
    with too_long_client:
        with source.open("rb") as handle:
            too_long = too_long_client.post("/api/videos", files={"file": ("clip.mp4", handle, "video/mp4")})
    assert too_long.status_code == 400
    assert too_long.json()["code"] == "video_too_long"

    huge = tmp_path / "huge.mp4"
    huge.write_bytes(b"0" * (1200 * 1024))
    small_client, _small_app = make_client(tmp_path / "small", max_upload_mb=1)
    with small_client:
        with huge.open("rb") as handle:
            oversized = small_client.post("/api/videos", files={"file": ("huge.mp4", handle, "video/mp4")})
    assert oversized.status_code == 413
    assert oversized.json()["code"] == "upload_too_large"
    assert application.state.db.get_video(video["id"]) is not None


def test_manual_anchor_box_lands_on_normalized_pixels(tmp_path):
    image = Image.new("RGB", (100, 50), (0, 0, 0))
    path = tmp_path / "frame.jpg"
    image.save(path, format="JPEG")
    rendered = Image.open(io.BytesIO(annotated_jpeg(path, {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4})))
    pixel = rendered.getpixel((10, 10))
    assert pixel[0] > 200 and pixel[1] > 100
