import io

from PIL import Image

from app.annotate import annotated_jpeg
from app.db import new_id, utcnow
from app.worker import _preamble, fingerprint
from tests.test_jobs import _prepare


def test_untouched_frames_stay_absent(tmp_path):
    client, _application, video, manifest, revision = _prepare(tmp_path, "untouched")
    try:
        assert len(revision["anchors"]) == 1
        assert revision["anchors"][0]["state"] == "located"
        assert revision["anchors"][0]["source"] == "manual"
        assert revision["needs_review"] == []
        loaded = client.get(f"/api/videos/{video['id']}").json()
        assert len(loaded["revisions"][-1]["anchors"]) == 1
        assert len(loaded["revisions"][-1]["anchors"]) < len(manifest["frames"])
    finally:
        client.__exit__(None, None, None)


def test_legacy_not_visible_needs_review(tmp_path):
    client, application, video, manifest, revision = _prepare(tmp_path, "legacy")
    try:
        hidden = manifest["frames"][1]["frame_id"]
        application.state.db.insert_revision(
            {
                "id": new_id("rev"),
                "video_id": video["id"],
                "manifest_id": manifest["id"],
                "revision": revision["revision"] + 1,
                "anchors": [
                    {
                        "frame_id": manifest["frames"][0]["frame_id"],
                        "state": "box",
                        "box": {"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.3},
                    },
                    {"frame_id": hidden, "state": "not_visible"},
                ],
                "jersey_note": "",
                "team_color_note": "",
                "identity_uncertain": True,
                "role": "fullback",
                "created_at": utcnow(),
            }
        )
        loaded = client.get(f"/api/videos/{video['id']}").json()
        legacy = loaded["revisions"][-1]
        assert legacy["anchors"][0]["state"] == "located"
        assert legacy["anchors"][0]["source"] == "manual"
        assert legacy["anchors"][1]["state"] == "not_visible"
        text = " ".join(legacy["needs_review"])
        assert "whole clip" in text
        assert hidden in text
    finally:
        client.__exit__(None, None, None)


def test_preamble_labels_estimates_and_leaves_gaps():
    text = _preamble(
        {"revision": 2, "role": "", "jersey_note": "", "team_color_note": ""},
        [{"frame_id": "f01", "source_t_ms": 0}, {"frame_id": "f02", "source_t_ms": 500}],
        {
            "f01": {
                "state": "located",
                "source": "estimated",
                "method": "csrt-fb",
                "box": {"x": 0.1, "y": 0.2, "w": 0.2, "h": 0.3},
            }
        },
    )
    assert "software estimate, unverified" in text
    assert "f02: not annotated" in text
    assert "Withhold attribution" not in text


def test_estimated_overlay_uses_a_cyan_mark(tmp_path):
    path = tmp_path / "frame.jpg"
    Image.new("RGB", (200, 120), (10, 10, 10)).save(path, quality=95)
    box = {"x": 0.2, "y": 0.25, "w": 0.4, "h": 0.4}
    estimated = Image.open(io.BytesIO(annotated_jpeg(path, box, "estimated")))
    manual = Image.open(io.BytesIO(annotated_jpeg(path, box, "manual")))
    edge_y = round(0.25 * 120)
    estimated_pixel = max((estimated.getpixel((x, edge_y)) for x in range(40, 120)), key=lambda pixel: pixel[2])
    manual_pixel = max((manual.getpixel((x, edge_y)) for x in range(40, 120)), key=lambda pixel: pixel[0])
    assert estimated_pixel[2] > estimated_pixel[0]
    assert manual_pixel[0] > manual_pixel[2]


def test_revision_prompt_or_schema_change_misses_the_cache():
    import app.worker as worker

    base = dict(video_sha256="abc", start_ms=0, end_ms=7000, revision_id="rev_a", model="claude-sonnet-5")
    first = fingerprint(**base)
    assert fingerprint(**{**base, "revision_id": "rev_b"}) != first
    original_schema = worker.SCHEMA_VERSION
    original_prompt = worker.PROMPT_VERSION
    try:
        worker.SCHEMA_VERSION = "9.9"
        assert fingerprint(**base) != first
        worker.SCHEMA_VERSION = original_schema
        worker.PROMPT_VERSION = "evidence-v9"
        assert fingerprint(**base) != first
    finally:
        worker.SCHEMA_VERSION = original_schema
        worker.PROMPT_VERSION = original_prompt
