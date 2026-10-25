from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Box(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def stays_inside(self) -> "Box":
        if self.x + self.w > 1.001 or self.y + self.h > 1.001:
            raise ValueError("box extends outside the frame")
        return self


class AnchorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame_id: str
    state: Literal["box", "not_visible"]
    box: Box | None = None

    @model_validator(mode="after")
    def box_matches_state(self) -> "AnchorIn":
        if self.state == "box" and self.box is None:
            raise ValueError("a box is required when the target is visible")
        if self.state == "not_visible" and self.box is not None:
            raise ValueError("a not-visible frame cannot include a box")
        return self


class SampleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)


class TargetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_id: str
    role: str = Field(default="fullback", max_length=40)
    jersey_note: str = Field(default="", max_length=80)
    team_color_note: str = Field(default="", max_length=80)
    identity_uncertain: bool = False
    anchors: list[AnchorIn] = Field(min_length=1, max_length=24)


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str
    manifest_id: str
    target_revision_id: str


class Category(str, Enum):
    first_touch = "first_touch"
    passing_action = "passing_action"
    carrying_action = "carrying_action"
    defending_action = "defending_action"
    off_ball_movement = "off_ball_movement"


class Outcome(str, Enum):
    completed_visible = "completed_visible"
    unsuccessful_visible = "unsuccessful_visible"
    not_observable = "not_observable"
    not_applicable = "not_applicable"


class EvidenceStatus(str, Enum):
    observable = "observable"
    ambiguous = "ambiguous"
    not_observable = "not_observable"


class IdentityStatus(str, Enum):
    clear_in_cited_frames = "clear_in_cited_frames"
    uncertain = "uncertain"
    not_visible = "not_visible"


class ProviderObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Category
    start_ms: int
    end_ms: int
    frame_ids: list[str] = Field(min_length=1, max_length=8)
    visible_action: str = Field(min_length=1, max_length=400)
    outcome: Outcome
    evidence_status: EvidenceStatus
    identity_status: IdentityStatus
    limitations: list[str] = Field(default_factory=list, max_length=6)


class ResampleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_ms: int
    end_ms: int
    reason: str = Field(min_length=1, max_length=300)


class ProviderEvidence(BaseModel):
    """Schema sent to the model. Server fields are not included."""

    model_config = ConfigDict(extra="forbid")
    schema_version: str
    target_revision: int
    observations: list[ProviderObservation] = Field(default_factory=list, max_length=5)
    gaps: list[str] = Field(default_factory=list, max_length=8)
    resample_request: ResampleRequest | None = None
    no_observation_reason: str | None = Field(default=None, max_length=400)


class FrameOut(BaseModel):
    frame_id: str
    source_t_ms: int
    derivative_t_ms: int
    width: int
    height: int
    url: str


class ManifestOut(BaseModel):
    id: str
    video_id: str
    start_ms: int
    end_ms: int
    sampler_version: str
    frames: list[FrameOut]


class RevisionOut(BaseModel):
    id: str
    video_id: str
    manifest_id: str
    revision: int
    anchors: list[AnchorIn]
    jersey_note: str
    team_color_note: str
    identity_uncertain: bool
    role: str
    created_at: str


class VideoOut(BaseModel):
    id: str
    duration_ms: int
    timeline_ms: int
    width: int
    height: int
    rotation: int
    codec: str
    media_url: str
    rights_note: str
    manifests: list[ManifestOut]
    revisions: list[RevisionOut]


class ObservationOut(BaseModel):
    id: str
    category: str
    start_ms: int
    end_ms: int
    frame_ids: list[str]
    visible_action: str
    outcome: str
    evidence_status: str
    identity_status: str
    limitations: list[str]
    review_status: str
    attribution_hold: bool


class IssueOut(BaseModel):
    code: str
    message: str
    index: int | None = None


class ResampleOut(BaseModel):
    start_ms: int
    end_ms: int
    reason: str
    executed: bool


class UsageOut(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None


class ProvenanceOut(BaseModel):
    model_requested: str
    model_returned: str | None
    prompt_version: str
    schema_version: str
    sampler_version: str
    usage: UsageOut
    cost_usd: float | None
    latency_ms: int | None
    stop_reason: str | None
    request_id: str | None
    provider_label: str
    cache_status: str
    created_at: str


class WindowOut(BaseModel):
    start_ms: int
    end_ms: int


class AnalysisOut(BaseModel):
    id: str
    video_id: str
    target_revision: int | None
    target_revision_id: str
    window: WindowOut | None
    status: str
    observations: list[ObservationOut]
    gaps: list[str]
    validation_issues: list[IssueOut]
    resample_request: ResampleOut | None
    no_observation_reason: str | None
    provenance: ProvenanceOut


class JobErrorOut(BaseModel):
    code: str
    user_message: str
    retryable: bool


class JobTimingsOut(BaseModel):
    created_at: str
    started_at: str | None
    finished_at: str | None


class StageOut(BaseModel):
    stage: str
    at: str


class JobOut(BaseModel):
    id: str
    video_id: str
    status: str
    stage: str
    stage_log: list[StageOut]
    attempts: int
    cache_status: str
    error: JobErrorOut | None
    result_run_id: str | None
    result: AnalysisOut | None
    timings: JobTimingsOut


class ProviderOut(BaseModel):
    mode: str
    configured: bool
    model: str
    reachable: bool
    detail: str


class ReadyOut(BaseModel):
    status: str
    ffmpeg: bool
    data_dir_writable: bool
    provider: ProviderOut


class HealthOut(BaseModel):
    status: str
