from app.schemas import IdentityStatus, EvidenceStatus, ScoutEventIn, ScoutReport
from app.scout.chunks import chunk_ranges, parse_showinfo_pts, stitch
from app.scout.discover import Event, ball_near_feet, coverage, dedupe, discover
from app.scout.identity import Det, FrameObs, follow
from app.scout.validate import validate_scout
from app.versions import SCOUT_SCHEMA_VERSION

BLUE = (1, 0, 0, 0, 0, 0, 0, 0)
RED = (0, 0, 0, 0, 0, 0, 0, 1)
PLAYER = (0.5, 0.4, 0.08, 0.2)


def _person(track_id, box=PLAYER, hue=BLUE):
    return Det(track_id, box, hue=hue)


def test_follow_keeps_the_anchored_track_and_ignores_time_before_it():
    frames = [
        FrameObs(0, [_person(1, (0.1, 0.4, 0.08, 0.2))]),
        FrameObs(500, [_person(7)]),
        FrameObs(1000, [_person(7, (0.52, 0.4, 0.08, 0.2))]),
    ]
    points, corrections = follow(frames, 500, PLAYER)
    assert corrections == []
    assert [point.t_ms for point in points] == [500, 1000]
    assert {point.track_id for point in points} == {7}
    assert all(point.state == "tracked" for point in points)


def test_two_similar_candidates_are_not_relinked():
    frames = [
        FrameObs(0, [_person(1)]),
        FrameObs(
            200,
            [
                _person(2, (0.48, 0.4, 0.08, 0.2), BLUE),
                _person(3, (0.55, 0.42, 0.08, 0.2), BLUE),
            ],
        ),
    ]
    points, _corrections = follow(frames, 0, PLAYER)
    assert points[1].state == "lost"


def test_a_single_clear_candidate_can_be_relinked():
    frames = [
        FrameObs(0, [_person(1)]),
        FrameObs(
            200,
            [
                _person(2, (0.52, 0.4, 0.08, 0.2), BLUE),
                _person(3, (0.9, 0.1, 0.08, 0.2), RED),
            ],
        ),
    ]
    points, corrections = follow(frames, 0, PLAYER)
    assert corrections == []
    assert points[1].state == "tracked"
    assert points[1].track_id == 2


def test_a_camera_cut_ends_the_identity():
    frames = [
        FrameObs(0, [_person(1)]),
        FrameObs(200, [_person(1)], cut=True),
        FrameObs(400, [_person(1, (0.52, 0.4, 0.08, 0.2))]),
    ]
    points, _corrections = follow(frames, 0, PLAYER)
    assert points[1].state == "lost"
    assert points[2].state == "lost"


def test_a_lost_track_asks_for_one_correction_after_three_seconds():
    frames = [FrameObs(0, [_person(1)])] + [FrameObs(t, [_person(9, (0.1, 0.1, 0.08, 0.2), RED)]) for t in (1000, 2500, 4000)]
    _points, corrections = follow(frames, 0, PLAYER)
    assert len(corrections) == 1
    assert corrections[0].t_ms == 1000
    assert corrections[0].reason == "track_lost"
    assert corrections[0].boxes[0].track_id == 9


def test_a_correction_stops_identity_before_a_later_similar_player():
    frames = [
        FrameObs(0, [_person(1)]),
        FrameObs(1000, []),
        FrameObs(4000, []),
        FrameObs(5000, [_person(2, (0.52, 0.4, 0.08, 0.2), BLUE)]),
    ]
    points, corrections = follow(frames, 0, PLAYER)
    assert len(corrections) == 1
    assert points[-1].state == "lost"


def test_chunk_bounds_overlap_and_stitch_keeps_source_order():
    assert chunk_ranges(0, 35_000, 15_000, 1_000) == [(0, 15_000), (14_000, 29_000), (28_000, 35_000)]
    from app.scout.identity import Point

    first = [Point(0, "tracked", PLAYER, 1, None), Point(14_000, "tracked", PLAYER, 1, None)]
    second = [Point(14_000, "tracked", PLAYER, 4, None), Point(20_000, "tracked", PLAYER, 4, None)]
    merged = stitch([first, second])
    assert [point.t_ms for point in merged] == [0, 14_000, 20_000]
    assert merged[1].track_id == 1
    assert parse_showinfo_pts("n: 3 pts_time:1.250 pts:123") == 1250


def test_discovery_needs_repeated_ball_proximity_and_records_coverage():
    from app.scout.identity import Point

    def tracked(t_ms, ball):
        return Point(t_ms, "tracked", PLAYER, 1, ball)

    ball = (0.52, 0.58, 0.02, 0.02)
    far = (0.1, 0.1, 0.02, 0.02)
    points = [
        tracked(0, far),
        tracked(200, ball),
        tracked(400, ball),
        tracked(3000, None),
        Point(4000, "lost", None, None, None),
        Point(5000, "lost", None, None, None),
    ]
    candidates, totals = discover(points, bounds=(0, 5000))
    assert len(candidates) == 1
    assert candidates[0].touch_start_ms == 200
    assert candidates[0].start_ms == 0
    assert candidates[0].end_ms == 400 + 1500
    assert totals == {"tracked_ms": 4000, "lost_ms": 1000, "ball_unseen_ms": 1000}
    assert ball_near_feet(PLAYER, far) is False


def test_a_long_contact_is_split_and_duplicate_events_collapse():
    from app.scout.identity import Point

    ball = (0.52, 0.58, 0.02, 0.02)
    points = [Point(t, "tracked", PLAYER, 1, ball) for t in range(0, 10_000, 200)]
    candidates, _totals = discover(points, bounds=(0, 12_000))
    assert len(candidates) == 2
    assert candidates[0].touch_end_ms - candidates[0].touch_start_ms <= 8000

    unclear = Event("pass", "unclear", 1000, 1800, ("a",), "observable", "Plays the ball forward.")
    known = Event("pass", "completed", 1400, 2200, ("a", "b"), "observable", "Plays the ball to a teammate.")
    kept = dedupe([unclear, known, Event("carry", "retained", 5000, 6000, ("c",), "observable", "Carries the ball.")])
    assert [(event.action, event.outcome) for event in kept] == [("pass", "completed"), ("carry", "retained")]


def _event(**overrides):
    values = dict(
        candidate_id="c1",
        action="pass",
        outcome="completed",
        start_ms=1000,
        end_ms=2000,
        frame_ids=["a", "b"],
        visible_action="Plays the ball to a teammate on the left.",
        evidence_status=EvidenceStatus.observable,
        identity_status=IdentityStatus.clear_in_cited_frames,
    )
    values.update(overrides)
    return ScoutEventIn(**values)


def test_validator_drops_proximity_and_downgrades_an_unshown_pass_outcome():
    report = ScoutReport(
        schema_version=SCOUT_SCHEMA_VERSION,
        events=[
            _event(outcome="completed", frame_ids=["a"], start_ms=1000, end_ms=1500),
            _event(candidate_id="c1", action="receive", outcome="controlled", visible_action="The ball is nearby.", frame_ids=["b"]),
            _event(action="carry", outcome="retained", visible_action="An elite talent carries the ball.", frame_ids=["a", "b"]),
        ],
    )
    checked = validate_scout(report, windows={"c1": (500, 2500)}, frames_by_id={"a": 1000, "b": 1800})
    assert [event.outcome for event in checked.events] == ["unclear", "retained"]
    assert "elite" not in checked.events[1].visible_action.lower()
    assert any("proximity_only" in issue for issue in checked.issues)
