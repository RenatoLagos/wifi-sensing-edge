from __future__ import annotations

import io
import json

import numpy as np
import pytest

from jetson.ingest import parse_stream
from jetson.pipeline import (
    JSONLinesEmitter,
    Pipeline,
    PipelineResult,
    SlidingWindow,
    StdoutEmitter,
)
from jetson.preprocess import MotionState
from scripts import csi_simulator


def _simulator_frames(mode: str, duration_s: float, seed: int = 42):
    buf = io.StringIO()
    csi_simulator.stream(
        mode=mode,  # type: ignore[arg-type]
        rate_hz=100.0,
        duration_s=duration_s,
        num_subcarriers=52,
        seed=seed,
        sink=buf,
    )
    buf.seek(0)
    return list(parse_stream(buf))


def test_sliding_window_basic():
    win = SlidingWindow(max_frames=3)
    frames = _simulator_frames("idle", duration_s=0.1)[:5]
    for f in frames:
        win.append(f)
    assert len(win) == 3
    out = win.amps_last_n(2)
    assert out is not None
    assert out.shape == (2, 52)


def test_sliding_window_returns_none_before_filled():
    win = SlidingWindow(max_frames=10)
    win.append(_simulator_frames("idle", duration_s=0.05)[0])
    assert win.amps_last_n(5) is None


def test_pipeline_emits_results_on_cadence():
    """Pipeline returns a result every `process_every_frames` frames."""
    pipeline = Pipeline(sample_rate_hz=100.0, process_every_frames=50)
    frames = _simulator_frames("presence", duration_s=2.0)
    results = [pipeline.feed(f) for f in frames]
    non_none = [r for r in results if r is not None]
    assert 3 <= len(non_none) <= 5
    for r in non_none:
        assert isinstance(r, PipelineResult)


def test_pipeline_motion_state_correct_for_walking():
    pipeline = Pipeline(sample_rate_hz=100.0, process_every_frames=100)
    frames = _simulator_frames("walking", duration_s=3.0)
    results = [r for r in (pipeline.feed(f) for f in frames) if r is not None]
    motion_results = [r.motion for r in results if r.motion is not None]
    assert motion_results, "expected at least one motion estimate"
    final_state = motion_results[-1].state
    assert final_state == MotionState.MOVEMENT


def test_pipeline_breath_rate_converges_on_breathing():
    """After 30+ seconds of synthetic breathing, the pipeline should report ~18 bpm."""
    pipeline = Pipeline(sample_rate_hz=100.0, process_every_frames=100)
    frames = _simulator_frames("breathing", duration_s=35.0)
    last_breath = None
    for f in frames:
        r = pipeline.feed(f)
        if r is not None and r.breath_rate is not None:
            last_breath = r.breath_rate
    assert last_breath is not None
    assert abs(last_breath.rate_bpm - 18.0) < 2.0


def test_pipeline_breath_rate_is_none_before_window_fills():
    """No breath rate result until the breath window has filled."""
    pipeline = Pipeline(
        sample_rate_hz=100.0,
        breath_window_seconds=30.0,
        process_every_frames=50,
    )
    frames = _simulator_frames("breathing", duration_s=1.0)
    results = [r for r in (pipeline.feed(f) for f in frames) if r is not None]
    breath_results = [r.breath_rate for r in results]
    assert all(b is None for b in breath_results)


def test_jsonl_emitter_writes_one_object_per_emit():
    pipeline = Pipeline(sample_rate_hz=100.0, process_every_frames=100)
    sink = io.StringIO()
    emitter = JSONLinesEmitter(stream=sink)
    for f in _simulator_frames("walking", duration_s=2.0):
        r = pipeline.feed(f)
        if r is not None:
            emitter.emit(r)
    lines = [ln for ln in sink.getvalue().splitlines() if ln]
    assert lines
    for ln in lines:
        payload = json.loads(ln)
        assert set(payload.keys()) >= {
            "timestamp_us",
            "motion_state",
            "motion_score",
            "breath_rate_bpm",
            "breath_confidence",
        }


def test_stdout_emitter_prints_human_readable_line():
    pipeline = Pipeline(sample_rate_hz=100.0, process_every_frames=100)
    sink = io.StringIO()
    emitter = StdoutEmitter(stream=sink)
    for f in _simulator_frames("walking", duration_s=2.0):
        r = pipeline.feed(f)
        if r is not None:
            emitter.emit(r)
    out = sink.getvalue()
    assert "breath:" in out and "motion:" in out


def test_pipeline_rejects_invalid_config():
    with pytest.raises(ValueError, match="sample_rate_hz"):
        Pipeline(sample_rate_hz=0)
    with pytest.raises(ValueError, match="process_every_frames"):
        Pipeline(sample_rate_hz=100.0, process_every_frames=0)
    with pytest.raises(ValueError, match="cannot exceed"):
        Pipeline(
            sample_rate_hz=100.0,
            window_seconds=10.0,
            breath_window_seconds=20.0,
        )
