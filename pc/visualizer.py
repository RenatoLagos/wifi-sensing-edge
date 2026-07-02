"""Privacy-safe camera-assisted WiFi visualizer.

Receives timestamped WiFi telemetry over TCP, aligns it to local camera
frames using a smoothed receive-time offset, and renders a privacy-first
overlay using silhouette or blur modes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import logging
from threading import Event, Thread
import time
from typing import Sequence

import numpy as np

from .fusion import FusedTelemetry, TelemetryBuffer
from .history import SignalHistory, to_polyline
from .loops import (
    CaptureFrame,
    InferenceResult,
    LatestSlot,
    PerfSnapshot,
    RateMeter,
    capture_loop,
    inference_loop,
)
from .telemetry import TelemetryServer, TelemetryServerStatus
from .tracking import PoseTrack, PoseTracker

logger = logging.getLogger(__name__)

_MOTION_STATE_COLORS: dict[str, tuple[int, int, int]] = {
    "idle": (150, 150, 150),
    "presence": (0, 200, 255),
    "movement": (60, 60, 255),
}
_DEFAULT_TRACE_COLOR = (200, 200, 200)
_BREATH_TRACE_COLOR = (56, 168, 255)
_BREATH_FALLBACK_RANGE_BPM = (8.0, 30.0)
_MIN_CHART_PANEL_HEIGHT = 90


@dataclass(frozen=True)
class VisualizerConfig:
    camera_index: int
    video_file: str | None
    pose_model: str | None
    width: int
    height: int
    telemetry_host: str
    telemetry_port: int
    privacy_mode: str
    max_telemetry_age_ms: float
    max_fusion_skew_ms: float
    headless: bool
    max_frames: int | None
    show_charts: bool
    chart_panel_height: int


def _load_cv2():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "Install `pc/requirements.txt` to run the camera-assisted visualizer."
        ) from exc
    return cv2


def _render_frame(
    frame_bgr: np.ndarray,
    *,
    track: PoseTrack,
    connections: Sequence[tuple[int, int]],
    fused: FusedTelemetry | None,
    status: TelemetryServerStatus,
    privacy_mode: str,
    history: SignalHistory,
    show_charts: bool,
    chart_panel_height: int,
    perf: PerfSnapshot | None = None,
) -> np.ndarray:
    cv2 = _load_cv2()
    height, width = frame_bgr.shape[:2]
    if privacy_mode == "blur":
        canvas = cv2.GaussianBlur(frame_bgr, (0, 0), sigmaX=20, sigmaY=20)
        canvas = (canvas * 0.55).astype(np.uint8)
    else:
        canvas = np.zeros_like(frame_bgr)
        canvas[:, :] = (12, 14, 18)

    if track.detected and track.segmentation_mask is not None:
        person_mask = track.segmentation_mask >= 0.35
        if privacy_mode == "silhouette":
            canvas[person_mask] = (56, 168, 255)
        else:
            accent = np.zeros_like(canvas)
            accent[:, :] = (40, 78, 120)
            canvas[person_mask] = accent[person_mask]

    if track.detected:
        for start_idx, end_idx in connections:
            if start_idx >= len(track.landmarks) or end_idx >= len(track.landmarks):
                continue
            x0, y0, v0 = track.landmarks[start_idx]
            x1, y1, v1 = track.landmarks[end_idx]
            if v0 < 0.5 or v1 < 0.5:
                continue
            cv2.line(canvas, (x0, y0), (x1, y1), (255, 255, 255), 2, cv2.LINE_AA)
        for x, y, visibility in track.landmarks:
            if visibility < 0.55:
                continue
            cv2.circle(canvas, (x, y), 4, (255, 255, 255), -1, cv2.LINE_AA)
        if track.bbox_xyxy is not None:
            x0, y0, x1, y1 = track.bbox_xyxy
            cv2.rectangle(canvas, (x0, y0), (x1, y1), (56, 168, 255), 2)

    panel_height = 164
    overlay = canvas.copy()
    cv2.rectangle(
        overlay, (20, 20), (min(width - 20, 460), 20 + panel_height), (6, 8, 12), -1
    )
    canvas = cv2.addWeighted(overlay, 0.74, canvas, 0.26, 0.0)

    lines = [
        "camera-assisted WiFi demo",
        f"telemetry: {'connected' if status.connected else 'waiting'} @ {status.host}:{status.port}",
        f"samples: {status.samples_received}  parse_errors: {status.parse_errors}",
    ]
    if fused is None:
        lines.append("fusion: no fresh WiFi sample matched to this frame")
    else:
        breath = "--"
        if fused.sample.breath_rate_bpm is not None:
            breath = f"{fused.sample.breath_rate_bpm:4.1f} bpm"
        conf = "--"
        if fused.sample.breath_confidence is not None:
            conf = f"{fused.sample.breath_confidence:5.1f}x"
        motion = fused.sample.motion_state or "--"
        motion_score = "--"
        if fused.sample.motion_score is not None:
            motion_score = f"{fused.sample.motion_score:5.2f}"
        lines.extend(
            [
                f"breath: {breath}  confidence: {conf}",
                f"motion: {motion}  score: {motion_score}",
                f"alignment: age {fused.age_ms:5.1f} ms  "
                f"frame skew {fused.skew_ms:5.1f} ms",
            ]
        )
    if track.detected:
        lines.append(f"pose lock: yes  confidence: {track.confidence:0.2f}")
    else:
        lines.append("pose lock: no")
    if perf is not None:
        age_txt = "--" if perf.pose_age_ms is None else f"{perf.pose_age_ms:5.0f}"
        lines.append(
            f"perf: capture {perf.capture_fps:4.1f} fps  "
            f"inference {perf.inference_fps:4.1f} fps  "
            f"render {perf.render_fps:4.1f} fps  pose age {age_txt} ms"
        )

    y = 48
    for idx, line in enumerate(lines):
        scale = 0.8 if idx == 0 else 0.6
        thickness = 2 if idx == 0 else 1
        cv2.putText(
            canvas,
            line,
            (36, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (245, 247, 250),
            thickness,
            cv2.LINE_AA,
        )
        y += 28

    hint_y = height - 24
    if show_charts:
        chart_canvas = _draw_chart_panel(
            cv2, canvas, history, panel_height=chart_panel_height
        )
        if chart_canvas is not None:
            canvas = chart_canvas
            hint_y = height - chart_panel_height - 32

    hint = (
        "privacy mode: silhouette"
        if privacy_mode == "silhouette"
        else "privacy mode: blur"
    )
    cv2.putText(
        canvas,
        hint,
        (24, hint_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (180, 190, 210),
        1,
        cv2.LINE_AA,
    )
    return canvas


def _draw_chart_panel(
    cv2,
    canvas: np.ndarray,
    history: SignalHistory,
    *,
    panel_height: int,
) -> np.ndarray | None:
    """Composite the chart panel onto a copy of `canvas`.

    Returns the composited canvas, or None when the panel does not fit the
    frame so the caller can keep the original layout untouched.
    """
    height, width = canvas.shape[:2]
    margin = 20
    panel_left = margin
    panel_right = width - margin
    panel_bottom = height - margin
    panel_top = panel_bottom - panel_height
    label_row_height = 18
    trace_gap = 10
    trace_width = (panel_right - panel_left) - 16
    trace_height = (panel_height - 2 * label_row_height - trace_gap) // 2
    if panel_top <= margin or trace_width <= 0 or trace_height < 20:
        return None

    overlay = canvas.copy()
    cv2.rectangle(
        overlay, (panel_left, panel_top), (panel_right, panel_bottom), (6, 8, 12), -1
    )
    canvas = cv2.addWeighted(overlay, 0.74, canvas, 0.26, 0.0)

    points = history.points()
    breath_series = to_polyline(
        [p.breath_bpm for p in points],
        width=trace_width,
        height=trace_height,
        fallback_range=_BREATH_FALLBACK_RANGE_BPM,
    )
    breath_origin = (panel_left + 8, panel_top + label_row_height)
    latest = points[-1] if points else None
    breath_bpm_txt = (
        "--"
        if latest is None or latest.breath_bpm is None
        else f"{latest.breath_bpm:4.1f}"
    )
    breath_conf_txt = (
        "--"
        if latest is None or latest.breath_confidence is None
        else f"{latest.breath_confidence:4.1f}x"
    )
    _put_chart_text(
        cv2,
        canvas,
        f"breath: {breath_bpm_txt} bpm (conf {breath_conf_txt})  "
        f"range [{breath_series.value_min:4.1f}, {breath_series.value_max:4.1f}]",
        (breath_origin[0], breath_origin[1] - 4),
    )
    _draw_trace(cv2, canvas, breath_series.points, breath_origin, _BREATH_TRACE_COLOR)

    motion_series = to_polyline(
        [p.motion_score for p in points], width=trace_width, height=trace_height
    )
    motion_origin = (
        panel_left + 8,
        breath_origin[1] + trace_height + trace_gap + label_row_height,
    )
    motion_state = latest.motion_state if latest is not None else None
    motion_score_txt = (
        "--"
        if latest is None or latest.motion_score is None
        else f"{latest.motion_score:5.2f}"
    )
    _put_chart_text(
        cv2,
        canvas,
        f"motion: {motion_state or '--'} ({motion_score_txt})  "
        f"range [{motion_series.value_min:4.2f}, {motion_series.value_max:4.2f}]",
        (motion_origin[0], motion_origin[1] - 4),
    )
    motion_color = _MOTION_STATE_COLORS.get(motion_state or "", _DEFAULT_TRACE_COLOR)
    _draw_trace(cv2, canvas, motion_series.points, motion_origin, motion_color)
    return canvas


def _draw_trace(
    cv2,
    canvas: np.ndarray,
    points: tuple[tuple[int, int], ...],
    origin: tuple[int, int],
    color: tuple[int, int, int],
) -> None:
    if len(points) < 2:
        return
    shifted = np.array(
        [(origin[0] + x, origin[1] + y) for x, y in points], dtype=np.int32
    )
    cv2.polylines(canvas, [shifted], False, color, 2, cv2.LINE_AA)


def _put_chart_text(
    cv2, canvas: np.ndarray, text: str, origin: tuple[int, int]
) -> None:
    cv2.putText(
        canvas,
        text,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (220, 224, 230),
        1,
        cv2.LINE_AA,
    )


def run_visualizer(config: VisualizerConfig) -> int:
    """Run the capture -> inference -> render pipeline.

    Capture and pose inference run on dedicated background threads, each
    handing its output to the next stage through a `LatestSlot`
    (freshest-wins, no growing queues) so a slow pose model only slows the
    inference stage - it never throttles the render loop. Rendering stays
    on this thread because `cv2.imshow` requires the main thread on some
    platforms. Any stage failure fails fast: it logs an ERROR, signals
    every other stage to stop, and the visualizer exits cleanly.
    """
    cv2 = _load_cv2()

    buffer = TelemetryBuffer()
    server = TelemetryServer(
        host=config.telemetry_host,
        port=config.telemetry_port,
        on_sample=buffer.add,
    )
    history = SignalHistory()
    if config.video_file is not None:
        capture = cv2.VideoCapture(config.video_file)
        source_desc = f"video file {config.video_file}"
        retry_on_failure = False
    else:
        capture = cv2.VideoCapture(config.camera_index)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)
        source_desc = f"camera index {config.camera_index}"
        retry_on_failure = True

    if not capture.isOpened():
        capture.release()
        raise RuntimeError(f"could not open {source_desc}")

    stop_event = Event()
    capture_done = Event()
    inference_done = Event()
    frame_slot: LatestSlot[CaptureFrame] = LatestSlot()
    result_slot: LatestSlot[InferenceResult] = LatestSlot()
    connections_slot: LatestSlot[tuple[tuple[int, int], ...]] = LatestSlot()
    capture_rate = RateMeter()
    inference_rate = RateMeter()
    render_rate = RateMeter()

    def _read_frame() -> tuple[bool, np.ndarray]:
        ok, raw = capture.read()
        if not ok:
            return False, raw
        return True, cv2.flip(raw, 1)

    def _capture_thread_body() -> None:
        # The capture thread owns the capture handle: releasing it here
        # (never from the main thread) avoids racing release() against a
        # read() still blocked on the same device.
        try:
            capture_loop(
                read_frame=_read_frame,
                frame_slot=frame_slot,
                stop_event=stop_event,
                capture_done=capture_done,
                retry_on_failure=retry_on_failure,
                rate_meter=capture_rate,
            )
        finally:
            capture.release()

    capture_thread = Thread(
        target=_capture_thread_body,
        name="visualizer-capture",
        daemon=True,
    )

    def _inference_thread_body() -> None:
        # The pose model download (when not cached) and MediaPipe's video
        # mode are both handled on this thread only, so the render path
        # never blocks on either. A setup failure (download, model load)
        # must fail fast like a run_pose failure: log, stop every stage,
        # and mark inference done so the render loop can exit.
        tracker: PoseTracker | None = None
        try:
            tracker = PoseTracker(model_path=config.pose_model)
            active_tracker = tracker
            connections_slot.put(tuple(active_tracker.connections))
            inference_loop(
                frame_slot=frame_slot,
                result_slot=result_slot,
                stop_event=stop_event,
                capture_done=capture_done,
                inference_done=inference_done,
                run_pose=lambda frame_bgr, timestamp_ms: active_tracker.process(
                    frame_bgr, timestamp_ms=timestamp_ms
                ),
                rate_meter=inference_rate,
            )
        except Exception:
            logger.exception("inference stage setup failed; stopping pipeline")
            stop_event.set()
        finally:
            inference_done.set()
            if tracker is not None:
                tracker.close()

    inference_thread = Thread(
        target=_inference_thread_body,
        name="visualizer-inference",
        daemon=True,
    )

    window_name = "wifi-sensing camera-assisted demo"
    frames_rendered = 0
    last_result: InferenceResult | None = None
    try:
        server.start()
        capture_thread.start()
        inference_thread.start()
        while True:
            if (
                config.max_frames is not None
                and frames_rendered >= config.max_frames
            ):
                break

            # Read the done flag BEFORE polling the slot: inference cannot
            # publish after setting inference_done, so "done and nothing
            # pending" is race-free in this order.
            inference_finished = inference_done.is_set()
            result = result_slot.get()
            fresh = result is not None
            if fresh:
                last_result = result
            elif inference_finished:
                # No newer pose can ever arrive - inference drained the
                # source (EOF) or died. Stop capture too and exit,
                # regardless of the capture stage's state.
                stop_event.set()
                break

            if last_result is None:
                if stop_event.wait(0.005):
                    break
                continue

            if config.headless and not fresh:
                # No window to keep alive, so re-compositing the same stale
                # pose is wasted work and would inflate the rendered-frame
                # count that --max-frames gates on. Wait for a fresh result.
                if stop_event.wait(0.02):
                    break
                continue

            now_us = time.monotonic_ns() // 1_000
            fused = buffer.match(
                now_us,
                max_age_ms=config.max_telemetry_age_ms,
                max_skew_ms=config.max_fusion_skew_ms,
            )
            if fused is not None:
                # match() gates freshness on live "now" so telemetry keeps
                # flowing while pose inference lags, but the displayed skew
                # must describe the frame actually on screen.
                fused = replace(
                    fused,
                    skew_ms=abs(
                        fused.aligned_local_us
                        - last_result.frame.captured_monotonic_us
                    )
                    / 1_000.0,
                )
                history.append(
                    t_mono=fused.aligned_local_us / 1_000_000.0,
                    breath_bpm=fused.sample.breath_rate_bpm,
                    breath_confidence=fused.sample.breath_confidence,
                    motion_score=fused.sample.motion_score,
                    motion_state=fused.sample.motion_state,
                )
            perf = PerfSnapshot(
                capture_fps=capture_rate.rate_hz(),
                inference_fps=inference_rate.rate_hz(),
                render_fps=render_rate.rate_hz(),
                pose_age_ms=(now_us - last_result.processed_monotonic_us) / 1_000.0,
            )
            rendered = _render_frame(
                last_result.frame.frame_bgr,
                track=last_result.track,
                connections=connections_slot.get(mark_consumed=False) or (),
                fused=fused,
                status=server.status(),
                privacy_mode=config.privacy_mode,
                history=history,
                show_charts=config.show_charts,
                chart_panel_height=config.chart_panel_height,
                perf=perf,
            )
            frames_rendered += 1
            render_rate.tick()
            if config.headless:
                continue

            cv2.imshow(window_name, rendered)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                stop_event.set()
                break
    finally:
        stop_event.set()
        # The capture thread owns the capture handle and releases it on its
        # way out; the main thread only releases when the thread never ran.
        if capture_thread.ident is not None:
            capture_thread.join(timeout=2.0)
        else:
            capture.release()
        if inference_thread.ident is not None:
            inference_thread.join(timeout=2.0)
        final_status = server.status()
        server.stop()
        if not config.headless:
            cv2.destroyAllWindows()
    if config.headless:
        print(
            "headless run complete "
            f"frames={frames_rendered} "
            f"samples={final_status.samples_received} "
            f"parse_errors={final_status.parse_errors}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--video-file", type=str, default=None)
    parser.add_argument("--pose-model", type=str, default=None)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--telemetry-host", type=str, default="0.0.0.0")
    parser.add_argument("--telemetry-port", type=int, default=8765)
    parser.add_argument(
        "--privacy-mode",
        choices=["silhouette", "blur"],
        default="silhouette",
    )
    parser.add_argument("--max-telemetry-age-ms", type=float, default=1500.0)
    parser.add_argument("--max-fusion-skew-ms", type=float, default=250.0)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument(
        "--chart-panel-height",
        type=int,
        default=150,
        help=(
            "chart panel height in pixels "
            f"(min {_MIN_CHART_PANEL_HEIGHT}, max half of --height)"
        ),
    )
    parser.add_argument(
        "--no-charts",
        dest="show_charts",
        action="store_false",
        help="disable the breath/motion chart panel overlay",
    )
    parser.set_defaults(show_charts=True)
    args = parser.parse_args(argv)
    if args.max_frames is not None and args.max_frames <= 0:
        parser.error("--max-frames must be > 0")
    if args.chart_panel_height < _MIN_CHART_PANEL_HEIGHT:
        parser.error(f"--chart-panel-height must be >= {_MIN_CHART_PANEL_HEIGHT}")
    if args.chart_panel_height > args.height // 2:
        parser.error("--chart-panel-height must be <= half of --height")
    config = VisualizerConfig(
        camera_index=args.camera_index,
        video_file=args.video_file,
        pose_model=args.pose_model,
        width=args.width,
        height=args.height,
        telemetry_host=args.telemetry_host,
        telemetry_port=args.telemetry_port,
        privacy_mode=args.privacy_mode,
        max_telemetry_age_ms=args.max_telemetry_age_ms,
        max_fusion_skew_ms=args.max_fusion_skew_ms,
        headless=args.headless,
        max_frames=args.max_frames,
        show_charts=args.show_charts,
        chart_panel_height=args.chart_panel_height,
    )
    return run_visualizer(config)
