"""Temporary in-process worker for M0.

One thread claims queued jobs. M1 should move this to a separate process.
A provider failure is recorded on the job. This module never calls a second provider.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
import time
from pathlib import Path

from app.anchors import present_anchor
from app.annotate import annotated_jpeg
from app.budget import actual_usd, can_reserve, estimate_usd, reconcile, release, reserve
from app.db import Database, new_id, utcnow
from app.evidence import EvidenceRejected, validate
from app.providers.base import EvidenceProvider, ProviderCallResult, ProviderError
from app.versions import PROMPT_VERSION, SAMPLER_VERSION, SCHEMA_VERSION

log = logging.getLogger("secondlook.worker")
PROMPT_TEXT = (Path(__file__).resolve().parent / "prompts" / "evidence_v2.md").read_text(encoding="utf-8")


def fingerprint(
    *,
    video_sha256: str,
    start_ms: int,
    end_ms: int,
    revision_id: str,
    model: str,
) -> str:
    payload = {
        "video_sha256": video_sha256,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "revision_id": revision_id,
        "sampler": SAMPLER_VERSION,
        "model": model,
        "prompt": PROMPT_VERSION,
        "schema": SCHEMA_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def worker_loop(app, stop: threading.Event) -> None:
    db: Database = app.state.db
    while not stop.is_set():
        try:
            job_id = db.claim_next_job()
        except Exception:
            log.exception("could not claim a job")
            stop.wait(0.5)
            continue
        if not job_id:
            stop.wait(0.3)
            continue
        try:
            process_job(app, job_id)
        except Exception:
            log.exception("job %s crashed", job_id)
            try:
                db.finish_job(
                    job_id,
                    status="failed",
                    stage="failed",
                    error_code="internal_error",
                    error_message="Analysis failed unexpectedly. Retry this window.",
                    error_retryable=True,
                )
            except Exception:
                log.exception("could not record the failure for %s", job_id)


def process_job(app, job_id: str) -> None:
    db: Database = app.state.db
    settings = app.state.settings
    provider: EvidenceProvider | None = app.state.provider
    job = db.get_job(job_id)
    if job is None or job["status"] not in ("running", "queued"):
        return
    started = time.monotonic()
    try:
        _deadline(settings, started)
        video = db.get_video(job["video_id"])
        manifest = db.get_manifest(job["manifest_id"])
        revision = db.get_revision(job["target_revision_id"])
        if video is None or manifest is None or revision is None:
            _fail(db, job_id, "missing_input", "The selected clip or target is no longer available.", False)
            return
        latest = db.latest_revision_for_manifest(manifest["id"])
        if latest is None or latest["id"] != revision["id"]:
            _fail(
                db,
                job_id,
                "stale_revision",
                "The target changed before analysis started. Save the target and run it again.",
                True,
            )
            return
        existing = db.find_succeeded_run(job["fingerprint"])
        if existing:
            db.finish_job(
                job_id,
                status="succeeded",
                stage="succeeded",
                result_run_id=existing["id"],
                cache_status="cached",
            )
            return
        if provider is None:
            _fail(
                db,
                job_id,
                "provider_not_configured",
                "Add ANTHROPIC_API_KEY on the server before running analysis. The upload and target are saved.",
                False,
            )
            return

        db.set_stage(job_id, "preparing_frames")
        _deadline(settings, started)
        frames = manifest["frames"]
        anchors = {anchor["frame_id"]: present_anchor(anchor) for anchor in revision["anchors"]}
        job_dir = settings.data_path / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        sent_meta = []
        content: list[dict] = [{"type": "text", "text": _preamble(revision, frames, anchors)}]
        for frame in frames:
            anchor = anchors.get(frame["frame_id"])
            box, kind = _overlay(anchor)
            image_path = _under(settings.data_path, frame["relative"])
            payload = annotated_jpeg(image_path, box, kind)
            digest = hashlib.sha256(payload).hexdigest()
            (job_dir / f"{frame['frame_id']}.jpg").write_bytes(payload)
            sent_meta.append(
                {
                    "frame_id": frame["frame_id"],
                    "source_t_ms": frame["source_t_ms"],
                    "sent_sha256": digest,
                    "anchor": anchor,
                }
            )
            content.append(
                {
                    "type": "text",
                    "text": f"frame_id={frame['frame_id']} source_t_ms={frame['source_t_ms']}",
                }
            )
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64.b64encode(payload).decode("ascii"),
                    },
                }
            )
        _write_json(
            job_dir / "input.json",
            {
                "prompt_version": PROMPT_VERSION,
                "schema_version": SCHEMA_VERSION,
                "sampler_version": SAMPLER_VERSION,
                "model": _model_name(settings, provider),
                "target_revision_id": revision["id"],
                "frames": sent_meta,
            },
        )
        messages = [{"role": "user", "content": content}]

        db.set_stage(job_id, "estimating_cost")
        _deadline(settings, started)
        input_tokens = _count_tokens(provider, PROMPT_TEXT, messages)
        estimate = estimate_usd(settings, input_tokens)
        blocked = can_reserve(db, settings, job_id, estimate)
        if blocked:
            _fail(db, job_id, "budget_exceeded", blocked, False)
            return

        db.set_stage(job_id, "analyzing")
        result, cost = _extract(db, settings, provider, job_id, PROMPT_TEXT, messages, estimate, input_tokens, started)
        _write_json(job_dir / "response.json", result.raw)

        db.set_stage(job_id, "validating_evidence")
        _deadline(settings, started)
        latest = db.latest_revision_for_manifest(manifest["id"])
        if latest is None or latest["id"] != revision["id"]:
            failed_run = _record_failed_run(db, settings, provider, job, result, cost, "stale_revision")
            _fail(
                db,
                job_id,
                "stale_revision",
                "The target changed while the model was running. This result was discarded.",
                True,
                failed_run,
            )
            return
        try:
            validated = validate(
                result.parsed,
                target_revision=revision["revision"],
                window_start_ms=manifest["start_ms"],
                window_end_ms=manifest["end_ms"],
                frames_by_id={frame["frame_id"]: frame["source_t_ms"] for frame in frames},
                located_ids={frame_id for frame_id, anchor in anchors.items() if anchor.get("state") == "located"},
                uncertain_ids={frame_id for frame_id, anchor in anchors.items() if anchor.get("state") == "uncertain"},
                not_visible_ids={
                    frame_id for frame_id, anchor in anchors.items() if anchor.get("state") == "not_visible"
                },
            )
        except EvidenceRejected as exc:
            failed_run = _record_failed_run(db, settings, provider, job, result, cost, exc.code)
            _fail(db, job_id, exc.code, exc.user_message, True, failed_run)
            return

        latency_ms = int((time.monotonic() - started) * 1000)
        run_id = new_id("run")
        now = utcnow()
        observations = []
        for item in validated.observations:
            observations.append({**item, "id": new_id("obs"), "run_id": run_id, "created_at": now})
        db.save_succeeded_analysis(
            {
                "id": run_id,
                "video_id": video["id"],
                "manifest_id": manifest["id"],
                "target_revision_id": revision["id"],
                "input_hash": job["fingerprint"],
                "model_requested": _model_name(settings, provider),
                "model_returned": result.model,
                "prompt_version": PROMPT_VERSION,
                "schema_version": SCHEMA_VERSION,
                "sampler_version": SAMPLER_VERSION,
                "status": "succeeded",
                "provider_label": provider.label,
                "usage": result.usage,
                "cost_usd": cost,
                "latency_ms": latency_ms,
                "stop_reason": result.stop_reason,
                "request_id": result.request_id,
                "gaps": validated.gaps,
                "issues": validated.issues,
                "resample": validated.resample,
                "no_observation_reason": validated.no_observation_reason,
                "created_at": now,
            },
            observations,
            job_id,
        )
    except ProviderError as exc:
        _fail(db, job_id, exc.code, exc.user_message, exc.retryable)
    except TimeoutError:
        _fail(db, job_id, "job_timeout", "Analysis took too long and was stopped. Retry this window.", True)


def _extract(db, settings, provider, job_id, system, messages, estimate, input_tokens, started):
    last: ProviderError | None = None
    for attempt in range(1, settings.max_model_calls_per_job + 1):
        _deadline(settings, started)
        db.set_attempts(job_id, attempt)
        blocked = can_reserve(db, settings, job_id, estimate)
        if blocked:
            raise ProviderError("budget_exceeded", blocked)
        reservation_id = reserve(db, job_id, estimate)
        try:
            result = provider.extract(system, messages)
        except ProviderError as exc:
            if exc.billed:
                usage = exc.usage or {"input_tokens": input_tokens, "output_tokens": 0}
                reconcile(db, reservation_id, job_id, actual_usd(settings, usage) or estimate, usage)
            else:
                release(db, reservation_id, job_id, estimate)
            last = exc
            if exc.retryable and attempt < settings.max_model_calls_per_job:
                time.sleep(min(2.0, exc.retry_after if exc.retry_after is not None else 1.0))
                continue
            raise
        cost = actual_usd(settings, result.usage)
        reconcile(db, reservation_id, job_id, cost, result.usage)
        return result, cost
    if last:
        raise last
    raise ProviderError("provider_unavailable", "The model request failed. Retry this window.", retryable=True)


def _count_tokens(provider: EvidenceProvider, system: str, messages: list[dict]) -> int:
    last: ProviderError | None = None
    for attempt in range(2):
        try:
            return provider.count_tokens(system, messages)
        except ProviderError as exc:
            last = exc
            if exc.retryable and attempt == 0:
                time.sleep(min(2.0, exc.retry_after if exc.retry_after is not None else 0.5))
                continue
            raise
    if last:
        raise last
    raise ProviderError("provider_unavailable", "The model request failed. Retry this window.", retryable=True)


def _record_failed_run(db, settings, provider, job, result: ProviderCallResult, cost: float, code: str) -> str:
    run_id = new_id("run")
    db.insert_run(
        {
            "id": run_id,
            "video_id": job["video_id"],
            "manifest_id": job["manifest_id"],
            "target_revision_id": job["target_revision_id"],
            "input_hash": job["fingerprint"],
            "model_requested": _model_name(settings, provider),
            "model_returned": result.model,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "sampler_version": SAMPLER_VERSION,
            "status": "failed",
            "provider_label": provider.label,
            "usage": result.usage,
            "cost_usd": cost,
            "latency_ms": None,
            "stop_reason": result.stop_reason,
            "request_id": result.request_id,
            "gaps": [],
            "issues": [{"code": code, "message": "The response was not stored as evidence."}],
            "resample": None,
            "no_observation_reason": None,
            "created_at": utcnow(),
        }
    )
    return run_id


def _fail(
    db: Database,
    job_id: str,
    code: str,
    message: str,
    retryable: bool,
    result_run_id: str | None = None,
) -> None:
    current = db.get_job(job_id)
    if current and current["status"] in ("succeeded", "failed", "interrupted", "cancelled"):
        return
    db.finish_job(
        job_id,
        status="failed",
        stage="failed",
        result_run_id=result_run_id,
        error_code=code,
        error_message=message,
        error_retryable=retryable,
    )


def _deadline(settings, started: float) -> None:
    if time.monotonic() - started > settings.job_deadline_seconds:
        raise TimeoutError


def _model_name(settings, provider: EvidenceProvider) -> str:
    if provider.label == "synthetic":
        return "synthetic-fixture"
    return settings.anthropic_model


def _overlay(anchor: dict | None) -> tuple[dict | None, str]:
    if not anchor or not anchor.get("box"):
        return None, "manual"
    if anchor.get("state") == "located" and anchor.get("source") == "estimated":
        return anchor["box"], "estimated"
    if anchor.get("state") == "uncertain":
        return anchor["box"], "uncertain"
    if anchor.get("state") == "located":
        return anchor["box"], "manual"
    return None, "manual"


def _preamble(revision: dict, frames: list[dict], anchors: dict) -> str:
    role = (revision.get("role") or "").strip() or "unspecified"
    lines = [
        f"schema_version={SCHEMA_VERSION}",
        f"target_revision={revision['revision']}",
        f"role={role}",
        "Jersey and team-colour notes are optional and are not used to identify the player.",
        f"jersey_note={revision['jersey_note'] or 'none'}",
        f"team_color_note={revision['team_color_note'] or 'none'}",
        "Refer to the person as the selected player. A name or shirt number is not required.",
        "Frame table:",
    ]
    for frame in frames:
        lines.append(f"frame_id={frame['frame_id']} source_t_ms={frame['source_t_ms']}")
    lines.append("Anchor states:")
    for frame in frames:
        anchor = anchors.get(frame["frame_id"])
        lines.append(f"{frame['frame_id']}: {_anchor_line(anchor)}")
    lines.append("A frame that is not annotated has no location. Do not treat it as target not visible.")
    return "\n".join(lines)


def _anchor_line(anchor: dict | None) -> str:
    if not anchor:
        return "not annotated"
    state = anchor.get("state")
    box = anchor.get("box") or {}
    box_text = f"x={box.get('x')} y={box.get('y')} w={box.get('w')} h={box.get('h')}"
    if state == "not_visible":
        return "not visible (explicit)"
    if state == "uncertain":
        reason = anchor.get("reason") or "needs a check"
        return f"location uncertain ({reason})" + (f", box {box_text}" if anchor.get("box") else "")
    if state == "located" and anchor.get("source") == "estimated":
        method = anchor.get("method") or "software"
        return f"located, software estimate, unverified, method={method}, box {box_text}"
    if state == "located":
        return f"located, manual selection, box {box_text}"
    return "not annotated"


def _under(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if root.resolve() not in path.parents and path != root.resolve():
        raise ProviderError("missing_input", "A sampled frame could not be read.", retryable=False)
    return path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)
