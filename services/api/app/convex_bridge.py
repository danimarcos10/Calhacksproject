"""Outbound worker connection to Convex.

Convex owns the analysis queue and the review state. This thread connects out to
Convex with the worker secret, claims one queued window at a time, runs it through the
existing SQLite job pipeline, and publishes progress and the versioned result. Nothing
in Convex calls this machine.

A claim that is retried after a crash creates a new SQLite job, but the fingerprint
cache and the active-job check return the stored result instead of a second model call.
"""

from __future__ import annotations

import logging
import threading

from app.db import Database, utcnow
from app.jobs import enqueue_analysis
from app.publish import anchor_from_convex, observation_payloads, run_payload, spend_payload

log = logging.getLogger("secondlook.convex")
TERMINAL = {"succeeded", "failed", "interrupted", "cancelled"}


def make_client(url: str):
    from convex import ConvexClient

    return ConvexClient(url)


def bridge_loop(app, stop: threading.Event) -> None:
    settings = app.state.settings
    try:
        client = make_client(settings.convex_url)
    except Exception as exc:
        log.error("convex client unavailable type=%s", type(exc).__name__)
        return
    log.info("convex worker connected worker_id=%s", settings.convex_worker_id)
    while not stop.is_set():
        try:
            claim = client.mutation(
                "worker:claimNext",
                {"secret": settings.convex_worker_secret, "workerId": settings.convex_worker_id},
            )
        except Exception as exc:
            log.warning("convex claim failed type=%s", type(exc).__name__)
            stop.wait(5)
            continue
        if not claim:
            stop.wait(settings.convex_poll_seconds)
            continue
        try:
            handle_claim(app, client, claim, stop)
        except Exception:
            log.exception("convex request %s crashed", claim.get("requestId"))
            _call(
                client,
                "worker:failRequest",
                {
                    "secret": settings.convex_worker_secret,
                    "requestId": claim["requestId"],
                    "errorCode": "internal_error",
                    "errorMessage": "Analysis failed unexpectedly on the worker. Queue the window again.",
                    "retryable": True,
                },
            )


def ensure_revision(db: Database, manifest: dict, revision: dict) -> dict:
    existing = db.get_revision(revision["key"])
    if existing:
        if existing["manifest_id"] != manifest["id"]:
            raise RuntimeError("revision belongs to another window")
        return existing
    with db.transaction():
        db.insert_revision(
            {
                "id": revision["key"],
                "video_id": manifest["video_id"],
                "manifest_id": manifest["id"],
                "revision": db.next_revision_number(manifest["video_id"]),
                "anchors": [anchor_from_convex(anchor) for anchor in revision["anchors"]],
                "jersey_note": revision.get("jerseyNote") or "",
                "team_color_note": revision.get("teamColorNote") or "",
                "identity_uncertain": False,
                "role": "",
                "note": revision.get("note") or "",
                "created_at": utcnow(),
            }
        )
    return db.get_revision(revision["key"])


def handle_claim(app, client, claim: dict, stop: threading.Event) -> None:
    db: Database = app.state.db
    settings = app.state.settings
    secret = settings.convex_worker_secret
    request_id = claim["requestId"]
    window = claim["window"]

    def fail(code: str, message: str, retryable: bool, job_key: str | None = None) -> None:
        body = {"secret": secret, "requestId": request_id, "errorCode": code, "errorMessage": message, "retryable": retryable}
        if job_key:
            body["jobKey"] = job_key
        _call(client, "worker:failRequest", body)

    video = db.get_video(window["videoKey"])
    manifest = db.get_manifest(window["manifestKey"])
    if video is None or manifest is None or manifest["video_id"] != video["id"]:
        fail("missing_input", "The clip or window is not on this worker.", False)
        return
    if settings.evidence_provider.strip().lower() == "anthropic" and not settings.anthropic_api_key.strip():
        fail("provider_not_configured", "Add ANTHROPIC_API_KEY on the worker before running analysis.", False)
        return
    revision = ensure_revision(db, manifest, claim["revision"])
    job = enqueue_analysis(db, settings, video, manifest, revision, f"cvx:{request_id}:{claim['attempt']}")
    last_stage = None
    while job["status"] not in TERMINAL:
        if job["stage"] != last_stage:
            last_stage = job["stage"]
            _call(client, "worker:progress", {"secret": secret, "requestId": request_id, "stage": last_stage, "jobKey": job["id"]})
        if stop.wait(0.5):
            return
        job = db.get_job(job["id"])

    _call(
        client,
        "worker:setWindowCost",
        {"secret": secret, "manifestKey": manifest["id"], **spend_payload(db.manifest_spend(manifest["id"]))},
    )
    if job["status"] == "succeeded" and job["result_run_id"]:
        run = db.get_run(job["result_run_id"])
        client.mutation(
            "worker:publishResult",
            {
                "secret": secret,
                "requestId": request_id,
                "jobKey": job["id"],
                "cacheStatus": job["cache_status"],
                "run": run_payload(run),
                "observations": observation_payloads(db.observations_for_run(run["id"])),
            },
        )
        return
    fail(
        job.get("error_code") or job["status"],
        job.get("error_message") or "Analysis did not finish.",
        bool(job.get("error_retryable")),
        job["id"],
    )


def _call(client, name: str, args: dict):
    try:
        return client.mutation(name, args)
    except Exception as exc:
        log.warning("convex call %s failed type=%s", name, type(exc).__name__)
        return None
