"""One model batch: cache, a single send, and no automatic repeat after an unknown outcome."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.budget import can_reserve, reconcile, release, reserve
from app.config import Settings
from app.db import Database


@dataclass(frozen=True)
class BatchDecision:
    action: str
    reservation_id: str | None = None
    response_json: str | None = None
    reason: str = ""


def decide_batch(
    db: Database,
    settings: Settings,
    *,
    job_id: str,
    batch_key: str,
    fingerprint: str,
    amount: float,
) -> BatchDecision:
    cached = db.get_scout_cache(fingerprint)
    if cached is not None:
        return BatchDecision("cache", response_json=cached)
    unknown = db.query_one(
        "SELECT id FROM model_attempts WHERE fingerprint=? AND state='unknown' LIMIT 1",
        (fingerprint,),
    )
    if unknown:
        return BatchDecision("skip_unknown", reason="An earlier call for these frames has no stored result, so it is not sent again.")
    existing = db.get_attempt(job_id, batch_key)
    if existing and existing["state"] == "unknown":
        return BatchDecision("skip_unknown", reason="An earlier call for this batch has no stored result, so it is not sent again.")
    if existing and existing["state"] == "succeeded" and existing["response_json"]:
        return BatchDecision("cache", response_json=existing["response_json"])
    tries = int(existing["tries"]) if existing else 0
    if tries >= 2:
        return BatchDecision("skip_failed", reason="This batch already failed twice.")
    job_spent = db.job_committed_usd(job_id) + db.job_open_reserve_usd(job_id)
    if job_spent + amount > settings.job_budget_usd + 1e-9:
        return BatchDecision("skip_budget", reason="The analysis cost limit was reached.")
    blocked = can_reserve(db, settings, job_id, amount)
    if blocked:
        return BatchDecision("skip_budget", reason=blocked)
    reservation_id = reserve(db, job_id, amount)
    db.upsert_attempt(
        job_id=job_id,
        batch_key=batch_key,
        state="sent",
        reservation_id=reservation_id,
        fingerprint=fingerprint,
        tries=tries + 1,
    )
    return BatchDecision("send", reservation_id=reservation_id)


def finish_batch(
    db: Database,
    settings: Settings,
    *,
    job_id: str,
    batch_key: str,
    fingerprint: str,
    reservation_id: str,
    amount: float,
    outcome: str,
    response_json: str | None = None,
    usage: dict | None = None,
) -> None:
    """outcome is succeeded, failed, or unknown. unknown keeps the reservation."""
    if outcome == "succeeded" and response_json is not None:
        spent = amount
        if usage:
            from app.budget import actual_usd

            spent = actual_usd(settings, usage)
        reconcile(db, reservation_id, job_id, spent, usage or {})
        db.put_scout_cache(fingerprint, response_json)
        db.upsert_attempt(
            job_id=job_id,
            batch_key=batch_key,
            state="succeeded",
            reservation_id=reservation_id,
            fingerprint=fingerprint,
            response_json=response_json,
        )
        return
    if outcome == "failed":
        release(db, reservation_id, job_id, amount)
        db.upsert_attempt(
            job_id=job_id,
            batch_key=batch_key,
            state="failed",
            reservation_id=reservation_id,
            fingerprint=fingerprint,
        )
        return
    db.upsert_attempt(
        job_id=job_id,
        batch_key=batch_key,
        state="unknown",
        reservation_id=reservation_id,
        fingerprint=fingerprint,
        response_json=json.dumps({"usage": usage}) if usage else None,
    )
