from __future__ import annotations

import io

import numpy as np
import pytest

from jetson.ingest import parse_stream
from jetson.preprocess import estimate_breath_rate
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


def test_recovers_breath_rate_within_2_bpm():
    """Simulator hard-codes 0.3 Hz (18 bpm); estimator must land within ±2 bpm."""
    amps = _simulate_amps("breathing", duration_s=30.0, seed=42)
    est = estimate_breath_rate(amps, sample_rate_hz=100.0)
    assert abs(est.rate_bpm - 18.0) < 2.0
    assert est.frequency_hz == pytest.approx(0.3, abs=0.05)


def test_breathing_confidence_higher_than_idle():
    """A clean breathing peak should dominate noise by >=5x in PSD ratio."""
    breathing = estimate_breath_rate(
        _simulate_amps("breathing", duration_s=30.0, seed=7),
        sample_rate_hz=100.0,
    )
    idle = estimate_breath_rate(
        _simulate_amps("idle", duration_s=30.0, seed=7),
        sample_rate_hz=100.0,
    )
    assert breathing.confidence > idle.confidence * 5


def test_recovers_breath_rate_across_seeds():
    """The estimator is not lucky on one seed."""
    errors = []
    for seed in (1, 13, 31, 99, 314):
        amps = _simulate_amps("breathing", duration_s=30.0, seed=seed)
        est = estimate_breath_rate(amps, sample_rate_hz=100.0)
        errors.append(abs(est.rate_bpm - 18.0))
    assert max(errors) < 2.0, f"per-seed errors: {errors}"


def test_too_short_window_raises():
    """Caller should get a clear error if the window cannot resolve the band."""
    amps = _simulate_amps("breathing", duration_s=1.0, seed=42)
    with pytest.raises(ValueError, match="samples to detect"):
        estimate_breath_rate(amps, sample_rate_hz=100.0)


def test_band_above_nyquist_raises():
    amps = _simulate_amps("idle", duration_s=30.0, seed=42)
    with pytest.raises(ValueError, match="Nyquist"):
        estimate_breath_rate(amps, sample_rate_hz=100.0, band_hz=(0.1, 80.0))
