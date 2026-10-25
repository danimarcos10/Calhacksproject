from app.opportunities import draft_email, stats_table as email_table
from app.schemas import ClipStats, OpportunityIn
from app.scout.profile import PlayerProfileIn, stats_table, text_ok, validate_profile
from tests.conftest import make_client
from tests.videos import build_vfr


def _clips():
    return [
        {
            "order": 1,
            "trackedMs": 10000,
            "events": [
                {"id": "e1", "action": "pass", "outcome": "completed", "text": "Plays it square.", "startMs": 1000, "held": False},
                {"id": "e2", "action": "pass", "outcome": "completed", "text": "Plays it forward.", "startMs": 4000, "held": False},
                {"id": "e3", "action": "loss", "outcome": "lost", "text": "A challenge takes it.", "startMs": 7000, "held": False},
                {"id": "e4", "action": "loss", "outcome": "lost", "text": "A heavy touch loses it.", "startMs": 9000, "held": False},
            ],
        }
    ]


def _draft(**overrides):
    values = dict(
        schema_version="profile-1",
        summary="Alex plays two completed passes and loses the ball twice.",
        qualities=[{"text": "Two completed passes leave the feet.", "event_ids": ["e1", "e2"]}],
        gaps=["No shot is in these clips."],
        ability={
            "overall": 60,
            "dimensions": [
                {"name": "passing", "score": 70, "reason": "Two completed passes.", "event_ids": ["e1", "e2"]},
                {"name": "ball_security", "score": 40, "reason": "The ball is lost twice.", "event_ids": ["e3", "e4"]},
            ],
        },
    )
    values.update(overrides)
    return PlayerProfileIn(**values)


def test_profile_keeps_cited_actions_and_drops_a_thin_estimate():
    table, listing, actions = stats_table(_clips())
    assert "passes 2 completed of 2" in table
    assert [item["id"] for item in listing] == ["e1", "e2", "e3", "e4"]
    kept = validate_profile(_draft(), actions=actions, table=table)
    assert kept is not None
    assert kept["qualities"][0]["eventIds"] == ["e1", "e2"]
    assert kept["ability"]["overall"] == 60
    assert [item["name"] for item in kept["ability"]["dimensions"]] == ["passing", "ball_security"]

    thin = _draft(ability={"overall": 60, "dimensions": [{"name": "passing", "score": 70, "reason": "Two completed passes.", "event_ids": ["e1", "e2"]}]})
    dropped = validate_profile(thin, actions=actions, table=table)
    assert dropped is not None
    assert "ability" not in dropped


def test_two_clips_add_up_and_the_ability_score_stays_out_of_the_email():
    clips = [
        _clips()[0],
        {
            "order": 2,
            "trackedMs": 5000,
            "events": [
                {"id": "e5", "action": "receive", "outcome": "controlled", "text": "Takes the ball.", "startMs": 1000, "held": False},
                {"id": "e6", "action": "carry", "outcome": "retained", "text": "Carries it forward.", "startMs": 3000, "held": False},
            ],
        },
    ]
    table, listing, actions = stats_table(clips)
    assert "Total across 2 clips: tracked 15s, receives 1, passes 2 completed of 2, carries 1, losses 2" in table
    assert [item["id"] for item in listing] == ["e1", "e2", "e3", "e4", "e5", "e6"]
    kept = validate_profile(_draft(), actions=actions, table=table)
    assert kept is not None
    assert kept["ability"]["overall"] == 60
    email_stats = ClipStats(
        tracked_s=15,
        receives=1,
        passes_completed=2,
        passes_attempted=2,
        carries=1,
        losses=2,
        reviewed=True,
        clips=2,
        confidence=37,
    )
    _subject, draft = draft_email(
        OpportunityIn(
            player_name="Alex",
            player_email="alex@example.com",
            position="Fullback",
            grad_year=2027,
            state="California",
            league="ecnl_rl",
            schools=["Biola University"],
            stats=email_stats,
            profile=kept["summary"],
        ),
        "Zach Watson",
        email_table(email_stats),
        kept["summary"],
    )
    assert kept["summary"] in draft
    assert "60" not in draft


def test_profile_rejects_invented_numbers_unknown_events_and_banned_words():
    table, _listing, actions = stats_table(_clips())
    assert validate_profile(_draft(summary="Alex plays 9 passes."), actions=actions, table=table) is None
    assert validate_profile(_draft(summary="Alex is an elite passer with 2 completed passes."), actions=actions, table=table) is None
    invented = _draft(qualities=[{"text": "Two completed passes.", "event_ids": ["missing"]}])
    kept = validate_profile(invented, actions=actions, table=table)
    assert kept is not None
    assert kept["qualities"] == []
    mismatched = _draft(
        ability={
            "overall": 50,
            "dimensions": [
                {"name": "carrying", "score": 50, "reason": "Two completed passes.", "event_ids": ["e1", "e2"]},
                {"name": "passing", "score": 70, "reason": "Two completed passes.", "event_ids": ["e1", "e2"]},
            ],
        }
    )
    without_carry = validate_profile(mismatched, actions=actions, table=table)
    assert without_carry is not None
    assert "ability" not in without_carry
    assert text_ok("No shot is shown.", table)


def test_batch_opens_one_submission_for_every_clip(tmp_path, monkeypatch):
    monkeypatch.setattr("app.scout.roboflow.start_tracking", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.scout.roboflow.read_progress", lambda *args, **kwargs: {"state": "succeeded", "done": 1, "total": 1})
    calls = []

    class FakeClient:
        def mutation(self, name, args):
            if name == "worker:claimNext":
                return None
            calls.append((name, args))
            if name == "worker:registerWindow":
                return f"win_{len(calls)}"
            return {"key": "sub_test"}

    monkeypatch.setattr("app.convex_bridge.make_client", lambda url: FakeClient())
    test_client, _application = make_client(tmp_path, convex_url="http://convex.local", convex_worker_secret="secret")
    test_client.__enter__()
    videos = []
    for index in range(2):
        path = tmp_path / f"clip-{index}.mp4"
        build_vfr(path)
        with path.open("rb") as handle:
            response = test_client.post("/api/videos", files={"file": (path.name, handle, "video/mp4")}, data={"rights_note": "test clip"})
        assert response.status_code == 201, response.text
        videos.append(response.json())
    box = {"x": 0.4, "y": 0.4, "w": 0.1, "h": 0.2}
    started = test_client.post(
        "/api/scout",
        json={
            "player_name": "Alex",
            "clips": [{"video_id": video["id"], "t_ms": 1000, "box": box} for video in videos],
        },
    )
    assert started.status_code == 201, started.text
    body = started.json()
    assert body["key"].startswith("sub_")
    assert len(body["window_ids"]) == 2
    names = [name for name, _args in calls]
    assert names.count("worker:createSubmission") == 1
    assert names.count("worker:registerWindow") == 2
    assert names.count("review:queueAnalysis") == 2
    orders = [args["order"] for name, args in calls if name == "worker:registerWindow"]
    assert orders == [1, 2]


def test_batch_rejects_a_repeated_clip_and_a_clip_still_tracking(tmp_path, monkeypatch):
    monkeypatch.setattr("app.scout.roboflow.start_tracking", lambda *args, **kwargs: None)
    test_client, _application = make_client(tmp_path, convex_url="http://convex.local", convex_worker_secret="secret")
    test_client.__enter__()
    path = tmp_path / "clip.mp4"
    build_vfr(path)
    with path.open("rb") as handle:
        video = test_client.post("/api/videos", files={"file": (path.name, handle, "video/mp4")}, data={"rights_note": "test"}).json()
    box = {"x": 0.4, "y": 0.4, "w": 0.1, "h": 0.2}
    clip = {"video_id": video["id"], "t_ms": 1000, "box": box}
    repeated = test_client.post("/api/scout", json={"player_name": "Alex", "clips": [clip, clip]})
    assert repeated.status_code == 422
    monkeypatch.setattr("app.scout.roboflow.read_progress", lambda *args, **kwargs: {"state": "running", "done": 1, "total": 4})
    waiting = test_client.post("/api/scout", json={"player_name": "Alex", "clips": [clip]})
    assert waiting.status_code == 409
