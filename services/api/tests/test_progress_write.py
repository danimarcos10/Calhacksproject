import json
from pathlib import Path

from app.scout.roboflow import _write_json


def test_progress_write_retries_when_the_replace_is_denied(tmp_path, monkeypatch):
    path = tmp_path / "progress.json"
    calls = {"n": 0}
    original = Path.replace

    def replace(self, target):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("denied")
        return original(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    _write_json(path, {"state": "running", "done": 1, "total": 4})
    assert json.loads(path.read_text(encoding="utf-8")) == {"state": "running", "done": 1, "total": 4}
    assert calls["n"] == 3
