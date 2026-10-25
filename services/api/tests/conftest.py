import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    data = tmp_path / "data"
    settings = Settings(
        data_dir=str(data),
        database_url="sqlite:///" + (data / "secondlook.db").as_posix(),
        evidence_provider="synthetic",
        anthropic_api_key="",
        min_video_seconds=1,
        max_video_seconds=30,
        min_window_seconds=1,
        max_window_seconds=30,
        app_origin="http://localhost:3000",
        convex_url="",
        convex_worker_secret="",
    )
    application = create_app(settings)
    with TestClient(application) as test_client:
        yield test_client, application


def make_client(tmp_path, **overrides):
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    values = dict(
        data_dir=str(data),
        database_url="sqlite:///" + (data / "secondlook.db").as_posix(),
        evidence_provider="synthetic",
        anthropic_api_key="",
        min_video_seconds=1,
        max_video_seconds=30,
        min_window_seconds=1,
        max_window_seconds=30,
        app_origin="http://localhost:3000",
        convex_url="",
        convex_worker_secret="",
    )
    values.update(overrides)
    application = create_app(Settings(**values))
    return TestClient(application), application
