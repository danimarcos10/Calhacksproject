from app.scout.goal import interpolate_marks, scorer_path


def _player(track_id, x, y=0.4):
    return {"id": track_id, "cls": 2, "box": [x, y, 0.04, 0.1]}


def _frame(t, players, ball=None):
    return {"t": t, "players": players, "ball": ball}


def test_the_click_locks_the_player_nearest_the_goal_and_the_ball():
    frames = []
    for index, t in enumerate(range(0, 3000, 100)):
        ball_x = 0.55 + index * 0.008
        frames.append(
            _frame(
                t,
                [_player(1, 0.2), _player(2, ball_x - 0.02)],
                [ball_x, 0.48, 0.02, 0.02],
            )
        )
    click = frames[-1]["players"][1]["box"]
    path = scorer_path(frames, 2900, tuple(click))
    assert path[-1]["t"] == 2900
    assert path[-1]["box"]["x"] == click[0]
    assert path[0]["t"] == 0
    assert 0.5 < path[0]["box"]["x"] < 0.6


def test_a_ball_that_jumps_across_the_frame_is_ignored():
    frames = [
        _frame(0, [_player(2, 0.7)], [0.74, 0.48, 0.02, 0.02]),
        _frame(100, [_player(2, 0.72), _player(9, 0.1)], [0.12, 0.48, 0.02, 0.02]),
        _frame(200, [_player(2, 0.74)], [0.76, 0.48, 0.02, 0.02]),
    ]
    path = scorer_path(frames, 200, tuple(frames[-1]["players"][0]["box"]))
    assert [round(item["box"]["x"], 2) for item in path] == [0.7, 0.72, 0.74]


def test_two_clicks_connect_in_a_straight_line():
    path = interpolate_marks([(1000, (0.4, 0.4, 0.04, 0.1)), (0, (0.2, 0.4, 0.04, 0.1))])
    assert path[0]["t"] == 0
    assert path[0]["box"]["x"] == 0.2
    assert path[-1]["t"] == 1000
    assert path[-1]["box"]["x"] == 0.4
    middle = path[len(path) // 2]
    assert 400 <= middle["t"] <= 600
    assert abs(middle["box"]["x"] - 0.3) < 0.03

