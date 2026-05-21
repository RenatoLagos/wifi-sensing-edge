"""Privacy-safe camera-assisted WiFi visualizer.

Receives timestamped WiFi telemetry over TCP, aligns it to local camera
frames using a smoothed receive-time offset, and renders a privacy-first
overlay using silhouette or blur modes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import time

import numpy as np

from .fusion import FusedTelemetry, TelemetryBuffer
from .telemetry import TelemetryServer, TelemetryServerStatus
from .tracking import PoseTrack, PoseTracker


@dataclass(frozen=True)
class VisualizerConfig:
    camera_index: int
    width: int
    height: int
    telemetry_host: str
    telemetry_port: int
    privacy_mode: str
    max_telemetry_age_ms: float
    max_fusion_skew_ms: float


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
    tracker: PoseTracker,
    fused: FusedTelemetry | None,
    status: TelemetryServerStatus,
    privacy_mode: str,
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
        for start_idx, end_idx in tracker.connections:
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
                f"alignment: age {fused.age_ms:5.1f} ms  skew {fused.skew_ms:5.1f} ms",
            ]
        )
    if track.detected:
        lines.append(f"pose lock: yes  confidence: {track.confidence:0.2f}")
    else:
        lines.append("pose lock: no")

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

    hint = (
        "privacy mode: silhouette"
        if privacy_mode == "silhouette"
        else "privacy mode: blur"
    )
    cv2.putText(
        canvas,
        hint,
        (24, height - 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (180, 190, 210),
        1,
        cv2.LINE_AA,
    )
    return canvas


def run_visualizer(config: VisualizerConfig) -> int:
    cv2 = _load_cv2()

    buffer = TelemetryBuffer()
    server = TelemetryServer(
        host=config.telemetry_host,
        port=config.telemetry_port,
        on_sample=buffer.add,
    )
    tracker = PoseTracker()
    capture = cv2.VideoCapture(config.camera_index)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)

    if not capture.isOpened():
        tracker.close()
        raise RuntimeError(f"could not open camera index {config.camera_index}")

    server.start()
    window_name = "wifi-sensing camera-assisted demo"
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                time.sleep(0.01)
                continue
            frame = cv2.flip(frame, 1)
            frame_local_us = time.monotonic_ns() // 1_000
            track = tracker.process(frame)
            fused = buffer.match(
                frame_local_us,
                max_age_ms=config.max_telemetry_age_ms,
                max_skew_ms=config.max_fusion_skew_ms,
            )
            rendered = _render_frame(
                frame,
                track=track,
                tracker=tracker,
                fused=fused,
                status=server.status(),
                privacy_mode=config.privacy_mode,
            )
            cv2.imshow(window_name, rendered)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
    finally:
        server.stop()
        tracker.close()
        capture.release()
        cv2.destroyAllWindows()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-index", type=int, default=0)
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
    args = parser.parse_args(argv)
    config = VisualizerConfig(
        camera_index=args.camera_index,
        width=args.width,
        height=args.height,
        telemetry_host=args.telemetry_host,
        telemetry_port=args.telemetry_port,
        privacy_mode=args.privacy_mode,
        max_telemetry_age_ms=args.max_telemetry_age_ms,
        max_fusion_skew_ms=args.max_fusion_skew_ms,
    )
    return run_visualizer(config)
