"""Pipeline orchestrator.

Feeds CSI frames in, runs breath-rate and motion estimators on a fixed
cadence, returns a PipelineResult each time it processes. Designed to
run on a single thread; the next iteration can move the source read to a
thread or asyncio loop without touching this code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from jetson.ingest import CSIFrame
from jetson.pipeline.window import SlidingWindow
from jetson.preprocess import (
    BreathRateEstimate,
    MotionEstimate,
    estimate_breath_rate,
    estimate_motion,
)


@dataclass(frozen=True)
class PipelineResult:
    timestamp_us: int
    breath_rate: Optional[BreathRateEstimate]
    motion: Optional[MotionEstimate]


class Pipeline:
    def __init__(
        self,
        *,
        sample_rate_hz: float,
        window_seconds: float = 60.0,
        breath_window_seconds: float = 30.0,
        motion_window_seconds: float = 2.0,
        process_every_frames: int = 100,
    ) -> None:
        if sample_rate_hz <= 0:
            raise ValueError(f"sample_rate_hz must be > 0, got {sample_rate_hz}")
        if process_every_frames <= 0:
            raise ValueError(
                f"process_every_frames must be > 0, got {process_every_frames}"
            )
        if breath_window_seconds > window_seconds:
            raise ValueError(
                "breath_window_seconds cannot exceed window_seconds "
                f"({breath_window_seconds} > {window_seconds})"
            )

        max_frames = int(window_seconds * sample_rate_hz)
        self.window = SlidingWindow(max_frames=max_frames)
        self.sample_rate_hz = sample_rate_hz
        self._breath_window_n = int(breath_window_seconds * sample_rate_hz)
        self._motion_window_n = int(motion_window_seconds * sample_rate_hz)
        self._process_every = process_every_frames
        self._counter = 0

    def feed(self, frame: CSIFrame) -> Optional[PipelineResult]:
        """Push one frame. Returns a result on the configured cadence, else None."""
        self.window.append(frame)
        self._counter += 1
        if self._counter % self._process_every != 0:
            return None
        return self._process()

    def _process(self) -> PipelineResult:
        breath_est: Optional[BreathRateEstimate] = None
        breath_amps = self.window.amps_last_n(self._breath_window_n)
        if breath_amps is not None:
            try:
                breath_est = estimate_breath_rate(breath_amps, self.sample_rate_hz)
            except ValueError:
                breath_est = None

        motion_est: Optional[MotionEstimate] = None
        motion_amps = self.window.amps_last_n(self._motion_window_n)
        if motion_amps is not None:
            try:
                motion_est = estimate_motion(motion_amps)
            except ValueError:
                motion_est = None

        ts = self.window.latest_timestamp_us() or 0
        return PipelineResult(
            timestamp_us=ts,
            breath_rate=breath_est,
            motion=motion_est,
        )
