from __future__ import annotations

import io

import numpy as np
import pytest

from jetson.ingest import parse_stream
from jetson.preprocess import MotionState, estimate_motion
from scripts import csi_simulator


def _simulate_amps(mode: str, duration_s: float, seed: int) -> np.ndarray:
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
    return np.stack([f.amps for f in parse_stream(buf)])


def test_idle_classifies_as_idle():
    amps = _simulate_amps("idle", duration_s=2.0, seed=42)
    est = estimate_motion(amps)
    assert est.state == MotionState.IDLE
    assert est.motion_score < 1.0


def test_presence_classifies_as_presence():
    amps = _simulate_amps("presence", duration_s=2.0, seed=42)
    est = estimate_motion(amps)
    assert est.state == MotionState.PRESENCE


def test_walking_classifies_as_movement():
    amps = _simulate_amps("walking", duration_s=2.0, seed=42)
    est = estimate_motion(amps)
    assert est.state == MotionState.MOVEMENT
    assert est.motion_score >= 15.0


def test_breathing_classifies_as_presence_not_idle():
    """A still-but-breathing person should be detected as present."""
    amps = _simulate_amps("breathing", duration_s=10.0, seed=42)
    est = estimate_motion(amps)
    assert est.state in (MotionState.PRESENCE, MotionState.MOVEMENT)
    assert est.state != MotionState.IDLE


def test_motion_score_monotonic_across_modes():
    """Score should rank: idle < breathing < presence < walking."""
    scores = {
        mode: estimate_motion(_simulate_amps(mode, duration_s=2.0, seed=7)).motion_score
        for mode in ("idle", "breathing", "presence", "walking")
    }
    assert scores["idle"] < scores["breathing"], scores
    assert scores["breathing"] < scores["presence"], scores
    assert scores["presence"] < scores["walking"], scores


def test_too_short_window_raises():
    amps = np.array([[1.0, 2.0, 3.0]])  # single packet
    with pytest.raises(ValueError, match="at least 2 packets"):
        estimate_motion(amps)


def test_invalid_thresholds_raise():
    amps = _simulate_amps("idle", duration_s=1.0, seed=42)
    with pytest.raises(ValueError, match="invalid thresholds"):
        estimate_motion(amps, presence_threshold=5.0, movement_threshold=1.0)
