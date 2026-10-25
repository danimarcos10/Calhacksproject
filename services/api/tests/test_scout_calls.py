from app.config import Settings
from app.db import Database
from app.scout.calls import decide_batch, finish_batch


def _settings(tmp_path) -> Settings:
    return Settings(
        data_dir=str(tmp_path),
        database_url="sqlite:///" + (tmp_path / "secondlook.db").as_posix(),
        job_budget_usd=1.0,
        app_budget_usd=15.0,
    )


def test_an_unknown_attempt_is_not_sent_again_and_its_reservation_stays(tmp_path):
    settings = _settings(tmp_path)
    db = Database(tmp_path / "secondlook.db")
    first = decide_batch(db, settings, job_id="job", batch_key="b1", fingerprint="fp", amount=0.2)
    assert first.action == "send"
    db.mark_interrupted()
    assert db.get_attempt("job", "b1")["state"] == "unknown"
    second = decide_batch(db, settings, job_id="job", batch_key="b1", fingerprint="fp", amount=0.2)
    assert second.action == "skip_unknown"
    assert db.job_open_reserve_usd("job") == 0.2
    db.close()


def test_a_budget_stop_leaves_earlier_spend_and_a_failure_can_be_retried(tmp_path):
    settings = _settings(tmp_path)
    db = Database(tmp_path / "secondlook.db")
    sent = decide_batch(db, settings, job_id="job", batch_key="b1", fingerprint="fp1", amount=0.8)
    finish_batch(
        db, settings, job_id="job", batch_key="b1", fingerprint="fp1",
        reservation_id=sent.reservation_id, amount=0.8, outcome="succeeded",
        response_json='{"events":[]}', usage={"input_tokens": 400_000, "output_tokens": 0},
    )
    blocked = decide_batch(db, settings, job_id="job", batch_key="b2", fingerprint="fp2", amount=0.3)
    assert blocked.action == "skip_budget"
    assert db.job_committed_usd("job") > 0

    retry = decide_batch(db, settings, job_id="job2", batch_key="b9", fingerprint="fp9", amount=0.1)
    finish_batch(
        db, settings, job_id="job2", batch_key="b9", fingerprint="fp9",
        reservation_id=retry.reservation_id, amount=0.1, outcome="failed",
    )
    again = decide_batch(db, settings, job_id="job2", batch_key="b9", fingerprint="fp9", amount=0.1)
    assert again.action == "send"
    finish_batch(
        db, settings, job_id="job2", batch_key="b9", fingerprint="fp9",
        reservation_id=again.reservation_id, amount=0.1, outcome="succeeded", response_json="{}",
    )
    cached = decide_batch(db, settings, job_id="other", batch_key="b9", fingerprint="fp9", amount=0.1)
    assert cached.action == "cache"
    db.close()
