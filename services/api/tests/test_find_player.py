from app.scout.describe import PlayerPick, apply_pick, choose_samples


def _frame(t, players, ball=None):
    return {"t": t, "players": players, "ball": ball}


def _player(track_id, box, cls=2):
    return {"id": track_id, "cls": cls, "box": list(box)}


def test_samples_prefer_frames_where_a_player_is_near_the_ball():
    far = [_frame(index * 1000, [_player(1, (0.1, 0.1, 0.05, 0.1))]) for index in range(6)]
    close = _frame(9000, [_player(4, (0.4, 0.4, 0.05, 0.1))], ball=[0.42, 0.5, 0.02, 0.02])
    chosen = choose_samples([*far, close], count=4)
    assert [frame["t"] for frame in chosen] == [9000]


def test_a_description_can_only_select_a_listed_track():
    frames = [_frame(12000, [_player(7, (0.3, 0.4, 0.04, 0.08)), _player(9, (0.8, 0.2, 0.04, 0.08), cls=3)])]
    kept = apply_pick(frames, PlayerPick(found=True, t_ms=12100, track_id=7, note="Orange, nearest the goal."))
    assert kept["found"] is True
    assert kept["track_id"] == 7
    assert kept["t_ms"] == 12000
    assert kept["box"]["x"] == 0.3
    missed = apply_pick(frames, PlayerPick(found=True, t_ms=12000, track_id=9, note="The referee."))
    assert missed["found"] is False
    absent = apply_pick(frames, PlayerPick(found=True, t_ms=12000, track_id=4, note="Someone else."))
    assert absent["found"] is False
