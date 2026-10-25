"""Semantic checks for a model evidence packet.

Schema-valid output can still cite a frame we never sent or a time outside
the window. Those observations are dropped. A wrong target revision rejects
the whole response. Nothing here invents a replacement claim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas import EvidenceStatus, IdentityStatus, Outcome, ProviderEvidence
from app.versions import SCHEMA_VERSION

_TRAIT = re.compile(
    r"football iq|ability rating|talent score|overall ability|world[- ]class|scholarship|"
    r"high potential|\belite\b|\b\d{1,3}\s*/\s*(?:10|100)\b",
    re.IGNORECASE,
)


@dataclass
class ValidatedEvidence:
    observations: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    resample: dict | None = None
    no_observation_reason: str | None = None


class EvidenceRejected(Exception):
    def __init__(self, code: str, user_message: str) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message


def validate(
    report: ProviderEvidence,
    *,
    target_revision: int,
    window_start_ms: int,
    window_end_ms: int,
    frames_by_id: dict[str, int],
    not_visible_ids: set[str],
    identity_uncertain: bool,
) -> ValidatedEvidence:
    if report.schema_version != SCHEMA_VERSION:
        raise EvidenceRejected(
            "schema_version_mismatch",
            "The model returned an unsupported evidence schema. Retry this window.",
        )
    if report.target_revision != target_revision:
        raise EvidenceRejected(
            "revision_mismatch",
            "The model response did not match the selected target. Retry this window.",
        )

    result = ValidatedEvidence(
        gaps=[gap.strip() for gap in report.gaps if gap.strip()],
        no_observation_reason=(report.no_observation_reason or "").strip() or None,
    )
    if report.resample_request is not None:
        resample = report.resample_request
        narrow = 0 < resample.end_ms - resample.start_ms <= (window_end_ms - window_start_ms)
        inside = window_start_ms <= resample.start_ms and resample.end_ms <= window_end_ms
        if narrow and inside and resample.reason.strip():
            result.resample = {
                "start_ms": resample.start_ms,
                "end_ms": resample.end_ms,
                "reason": resample.reason.strip(),
                "executed": False,
            }
        else:
            result.issues.append(
                {
                    "code": "resample_rejected",
                    "message": "A resample request fell outside the selected window and was ignored.",
                }
            )

    for index, observation in enumerate(report.observations):
        action = observation.visible_action.strip()
        if observation.start_ms >= observation.end_ms:
            result.issues.append({"index": index, "code": "bad_interval", "message": "The time range was empty."})
            continue
        if observation.start_ms < window_start_ms or observation.end_ms > window_end_ms:
            result.issues.append(
                {
                    "index": index,
                    "code": "out_of_window",
                    "message": "The time range is outside the analyzed window and was not clamped into it.",
                }
            )
            continue
        unknown = [frame_id for frame_id in observation.frame_ids if frame_id not in frames_by_id]
        if unknown:
            result.issues.append(
                {
                    "index": index,
                    "code": "unknown_frame",
                    "message": "The observation cited a frame that was not sent.",
                }
            )
            continue
        cited_inside = [
            frame_id
            for frame_id in observation.frame_ids
            if observation.start_ms <= frames_by_id[frame_id] <= observation.end_ms
        ]
        if not cited_inside:
            result.issues.append(
                {
                    "index": index,
                    "code": "frame_outside_interval",
                    "message": "None of the cited frames fall inside the observation interval.",
                }
            )
            continue
        if _TRAIT.search(action):
            result.issues.append(
                {
                    "index": index,
                    "code": "trait_language",
                    "message": "The wording claimed ability, odds, or a rating, so the observation was dropped.",
                }
            )
            continue

        outcome = observation.outcome
        limitations = [item.strip() for item in observation.limitations if item.strip()]
        visible_outcome = outcome in (Outcome.completed_visible, Outcome.unsuccessful_visible)
        supported = (
            observation.evidence_status == EvidenceStatus.observable
            and observation.identity_status == IdentityStatus.clear_in_cited_frames
        )
        if visible_outcome and not supported:
            outcome = Outcome.not_observable
            limitations.append(
                "The model marked an outcome as visible without a clearly attributed view, so the outcome was cleared."
            )
        every_cited_hidden = all(frame_id in not_visible_ids for frame_id in observation.frame_ids)
        hold = (
            identity_uncertain
            or observation.identity_status != IdentityStatus.clear_in_cited_frames
            or every_cited_hidden
        )
        result.observations.append(
            {
                "category": observation.category.value,
                "start_ms": observation.start_ms,
                "end_ms": observation.end_ms,
                "frame_ids": list(observation.frame_ids),
                "visible_action": action,
                "outcome": outcome.value,
                "evidence_status": observation.evidence_status.value,
                "identity_status": observation.identity_status.value,
                "limitations": limitations[:6],
                "review_status": "candidate",
                "attribution_hold": hold,
            }
        )
    return result
