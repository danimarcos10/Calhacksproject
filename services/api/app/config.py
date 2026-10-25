from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    data_dir: str = "./data"
    database_url: str = "sqlite:///./data/secondlook.db"
    app_origin: str = "http://localhost:3000"
    api_origin: str = "http://localhost:8000"
    max_upload_mb: int = 400
    max_video_seconds: int = 90
    scout_max_video_seconds: int = 330
    scout_max_clips: int = 6
    min_video_seconds: int = 6
    max_window_seconds: int = 8
    min_window_seconds: int = 6
    max_frames_per_call: int = 24
    sample_frame_cap: int = 16
    max_model_calls_per_job: int = 3
    app_budget_usd: float = 15.0
    job_budget_usd: float = 1.0
    price_input_per_mtok: float = 2.0
    price_output_per_mtok: float = 10.0
    max_output_tokens: int = 4000
    provider_timeout_seconds: float = 90.0
    job_deadline_seconds: float = 120.0
    tracker_backend: str = "manual"
    enable_jev: bool = False
    evidence_provider: str = "anthropic"
    allow_replay: bool = False
    apify_token: str = ""
    apify_timeout_seconds: float = 45
    smtp_user: str = ""
    smtp_app_password: str = ""
    mail_from_name: str = "SecondLook"
    mail_test_to: str = ""
    mail_live: bool = False
    outreach_live_cap: int = 5
    convex_url: str = ""
    convex_worker_secret: str = ""
    convex_worker_id: str = "laptop-worker"
    convex_poll_seconds: float = 2.0

    @property
    def root(self) -> Path:
        return ROOT

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir)
        if not path.is_absolute():
            path = ROOT / path
        return path

    @property
    def db_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise RuntimeError("Only a sqlite DATABASE_URL is supported")
        raw = self.database_url[len("sqlite:///") :]
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / path
        return path
