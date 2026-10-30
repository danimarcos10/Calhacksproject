"""Geometric counts on hand-built frames. No model and no video."""

from app.scout.stats import summarise


def box_at(feet_x, feet_y=0.52, w=0.04, h=0.12):
    return [round(feet_x - w / 2, 4), round(feet_y - h, 4), w, h]


def ball_at(feet_x, feet_y=0.52):
    return [feet_x - 0.005, feet_y - 0.005, 0.01, 0.01]


def player(track_id, team, x, y, feet=(0.30, 0.52)):
    return {"id": track_id, "cls": 2, "team": team, "box": box_at(*feet), "pitch": [x, y]}


def frame(t, players, ball, ball_box=None):
    return {
        "t": t,
        "players": players,
        "ball": ball_box if ball is not None else None,
        "ball_pitch": list(ball) if ball else None,
    }


def test_possession_follows_the_body_nearest_the_ball():
    frames = []
    for t in range(0, 800, 100):
        owner = player(1, 1 if t == 0 else 0, 3000, 3500, (0.30, 0.52))
        other = player(2, 1, 9000, 3500, (0.75, 0.52))
        frames.append(frame(t, [owner, other], (3100, 3500), ball_at(0.30, 0.52)))
    for t in range(800, 1000, 100):
        frames.append(frame(
            t,
            [player(1, 0, 3000, 3500, (0.75, 0.52)), player(2, 1, 9000, 3500, (0.30, 0.52))],
            (9100, 3500),
            ball_at(0.30, 0.52),
        ))
    frames.append(frame(1000, [player(1, 0, 3000, 3500)], None))
    teams = {row["team"]: row for row in summarise(frames)["teams"]}
    assert teams[0]["possession"] == 0.8
    assert teams[1]["possession"] == 0.2


def test_a_team_far_from_the_ball_has_no_possession_or_passes():
    frames = []
    for t in range(0, 500, 100):
        frames.append(frame(
            t,
            [
                player(1, 0, 9000, 3500, (0.30, 0.52)),
                player(2, 1, 3100, 3500, (0.80, 0.52)),
            ],
            (3100, 3500),
            ball_at(0.30, 0.52),
        ))
    teams = {row["team"]: row for row in summarise(frames)["teams"]}
    assert teams[0]["possession"] == 1
    assert teams[0]["passes"] == 0
    assert teams[1]["possession"] == 0
    assert teams[1]["passes"] == 0
    assert teams[1]["pass_completion"] is None


def test_standing_near_the_ball_is_not_a_touch():
    frames = []
    for t in range(0, 500, 100):
        frames.append(frame(t, [player(5, 0, 3000, 3500, (0.30, 0.52))], (3000, 3500), ball_at(0.354, 0.52)))
    teams = {row["team"]: row for row in summarise(frames)["teams"]}
    assert teams[0]["possession"] == 0
    assert teams[0]["passes"] == 0
    assert teams[0]["pass_completion"] is None
    assert summarise(frames)["players"][0]["touches"] == 0


def test_a_pass_is_the_ball_reaching_a_teammate():
    frames = []
    for t in range(0, 500, 100):
        frames.append(frame(
            t,
            [player(7, 0, 2000, 3500, (0.25, 0.52)), player(8, 0, 4500, 3500, (0.55, 0.52))],
            (2100, 3500),
            ball_at(0.25, 0.52),
        ))
    for t in range(800, 1300, 100):
        frames.append(frame(
            t,
            [player(7, 0, 2000, 3500, (0.25, 0.52)), player(8, 0, 4500, 3500, (0.55, 0.52))],
            (4600, 3500),
            ball_at(0.55, 0.52),
        ))
    summary = summarise(frames)
    team = summary["teams"][0]
    assert team["passes"] == 1
    assert team["pass_completion"] == 1
    by_id = {row["id"]: row for row in summary["players"]}
    assert by_id[7]["passes"] == 1
    assert by_id[7]["touches"] == 1
    assert by_id[7]["dribbles"] == 0
    assert by_id[8]["passes"] == 0
    assert by_id[8]["touches"] == 1
    assert by_id[8]["dribbles"] == 0


def test_carrying_the_ball_without_a_defender_is_not_a_dribble():
    frames = []
    for index, t in enumerate(range(0, 1300, 100)):
        feet_x = 0.20 + index * 0.03
        frames.append(frame(t, [player(4, 0, 2000 + index * 50, 3500, (feet_x, 0.52))], (2000, 3500), ball_at(feet_x, 0.52)))
    player_row = summarise(frames)["players"][0]
    assert player_row["dribbles"] == 0
    assert player_row["touches"] == 1
    assert player_row["passes"] == 0


def test_a_dribble_is_going_past_a_defender_with_the_ball():
    frames = []
    for index, feet_x in enumerate((0.30, 0.34, 0.38, 0.42, 0.46, 0.50)):
        frames.append(frame(
            index * 200,
            [
                player(4, 0, 2000 + index * 100, 3500, (feet_x, 0.52)),
                player(9, 1, 4000, 3500, (0.40, 0.52)),
            ],
            (2000, 3500),
            ball_at(feet_x, 0.52),
        ))
    by_id = {row["id"]: row for row in summarise(frames)["players"]}
    assert by_id[4]["dribbles"] == 1
    assert by_id[4]["touches"] == 1
    assert by_id[4]["passes"] == 0
    assert by_id[9]["dribbles"] == 0


def test_a_shot_reaches_the_penalty_area_quickly():
    frames = []
    keeper = player(3, 1, 8000, 3500, (0.42, 0.52))
    for t in (0, 100, 200):
        frames.append(frame(t, [keeper], (8100, 3500), ball_at(0.42, 0.52)))
    frames.append(frame(300, [keeper], (9500, 3500), ball_at(0.10, 0.10)))
    frames.append(frame(400, [keeper], (10500, 3500), ball_at(0.10, 0.10)))
    summary = summarise(frames)
    assert summary["teams"][1]["shots"] == 1
    assert summary["players"][0]["shots"] == 1
    assert summary["teams"][1]["passes"] == 0
