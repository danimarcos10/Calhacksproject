import pytest
from pydantic import ValidationError

from app.evidence import EvidenceRejected, validate
from app.schemas import ProviderEvidence, ProviderObservation


def _report(**overrides) -> ProviderEvidence:
    observation = {
        "category": "passing_action",
        "start_ms": 1000,
        "end_ms": 2500,
        "frame_ids": ["f01", "f02"],
        "visible_action": "The target plays the ball toward a teammate.",
        "outcome": "not_observable",
        "evidence_status": "ambiguous",
        "identity_status": "clear_in_cited_frames",
        "limitations": ["The recipient is out of frame."],
    }
    observation.update(overrides.pop("observation", {}))
    body = {
        "schema_version": "1.0",
        "target_revision": 2,
        "observations": [observation],
        "gaps": [],
        "resample_request": None,
        "no_observation_reason": None,
    }
    body.update(overrides)
    return ProviderEvidence.model_validate(body)


def _validate(report: ProviderEvidence, **overrides):
    context = dict(
        target_revision=2,
        window_start_ms=0,
        window_end_ms=8000,
        frames_by_id={"f01": 1000, "f02": 2500},
        not_visible_ids=set(),
        identity_uncertain=False,
    )
    context.update(overrides)
    return validate(report, **context)


def test_zero_observations_are_valid():
    report = ProviderEvidence.model_validate(
        {
            "schema_version": "1.0",
            "target_revision": 2,
            "observations": [],
            "gaps": ["No ball is visible."],
            "no_observation_reason": "The target is in frame but no action is supported.",
        }
    )
    result = _validate(report)
    assert result.observations == []
    assert result.gaps == ["No ball is visible."]


def test_unknown_frame_is_dropped_not_clamped():
    result = _validate(_report(observation={"frame_ids": ["f99"]}))
    assert result.observations == []
    assert result.issues[0]["code"] == "unknown_frame"


def test_interval_outside_window_is_rejected():
    result = _validate(_report(observation={"start_ms": 7000, "end_ms": 9000}))
    assert result.observations == []
    assert result.issues[0]["code"] == "out_of_window"


def test_revision_mismatch_rejects_the_response():
    with pytest.raises(EvidenceRejected) as caught:
        _validate(_report(target_revision=9))
    assert caught.value.code == "revision_mismatch"


def test_extra_field_and_bad_enum_fail_schema():
    with pytest.raises(ValidationError):
        ProviderEvidence.model_validate(
            {
                "schema_version": "1.0",
                "target_revision": 1,
                "observations": [],
                "gaps": [],
                "scholarship_odds": 0.2,
            }
        )
    with pytest.raises(ValidationError):
        ProviderObservation.model_validate(
            {
                "category": "elite_passing",
                "start_ms": 0,
                "end_ms": 1,
                "frame_ids": ["f01"],
                "visible_action": "A pass.",
                "outcome": "not_observable",
                "evidence_status": "ambiguous",
                "identity_status": "uncertain",
            }
        )


def test_trait_language_is_dropped():
    result = _validate(_report(observation={"visible_action": "The target shows excellent football IQ."}))
    assert result.observations == []
    assert result.issues[0]["code"] == "trait_language"


def test_visible_outcome_without_support_is_downgraded():
    result = _validate(
        _report(observation={"outcome": "completed_visible", "evidence_status": "ambiguous"})
    )
    assert result.observations[0]["outcome"] == "not_observable"
    assert result.observations[0]["review_status"] == "candidate"
    assert "cleared" in result.observations[0]["limitations"][-1]


def test_uncertain_identity_holds_attribution():
    result = _validate(_report(), identity_uncertain=True)
    assert result.observations[0]["attribution_hold"] is True


def test_clear_supported_observation_is_kept():
    result = _validate(
        _report(
            observation={
                "outcome": "completed_visible",
                "evidence_status": "observable",
                "identity_status": "clear_in_cited_frames",
            }
        )
    )
    assert result.observations[0]["outcome"] == "completed_visible"
    assert result.observations[0]["attribution_hold"] is False
