"""Possession rules on a hand-built track. No model and no video."""

from app.scout.possession import events_along, events_for, follow_track, select_track


def frame(t, players, ball=None):
    return {"t": t, "players": players, "ball": ball}


def player(track_id, x, team=0):
    return {"id": track_id, "cls": 2, "team": team, "box": [x, 0.4, 0.04, 0.12]}


def test_click_selects_the_overlapping_track():
    frames = [frame(1000, [player(7, 0.2), player(8, 0.6, team=1)])]
    assert select_track(frames, 1000, (0.2, 0.4, 0.04, 0.12)) == 7


def test_pass_receive_and_carry():
    frames = []
    for index, t in enumerate(range(0, 3000, 100)):
        owner = 7 if t < 1800 else 8
        moved = 0.10 + min(t, 1700) / 1700 * 0.32
        ball_x = (moved + 0.02) if t < 1800 else 0.57
        frames.append(frame(t, [player(7, moved if owner == 7 else 0.10), player(8, 0.55, team=0)], [ball_x, 0.50, 0.01, 0.01]))
    points, corrections, identity = follow_track(frames, 7, 0)
    assert 7 in identity and corrections == []
    assert any(point.state == "tracked" for point in points)
    events = events_for(frames, {7})
    actions = [event.action for event in events]
    assert "receive" in actions
    assert "carry" in actions
    assert any(event.action == "pass" and event.outcome == "completed" for event in events)


def test_loss_to_an_opponent_nearby():
    frames = []
    for t in range(0, 1200, 100):
        owner = 7 if t < 600 else 9
        ball_x = 0.30 if owner == 7 else 0.34
        frames.append(frame(t, [player(7, 0.30), player(9, 0.34, team=1)], [ball_x, 0.5, 0.01, 0.01]))
    events = events_for(frames, {7})
    assert any(event.action == "loss" and event.outcome == "lost" for event in events)


def test_a_clicked_path_counts_the_ball_near_that_box():
    path = []
    frames = []
    for t in range(0, 2000, 100):
        x = 0.2 + t / 2000 * 0.3
        path.append((t, (x, 0.4, 0.04, 0.12)))
        frames.append(frame(t, [], [x + 0.02, 0.50, 0.01, 0.01]))
    actions = [event.action for event in events_along(path, frames)]
    assert "receive" in actions
    assert "carry" in actions
    assert "loss" not in actions
