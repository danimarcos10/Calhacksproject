"""Create analysis jobs. Shared by the HTTP route and the Convex worker bridge.

A repeated request returns the job it already created, an active job with the same
inputs, or a cached successful run. None of those paths starts a second model call.
"""

from __future__ import annotations

import sqlite3

from app.config import Settings
from app.db import Database, new_id, utcnow
from app.worker import fingerprint


def model_name(settings: Settings) -> str:
    return "synthetic-fixture" if settings.evidence_provider.strip().lower() == "synthetic" else settings.anthropic_model


def enqueue_analysis(
    db: Database,
    settings: Settings,
    video: dict,
    manifest: dict,
    revision: dict,
    key: str | None,
) -> dict:
    if key:
        existing = db.job_by_idempotency(key)
        if existing:
            return existing
    digest = fingerprint(
        video_sha256=video["sha256"],
        start_ms=manifest["start_ms"],
        end_ms=manifest["end_ms"],
        revision_id=revision["id"],
        model=model_name(settings),
    )
    active = db.active_job_for_fingerprint(digest)
    if active:
        return active
    cached = db.find_succeeded_run(digest)
    now = utcnow()
    job_id = new_id("job")
    row = {
        "id": job_id,
        "video_id": video["id"],
        "manifest_id": manifest["id"],
        "target_revision_id": revision["id"],
        "status": "succeeded" if cached else "queued",
        "stage": "succeeded" if cached else "queued",
        "attempts": 0,
        "error_code": None,
        "error_message": None,
        "error_retryable": None,
        "result_run_id": cached["id"] if cached else None,
        "idempotency_key": key or None,
        "fingerprint": digest,
        "cache_status": "cached" if cached else "live",
        "stage_log": [{"stage": "succeeded" if cached else "queued", "at": now}],
        "created_at": now,
        "started_at": now if cached else None,
        "finished_at": now if cached else None,
    }
    try:
        db.insert_job(row)
    except sqlite3.IntegrityError:
        if key:
            existing = db.job_by_idempotency(key)
            if existing:
                return existing
        raise
    return db.get_job(job_id)
