"""Person tracking with a maintained pretrained model. No training in this project.

Ultralytics YOLO with BoT-SORT. BoT-SORT compensates for a moving camera, which
broadcast and sideline footage needs. The weights are the nano model so a 4 GB
laptop GPU can run them. Detection is separate from identity: this file never
decides that a track is the selected player.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("YOLO_AUTOINSTALL", "false")

import numpy as np

from app.scout.identity import Box, Det

PERSON = 0
BALL = 32


def _xywh(xyxy, width: int, height: int) -> Box:
    x0, y0, x1, y1 = [float(value) for value in xyxy]
    return (
        round(max(0.0, x0 / width), 4),
        round(max(0.0, y0 / height), 4),
        round(max(0.01, (x1 - x0) / width), 4),
        round(max(0.01, (y1 - y0) / height), 4),
    )


class YoloTracker:
    def __init__(self, weights: str | None = None) -> None:
        if weights is None:
            bundled = Path(__file__).resolve().parents[4] / "data" / "models" / "yolo26n.pt"
            weights = str(bundled if bundled.exists() else "yolo26n.pt")
        import torch
        from ultralytics import YOLO

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.weights = weights
        try:
            self.people = YOLO(weights)
        except Exception:
            self.weights = "yolo11n.pt"
            self.people = YOLO(self.weights)
        self.ball = YOLO(self.weights)

    def reset(self) -> None:
        self.people.predictor = None

    def track_people(self, frame: np.ndarray) -> list[Det]:
        height, width = frame.shape[:2]
        result = self.people.track(
            frame,
            persist=True,
            tracker="botsort.yaml",
            classes=[PERSON],
            imgsz=640,
            device=self.device,
            verbose=False,
        )[0]
        boxes = result.boxes
        if boxes is None or boxes.xyxy is None or len(boxes) == 0:
            return []
        ids = boxes.id.int().tolist() if boxes.is_track and boxes.id is not None else list(range(len(boxes)))
        confs = boxes.conf.tolist() if boxes.conf is not None else [1.0] * len(ids)
        return [
            Det(int(track_id), _xywh(xyxy, width, height), float(conf))
            for track_id, xyxy, conf in zip(ids, boxes.xyxy.tolist(), confs)
        ]

    def balls_in_crop(self, frame: np.ndarray, box: Box) -> list[Det]:
        height, width = frame.shape[:2]
        x, y, w, h = box
        half = max(h * height, w * width, 8) * 2
        cx, cy = (x + w / 2) * width, (y + h / 2) * height
        x0, y0 = int(max(0, cx - half)), int(max(0, cy - half))
        x1, y1 = int(min(width, cx + half)), int(min(height, cy + half))
        crop = frame[y0:y1, x0:x1]
        if crop.size == 0:
            return []
        result = self.ball.predict(crop, classes=[BALL], imgsz=640, conf=0.15, device=self.device, verbose=False)[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return []
        found = []
        crop_h, crop_w = crop.shape[:2]
        for xyxy, conf in zip(boxes.xyxy.tolist(), boxes.conf.tolist()):
            local = _xywh(xyxy, crop_w, crop_h)
            found.append(
                Det(
                    0,
                    (
                        round((x0 + local[0] * crop_w) / width, 4),
                        round((y0 + local[1] * crop_h) / height, 4),
                        round(local[2] * crop_w / width, 4),
                        round(local[3] * crop_h / height, 4),
                    ),
                    float(conf),
                    "ball",
                )
            )
        return found

    def detect_people(self, frame: np.ndarray) -> list[Det]:
        height, width = frame.shape[:2]
        result = self.people.predict(frame, classes=[PERSON], imgsz=640, device=self.device, verbose=False)[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return []
        found = []
        for xyxy, conf in zip(boxes.xyxy.tolist(), boxes.conf.tolist()):
            x, y, w, h = _xywh(xyxy, width, height)
            w, h = min(w, round(1 - x, 4)), min(h, round(1 - y, 4))
            if w >= 0.01 and h >= 0.01:
                found.append(Det(0, (x, y, w, h), float(conf)))
        return found
