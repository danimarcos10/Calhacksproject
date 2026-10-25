import threading

from app.convex_bridge import ensure_revision, handle_claim
from app.db import new_id, utcnow
from app.providers.base import ProviderError
from app.publish import PublishedObservation, PublishedRun, anchor_from_convex, anchor_to_convex
from tests.test_jobs import Scripted, _post, _prepare, _result


class FakeConvex:
    def __init__(self):
        self.calls = []

    def mutation(self, name, args):
        self.calls.append((name, args))
        return True

    def named(self, name):
        return [args for called, args in self.calls if called == name]


def _claim(request_id, attempt, video, manifest, revision_key, anchors):
    return {
        "requestId": request_id,
        "attempt": attempt,
        "window": {"videoKey": video["id"], "manifestKey": manifest["id"]},
        "revision": {"key": revision_key, "number": 1, "anchors": anchors, "jerseyNote": "", "teamColorNote": "", "note": ""},
    }


def _anchors(manifest, x=0.2):
    return [{"frameId": manifest["frames"][0]["frame_id"], "state": "located", "source": "manual", "box": {"x": x, "y": 0.2, "w": 0.2, "h": 0.4}}]


def _scripted_for(application, revision_key, manifest):
    def extract(system, messages):
        number = application.state.db.get_revision(revision_key)["revision"]
        return _result(number, frame_ids=[manifest["frames"][0]["frame_id"]], start_ms=manifest["start_ms"], end_ms=manifest["start_ms"] + 800)

    return Scripted(extract)


def _budget_rows(application):
    return application.state.db.query_one("SELECT COUNT(*) AS n FROM budget_entries")["n"]


def test_retried_claim_and_refresh_never_pay_twice(tmp_path):
    client, application, video, manifest, _revision = _prepare(tmp_path, "bridge-retry")
    try:
        key = new_id("rev")
        scripted = _scripted_for(application, key, manifest)
        application.state.provider = scripted
        fake = FakeConvex()
        stop = threading.Event()

        handle_claim(application, fake, _claim("req1", 1, video, manifest, key, _anchors(manifest)), stop)
        first = fake.named("worker:publishResult")
        assert len(first) == 1 and first[0]["cacheStatus"] == "live"
        assert scripted.extract_calls == 1
        rows = _budget_rows(application)

        handle_claim(application, fake, _claim("req1", 2, video, manifest, key, _anchors(manifest)), stop)
        handle_claim(application, fake, _claim("req2", 1, video, manifest, key, _anchors(manifest)), stop)
        published = fake.named("worker:publishResult")
        assert [item["cacheStatus"] for item in published] == ["live", "cached", "cached"]
        assert {item["run"]["key"] for item in published} == {first[0]["run"]["key"]}
        assert scripted.extract_calls == 1
        assert _budget_rows(application) == rows

        PublishedRun.model_validate(first[0]["run"])
        observation = PublishedObservation.model_validate(first[0]["observations"][0])
        assert observation.startMs == manifest["start_ms"]
        assert observation.endMs == manifest["start_ms"] + 800
        spend = fake.named("worker:setWindowCost")[-1]
        assert spend["liveCalls"] == 1 and spend["cachedReuses"] == 2
    finally:
        client.__exit__(None, None, None)


def test_staleness_is_per_window(tmp_path):
    client, application, video, manifest, _revision = _prepare(tmp_path, "bridge-window")
    try:
        db = application.state.db
        other = client.post(f"/api/videos/{video['id']}/samples", json={"start_ms": 0, "end_ms": 2000}).json()
        key = new_id("rev")
        newer_elsewhere = {}

        def extract(system, messages):
            mine = db.get_revision(key)
            newer_elsewhere["id"] = new_id("rev")
            db.insert_revision(
                {
                    "id": newer_elsewhere["id"],
                    "video_id": video["id"],
                    "manifest_id": other["id"],
                    "revision": db.next_revision_number(video["id"]),
                    "anchors": [anchor_from_convex(a) for a in _anchors(other, 0.5)],
                    "jersey_note": "",
                    "team_color_note": "",
                    "identity_uncertain": False,
                    "role": "",
                    "created_at": utcnow(),
                }
            )
            return _result(mine["revision"], frame_ids=[manifest["frames"][0]["frame_id"]], start_ms=manifest["start_ms"], end_ms=manifest["start_ms"] + 500)

        application.state.provider = Scripted(extract)
        fake = FakeConvex()
        handle_claim(application, fake, _claim("req-a", 1, video, manifest, key, _anchors(manifest)), threading.Event())
        assert newer_elsewhere["id"]
        assert len(fake.named("worker:publishResult")) == 1
        assert fake.named("worker:failRequest") == []
    finally:
        client.__exit__(None, None, None)


def test_newer_selection_on_the_same_window_fails_as_stale(tmp_path):
    client, application, video, manifest, _revision = _prepare(tmp_path, "bridge-stale")
    try:
        db = application.state.db
        key = new_id("rev")

        def extract(system, messages):
            mine = db.get_revision(key)
            ensure_revision(db, manifest, {"key": new_id("rev"), "anchors": _anchors(manifest, 0.6)})
            return _result(mine["revision"], frame_ids=[manifest["frames"][0]["frame_id"]], start_ms=manifest["start_ms"], end_ms=manifest["start_ms"] + 500)

        application.state.provider = Scripted(extract)
        fake = FakeConvex()
        handle_claim(application, fake, _claim("req-s", 1, video, manifest, key, _anchors(manifest)), threading.Event())
        assert fake.named("worker:publishResult") == []
        failed = fake.named("worker:failRequest")
        assert failed and failed[0]["errorCode"] == "stale_revision"
    finally:
        client.__exit__(None, None, None)


def test_provider_failure_is_published_as_failure_with_cost_visible(tmp_path):
    client, application, video, manifest, _revision = _prepare(tmp_path, "bridge-fail")
    try:
        application.state.provider = Scripted(
            lambda system, messages: (_ for _ in ()).throw(ProviderError("provider_auth", "The API key was rejected."))
        )
        fake = FakeConvex()
        handle_claim(application, fake, _claim("req-f", 1, video, manifest, new_id("rev"), _anchors(manifest)), threading.Event())
        assert fake.named("worker:publishResult") == []
        assert fake.named("worker:failRequest")[0]["errorCode"] == "provider_auth"
        spend = fake.named("worker:setWindowCost")[-1]
        assert spend["failedJobs"] == 1 and spend["liveCalls"] == 0
    finally:
        client.__exit__(None, None, None)


def test_submission_windows_refuse_the_single_clip_routes(tmp_path):
    client, application, video, manifest, revision = _prepare(tmp_path, "bridge-attached")
    try:
        application.state.db.attach_manifest(manifest["id"], "sub_" + "a" * 16)
        target = client.post(
            f"/api/videos/{video['id']}/targets",
            json={"manifest_id": manifest["id"], "anchors": [{"frame_id": manifest["frames"][0]["frame_id"], "state": "located", "source": "manual", "box": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.3}}]},
        )
        assert target.status_code == 409 and target.json()["code"] == "window_in_submission"
        analysis = _post(client, video, manifest, revision, "attached")
        assert analysis.status_code == 409 and analysis.json()["code"] == "window_in_submission"
    finally:
        client.__exit__(None, None, None)


def test_estimated_anchors_stay_estimated_through_convex(tmp_path):
    client, application, video, manifest, _revision = _prepare(tmp_path, "bridge-anchors")
    try:
        estimated = {"frame_id": "f02", "state": "located", "source": "estimated", "box": {"x": 0.3, "y": 0.3, "w": 0.1, "h": 0.2}, "method": "csrt", "reason": None, "explicit": False}
        sent = anchor_to_convex(estimated)
        assert sent["source"] == "estimated" and sent["method"] == "csrt"
        assert anchor_from_convex(sent)["source"] == "estimated"
        legacy = anchor_to_convex({"frame_id": "f01", "state": "box", "box": {"x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1}})
        assert legacy["state"] == "located" and legacy["source"] == "manual"

        key = new_id("rev")
        frame_ids = [f["frame_id"] for f in manifest["frames"]]
        stored = ensure_revision(
            application.state.db,
            manifest,
            {"key": key, "anchors": [_anchors(manifest)[0], {**sent, "frameId": frame_ids[1]}]},
        )
        sources = {a["frame_id"]: a["source"] for a in stored["anchors"]}
        assert sources[frame_ids[0]] == "manual" and sources[frame_ids[1]] == "estimated"
        assert ensure_revision(application.state.db, manifest, {"key": key, "anchors": []})["id"] == key
    finally:
        client.__exit__(None, None, None)
