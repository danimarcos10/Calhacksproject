import time

from app.db import new_id, utcnow
from app.providers.base import ProviderCallResult, ProviderError
from app.schemas import ProviderEvidence
from app.versions import SCHEMA_VERSION
from tests.conftest import make_client
from tests.videos import build_vfr


class Scripted:
    label = "live"

    def __init__(self, extract_fn, tokens=1000):
        self.extract_fn = extract_fn
        self.tokens = tokens
        self.extract_calls = 0

    def count_tokens(self, system, messages):
        return self.tokens

    def extract(self, system, messages):
        self.extract_calls += 1
        return self.extract_fn(system, messages)


def _result(revision: int, frame_ids: list[str] | None = None, **observation) -> ProviderCallResult:
    ids = frame_ids or ["f01"]
    body = {
        "category": "defending_action",
        "start_ms": 0,
        "end_ms": 1000,
        "frame_ids": ids,
        "visible_action": "The target steps toward the ball carrier.",
        "outcome": "not_observable",
        "evidence_status": "ambiguous",
        "identity_status": "clear_in_cited_frames",
        "limitations": [],
    }
    body.update(observation)
    parsed = ProviderEvidence(
        schema_version=SCHEMA_VERSION,
        target_revision=revision,
        observations=[] if frame_ids == [] else [body],
        gaps=[],
        no_observation_reason="Nothing supported." if frame_ids == [] else None,
    )
    return ProviderCallResult(
        parsed=parsed,
        model="scripted-test",
        usage={"input_tokens": 1000, "output_tokens": 50},
        stop_reason="end_turn",
        request_id="scripted",
        raw={"label": "scripted-test"},
    )


def _prepare(tmp_path, name="jobs"):
    source = tmp_path / "vfr.mp4"
    if not source.exists():
        build_vfr(source, offset=0)
    client, application = make_client(tmp_path / name, evidence_provider="anthropic", anthropic_api_key="test-key")
    client.__enter__()
    with source.open("rb") as handle:
        video = client.post("/api/videos", files={"file": ("vfr.mp4", handle, "video/mp4")}).json()
    end_ms = min(7000, video["duration_ms"])
    manifest = client.post(f"/api/videos/{video['id']}/samples", json={"start_ms": 0, "end_ms": end_ms})
    assert manifest.status_code == 200, manifest.text
    manifest = manifest.json()
    anchors = [
        {"frame_id": frame["frame_id"], "state": "located", "source": "manual", "box": {"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.4}}
        for frame in manifest["frames"][:1]
    ]
    revision = client.post(
        f"/api/videos/{video['id']}/targets",
        json={
            "manifest_id": manifest["id"],
            "role": "fullback",
            "jersey_note": "white 4",
            "team_color_note": "white",
            "anchors": anchors,
        },
    )
    assert revision.status_code == 200, revision.text
    return client, application, video, manifest, revision.json()


def _wait(client, job_id):
    deadline = time.time() + 15
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in {"succeeded", "failed", "interrupted", "cancelled"}:
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def _post(client, video, manifest, revision, key):
    return client.post(
        "/api/analyses",
        headers={"Idempotency-Key": key},
        json={"video_id": video["id"], "manifest_id": manifest["id"], "target_revision_id": revision["id"]},
    )


def test_synthetic_run_is_labeled_and_seekable(client, tmp_path):
    test_client, _application = client
    source = tmp_path / "vfr.mp4"
    build_vfr(source, offset=0)
    with source.open("rb") as handle:
        video = test_client.post("/api/videos", files={"file": ("vfr.mp4", handle, "video/mp4")}).json()
    end_ms = min(7000, video["duration_ms"])
    manifest = test_client.post(f"/api/videos/{video['id']}/samples", json={"start_ms": 0, "end_ms": end_ms}).json()
    revision = test_client.post(
        f"/api/videos/{video['id']}/targets",
        json={
            "manifest_id": manifest["id"],
            "anchors": [
                {"frame_id": manifest["frames"][0]["frame_id"], "state": "located", "source": "manual", "box": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.3}}
            ],
        },
    ).json()
    job = _post(test_client, video, manifest, revision, "synthetic-1")
    assert job.status_code == 200, job.text
    finished = _wait(test_client, job.json()["id"])
    assert finished["status"] == "succeeded"
    assert finished["result"]["provenance"]["provider_label"] == "synthetic"
    assert "SYNTHETIC FIXTURE" in finished["result"]["observations"][0]["visible_action"]
    assert finished["result"]["observations"][0]["review_status"] == "candidate"
    assert finished["stage_log"]


def test_auth_failure_does_not_invent_evidence(tmp_path):
    client, application, video, manifest, revision = _prepare(tmp_path, "auth")
    try:
        application.state.provider = Scripted(
            lambda system, messages: (_ for _ in ()).throw(
                ProviderError("provider_auth", "The API key was rejected. Check ANTHROPIC_API_KEY on the server.")
            )
        )
        finished = _wait(client, _post(client, video, manifest, revision, "auth-1").json()["id"])
        assert finished["status"] == "failed"
        assert finished["error"]["code"] == "provider_auth"
        assert finished["result"] is None or finished["result"]["observations"] == []
        assert application.state.db.count_observations(finished["result_run_id"] or "none") == 0
    finally:
        client.__exit__(None, None, None)


def test_malformed_and_bad_citation_and_zero(tmp_path):
    client, application, video, manifest, revision = _prepare(tmp_path, "malformed")
    try:
        application.state.provider = Scripted(
            lambda system, messages: (_ for _ in ()).throw(
                ProviderError("malformed_output", "The model response did not match the evidence schema.", billed=True, usage={"input_tokens": 10, "output_tokens": 1})
            )
        )
        failed = _wait(client, _post(client, video, manifest, revision, "bad-1").json()["id"])
        assert failed["error"]["code"] == "malformed_output"
        assert application.state.db.count_observations(failed["result_run_id"] or "none") == 0

        application.state.provider = Scripted(lambda system, messages: _result(revision["revision"], frame_ids=["nope"]))
        cited = _wait(client, _post(client, video, manifest, revision, "bad-2").json()["id"])
        assert cited["status"] == "succeeded"
        assert cited["result"]["observations"] == []
        assert cited["result"]["validation_issues"][0]["code"] == "unknown_frame"

        empty_revision = client.post(
            f"/api/videos/{video['id']}/targets",
            json={
                "manifest_id": manifest["id"],
                "anchors": [
                    {"frame_id": manifest["frames"][0]["frame_id"], "state": "located", "source": "manual", "box": {"x": 0.25, "y": 0.2, "w": 0.2, "h": 0.3}}
                ],
            },
        ).json()
        application.state.provider = Scripted(lambda system, messages: _result(empty_revision["revision"], frame_ids=[]))
        empty = _wait(client, _post(client, video, manifest, empty_revision, "bad-3").json()["id"])
        assert empty["status"] == "succeeded"
        assert empty["result"]["observations"] == []
        assert empty["result"]["no_observation_reason"] == "Nothing supported."
    finally:
        client.__exit__(None, None, None)


def test_idempotency_cache_budget_and_stale_revision(tmp_path):
    client, application, video, manifest, revision = _prepare(tmp_path, "cache")
    try:
        scripted = Scripted(lambda system, messages: _result(revision["revision"], frame_ids=[manifest["frames"][0]["frame_id"]], start_ms=manifest["start_ms"], end_ms=manifest["start_ms"] + 1000))
        application.state.provider = scripted
        first = _post(client, video, manifest, revision, "same-key")
        second = _post(client, video, manifest, revision, "same-key")
        assert first.json()["id"] == second.json()["id"]
        _wait(client, first.json()["id"])
        assert scripted.extract_calls == 1

        third = _wait(client, _post(client, video, manifest, revision, "other-key").json()["id"])
        assert third["cache_status"] == "cached"
        assert scripted.extract_calls == 1

        expensive = Scripted(lambda system, messages: _result(revision["revision"]), tokens=2_000_000)
        application.state.provider = expensive
        fresh = client.post(
            f"/api/videos/{video['id']}/targets",
            json={
                "manifest_id": manifest["id"],
                "anchors": [
                    {"frame_id": manifest["frames"][0]["frame_id"], "state": "located", "source": "manual", "box": {"x": 0.3, "y": 0.2, "w": 0.2, "h": 0.3}}
                ],
            },
        ).json()
        blocked = _wait(client, _post(client, video, manifest, fresh, "budget").json()["id"])
        assert blocked["error"]["code"] == "budget_exceeded"
        assert expensive.extract_calls == 0

        def stale_extract(system, messages):
            latest = application.state.db.latest_revision(video["id"])
            application.state.db.insert_revision(
                {
                    "id": new_id("rev"),
                    "video_id": video["id"],
                    "manifest_id": manifest["id"],
                    "revision": latest["revision"] + 1,
                    "anchors": latest["anchors"],
                    "jersey_note": "",
                    "team_color_note": "",
                    "identity_uncertain": False,
                    "role": "fullback",
                    "created_at": utcnow(),
                }
            )
            return _result(latest["revision"], frame_ids=[manifest["frames"][0]["frame_id"]], start_ms=manifest["start_ms"], end_ms=manifest["start_ms"] + 500)

        application.state.provider = Scripted(stale_extract, tokens=100)
        newer = client.post(
            f"/api/videos/{video['id']}/targets",
            json={
                "manifest_id": manifest["id"],
                "anchors": [
                    {"frame_id": manifest["frames"][0]["frame_id"], "state": "located", "source": "manual", "box": {"x": 0.4, "y": 0.2, "w": 0.2, "h": 0.3}}
                ],
            },
        ).json()
        stale = _wait(client, _post(client, video, manifest, newer, "stale").json()["id"])
        assert stale["error"]["code"] == "stale_revision"
        assert application.state.db.count_observations(stale["result_run_id"] or "none") == 0
    finally:
        client.__exit__(None, None, None)


def test_missing_key_does_not_create_a_job(tmp_path):
    client, _application = make_client(tmp_path / "nokey", evidence_provider="anthropic", anthropic_api_key="")
    with client:
        response = client.post(
            "/api/analyses",
            json={"video_id": "vid_" + "a" * 16, "manifest_id": "man_" + "b" * 16, "target_revision_id": "rev_" + "c" * 16},
        )
    assert response.status_code == 400
    assert response.json()["code"] == "provider_not_configured"
