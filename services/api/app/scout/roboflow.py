"""All-player tracking with the Roboflow sports football weights.

The player model, the ball model and ByteTrack come from
https://github.com/roboflow/sports (Apache-2.0). Team colour is a two-cluster
fit on torso colour, so this machine does not need the SigLIP team encoder.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from app.versions import TRACKER_VERSION

log = logging.getLogger("secondlook.roboflow")

PLAYER_CLASS = 2
GOALKEEPER_CLASS = 1
REFEREE_CLASS = 3
SAMPLE_FPS = 10


class BallTracker:
    """Keep the detection closest to the recent ball positions. From roboflow/sports."""

    def __init__(self, buffer_size: int = 10):
        self.buffer: deque = deque(maxlen=buffer_size)

    def update(self, detections):
        xy = detections.get_anchors_coordinates(__import__("supervision").Position.CENTER)
        self.buffer.append(xy)
        if len(detections) == 0:
            return detections
        centroid = np.mean(np.concatenate(self.buffer), axis=0)
        distances = np.linalg.norm(xy - centroid, axis=1)
        return detections[[int(np.argmin(distances))]]


def models_dir(data_path: Path) -> Path:
    return data_path / "models"


def cache_dir(data_path: Path, sha: str) -> Path:
    return data_path / "tracks" / sha / TRACKER_VERSION


def tracks_path(data_path: Path, sha: str) -> Path:
    return cache_dir(data_path, sha) / "tracks.json"


def progress_path(data_path: Path, sha: str) -> Path:
    return cache_dir(data_path, sha) / "progress.json"


def read_progress(data_path: Path, sha: str) -> dict:
    path = progress_path(data_path, sha)
    if tracks_path(data_path, sha).is_file() and not path.is_file():
        return {"state": "succeeded", "done": 1, "total": 1}
    if not path.is_file():
        return {"state": "waiting", "done": 0, "total": 0}
    delay = 0.02
    for attempt in range(4):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"state": "running", "done": 0, "total": 0}
        except OSError:
            if attempt == 3:
                return {"state": "running", "done": 0, "total": 0}
            time.sleep(delay)
            delay *= 2


def load_tracks(data_path: Path, sha: str) -> dict | None:
    path = tracks_path(data_path, sha)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    """Replace the file. Windows denies the replace while a status read has it open."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    delay = 0.05
    for attempt in range(6):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(delay)
            delay = min(0.4, delay * 2)


class FootballModels:
    def __init__(self, root: Path):
        import torch
        from ultralytics import YOLO

        player = root / "football-player-detection.pt"
        ball = root / "football-ball-detection.pt"
        if not player.is_file() or not ball.is_file():
            raise FileNotFoundError("football weights missing")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.player = YOLO(str(player))
        self.ball = YOLO(str(ball))
        pitch = root / "football-pitch-detection.pt"
        self.pitch = YOLO(str(pitch)) if pitch.is_file() else None

    def detect_players(self, frame: np.ndarray):
        import supervision as sv

        if frame.shape[1] > 2500:
            def callback(image):
                result = self.player(image, imgsz=1280, verbose=False, device=self.device, conf=0.25)[0]
                return sv.Detections.from_ultralytics(result)

            slicer = sv.InferenceSlicer(callback=callback, overlap_filter=sv.OverlapFilter.NON_MAX_SUPPRESSION, slice_wh=(1280, 1280))
            return slicer(frame)
        result = self.player(frame, imgsz=1280, verbose=False, device=self.device, conf=0.25)[0]
        return sv.Detections.from_ultralytics(result)

    def detect_ball(self, frame: np.ndarray, tracker: BallTracker):
        import supervision as sv

        if frame.shape[1] > 2500:
            def callback(image):
                result = self.ball(image, imgsz=640, verbose=False, device=self.device, conf=0.15)[0]
                return sv.Detections.from_ultralytics(result)

            slicer = sv.InferenceSlicer(callback=callback, overlap_filter=sv.OverlapFilter.NONE, slice_wh=(640, 640))
            found = slicer(frame).with_nms(threshold=0.1)
            return tracker.update(found)
        # One 1280 pass finds the ball on a 1920 broadcast frame. Scaling that
        # frame to 640 found it in about a quarter of the measured frames.
        result = self.ball(frame, imgsz=1280, verbose=False, device=self.device, conf=0.15)[0]
        return tracker.update(sv.Detections.from_ultralytics(result).with_nms(threshold=0.1))


def iter_sampled(path: Path, fps_out: int = SAMPLE_FPS):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError("could not open the video")
    native = cap.get(cv2.CAP_PROP_FPS) or 25.0
    count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    step = max(1, int(round(native / fps_out)))
    total = int(count // step) if count else 0
    index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if index % step == 0:
                yield int(round(index / native * 1000)), frame, total
            index += 1
    finally:
        cap.release()


def _norm_box(xyxy, width: int, height: int) -> list[float]:
    x1, y1, x2, y2 = [float(v) for v in xyxy]
    return [round(x1 / width, 4), round(y1 / height, 4), round((x2 - x1) / width, 4), round((y2 - y1) / height, 4)]


def _torso(frame: np.ndarray, xyxy) -> list[float] | None:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in xyxy]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width, x2), min(height, y2)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    ch, cw = crop.shape[:2]
    torso = crop[ch // 5 : ch // 2, cw // 4 : (3 * cw) // 4]
    if torso.size == 0:
        return None
    mean = torso.reshape(-1, 3).mean(axis=0)
    return [round(float(mean[2]), 1), round(float(mean[1]), 1), round(float(mean[0]), 1)]


def _assign_teams(records: list[dict]) -> None:
    colours = []
    where = []
    for frame_index, frame in enumerate(records):
        for player_index, player in enumerate(frame["players"]):
            if player["cls"] != PLAYER_CLASS or player.get("rgb") is None:
                continue
            colours.append(player["rgb"])
            where.append((frame_index, player_index))
    labels = None
    if len(colours) >= 8:
        from sklearn.cluster import KMeans

        labels = KMeans(n_clusters=2, n_init=10, random_state=0).fit_predict(np.array(colours))
        for (frame_index, player_index), label in zip(where, labels):
            records[frame_index]["players"][player_index]["team"] = int(label)
    for frame in records:
        players = [player for player in frame["players"] if player["cls"] == PLAYER_CLASS and player["team"] is not None]
        if not players:
            continue
        for player in frame["players"]:
            if player["cls"] != GOALKEEPER_CLASS:
                continue
            feet = (player["box"][0] + player["box"][2] / 2, player["box"][1] + player["box"][3])
            centroids = []
            for team in (0, 1):
                mates = [item for item in players if item["team"] == team]
                if not mates:
                    centroids.append(None)
                    continue
                centroids.append(np.mean([[item["box"][0] + item["box"][2] / 2, item["box"][1] + item["box"][3]] for item in mates], axis=0))
            if centroids[0] is None or centroids[1] is None:
                continue
            d0 = float(np.linalg.norm(np.array(feet) - centroids[0]))
            d1 = float(np.linalg.norm(np.array(feet) - centroids[1]))
            player["team"] = 0 if d0 <= d1 else 1
    for frame in records:
        for player in frame["players"]:
            player.pop("rgb", None)


def track_video(video: Path, dest: Path, models_root: Path, on_progress) -> dict:
    """Write tracks.json. on_progress(done, total) may be called often."""
    from trackers import ByteTrackTracker

    models = FootballModels(models_root)
    tracker = ByteTrackTracker(frame_rate=SAMPLE_FPS, track_activation_threshold=0.25, minimum_consecutive_frames=2)
    ball_tracker = BallTracker()
    records: list[dict] = []
    for t_ms, frame, total in iter_sampled(video):
        height, width = frame.shape[:2]
        detections = models.detect_players(frame)
        detections = tracker.update(detections)
        players = []
        if detections.tracker_id is not None:
            for xyxy, class_id, track_id in zip(detections.xyxy, detections.class_id, detections.tracker_id):
                if track_id is None or int(track_id) < 0:
                    continue
                kind = int(class_id)
                if kind not in {PLAYER_CLASS, GOALKEEPER_CLASS, REFEREE_CLASS}:
                    continue
                players.append({
                    "id": int(track_id),
                    "cls": kind,
                    "team": None,
                    "box": _norm_box(xyxy, width, height),
                    "rgb": None if kind == REFEREE_CLASS else _torso(frame, xyxy),
                })
        ball = None
        balls = models.detect_ball(frame, ball_tracker)
        if len(balls):
            ball = _norm_box(balls.xyxy[0], width, height)
        records.append({"t": t_ms, "players": players, "ball": ball})
        on_progress(len(records), total or len(records))
    _assign_teams(records)
    payload = {"fps": SAMPLE_FPS, "version": TRACKER_VERSION, "frames": records}
    _write_json(dest, payload)
    return payload


_inflight: set[str] = set()
_inflight_lock = threading.Lock()
# One clip at a time. Several uploads otherwise share the GPU and stall each other.
_gpu = threading.Semaphore(1)


def start_tracking(app, video_id: str) -> None:
    with _inflight_lock:
        if video_id in _inflight:
            return
        _inflight.add(video_id)
    threading.Thread(target=_track_job, args=(app, video_id), name=f"track-{video_id}", daemon=True).start()


def _track_job(app, video_id: str) -> None:
    settings = app.state.settings
    db = app.state.db
    try:
        video = db.get_video(video_id)
        if video is None:
            return
        sha = video["sha256"]
        dest = tracks_path(settings.data_path, sha)
        if dest.is_file():
            _write_json(progress_path(settings.data_path, sha), {"state": "succeeded", "done": 1, "total": 1})
            return
        folder = dest.parent
        folder.mkdir(parents=True, exist_ok=True)
        _write_json(progress_path(settings.data_path, sha), {"state": "queued", "done": 0, "total": 0})
        _gpu.acquire()
        try:
            if dest.is_file():
                _write_json(progress_path(settings.data_path, sha), {"state": "succeeded", "done": 1, "total": 1})
                return

            def on_progress(done: int, total: int) -> None:
                if done != 1 and done % 5 != 0:
                    return
                try:
                    _write_json(progress_path(settings.data_path, sha), {"state": "running", "done": done, "total": total})
                except OSError:
                    log.warning("progress write skipped video=%s done=%s", video_id, done)

            _write_json(progress_path(settings.data_path, sha), {"state": "running", "done": 0, "total": 0})
            source = settings.data_path / video["original_path"]
            track_video(source, dest, models_dir(settings.data_path), on_progress)
            done = read_progress(settings.data_path, sha).get("done", 1)
            _write_json(progress_path(settings.data_path, sha), {"state": "succeeded", "done": done, "total": done})
            log.info("tracking finished video=%s", video_id)
        finally:
            _gpu.release()
    except Exception:
        log.exception("tracking failed video=%s", video_id)
        try:
            video = db.get_video(video_id)
            if video:
                _write_json(progress_path(settings.data_path, video["sha256"]), {"state": "failed", "done": 0, "total": 0})
        except Exception:
            log.exception("could not record the tracking failure")
    finally:
        with _inflight_lock:
            _inflight.discard(video_id)
