"""Checks for a scouting-model response. Drops what the frames cannot support."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas import ScoutReport
from app.scout.discover import Event
from app.versions import SCOUT_SCHEMA_VERSION

_TRAIT = re.compile(
    r"football iq|ability rating|talent score|overall ability|world[- ]class|scholarship|"
    r"high potential|\belite\b|\b\d{1,3}\s*/\s*(?:10|100)\b",
    re.IGNORECASE,
)
_PROXIMITY = re.compile(
    r"\b(?:near|nearby|close to|in the vicinity of) the ball\b|\bball (?:is )?(?:near|nearby|close)\b",
    re.IGNORECASE,
)
_TOUCH = re.compile(
    r"\b(receiv|control|touch|pass|play|carr|dribbl|turn|shoot|clear|lose|dispossess|tackle|head)\w*",
    re.IGNORECASE,
)
_KNOWN_PASS = {"completed", "intercepted", "out_of_play"}


@dataclass
class ScoutValidation:
    events: list[Event] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def validate_scout(
    report: ScoutReport,
    *,
    windows: dict[str, tuple[int, int]],
    frames_by_id: dict[str, int],
) -> ScoutValidation:
    if report.schema_version != SCOUT_SCHEMA_VERSION:
        raise ValueError("schema_version_mismatch")
    result = ScoutValidation()
    for index, item in enumerate(report.events):
        bounds = windows.get(item.candidate_id)
        if bounds is None:
            result.issues.append(f"{index}:unknown_candidate")
            continue
        start, end = bounds
        if item.start_ms >= item.end_ms or item.start_ms < start or item.end_ms > end:
            result.issues.append(f"{index}:out_of_candidate")
            continue
        unknown = [frame_id for frame_id in item.frame_ids if frame_id not in frames_by_id]
        if unknown:
            result.issues.append(f"{index}:unknown_frame")
            continue
        action = _TRAIT.sub("", item.visible_action).strip()
        if not action:
            result.issues.append(f"{index}:empty_action")
            continue
        if _PROXIMITY.search(action) and not _TOUCH.search(action):
            result.issues.append(f"{index}:proximity_only")
            continue
        outcome = item.outcome
        limitations = [part.strip() for part in item.limitations if part.strip()]
        if item.action == "pass" and outcome in _KNOWN_PASS:
            cited = [frames_by_id[frame_id] for frame_id in item.frame_ids]
            if not any(t_ms > item.start_ms for t_ms in cited):
                outcome = "unclear"
                limitations.append("The outcome is unclear: no cited frame shows the ball after it was played.")
        if item.action == "other":
            result.issues.append(f"{index}:other_kept_out")
            continue
        result.events.append(
            Event(
                action=item.action,
                outcome=outcome,
                start_ms=item.start_ms,
                end_ms=item.end_ms,
                frame_ids=tuple(item.frame_ids),
                evidence_status=item.evidence_status,
                visible_action=action,
                identity_status=item.identity_status,
                limitations=tuple(limitations),
            )
        )
    return result
