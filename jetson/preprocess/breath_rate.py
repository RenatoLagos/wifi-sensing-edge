"""Breath rate estimation from a window of CSI amplitudes.

Classical signal-processing pipeline. No ML. The point is to have a baseline
that already runs at <50 ms on a Jetson Nano so any ML refinement later has
to beat it on accuracy AND latency.

Pipeline:
  1. Per-subcarrier linear detrend (remove DC + drift).
  2. Real FFT per subcarrier; in-band power scores each subcarrier's SNR.
  3. Combine top-K subcarriers (highest in-band power) by PSD summation.
  4. Locate dominant peak in the breathing band.
  5. Convert peak frequency to bpm. Report confidence = peak / in-band median.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal as _scipy_signal


@dataclass(frozen=True)
class BreathRateEstimate:
    rate_bpm: float
    frequency_hz: float
    confidence: float
    n_subcarriers_used: int


def estimate_breath_rate(
    amps: np.ndarray,
    sample_rate_hz: float,
    *,
    band_hz: tuple[float, float] = (0.1, 0.5),
    top_k_subcarriers: int = 10,
) -> BreathRateEstimate:
    """Estimate breath rate from a (time, subcarriers) window of amplitudes.

    Args:
        amps: shape (n_packets, n_subcarriers), CSI amplitude per subcarrier
            over time.
        sample_rate_hz: emission rate of the CSI stream (e.g., 100.0).
        band_hz: (low, high) Hz band where breathing lives. Default 0.1-0.5
            covers 6-30 bpm; relaxed adults sit in 12-18 bpm (0.2-0.3 Hz).
        top_k_subcarriers: number of highest-SNR subcarriers to combine.

    Returns:
        BreathRateEstimate. Confidence is peak power divided by median in-band
        power: clean peaks score >>1, diffuse noise sits near 1.
    """
    if amps.ndim != 2:
        raise ValueError(f"amps must be 2D (time, subcarriers), got shape {amps.shape}")

    n_packets, n_subcarriers = amps.shape
    low_hz, high_hz = band_hz
    if low_hz <= 0 or high_hz <= low_hz:
        raise ValueError(f"invalid band {band_hz}: need 0 < low < high")
    if high_hz > sample_rate_hz / 2:
        raise ValueError(
            f"band high {high_hz} Hz exceeds Nyquist {sample_rate_hz / 2} Hz"
        )

    min_samples_for_band = int(np.ceil(2.0 * sample_rate_hz / low_hz))
    if n_packets < min_samples_for_band:
        raise ValueError(
            f"need >= {min_samples_for_band} samples to detect {low_hz} Hz "
            f"reliably, got {n_packets} "
            f"(window of {n_packets / sample_rate_hz:.2f}s at {sample_rate_hz} Hz)"
        )

    detrended = _scipy_signal.detrend(amps.astype(np.float64), axis=0, type="linear")

    freqs = np.fft.rfftfreq(n_packets, d=1.0 / sample_rate_hz)
    spectra = np.abs(np.fft.rfft(detrended, axis=0)) ** 2  # shape (n_freqs, n_subcarriers)

    band_mask = (freqs >= low_hz) & (freqs <= high_hz)
    if not band_mask.any():
        raise ValueError(
            f"band {band_hz} has no FFT bins at resolution "
            f"{sample_rate_hz / n_packets:.4f} Hz"
        )

    in_band_power_per_sub = spectra[band_mask].sum(axis=0)
    k = int(min(top_k_subcarriers, n_subcarriers))
    top_idx = np.argsort(in_band_power_per_sub)[-k:]
    combined = spectra[:, top_idx].sum(axis=1)

    in_band_combined = combined[band_mask]
    in_band_freqs = freqs[band_mask]
    peak_idx = int(np.argmax(in_band_combined))
    peak_freq = float(in_band_freqs[peak_idx])
    peak_power = float(in_band_combined[peak_idx])
    median_in_band = float(np.median(in_band_combined))
    confidence = peak_power / max(median_in_band, 1e-12)

    return BreathRateEstimate(
        rate_bpm=peak_freq * 60.0,
        frequency_hz=peak_freq,
        confidence=confidence,
        n_subcarriers_used=k,
    )
