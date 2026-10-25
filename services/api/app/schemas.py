import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class ScoutStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t_ms: int = Field(ge=0)
    box: Box
    player_name: str = Field(min_length=1, max_length=80)


class MarkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t_ms: int = Field(ge=0)
    box: Box


class ScoutClipIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str
    t_ms: int = Field(ge=0)
    box: Box
    marks: list[MarkIn] = Field(default_factory=list, max_length=24)


class ScoutBatchIn(BaseModel):
    """One player, several clips. Each clip is clicked on the picture."""

    model_config = ConfigDict(extra="forbid")
    player_name: str = Field(min_length=1, max_length=80)
    clips: list[ScoutClipIn] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def one_row_per_clip(self) -> "ScoutBatchIn":
        ids = [clip.video_id for clip in self.clips]
        if len(set(ids)) != len(ids):
            raise ValueError("Each clip can be included once.")
        return self


class FindPlayerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=3, max_length=200)


class FindPlayerOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    found: bool
    t_ms: int = 0
    track_id: int | None = None
    box: Box | None = None
    message: str


class StickIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t_ms: int = Field(ge=0)
    box: Box


class StickFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t: int
    box: Box


class StickOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frames: list[StickFrame]
    message: str


class AnchorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame_id: str
    state: Literal["located", "not_visible", "uncertain"]
    source: Literal["manual", "estimated"] | None = None
    box: Box | None = None
    method: str | None = Field(default=None, max_length=40)
    reason: str | None = Field(default=None, max_length=200)
    explicit: bool = False

    @model_validator(mode="after")
    def box_matches_state(self) -> "AnchorIn":
        if self.state == "located":
            if self.box is None:
                raise ValueError("a box is required when the target is located")
            if self.source is None:
                self.source = "manual"
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
    role: str = Field(default="", max_length=40)
    jersey_note: str = Field(default="", max_length=80)
    team_color_note: str = Field(default="", max_length=80)
    note: str = Field(default="", max_length=400)
    anchors: list[AnchorIn] = Field(min_length=1, max_length=24)


class ProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_id: str
    anchors: list[AnchorIn] = Field(min_length=1, max_length=24)


class ProposalOut(BaseModel):
    anchors: list[AnchorIn]


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


class ContinuityIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame_id: str
    reason: str = Field(min_length=1, max_length=200)


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
    continuity_issues: list[ContinuityIssue] = Field(default_factory=list, max_length=8)


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


class ScoutAction(str, Enum):
    receive = "receive"
    pass_ = "pass"
    carry = "carry"
    loss = "loss"
    other = "other"


class ScoutOutcome(str, Enum):
    completed = "completed"
    intercepted = "intercepted"
    out_of_play = "out_of_play"
    controlled = "controlled"
    miscontrolled = "miscontrolled"
    retained = "retained"
    lost = "lost"
    unclear = "unclear"


class ScoutEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    action: ScoutAction
    outcome: ScoutOutcome
    start_ms: int
    end_ms: int
    frame_ids: list[str] = Field(min_length=1, max_length=8)
    visible_action: str = Field(min_length=1, max_length=400)
    evidence_status: EvidenceStatus
    identity_status: IdentityStatus
    limitations: list[str] = Field(default_factory=list, max_length=6)
    direction: str | None = Field(default=None, max_length=40)
    length: str | None = Field(default=None, max_length=40)
    touches: int | None = None
    under_pressure: bool | None = None


class ScoutReport(BaseModel):
    """Schema for one batch of candidate involvements. No scores and no rankings."""

    model_config = ConfigDict(extra="forbid")
    schema_version: str
    events: list[ScoutEventIn] = Field(default_factory=list, max_length=12)


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
    note: str
    needs_review: list[str]
    created_at: str


class TrackingOut(BaseModel):
    state: str
    done: int = 0
    total: int = 0


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
    tracking: TrackingOut | None = None


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
    continuity_issues: list[ContinuityIssue]
    seek_ms: int
    review_status: str
    attribution_hold: bool
    hold_reason: str
    hold_frame_id: str | None = None


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


STATES = (
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "District of Columbia", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois",
    "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts",
    "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
    "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin",
    "Wyoming",
)
League = Literal["mls_next", "ecnl", "ecnl_rl", "npl", "usys", "high_school", "club"]
EMAIL_ADDRESS = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _state(value: str) -> str:
    cleaned = " ".join(value.split())
    if cleaned not in STATES:
        raise ValueError("Choose a US state.")
    return cleaned


def _email(value: str) -> str:
    cleaned = value.strip()
    if not EMAIL_ADDRESS.fullmatch(cleaned):
        raise ValueError("Enter an email address.")
    return cleaned


class ClipStats(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tracked_s: float = Field(ge=0, le=2000)
    receives: int = Field(ge=0, le=200)
    passes_completed: int = Field(ge=0, le=200)
    passes_attempted: int = Field(ge=0, le=200)
    carries: int = Field(ge=0, le=200)
    losses: int = Field(ge=0, le=200)
    reviewed: bool
    clips: int = Field(default=1, ge=1, le=6)
    confidence: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def passes_fit(self) -> "ClipStats":
        if self.passes_completed > self.passes_attempted:
            raise ValueError("Completed passes cannot exceed attempted passes.")
        return self


class ProgramsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str
    league: League

    @field_validator("state")
    @classmethod
    def known_state(cls, value: str) -> str:
        return _state(value)


class ProgramOut(BaseModel):
    school: str
    short_name: str
    city: str
    state: str
    conference: str
    division: Literal["d1", "d2"]
    fit: Literal["fit", "possible", "reach"]
    fit_reason: str


class ProgramsOut(BaseModel):
    programs: list[ProgramOut]
    divisions: list[Literal["d1", "d2"]]
    rule: str
    note: str
    run_ids: list[str]
    actors: list[str]
    cache_status: Literal["live", "cached"]
    retrieved_at: str
    message: str | None = None


class OpportunityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    player_name: str = Field(default="", max_length=80)
    player_email: str = Field(max_length=120)
    position: str = Field(min_length=1, max_length=40)
    grad_year: int = Field(ge=2024, le=2035)
    state: str
    league: League
    clip_url: str = Field(default="", max_length=300)
    schools: list[str] = Field(min_length=1, max_length=5)
    stats: ClipStats
    profile: str = Field(default="", max_length=600)

    @field_validator("state")
    @classmethod
    def known_state(cls, value: str) -> str:
        return _state(value)

    @field_validator("player_email")
    @classmethod
    def email_shape(cls, value: str) -> str:
        return _email(value)

    @field_validator("clip_url")
    @classmethod
    def clip_link(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned and not cleaned.startswith("https://"):
            raise ValueError("The clip link has to start with https://.")
        return cleaned

    @field_validator("schools")
    @classmethod
    def unique_schools(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            name = " ".join(item.split())
            if not name or name in seen:
                continue
            if len(name) > 160:
                raise ValueError("A school name is too long.")
            seen.add(name)
            cleaned.append(name)
        if not cleaned:
            raise ValueError("Choose a school.")
        return cleaned


class CoachCardOut(BaseModel):
    school: str
    division: Literal["d1", "d2"]
    conference: str
    coach_name: str | None
    title: str | None
    email: str | None
    phone: str | None
    url: str | None
    subject: str
    draft: str


class OpportunityOut(BaseModel):
    result_id: str
    review_id: str
    player_email: str
    cards: list[CoachCardOut]
    summary: str
    stats_table: str
    rule: str
    run_ids: list[str]
    actors: list[str]
    cache_status: Literal["live", "cached"]
    retrieved_at: str
    message: str | None = None


class SendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_id: str = Field(pattern=r"^out_[0-9a-f]{16}$")
    email: str = Field(max_length=120)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)
    reply_to: str = Field(max_length=120)

    @field_validator("email", "reply_to")
    @classmethod
    def email_shape(cls, value: str) -> str:
        return _email(value)


class SendOut(BaseModel):
    sent_to: str
    test_mode: bool
    message: str


class ReachIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: str = Field(min_length=1, max_length=40)
    grad_year: int = Field(ge=2024, le=2035)
    state: str
    league: League
    school: str = Field(min_length=1, max_length=160)
    stats: ClipStats
    profile: str = Field(default="", max_length=600)

    @field_validator("state")
    @classmethod
    def known_state(cls, value: str) -> str:
        return _state(value)

    @field_validator("school")
    @classmethod
    def school_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Choose a school.")
        return cleaned


class ReachStepOut(BaseModel):
    title: str
    detail: str
    cost: Literal["free", "low cost"]


class ReachOut(BaseModel):
    school: str
    division: Literal["d1", "d2"]
    conference: str
    reason: str
    read: str
    steps: list[ReachStepOut]
    source: Literal["claude", "standard"]
