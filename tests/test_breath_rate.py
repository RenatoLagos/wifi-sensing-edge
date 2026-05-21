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


def _synthetic_amps(
    *,
    sample_rate_hz: float,
    duration_s: float,
    breathing_hz: float,
    n_breathing_subcarriers: int,
    n_confuser_subcarriers: int,
    confuser_hz: float,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(sample_rate_hz * duration_s), dtype=np.float64) / sample_rate_hz
    cols = []

    for _ in range(n_breathing_subcarriers):
        phase = rng.uniform(0.0, 2.0 * np.pi)
        gain = rng.uniform(0.8, 1.2)
        series = gain * np.sin(2.0 * np.pi * breathing_hz * t + phase)
        series += 0.20 * np.sin(2.0 * np.pi * 0.03 * t + phase / 2.0)
        series += rng.normal(scale=0.10, size=t.shape)
        cols.append(series)

    for _ in range(n_confuser_subcarriers):
        phase = rng.uniform(0.0, 2.0 * np.pi)
        gain = rng.uniform(1.8, 2.5)
        series = gain * np.sin(2.0 * np.pi * confuser_hz * t + phase)
        series += 0.30 * np.sin(2.0 * np.pi * 0.02 * t + phase)
        series += rng.normal(scale=0.18, size=t.shape)
        cols.append(series)

    return np.stack(cols, axis=1)


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


def test_recovers_breath_rate_at_realistic_jetson_sample_rate():
    amps = _synthetic_amps(
        sample_rate_hz=12.5,
        duration_s=60.0,
        breathing_hz=0.20,
        n_breathing_subcarriers=12,
        n_confuser_subcarriers=0,
        confuser_hz=0.40,
        seed=123,
    )
    est = estimate_breath_rate(amps, sample_rate_hz=12.5)
    assert abs(est.rate_bpm - 12.0) < 2.0


def test_majority_frequency_consensus_beats_stronger_outlier_subcarriers():
    amps = _synthetic_amps(
        sample_rate_hz=12.5,
        duration_s=60.0,
        breathing_hz=0.30,
        n_breathing_subcarriers=8,
        n_confuser_subcarriers=4,
        confuser_hz=0.45,
        seed=7,
    )
    est = estimate_breath_rate(amps, sample_rate_hz=12.5, top_k_subcarriers=8)
    assert abs(est.rate_bpm - 18.0) < 3.0
