import numpy as np

from app.scout.stick import track_grays


def test_flow_follows_a_patch_backward():
    grays = []
    for index in range(15):
        image = np.zeros((90, 140), np.uint8)
        x = 20 + index * 3
        image[30:62, x : x + 18] = 30
        image[34:58, x + 2 : x + 8] = 210
        image[36:56, x + 8 : x + 14] = 120
        image[40:50, x + 4 : x + 16] = 250
        grays.append(image)
    seed = len(grays) - 1
    start_x = 20 + seed * 3
    box = (start_x / 140, 30 / 90, 18 / 140, 32 / 90)
    found = track_grays(grays, seed, box, -1)
    assert len(found) >= 8
    earliest = found[min(found)]
    assert earliest[0] < box[0]
