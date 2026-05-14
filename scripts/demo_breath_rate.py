"""End-to-end synthetic demo: simulator -> ingest parser -> breath rate.

Proves the algorithm works before real CSI lands. The exact same code path
will run on the Jetson when the ESP32 streams real packets — only the input
source changes (UART read instead of in-memory simulator).

Run from the repo root as a module so `jetson` and `scripts` resolve:

    python -m scripts.demo_breath_rate
    python -m scripts.demo_breath_rate --mode walking
    python -m scripts.demo_breath_rate --duration 60 --plot psd.png
"""
from __future__ import annotations

import argparse
import io
import sys

import numpy as np

from jetson.ingest import parse_stream
from jetson.preprocess import estimate_breath_rate
from scripts import csi_simulator


def _maybe_plot(amps: np.ndarray, sample_rate_hz: float, out_path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy import signal as scipy_signal

    detrended = scipy_signal.detrend(amps.astype(np.float64), axis=0, type="linear")
    freqs = np.fft.rfftfreq(amps.shape[0], d=1.0 / sample_rate_hz)
    psd_per_sub = np.abs(np.fft.rfft(detrended, axis=0)) ** 2

    fig, (ax_time, ax_freq) = plt.subplots(2, 1, figsize=(10, 6))
    t = np.arange(amps.shape[0]) / sample_rate_hz
    mean_amp = amps.mean(axis=1)
    ax_time.plot(t, mean_amp, lw=0.7)
    ax_time.set_xlabel("time (s)")
    ax_time.set_ylabel("mean amplitude across subcarriers")
    ax_time.set_title("CSI amplitude over time")

    band_mask = (freqs > 0) & (freqs < 1.5)
    ax_freq.plot(freqs[band_mask], psd_per_sub[band_mask].sum(axis=1), lw=0.9)
    ax_freq.axvspan(0.1, 0.5, alpha=0.15, color="green", label="breathing band")
    ax_freq.set_xlabel("frequency (Hz)")
    ax_freq.set_ylabel("combined PSD")
    ax_freq.set_title("Power spectrum (summed over subcarriers)")
    ax_freq.legend()

    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    print(f"plot saved: {out_path}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=csi_simulator.MODES, default="breathing")
    p.add_argument("--rate", type=float, default=100.0, help="packets per second")
    p.add_argument("--duration", type=float, default=30.0, help="seconds")
    p.add_argument("--subcarriers", type=int, default=52)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--plot", type=str, default=None, help="save PSD plot to this path")
    args = p.parse_args(argv)

    buf = io.StringIO()
    n = csi_simulator.stream(
        mode=args.mode,
        rate_hz=args.rate,
        duration_s=args.duration,
        num_subcarriers=args.subcarriers,
        seed=args.seed,
        sink=buf,
    )
    buf.seek(0)
    amps = np.stack([f.amps for f in parse_stream(buf)])
    est = estimate_breath_rate(amps, sample_rate_hz=args.rate)

    print(f"mode               {args.mode}")
    print(f"window             {args.duration}s @ {args.rate} Hz  ({n} packets)")
    print(f"rate (bpm)         {est.rate_bpm:.2f}")
    print(f"peak (Hz)          {est.frequency_hz:.4f}")
    print(f"confidence         {est.confidence:.2f}  (peak / median in-band)")
    print(f"subcarriers used   {est.n_subcarriers_used}")
    if args.mode == "breathing":
        truth_bpm = 0.3 * 60
        err = abs(est.rate_bpm - truth_bpm)
        print(f"ground truth bpm   {truth_bpm:.1f}    |error| {err:.2f} bpm")

    if args.plot:
        _maybe_plot(amps, args.rate, args.plot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
