"""The pitch plane keeps a bad keypoint from dragging every player to midfield."""

import numpy as np

from app.scout.roboflow import _choose_transformer, _fit_homography, _spread_ok
from sports.configs.soccer import SoccerPitchConfiguration


class Keypoints:
    def __init__(self, xy, confidence):
        self.xy = np.asarray([xy], dtype=np.float32)
        self.confidence = np.asarray([confidence], dtype=np.float32)


def _picture(vertices):
    return vertices * 0.05 + 80


def test_an_outlier_keypoint_does_not_move_the_plane():
    config = SoccerPitchConfiguration()
    vertices = np.array(config.vertices, dtype=np.float32)
    source = _picture(vertices)
    source[10] = (30, 40)
    confidence = np.ones(len(vertices), dtype=np.float32)
    plane = _fit_homography(Keypoints(source, confidence), config)
    assert plane is not None
    mapped = plane.transform_points(_picture(vertices[15:16]))
    assert abs(float(mapped[0, 0]) - float(vertices[15, 0])) < 50
    assert abs(float(mapped[0, 1]) - float(vertices[15, 1])) < 50


def test_low_confidence_keypoints_are_not_enough():
    config = SoccerPitchConfiguration()
    vertices = np.array(config.vertices, dtype=np.float32)
    confidence = np.full(len(vertices), 0.1, dtype=np.float32)
    confidence[:4] = 0.9
    assert _fit_homography(Keypoints(_picture(vertices), confidence), config) is None


def test_a_collapsed_fit_keeps_the_previous_plane():
    config = SoccerPitchConfiguration()
    vertices = np.array(config.vertices, dtype=np.float32)
    confidence = np.ones(len(vertices), dtype=np.float32)
    collapsed = _fit_homography(Keypoints(vertices, confidence), config)
    assert collapsed is not None
    image = np.array([[0, 0], [600, 0], [0, 200], [600, 200]], dtype=np.float32)
    assert _spread_ok(collapsed, image) is False
    previous = _fit_homography(Keypoints(_picture(vertices), confidence), config)
    kept = _choose_transformer(Keypoints(vertices, confidence), config, image, previous)
    assert kept is previous
