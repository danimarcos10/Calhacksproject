"""30-frame measurement of the Roboflow football models. Prints counts only."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from sports.common.ball import BallTracker

from app.scout.roboflow import FootballModels, _ball_slicer, iter_frames

ROOT = Path(__file__).resolve().parents[1]


def measure(path: Path, models: FootballModels, limit: int = 30) -> None:
    import supervision as sv

    tracker = sv.ByteTrack(minimum_consecutive_frames=3)
    ball_tracker = BallTracker(buffer_size=20)
    slicer = _ball_slicer(models)
    players = []
    balls = 0
    started = time.perf_counter()
    used = 0
    for _index, _t, frame, _total, _native in iter_frames(path):
        detections = tracker.update_with_detections(models.detect_players(frame))
        kind = detections.class_id
        count = 0 if kind is None else int(((kind == 1) | (kind == 2) | (kind == 3)).sum())
        players.append(count)
        found = ball_tracker.update(slicer(frame).with_nms(threshold=0.1))
        if len(found):
            balls += 1
        used += 1
        if used >= limit:
            break
    elapsed = time.perf_counter() - started
    mean = sum(players) / len(players) if players else 0
    print(f"{path.name} frames={used} players_mean={mean:.1f} ball_share={balls / used if used else 0:.2f} ms={elapsed / used * 1000 if used else 0:.0f}")


def main() -> None:
    models = FootballModels(ROOT / "data" / "models")
    dfl = ROOT / "data" / "footage" / "dfl-0bfacc_0.mp4"
    if dfl.is_file():
        measure(dfl, models)
    cache = list(Path.home().joinpath(".cache", "huggingface", "hub").glob("datasets--atomscott--soccertrack-v2/**/mot/clips/118577.mp4"))
    if cache:
        measure(cache[0], models)
    else:
        print("soccertrack full clip not in the huggingface cache")


if __name__ == "__main__":
    sys.exit(main())
