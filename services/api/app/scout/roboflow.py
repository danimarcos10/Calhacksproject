"""All-player tracking with the Roboflow soccer example.

Detection, ByteTrack, the SigLIP team classifier and the pitch homography
follow https://github.com/roboflow/sports/blob/main/examples/soccer/main.py
(MIT). The three football weights live in data/models.
"""

from __future__ import annotations

import inspect
import json
import logging
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from app.versions import TRACKER_VERSION

log = logging.getLogger("secondlook.roboflow")

PLAYER_CLASS = 2
GOALKEEPER_CLASS = 1
REFEREE_CLASS = 3
STRIDE = 60
KEYPOINT_CONFIDENCE = 0.5
MIN_INLIERS = 6
RANSAC_CM = 300.0
SPREAD_IMAGE_X = 200
SPREAD_PITCH_X = 1500
SPREAD_IMAGE_Y = 80
SPREAD_PITCH_Y = 800


def models_dir(data_path: Path) -> Path:
    return data_path / "models"


def cache_dir(data_path: Path, sha: str) -> Path:
    return data_path / "tracks" / sha / TRACKER_VERSION


def tracks_path(data_path: Path, sha: str) -> Path:
    return cache_dir(data_path, sha) / "tracks.json"


def analysis_path(data_path: Path, sha: str) -> Path:
    return cache_dir(data_path, sha) / "analysis.json"


def progress_path(data_path: Path, sha: str) -> Path:
    return cache_dir(data_path, sha) / "progress.json"


def read_progress(data_path: Path, sha: str) -> dict:
    path = progress_path(data_path, sha)
    if tracks_path(data_path, sha).is_file() and not path.is_file():
        return {"state": "succeeded", "done": 1, "total": 1, "phase": "done"}
    if not path.is_file():
        return {"state": "waiting", "done": 0, "total": 0, "phase": None}
    delay = 0.02
    for attempt in range(4):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload.setdefault("phase", None)
            return payload
        except json.JSONDecodeError:
            return {"state": "running", "done": 0, "total": 0, "phase": None}
        except OSError:
            if attempt == 3:
                return {"state": "running", "done": 0, "total": 0, "phase": None}
            time.sleep(delay)
            delay *= 2


def load_tracks(data_path: Path, sha: str) -> dict | None:
    path = tracks_path(data_path, sha)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_analysis(data_path: Path, sha: str) -> dict | None:
    tracks = load_tracks(data_path, sha)
    if tracks is None:
        return None
    path = analysis_path(data_path, sha)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    from app.scout.stats import summarise

    summary = summarise(tracks.get("frames") or [])
    _write_json(path, summary)
    return summary


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
        pitch = root / "football-pitch-detection.pt"
        missing = [path.name for path in (player, ball, pitch) if not path.is_file()]
        if missing:
            raise FileNotFoundError("football weights missing: " + ", ".join(missing))
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.player = YOLO(str(player))
        self.ball = YOLO(str(ball))
        self.pitch = YOLO(str(pitch))

    def detect_players(self, frame: np.ndarray):
        import supervision as sv

        result = self.player(frame, imgsz=1280, verbose=False, device=self.device, conf=0.25)[0]
        return sv.Detections.from_ultralytics(result)


def iter_frames(path: Path):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError("could not open the video")
    native = cap.get(cv2.CAP_PROP_FPS) or 25.0
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield index, int(round(index / native * 1000)), frame, count or index + 1, native
            index += 1
    finally:
        cap.release()


def _norm_box(xyxy, width: int, height: int) -> list[float]:
    x1, y1, x2, y2 = [float(v) for v in xyxy]
    return [
        round(x1 / width, 4),
        round(y1 / height, 4),
        round((x2 - x1) / width, 4),
        round((y2 - y1) / height, 4),
    ]


def _sane(point) -> list[float] | None:
    x, y = float(point[0]), float(point[1])
    if not np.isfinite(x) or not np.isfinite(y):
        return None
    if x < -2000 or y < -2000 or x > 14000 or y > 9000:
        return None
    return [round(x, 1), round(y, 1)]


def _ball_slicer(models: FootballModels):
    import supervision as sv

    def callback(image: np.ndarray):
        result = models.ball(image, imgsz=640, verbose=False, device=models.device, conf=0.15)[0]
        return sv.Detections.from_ultralytics(result)

    params = inspect.signature(sv.InferenceSlicer.__init__).parameters
    kwargs = {"callback": callback, "slice_wh": (640, 640)}
    if "overlap_filter_strategy" in params:
        kwargs["overlap_filter_strategy"] = sv.OverlapFilter.NONE
    else:
        kwargs["overlap_filter"] = sv.OverlapFilter.NONE
    return sv.InferenceSlicer(**kwargs)


def _fit_teams(video: Path, models: FootballModels):
    import supervision as sv
    import umap
    from sports.common.team import TeamClassifier

    crops = []
    for index, _t_ms, frame, _total, _native in iter_frames(video):
        if index % STRIDE != 0:
            continue
        detections = models.detect_players(frame)
        if detections.class_id is None or len(detections) == 0:
            continue
        players = detections[detections.class_id == PLAYER_CLASS]
        crops.extend(sv.crop_image(frame, xyxy) for xyxy in players.xyxy)
    crops = [crop for crop in crops if getattr(crop, "size", 0)]
    if len(crops) < 8:
        log.warning("team fit skipped crops=%s", len(crops))
        return None
    classifier = TeamClassifier(device=models.device, batch_size=8)
    neighbors = min(15, len(crops) - 1)
    classifier.reducer = umap.UMAP(n_components=3, n_neighbors=max(2, neighbors), random_state=0)
    try:
        classifier.fit(crops)
    except Exception:
        log.exception("team fit failed")
        return None
    return classifier


class _Plane:
    """A homography that maps image pixels onto the pitch in centimetres."""

    def __init__(self, matrix: np.ndarray):
        self.m = np.asarray(matrix, dtype=np.float64)

    def transform_points(self, points: np.ndarray) -> np.ndarray:
        if points.size == 0:
            return np.zeros((0, 2), dtype=np.float32)
        reshaped = np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(reshaped, self.m).reshape(-1, 2).astype(np.float32)


def _confidence_row(keypoints, count: int):
    confidence = getattr(keypoints, "keypoint_confidence", None)
    if confidence is None:
        confidence = getattr(keypoints, "confidence", None)
    if confidence is None:
        return None
    row = np.asarray(confidence, dtype=np.float32).reshape(-1)
    if row.shape[0] < count or row.shape[0] % count != 0:
        return None
    return row.reshape(-1, count)[0]


def _fit_homography(keypoints, config):
    """RANSAC fit. Low-confidence points and outliers do not move the plane."""
    if keypoints is None or getattr(keypoints, "xy", None) is None or len(keypoints.xy) == 0:
        return None
    xy = np.asarray(keypoints.xy[0], dtype=np.float32)
    vertices = np.array(config.vertices, dtype=np.float32)
    if xy.ndim != 2 or xy.shape[0] != len(vertices):
        return None
    mask = (xy[:, 0] > 1) & (xy[:, 1] > 1)
    confidence = _confidence_row(keypoints, xy.shape[0])
    if confidence is not None:
        mask = mask & (confidence >= KEYPOINT_CONFIDENCE)
    if int(mask.sum()) < MIN_INLIERS:
        return None
    source = xy[mask]
    target = vertices[mask]
    matrix, inliers = cv2.findHomography(source, target, cv2.RANSAC, RANSAC_CM)
    if matrix is None or inliers is None:
        return None
    keep = inliers.ravel().astype(bool)
    if int(keep.sum()) < MIN_INLIERS:
        return None
    refined, _status = cv2.findHomography(source[keep], target[keep], 0)
    return _Plane(refined if refined is not None else matrix)


def _spread_ok(plane, image_points) -> bool:
    """Reject a fit that piles a spread-out group of players into a few metres."""
    points = np.asarray(image_points, dtype=np.float32).reshape(-1, 2)
    if len(points) < 4:
        return True
    image_x = float(points[:, 0].max() - points[:, 0].min())
    image_y = float(points[:, 1].max() - points[:, 1].min())
    pitch = plane.transform_points(points)
    if pitch.size == 0 or not np.isfinite(pitch).all():
        return False
    pitch_x = float(pitch[:, 0].max() - pitch[:, 0].min())
    pitch_y = float(pitch[:, 1].max() - pitch[:, 1].min())
    if image_x > SPREAD_IMAGE_X and pitch_x < SPREAD_PITCH_X:
        return False
    if image_y > SPREAD_IMAGE_Y and pitch_y < SPREAD_PITCH_Y:
        return False
    return True


def _choose_transformer(keypoints, config, image_points, previous):
    fitted = _fit_homography(keypoints, config)
    if fitted is not None and _spread_ok(fitted, image_points):
        return fitted
    return previous


def _anchor_points(detections):
    import supervision as sv

    if detections is None or len(detections) == 0:
        return np.zeros((0, 2), dtype=np.float32)
    return np.asarray(detections.get_anchors_coordinates(anchor=sv.Position.BOTTOM_CENTER), dtype=np.float32)


def _pitches(detections, transformer):
    import supervision as sv

    if transformer is None or len(detections) == 0:
        return None
    xy = detections.get_anchors_coordinates(anchor=sv.Position.BOTTOM_CENTER)
    return transformer.transform_points(points=np.asarray(xy, dtype=np.float32))


def _predict_teams(frame, players, classifier):
    import supervision as sv

    if classifier is None or len(players) == 0:
        return np.array([])
    crops = [sv.crop_image(frame, xyxy) for xyxy in players.xyxy]
    if any(getattr(crop, "size", 0) == 0 for crop in crops):
        return np.array([])
    try:
        return np.asarray(classifier.predict(crops))
    except Exception:
        log.exception("team predict failed")
        return np.array([])


def _keeper_teams(players, player_teams, keepers):
    import supervision as sv

    if len(keepers) == 0:
        return np.array([], dtype=int)
    if len(players) == 0 or len(player_teams) == 0:
        return np.zeros(len(keepers), dtype=int)
    player_teams = np.asarray(player_teams)
    players_xy = players.get_anchors_coordinates(sv.Position.BOTTOM_CENTER)
    keepers_xy = keepers.get_anchors_coordinates(sv.Position.BOTTOM_CENTER)
    team_0 = players_xy[player_teams == 0]
    team_1 = players_xy[player_teams == 1]
    if len(team_0) == 0 or len(team_1) == 0:
        only = 0 if len(team_0) else 1
        return np.full(len(keepers), only, dtype=int)
    centroid_0 = team_0.mean(axis=0)
    centroid_1 = team_1.mean(axis=0)
    labels = []
    for xy in keepers_xy:
        labels.append(0 if np.linalg.norm(xy - centroid_0) <= np.linalg.norm(xy - centroid_1) else 1)
    return np.array(labels, dtype=int)


def _pack(detections, teams, kind: int, transformer, width: int, height: int) -> list[dict]:
    if detections is None or len(detections) == 0 or detections.tracker_id is None:
        return []
    pitches = _pitches(detections, transformer)
    found = []
    for index, (xyxy, track_id) in enumerate(zip(detections.xyxy, detections.tracker_id)):
        if track_id is None or int(track_id) < 0:
            continue
        team = None
        if kind != REFEREE_CLASS and teams is not None and index < len(teams):
            team = int(teams[index])
        pitch = None if pitches is None else _sane(pitches[index])
        found.append({
            "id": int(track_id),
            "cls": kind,
            "team": team,
            "box": _norm_box(xyxy, width, height),
            "pitch": pitch,
        })
    return found


def _players(frame, detections, classifier, transformer, width: int, height: int) -> list[dict]:
    if detections.class_id is None or len(detections) == 0:
        return []
    players = detections[detections.class_id == PLAYER_CLASS]
    keepers = detections[detections.class_id == GOALKEEPER_CLASS]
    referees = detections[detections.class_id == REFEREE_CLASS]
    player_teams = _predict_teams(frame, players, classifier)
    keeper_teams = _keeper_teams(players, player_teams, keepers)
    return (
        _pack(players, player_teams, PLAYER_CLASS, transformer, width, height)
        + _pack(keepers, keeper_teams, GOALKEEPER_CLASS, transformer, width, height)
        + _pack(referees, None, REFEREE_CLASS, transformer, width, height)
    )


def _ball(frame, slicer, ball_tracker, transformer, width: int, height: int):
    import supervision as sv

    found = ball_tracker.update(slicer(frame).with_nms(threshold=0.1))
    if len(found) == 0:
        return None, None
    box = _norm_box(found.xyxy[0], width, height)
    pitch = None
    if transformer is not None:
        xy = found.get_anchors_coordinates(anchor=sv.Position.CENTER)
        transformed = transformer.transform_points(points=np.asarray(xy[:1], dtype=np.float32))
        pitch = _sane(transformed[0])
    return box, pitch


def _frame_record(frame, t_ms, models, tracker, ball_tracker, slicer, classifier, config, previous):
    import supervision as sv

    height, width = frame.shape[:2]
    keypoints = sv.KeyPoints.from_ultralytics(models.pitch(frame, verbose=False, device=models.device)[0])
    detections = tracker.update_with_detections(models.detect_players(frame))
    transformer = _choose_transformer(keypoints, config, _anchor_points(detections), previous)
    ball, ball_pitch = _ball(frame, slicer, ball_tracker, transformer, width, height)
    record = {
        "t": t_ms,
        "players": _players(frame, detections, classifier, transformer, width, height),
        "ball": ball,
        "ball_pitch": ball_pitch,
    }
    return record, transformer


def track_video(video: Path, dest: Path, models_root: Path, on_progress) -> dict:
    """Write tracks.json and analysis.json. on_progress(done, total, phase) may be called often."""
    import supervision as sv
    from sports.common.ball import BallTracker
    from sports.configs.soccer import SoccerPitchConfiguration

    models = FootballModels(models_root)
    config = SoccerPitchConfiguration()
    first = next(iter_frames(video), None)
    total = 1 if first is None else int(first[3])
    native = 25.0 if first is None else float(first[4])
    on_progress(0, total, "teams")
    classifier = _fit_teams(video, models)
    tracker = sv.ByteTrack(frame_rate=max(1, int(round(native))), minimum_consecutive_frames=3)
    ball_tracker = BallTracker(buffer_size=20)
    slicer = _ball_slicer(models)
    records: list[dict] = []
    previous = None
    for index, t_ms, frame, count, _native in iter_frames(video):
        record, previous = _frame_record(frame, t_ms, models, tracker, ball_tracker, slicer, classifier, config, previous)
        records.append(record)
        on_progress(index + 1, int(count), "tracking")
    from app.scout.stats import summarise

    payload = {"fps": round(native, 3), "version": TRACKER_VERSION, "frames": records}
    _write_json(dest, payload)
    _write_json(dest.parent / "analysis.json", summarise(records))
    return payload


def _load_pitch(root: Path):
    import torch
    from ultralytics import YOLO

    pitch = root / "football-pitch-detection.pt"
    if not pitch.is_file():
        raise FileNotFoundError(f"football weights missing: {pitch.name}")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return YOLO(str(pitch)), device


def _pixel(box, width: int, height: int, center: bool) -> tuple[float, float] | None:
    if not box or len(box) < 4:
        return None
    x, y, w, h = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
    return ((x + w / 2) * width, (y + (h / 2 if center else h)) * height)


def _project(point, transformer):
    if point is None or transformer is None:
        return None
    return _sane(transformer.transform_points(np.asarray([point], dtype=np.float32))[0])


def reproject_tracks(video: Path, tracks_file: Path, models_root: Path) -> dict:
    """Rewrite pitch coordinates from saved boxes. Does not rerun players or team color."""
    import supervision as sv
    from sports.configs.soccer import SoccerPitchConfiguration

    from app.scout.stats import summarise

    payload = json.loads(tracks_file.read_text(encoding="utf-8"))
    frames = payload.get("frames") or []
    model, device = _load_pitch(models_root)
    config = SoccerPitchConfiguration()
    previous = None
    seen = 0
    for index, _t_ms, image, count, _native in iter_frames(video):
        if index >= len(frames):
            break
        record = frames[index]
        height, width = image.shape[:2]
        keypoints = sv.KeyPoints.from_ultralytics(model(image, verbose=False, device=device)[0])
        feet = [
            point
            for player in (record.get("players") or [])
            if (point := _pixel(player.get("box"), width, height, center=False)) is not None
        ]
        image_points = np.asarray(feet, dtype=np.float32) if feet else np.zeros((0, 2), dtype=np.float32)
        previous = _choose_transformer(keypoints, config, image_points, previous)
        for player in record.get("players") or []:
            player["pitch"] = _project(_pixel(player.get("box"), width, height, center=False), previous)
        record["ball_pitch"] = _project(_pixel(record.get("ball"), width, height, center=True), previous)
        seen += 1
        if index % 25 == 0:
            log.info("reproject %s/%s file=%s", index + 1, min(count, len(frames)), tracks_file.parent.name)
    summary = summarise(frames)
    _write_json(tracks_file, payload)
    _write_json(tracks_file.parent / "analysis.json", summary)
    log.info("reproject wrote %s frames from %s", seen, video.name)
    return summary


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
            _write_json(progress_path(settings.data_path, sha), {"state": "succeeded", "done": 1, "total": 1, "phase": "done"})
            return
        folder = dest.parent
        folder.mkdir(parents=True, exist_ok=True)
        _write_json(progress_path(settings.data_path, sha), {"state": "queued", "done": 0, "total": 0, "phase": None})
        _gpu.acquire()
        try:
            if dest.is_file():
                _write_json(progress_path(settings.data_path, sha), {"state": "succeeded", "done": 1, "total": 1, "phase": "done"})
                return

            def on_progress(done: int, total: int, phase: str = "tracking") -> None:
                if phase == "tracking" and done != 1 and done % 5 != 0:
                    return
                try:
                    _write_json(
                        progress_path(settings.data_path, sha),
                        {"state": "running", "done": done, "total": total, "phase": phase},
                    )
                except OSError:
                    log.warning("progress write skipped video=%s done=%s", video_id, done)

            _write_json(progress_path(settings.data_path, sha), {"state": "running", "done": 0, "total": 0, "phase": "teams"})
            source = settings.data_path / video["original_path"]
            track_video(source, dest, models_dir(settings.data_path), on_progress)
            done = read_progress(settings.data_path, sha).get("done", 1)
            _write_json(progress_path(settings.data_path, sha), {"state": "succeeded", "done": done, "total": done, "phase": "done"})
            log.info("tracking finished video=%s", video_id)
        finally:
            _gpu.release()
    except Exception:
        log.exception("tracking failed video=%s", video_id)
        try:
            video = db.get_video(video_id)
            if video:
                _write_json(
                    progress_path(settings.data_path, video["sha256"]),
                    {"state": "failed", "done": 0, "total": 0, "phase": None},
                )
        except Exception:
            log.exception("could not record the tracking failure")
    finally:
        with _inflight_lock:
            _inflight.discard(video_id)
