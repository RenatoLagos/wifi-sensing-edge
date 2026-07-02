"""Thread-safe primitives and thread-body loops for the visualizer pipeline.

Pure stdlib (`threading`, `collections`, `dataclasses`) plus numpy for frame
array typing. No cv2/mediapipe imports here: those stay lazily imported
inside `pc/visualizer.py` and `pc/tracking.py` so this module can be
imported and unit tested without the camera/inference stack installed.

The visualizer pipeline runs three independent stages - capture, pose
inference, render - handed off through `LatestSlot`, a freshest-wins
single-value slot (no growing queues). Each stage advances at its own pace,
so a slow pose model only slows the inference stage; it never throttles the
render loop.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging
from threading import Event, Lock
import time
from typing import Callable, Generic, TypeVar

import numpy as np

from .tracking import PoseTrack

logger = logging.getLogger(__name__)

T = TypeVar("T")

_READ_FAILURE_WARN_THRESHOLD = 100


@dataclass(frozen=True)
class LatestSlotStats:
    puts: int
    drops: int


class LatestSlot(Generic[T]):
    """Thread-safe single-value handoff between pipeline stages.

    `put()` always overwrites the current value - there is no queue, so a
    fast producer never backs up behind a slow consumer. If the value being
    overwritten was never retrieved through a consuming `get()`, it counts
    as a drop.

    `get()` defaults to "take" semantics: it returns a value only once per
    `put()`, so a consumer polling in a loop can tell "new data arrived" (a
    value) apart from "nothing new yet" (`None`) without any extra state of
    its own. Pass `mark_consumed=False` to peek at the current value
    without affecting that bookkeeping - useful for read-mostly data (e.g.
    a value published once and read every frame afterwards).
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._value: T | None = None
        self._has_value = False
        self._consumed = True
        self._puts = 0
        self._drops = 0

    def put(self, value: T) -> None:
        with self._lock:
            if self._has_value and not self._consumed:
                self._drops += 1
            self._value = value
            self._has_value = True
            self._consumed = False
            self._puts += 1

    def get(self, *, mark_consumed: bool = True) -> T | None:
        with self._lock:
            if not self._has_value:
                return None
            if not mark_consumed:
                return self._value
            if self._consumed:
                return None
            self._consumed = True
            return self._value

    @property
    def stats(self) -> LatestSlotStats:
        with self._lock:
            return LatestSlotStats(puts=self._puts, drops=self._drops)


class RateMeter:
    """Tracks events per second over a trailing time window.

    Events are recorded with `tick()`; `rate_hz()` divides the number of
    ticks still inside the window by the window length. The clock is
    injectable so tests can drive it deterministically instead of racing
    real time.
    """

    def __init__(
        self,
        *,
        window_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError(f"window_seconds must be > 0, got {window_seconds}")
        self._window_seconds = window_seconds
        self._clock = clock
        self._lock = Lock()
        self._timestamps: deque[float] = deque()

    def tick(self) -> None:
        now = self._clock()
        with self._lock:
            self._timestamps.append(now)
            self._trim_locked(now)

    def rate_hz(self) -> float:
        now = self._clock()
        with self._lock:
            self._trim_locked(now)
            return len(self._timestamps) / self._window_seconds

    def _trim_locked(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()


@dataclass(frozen=True)
class CaptureFrame:
    """One captured frame stamped with a monotonic capture time and sequence number."""

    frame_bgr: np.ndarray
    captured_monotonic_us: int
    seq: int


@dataclass(frozen=True)
class InferenceResult:
    """A pose track computed for one `CaptureFrame`."""

    frame: CaptureFrame
    track: PoseTrack
    processed_monotonic_us: int
    seq: int


@dataclass(frozen=True)
class PerfSnapshot:
    """Lightweight FPS/staleness instrumentation for the overlay."""

    capture_fps: float
    inference_fps: float
    render_fps: float
    pose_age_ms: float | None


def capture_loop(
    *,
    read_frame: Callable[[], tuple[bool, np.ndarray]],
    frame_slot: LatestSlot[CaptureFrame],
    stop_event: Event,
    capture_done: Event,
    retry_on_failure: bool,
    rate_meter: RateMeter | None = None,
    retry_sleep_s: float = 0.01,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Capture-thread body: read frames and publish the freshest one.

    `read_frame` mimics `cv2.VideoCapture.read()`, returning `(ok, frame)`.
    When `ok` is False and `retry_on_failure` is True (live camera), a
    transient read hiccup is assumed: the loop sleeps briefly and retries,
    logging one WARNING per streak of `_READ_FAILURE_WARN_THRESHOLD`
    consecutive failures (the counter resets on the next good read). When
    `retry_on_failure` is False (video file), `ok` False means end of
    stream and the loop returns.

    Fail-fast contract: an unexpected exception logs an ERROR and sets
    `stop_event` so every other stage unwinds; `capture_done` is always set
    before this function returns, so downstream stages never block forever
    waiting on a dead capture thread.
    """
    seq = 0
    consecutive_failures = 0
    try:
        while not stop_event.is_set():
            ok, frame = read_frame()
            if not ok:
                if not retry_on_failure:
                    return
                consecutive_failures += 1
                if consecutive_failures == _READ_FAILURE_WARN_THRESHOLD:
                    logger.warning(
                        "capture stage: %d consecutive failed reads; "
                        "still retrying",
                        consecutive_failures,
                    )
                stop_event.wait(retry_sleep_s)
                continue
            consecutive_failures = 0
            seq += 1
            frame_slot.put(
                CaptureFrame(
                    frame_bgr=frame,
                    captured_monotonic_us=int(clock() * 1_000_000),
                    seq=seq,
                )
            )
            if rate_meter is not None:
                rate_meter.tick()
    except Exception:
        logger.exception("capture stage failed; stopping pipeline")
        stop_event.set()
    finally:
        capture_done.set()


def inference_loop(
    *,
    frame_slot: LatestSlot[CaptureFrame],
    result_slot: LatestSlot[InferenceResult],
    stop_event: Event,
    capture_done: Event,
    inference_done: Event,
    run_pose: Callable[[np.ndarray, int], PoseTrack],
    rate_meter: RateMeter | None = None,
    idle_sleep_s: float = 0.001,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Inference-thread body: run pose on the freshest frame available.

    MediaPipe's video-mode pose landmarker is stateful and requires
    monotonically increasing timestamps, so exactly one thread may call
    `run_pose`; this loop is that thread's entire job. When no new frame
    has arrived, it idles briefly instead of reprocessing the same frame.

    It returns once `capture_done` is set and the frame slot has been fully
    drained (no frame arrived after the last one was consumed). This is how
    video-file end-of-stream propagates downstream without polling the
    capture thread's liveness directly.

    Fail-fast contract: an unexpected exception (e.g. a `run_pose` failure)
    logs an ERROR and sets `stop_event` so every other stage unwinds;
    `inference_done` is always set before returning, so the render loop
    never blocks forever waiting on a dead inference thread.
    """
    try:
        while not stop_event.is_set():
            frame = frame_slot.get()
            if frame is None:
                if capture_done.is_set():
                    return
                stop_event.wait(idle_sleep_s)
                continue
            track = run_pose(frame.frame_bgr, frame.captured_monotonic_us // 1_000)
            result_slot.put(
                InferenceResult(
                    frame=frame,
                    track=track,
                    processed_monotonic_us=int(clock() * 1_000_000),
                    seq=frame.seq,
                )
            )
            if rate_meter is not None:
                rate_meter.tick()
    except Exception:
        logger.exception("inference stage failed; stopping pipeline")
        stop_event.set()
    finally:
        inference_done.set()
