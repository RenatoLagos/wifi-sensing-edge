"""Breath rate estimation from a window of CSI amplitudes.

Classical signal-processing pipeline. No ML. The point is to have a baseline
that already runs at <50 ms on a Jetson Nano so any ML refinement later has
to beat it on accuracy AND latency.

Pipeline:
  1. Per-subcarrier linear detrend (remove DC + drift).
  2. Bandpass to the respiration band.
  3. Welch PSD per subcarrier for a more stable spectrum on noisy real data.
  4. Score subcarriers by peak sharpness, not raw in-band energy.
  5. Find the dominant frequency cluster across subcarriers.
  6. Combine only subcarriers that agree with that cluster.
  7. Locate the dominant peak and convert it to bpm.
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


def _parabolic_peak_offset(y0: float, y1: float, y2: float) -> float:
    denom = y0 - 2.0 * y1 + y2
    if abs(denom) < 1e-12:
        return 0.0
    return 0.5 * (y0 - y2) / denom


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

    sos = _scipy_signal.butter(
        2,
        [low_hz, high_hz],
        btype="bandpass",
        fs=sample_rate_hz,
        output="sos",
    )
    filtered = _scipy_signal.sosfiltfilt(sos, detrended, axis=0)
    valid_subcarrier_mask = filtered.std(axis=0) > 1e-6
    if not valid_subcarrier_mask.any():
        raise ValueError("all subcarriers are near-constant after bandpass filtering")
    filtered = filtered[:, valid_subcarrier_mask]

    nperseg = min(n_packets, max(64, int(sample_rate_hz * 20.0)))
    noverlap = nperseg // 2
    freqs, spectra = _scipy_signal.welch(
        filtered,
        fs=sample_rate_hz,
        window="hann",
        nperseg=nperseg,
        noverlap=noverlap,
        detrend=False,
        scaling="spectrum",
        axis=0,
    )

    band_mask = (freqs >= low_hz) & (freqs <= high_hz)
    if not band_mask.any():
        raise ValueError(
            f"band {band_hz} has no FFT bins at resolution "
            f"{sample_rate_hz / n_packets:.4f} Hz"
        )

    in_band_per_sub = spectra[band_mask]
    per_sub_median = np.maximum(np.median(in_band_per_sub, axis=0), 1e-12)
    normalized_in_band = in_band_per_sub / per_sub_median
    peak_bin_per_sub = np.argmax(normalized_in_band, axis=0)
    peak_ratio_per_sub = normalized_in_band[
        peak_bin_per_sub, np.arange(normalized_in_band.shape[1])
    ]
    peak_weights = np.maximum(peak_ratio_per_sub - 1.0, 0.0)
    if float(peak_weights.sum()) <= 1e-12:
        peak_weights = peak_ratio_per_sub

    dominant_bin_weights = np.bincount(
        peak_bin_per_sub,
        weights=peak_weights,
        minlength=normalized_in_band.shape[0],
    )
    dominant_bin = int(np.argmax(dominant_bin_weights))
    consensus_mask = np.abs(peak_bin_per_sub - dominant_bin) <= 1

    candidate_scores = peak_ratio_per_sub.copy()
    candidate_scores[~consensus_mask] = -np.inf
    finite_idx = np.flatnonzero(np.isfinite(candidate_scores))
    if finite_idx.size == 0:
        finite_idx = np.arange(peak_ratio_per_sub.size)
        candidate_scores = peak_ratio_per_sub

    k = int(min(top_k_subcarriers, finite_idx.size))
    top_idx = np.argsort(candidate_scores)[-k:]
    selected_in_band = normalized_in_band[:, top_idx]
    combined_in_band = selected_in_band.mean(axis=1)

    in_band_combined = combined_in_band
    in_band_freqs = freqs[band_mask]
    peak_idx = int(np.argmax(in_band_combined))
    peak_power = float(in_band_combined[peak_idx])
    median_in_band = float(np.median(in_band_combined))
    confidence = peak_power / max(median_in_band, 1e-12)

    total_cluster_weight = float(dominant_bin_weights.sum())
    if total_cluster_weight > 1e-12:
        confidence *= float(dominant_bin_weights[dominant_bin]) / total_cluster_weight

    peak_freq = float(in_band_freqs[peak_idx])
    if 0 < peak_idx < len(in_band_combined) - 1:
        bin_width = float(in_band_freqs[1] - in_band_freqs[0])
        offset = _parabolic_peak_offset(
            float(in_band_combined[peak_idx - 1]),
            float(in_band_combined[peak_idx]),
            float(in_band_combined[peak_idx + 1]),
        )
        peak_freq += float(np.clip(offset, -1.0, 1.0)) * bin_width

    return BreathRateEstimate(
        rate_bpm=peak_freq * 60.0,
        frequency_hz=peak_freq,
        confidence=confidence,
        n_subcarriers_used=k,
    )
