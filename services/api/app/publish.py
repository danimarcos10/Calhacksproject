"""Versioned analysis records sent from the Python worker to Convex.

These Pydantic models are the contract for what Convex stores as read-only analysis
records. Runs and observations are immutable once published. Convex decides whether a
run is current from the window's revision number, never from the arrival order.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.anchors import present_anchor


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublishedObservation(_Strict):
    key: str
    category: str
    startMs: int
    endMs: int
    seekMs: int
    frameIds: list[str]
    visibleAction: str
    outcome: str
    evidenceStatus: str
    identityStatus: str
    limitations: list[str]
    attributionHold: bool
    holdReason: str | None
    holdFrameId: str | None


class PublishedRun(_Strict):
    key: str
    model: str
    promptVersion: str
    schemaVersion: str
    providerLabel: str
    costUsd: float | None
    inputTokens: int | None
    outputTokens: int | None
    latencyMs: int | None
    gaps: list[str]
    issues: list[str]
    noObservationReason: str | None
    createdAt: str


class PublishedAnchor(_Strict):
    frameId: str
    state: str
    source: str | None = None
    box: dict | None = None
    method: str | None = None
    reason: str | None = None
    explicit: bool | None = None


class WindowSpend(_Strict):
    reconciledUsd: float
    liveCalls: int
    syntheticCalls: int
    unknownUsageAttempts: int
    failedJobs: int
    cachedReuses: int


def run_payload(run: dict) -> dict:
    usage = run.get("usage") or {}
    issues = [item.get("message", str(item)) if isinstance(item, dict) else str(item) for item in run.get("issues") or []]
    return PublishedRun(
        key=run["id"],
        model=run.get("model_returned") or run["model_requested"],
        promptVersion=run["prompt_version"],
        schemaVersion=run["schema_version"],
        providerLabel=run["provider_label"],
        costUsd=run.get("cost_usd"),
        inputTokens=usage.get("input_tokens"),
        outputTokens=usage.get("output_tokens"),
        latencyMs=run.get("latency_ms"),
        gaps=list(run.get("gaps") or []),
        issues=issues,
        noObservationReason=run.get("no_observation_reason"),
        createdAt=run["created_at"],
    ).model_dump()


def observation_payloads(observations: list[dict]) -> list[dict]:
    return [
        PublishedObservation(
            key=item["id"],
            category=item["category"],
            startMs=item["start_ms"],
            endMs=item["end_ms"],
            seekMs=item.get("seek_ms", item["start_ms"]),
            frameIds=list(item["frame_ids"]),
            visibleAction=item["visible_action"],
            outcome=item["outcome"],
            evidenceStatus=item["evidence_status"],
            identityStatus=item["identity_status"],
            limitations=list(item["limitations"]),
            attributionHold=bool(item["attribution_hold"]),
            holdReason=item.get("hold_reason") or None,
            holdFrameId=item.get("hold_frame_id"),
        ).model_dump()
        for item in observations
    ]


def anchor_to_convex(anchor: dict) -> dict:
    shown = present_anchor(anchor)
    body = PublishedAnchor(
        frameId=shown["frame_id"],
        state=shown["state"],
        source=shown.get("source"),
        box=shown.get("box"),
        method=shown.get("method"),
        reason=shown.get("reason"),
        explicit=shown.get("explicit"),
    ).model_dump()
    return {key: value for key, value in body.items() if value is not None}


def anchor_from_convex(anchor: dict) -> dict:
    return {
        "frame_id": anchor["frameId"],
        "state": anchor["state"],
        "source": anchor.get("source"),
        "box": anchor.get("box"),
        "method": anchor.get("method"),
        "reason": anchor.get("reason"),
        "explicit": bool(anchor.get("explicit", False)),
    }


def spend_payload(spend: dict) -> dict:
    return WindowSpend(
        reconciledUsd=spend["reconciled_usd"],
        liveCalls=spend["live_calls"],
        syntheticCalls=spend["synthetic_calls"],
        unknownUsageAttempts=spend["unknown_usage_attempts"],
        failedJobs=spend["failed_jobs"],
        cachedReuses=spend["cached_reuses"],
    ).model_dump()
