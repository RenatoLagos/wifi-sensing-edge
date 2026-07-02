from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from pc.history import SignalHistory
from pc.telemetry import TelemetryServerStatus
from pc.tracking import PoseTrack
from pc.visualizer import _MIN_CHART_PANEL_HEIGHT, _draw_chart_panel, main


def _make_cv2_stub(
    recorded_polylines: list[np.ndarray],
    recorded_texts: list[tuple[str, tuple[int, int]]],
) -> types.ModuleType:
    stub = types.ModuleType("cv2")
    stub.LINE_AA = 16
    stub.FONT_HERSHEY_SIMPLEX = 0

    def rectangle(img, pt1, pt2, color, thickness=1):
        return img

    def add_weighted(src1, alpha, src2, beta, gamma):
        return src1.copy()

    def put_text(img, text, org, font, scale, color, thickness=1, line_type=None):
        recorded_texts.append((text, org))
        return img

    def polylines(img, pts_list, is_closed, color, thickness=1, line_type=None):
        recorded_polylines.extend(pts.copy() for pts in pts_list)
        return img

    stub.rectangle = rectangle
    stub.addWeighted = add_weighted
    stub.putText = put_text
    stub.polylines = polylines
    stub.GaussianBlur = lambda img, ksize, sigmaX=0, sigmaY=0: img
    stub.line = lambda img, *args, **kwargs: img
    stub.circle = lambda img, *args, **kwargs: img
    return stub


def _history_with_samples() -> SignalHistory:
    history = SignalHistory()
    for i in range(6):
        history.append(
            t_mono=float(i),
            breath_bpm=10.0 + i,
            breath_confidence=8.0,
            motion_score=0.1 * i,
            motion_state="presence",
        )
    return history


class _NoPoseTracker:
    connections: tuple[tuple[int, int], ...] = ()


def _no_pose_track() -> PoseTrack:
    return PoseTrack(
        detected=False,
        confidence=0.0,
        bbox_xyxy=None,
        segmentation_mask=None,
        landmarks=(),
    )


def _status() -> TelemetryServerStatus:
    return TelemetryServerStatus(
        host="0.0.0.0",
        port=8765,
        connected=True,
        connections_accepted=1,
        disconnects=0,
        samples_received=6,
        parse_errors=0,
        last_sample_monotonic_us=1,
        last_error=None,
    )


def test_chart_panel_traces_fit_minimum_panel_height():
    recorded_polylines: list[np.ndarray] = []
    recorded_texts: list[tuple[str, tuple[int, int]]] = []
    cv2_stub = _make_cv2_stub(recorded_polylines, recorded_texts)
    canvas = np.zeros((540, 960, 3), dtype=np.uint8)

    result = _draw_chart_panel(
        cv2_stub,
        canvas,
        _history_with_samples(),
        panel_height=_MIN_CHART_PANEL_HEIGHT,
    )

    assert result is not None
    margin = 20
    panel_bottom = 540 - margin
    panel_top = panel_bottom - _MIN_CHART_PANEL_HEIGHT
    assert len(recorded_polylines) == 2
    for pts in recorded_polylines:
        assert pts[:, 0].min() >= margin
        assert pts[:, 0].max() <= 960 - margin
        assert pts[:, 1].min() >= panel_top
        assert pts[:, 1].max() <= panel_bottom


def test_chart_panel_declines_when_frame_too_small():
    recorded_polylines: list[np.ndarray] = []
    recorded_texts: list[tuple[str, tuple[int, int]]] = []
    cv2_stub = _make_cv2_stub(recorded_polylines, recorded_texts)
    canvas = np.zeros((100, 200, 3), dtype=np.uint8)

    result = _draw_chart_panel(
        cv2_stub, canvas, _history_with_samples(), panel_height=150
    )

    assert result is None
    assert recorded_polylines == []


def test_privacy_hint_stays_on_canvas_in_both_panel_outcomes():
    recorded_polylines: list[np.ndarray] = []
    recorded_texts: list[tuple[str, tuple[int, int]]] = []
    cv2_stub = _make_cv2_stub(recorded_polylines, recorded_texts)
    sys.modules["cv2"] = cv2_stub
    try:
        from pc.visualizer import _render_frame

        frame = np.zeros((540, 960, 3), dtype=np.uint8)
        for panel_height, expected_hint_y in ((150, 540 - 150 - 32), (1000, 540 - 24)):
            recorded_texts.clear()
            _render_frame(
                frame,
                track=_no_pose_track(),
                tracker=_NoPoseTracker(),
                fused=None,
                status=_status(),
                privacy_mode="silhouette",
                history=_history_with_samples(),
                show_charts=True,
                chart_panel_height=panel_height,
            )
            hints = [
                org for text, org in recorded_texts if text.startswith("privacy mode:")
            ]
            assert hints == [(24, expected_hint_y)]
            assert expected_hint_y > 0
    finally:
        del sys.modules["cv2"]


def test_cli_rejects_out_of_range_chart_panel_height():
    with pytest.raises(SystemExit):
        main(["--chart-panel-height", str(_MIN_CHART_PANEL_HEIGHT - 1)])
    with pytest.raises(SystemExit):
        main(["--height", "540", "--chart-panel-height", "300"])
