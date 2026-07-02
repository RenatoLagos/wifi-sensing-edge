from __future__ import annotations

import logging
from threading import Event, Thread
import time

import numpy as np
import pytest

from pc.loops import (
    CaptureFrame,
    InferenceResult,
    LatestSlot,
    LatestSlotStats,
    RateMeter,
    capture_loop,
    inference_loop,
)
from pc.tracking import PoseTrack


def _no_pose_track() -> PoseTrack:
    return PoseTrack(
        detected=False,
        confidence=0.0,
        bbox_xyxy=None,
        segmentation_mask=None,
        landmarks=(),
    )


# --- LatestSlot -----------------------------------------------------------


def test_latest_slot_starts_empty():
    slot: LatestSlot[str] = LatestSlot()
    assert slot.get() is None
    assert slot.stats == LatestSlotStats(puts=0, drops=0)


def test_latest_slot_take_semantics_return_value_once():
    slot: LatestSlot[str] = LatestSlot()
    slot.put("a")
    assert slot.get() == "a"
    assert slot.get() is None  # already consumed, nothing new since


def test_latest_slot_overwrite_of_unconsumed_value_counts_as_drop():
    slot: LatestSlot[int] = LatestSlot()
    slot.put(1)
    slot.put(2)  # 1 was never consumed -> drop
    slot.put(3)  # 2 was never consumed -> drop
    assert slot.get() == 3
    assert slot.stats == LatestSlotStats(puts=3, drops=2)


def test_latest_slot_consumed_value_overwrite_does_not_count_as_drop():
    slot: LatestSlot[int] = LatestSlot()
    slot.put(1)
    assert slot.get() == 1
    slot.put(2)
    assert slot.stats == LatestSlotStats(puts=2, drops=0)


def test_latest_slot_peek_does_not_mark_consumed():
    slot: LatestSlot[int] = LatestSlot()
    slot.put(1)
    assert slot.get(mark_consumed=False) == 1
    assert slot.get(mark_consumed=False) == 1  # peek is repeatable
    assert slot.get() == 1  # still available for a real take
    assert slot.get() is None


def test_latest_slot_thread_safety_smoke():
    slot: LatestSlot[int] = LatestSlot()
    stop = Event()
    got: list[int] = []
    put_count = 2000

    def producer() -> None:
        for i in range(put_count):
            slot.put(i)

    def consumer() -> None:
        while not stop.is_set():
            value = slot.get()
            if value is not None:
                got.append(value)

    consumer_thread = Thread(target=consumer)
    producer_thread = Thread(target=producer)
    consumer_thread.start()
    producer_thread.start()
    producer_thread.join(timeout=5.0)
    assert not producer_thread.is_alive()
    stop.set()
    consumer_thread.join(timeout=5.0)
    assert not consumer_thread.is_alive()

    stats = slot.stats
    assert stats.puts == put_count
    assert 0 <= stats.drops < stats.puts
    # Freshest-wins + take semantics: every value the consumer observed is
    # unique and strictly increasing, since put() only ever advances i.
    assert got == sorted(set(got))
    assert len(got) <= put_count


# --- RateMeter --------------------------------------------------------------


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> None:
        self.now += dt


def test_rate_meter_empty_window_is_zero():
    clock = _FakeClock()
    meter = RateMeter(window_seconds=1.0, clock=clock)
    assert meter.rate_hz() == 0.0


def test_rate_meter_steady_ticks_match_expected_rate():
    clock = _FakeClock()
    meter = RateMeter(window_seconds=1.0, clock=clock)
    for _ in range(10):
        meter.tick()
        clock.advance(0.1)
    assert meter.rate_hz() == pytest.approx(10.0, rel=1e-6)


def test_rate_meter_drops_ticks_once_they_leave_the_window():
    clock = _FakeClock()
    meter = RateMeter(window_seconds=1.0, clock=clock)
    for _ in range(5):
        meter.tick()
        clock.advance(0.1)
    clock.advance(2.0)  # window fully elapses
    assert meter.rate_hz() == 0.0


def test_rate_meter_burst_counts_all_ticks_within_window():
    clock = _FakeClock()
    meter = RateMeter(window_seconds=0.5, clock=clock)
    for _ in range(20):
        meter.tick()  # all at the same instant
    assert meter.rate_hz() == pytest.approx(40.0)


def test_rate_meter_rejects_non_positive_window():
    with pytest.raises(ValueError):
        RateMeter(window_seconds=0.0)


# --- capture_loop / inference_loop integration ------------------------------


def test_capture_and_inference_loops_drain_cleanly_on_source_eof():
    frames = [np.full((2, 2, 3), i, dtype=np.uint8) for i in range(5)]
    cursor = {"i": 0}

    def fake_read_frame() -> tuple[bool, np.ndarray | None]:
        idx = cursor["i"]
        if idx >= len(frames):
            return False, None
        cursor["i"] += 1
        return True, frames[idx]

    processed_timestamps: list[int] = []

    def fake_run_pose(frame_bgr: np.ndarray, timestamp_ms: int) -> PoseTrack:
        processed_timestamps.append(timestamp_ms)
        return _no_pose_track()

    frame_slot: LatestSlot[CaptureFrame] = LatestSlot()
    result_slot: LatestSlot[InferenceResult] = LatestSlot()
    stop_event = Event()
    capture_done = Event()
    inference_done = Event()

    capture_thread = Thread(
        target=capture_loop,
        kwargs=dict(
            read_frame=fake_read_frame,
            frame_slot=frame_slot,
            stop_event=stop_event,
            capture_done=capture_done,
            retry_on_failure=False,
        ),
    )
    inference_thread = Thread(
        target=inference_loop,
        kwargs=dict(
            frame_slot=frame_slot,
            result_slot=result_slot,
            stop_event=stop_event,
            capture_done=capture_done,
            inference_done=inference_done,
            run_pose=fake_run_pose,
        ),
    )

    capture_thread.start()
    inference_thread.start()
    capture_thread.join(timeout=2.0)
    inference_thread.join(timeout=2.0)

    assert not capture_thread.is_alive()
    assert not inference_thread.is_alive()
    assert capture_done.is_set()
    assert inference_done.is_set()

    last = result_slot.get(mark_consumed=False)
    assert last is not None
    assert last.seq == 5
    assert processed_timestamps  # inference ran at least once
    assert processed_timestamps == sorted(processed_timestamps)


def test_capture_and_inference_loops_stop_promptly_on_stop_event():
    def fake_read_frame() -> tuple[bool, np.ndarray]:
        return True, np.zeros((2, 2, 3), dtype=np.uint8)

    def fake_run_pose(frame_bgr: np.ndarray, timestamp_ms: int) -> PoseTrack:
        return _no_pose_track()

    frame_slot: LatestSlot[CaptureFrame] = LatestSlot()
    result_slot: LatestSlot[InferenceResult] = LatestSlot()
    stop_event = Event()
    capture_done = Event()
    inference_done = Event()

    capture_thread = Thread(
        target=capture_loop,
        kwargs=dict(
            read_frame=fake_read_frame,
            frame_slot=frame_slot,
            stop_event=stop_event,
            capture_done=capture_done,
            retry_on_failure=True,
            retry_sleep_s=0.001,
        ),
    )
    inference_thread = Thread(
        target=inference_loop,
        kwargs=dict(
            frame_slot=frame_slot,
            result_slot=result_slot,
            stop_event=stop_event,
            capture_done=capture_done,
            inference_done=inference_done,
            run_pose=fake_run_pose,
            idle_sleep_s=0.001,
        ),
    )

    capture_thread.start()
    inference_thread.start()
    time.sleep(0.05)  # let a handful of iterations run on a live source
    stop_event.set()
    capture_thread.join(timeout=2.0)
    inference_thread.join(timeout=2.0)

    assert not capture_thread.is_alive()
    assert not inference_thread.is_alive()
    assert capture_done.is_set()
    assert inference_done.is_set()
    assert result_slot.get() is not None


def test_inference_failure_fails_fast_and_unblocks_render_exit(caplog):
    caplog.set_level(logging.ERROR, logger="pc.loops")

    def fake_read_frame() -> tuple[bool, np.ndarray]:
        # A healthy live source: capture alone must never keep the
        # pipeline alive once inference has died.
        return True, np.zeros((2, 2, 3), dtype=np.uint8)

    def failing_run_pose(frame_bgr: np.ndarray, timestamp_ms: int) -> PoseTrack:
        raise RuntimeError("pose model exploded")

    frame_slot: LatestSlot[CaptureFrame] = LatestSlot()
    result_slot: LatestSlot[InferenceResult] = LatestSlot()
    stop_event = Event()
    capture_done = Event()
    inference_done = Event()

    capture_thread = Thread(
        target=capture_loop,
        kwargs=dict(
            read_frame=fake_read_frame,
            frame_slot=frame_slot,
            stop_event=stop_event,
            capture_done=capture_done,
            retry_on_failure=True,
            retry_sleep_s=0.001,
        ),
    )
    inference_thread = Thread(
        target=inference_loop,
        kwargs=dict(
            frame_slot=frame_slot,
            result_slot=result_slot,
            stop_event=stop_event,
            capture_done=capture_done,
            inference_done=inference_done,
            run_pose=failing_run_pose,
            idle_sleep_s=0.001,
        ),
    )

    capture_thread.start()
    inference_thread.start()

    # Fail-fast propagation: the dying stage marks itself done and stops
    # every other stage, within a bounded wait.
    assert inference_done.wait(timeout=2.0)
    assert stop_event.wait(timeout=2.0)
    capture_thread.join(timeout=2.0)
    inference_thread.join(timeout=2.0)
    assert not capture_thread.is_alive()
    assert not inference_thread.is_alive()
    assert capture_done.is_set()

    # The render loop's exit condition - inference done and no pending
    # result - must be reachable regardless of the capture stage's state.
    while result_slot.get() is not None:
        pass
    assert inference_done.is_set()
    assert any(
        "inference stage failed" in record.getMessage()
        for record in caplog.records
    )


def test_capture_loop_failure_sets_done_and_stop_event(caplog):
    caplog.set_level(logging.ERROR, logger="pc.loops")

    def exploding_read_frame() -> tuple[bool, np.ndarray]:
        raise RuntimeError("camera exploded")

    stop_event = Event()
    capture_done = Event()
    capture_loop(
        read_frame=exploding_read_frame,
        frame_slot=LatestSlot(),
        stop_event=stop_event,
        capture_done=capture_done,
        retry_on_failure=True,
    )

    assert capture_done.is_set()
    assert stop_event.is_set()
    assert any(
        "capture stage failed" in record.getMessage() for record in caplog.records
    )


def test_capture_loop_warns_once_per_failed_read_streak(caplog):
    caplog.set_level(logging.WARNING, logger="pc.loops")
    stop_event = Event()
    reads = {"n": 0}

    def scripted_read_frame() -> tuple[bool, np.ndarray | None]:
        # 100 failures (one warning), one good read (resets the streak),
        # 100 more failures (second warning), then stop.
        reads["n"] += 1
        n = reads["n"]
        if n == 101:
            return True, np.zeros((2, 2, 3), dtype=np.uint8)
        if n > 201:
            stop_event.set()
        return False, None

    capture_loop(
        read_frame=scripted_read_frame,
        frame_slot=LatestSlot(),
        stop_event=stop_event,
        capture_done=Event(),
        retry_on_failure=True,
        retry_sleep_s=0.0,
    )

    warnings = [
        record for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert len(warnings) == 2
    assert all("consecutive failed reads" in w.getMessage() for w in warnings)
