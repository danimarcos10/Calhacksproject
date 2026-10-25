import re

from app.providers.base import EvidenceProvider, ProviderCallResult
from app.schemas import (
    EvidenceStatus,
    IdentityStatus,
    Outcome,
    ProviderEvidence,
    ProviderObservation,
)
from app.versions import SCHEMA_VERSION

_FRAME = re.compile(r"frame_id=(f\d+)")
_REVISION = re.compile(r"target_revision=(\d+)")


class SyntheticProvider(EvidenceProvider):
    """Plumbing fixture. It never represents a football observation."""

    label = "synthetic"

    def count_tokens(self, system: str, messages: list[dict]) -> int:
        return 100

    def extract(self, system: str, messages: list[dict]) -> ProviderCallResult:
        text = _text(messages)
        frame_ids: list[str] = []
        for frame_id in _FRAME.findall(text):
            if frame_id not in frame_ids:
                frame_ids.append(frame_id)
        revision = int(_REVISION.search(text).group(1)) if _REVISION.search(text) else 0
        observations: list[ProviderObservation] = []
        if len(frame_ids) >= 2:
            observations.append(
                ProviderObservation(
                    category="carrying_action",
                    start_ms=_time(text, frame_ids[0]),
                    end_ms=max(_time(text, frame_ids[-1]), _time(text, frame_ids[0]) + 1),
                    frame_ids=[frame_ids[0], frame_ids[-1]],
                    visible_action="SYNTHETIC FIXTURE: a coloured box changes position. This is not football analysis.",
                    outcome=Outcome.not_observable,
                    evidence_status=EvidenceStatus.ambiguous,
                    identity_status=IdentityStatus.uncertain,
                    limitations=["Synthetic fixture. No player was observed."],
                )
            )
        parsed = ProviderEvidence(
            schema_version=SCHEMA_VERSION,
            target_revision=revision,
            observations=observations,
            gaps=["Synthetic fixture: nothing here is evidence about a player."],
            no_observation_reason=None if observations else "Synthetic fixture produced no frames.",
        )
        return ProviderCallResult(
            parsed=parsed,
            model="synthetic-fixture",
            usage={"input_tokens": 100, "output_tokens": 40},
            stop_reason="end_turn",
            request_id="synthetic",
            raw={"label": "synthetic-fixture", "not_football_analysis": True},
        )


def _text(messages: list[dict]) -> str:
    parts: list[str] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
    return "\n".join(parts)


def _time(text: str, frame_id: str) -> int:
    match = re.search(rf"frame_id={frame_id} source_t_ms=(\d+)", text)
    return int(match.group(1)) if match else 0
