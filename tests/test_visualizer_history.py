from __future__ import annotations

from pc.history import SignalHistory, to_polyline


def test_signal_history_respects_capacity():
    history = SignalHistory(capacity=3)
    for i in range(5):
        history.append(
            t_mono=float(i),
            breath_bpm=float(i),
            breath_confidence=1.0,
            motion_score=0.1,
            motion_state="idle",
        )
    points = history.points()
    assert len(history) == 3
    assert [p.t_mono for p in points] == [2.0, 3.0, 4.0]


def test_signal_history_dedups_same_telemetry_timestamp():
    history = SignalHistory(capacity=10)
    history.append(
        t_mono=1.0,
        breath_bpm=12.0,
        breath_confidence=8.0,
        motion_score=0.2,
        motion_state="idle",
    )
    history.append(
        t_mono=1.0,
        breath_bpm=99.0,
        breath_confidence=99.0,
        motion_score=99.0,
        motion_state="movement",
    )
    history.append(
        t_mono=2.0,
        breath_bpm=13.0,
        breath_confidence=9.0,
        motion_score=0.3,
        motion_state="presence",
    )
    points = history.points()
    assert len(points) == 2
    assert points[0].breath_bpm == 12.0
    assert points[1].t_mono == 2.0


def test_signal_history_preserves_chronological_order():
    history = SignalHistory(capacity=10)
    for i in range(4):
        history.append(
            t_mono=float(i),
            breath_bpm=None,
            breath_confidence=None,
            motion_score=None,
            motion_state=None,
        )
    points = history.points()
    assert [p.t_mono for p in points] == [0.0, 1.0, 2.0, 3.0]


def test_signal_history_rejects_non_positive_capacity():
    try:
        SignalHistory(capacity=0)
    except ValueError:
        return
    raise AssertionError("expected ValueError for capacity <= 0")


def test_to_polyline_empty_series_uses_fallback_range():
    series = to_polyline([], width=100, height=50, fallback_range=(0.0, 2.0))
    assert series.points == ()
    assert series.value_min == 0.0
    assert series.value_max == 2.0


def test_to_polyline_all_none_series_uses_fallback_range():
    series = to_polyline([None, None, None], width=100, height=50)
    assert series.points == ()
    assert series.value_min == 0.0
    assert series.value_max == 1.0


def test_to_polyline_flat_series_pads_around_value():
    series = to_polyline([3.0, 3.0, 3.0], width=101, height=51, fallback_range=(0.0, 1.0))
    assert series.value_min == 2.5
    assert series.value_max == 3.5
    assert len(series.points) == 3


def test_to_polyline_maps_values_to_pixel_coordinates():
    series = to_polyline([0.0, 5.0, 10.0], width=101, height=51)
    assert series.value_min == 0.0
    assert series.value_max == 10.0
    assert series.points == ((0, 50), (50, 25), (100, 0))
    for x, y in series.points:
        assert isinstance(x, int)
        assert isinstance(y, int)


def test_to_polyline_skips_none_but_keeps_index_spacing():
    series = to_polyline([0.0, None, 10.0], width=101, height=51)
    assert series.points == ((0, 50), (100, 0))
