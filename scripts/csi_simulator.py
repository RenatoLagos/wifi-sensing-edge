"""Synthetic CSI stream generator.

Emits line-delimited CSV in the same format the ESP32 firmware will use,
so the rest of the pipeline can be exercised before real hardware arrives.

Usage:
    python scripts/csi_simulator.py --mode breathing --rate 100 --duration 5
    python scripts/csi_simulator.py --mode walking --output sample.csv
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from typing import Literal, TextIO

import numpy as np

Mode = Literal["idle", "presence", "breathing", "walking"]
MODES: tuple[Mode, ...] = ("idle", "presence", "breathing", "walking")


def _amplitude_baseline(num_subcarriers: int, rng: np.random.Generator) -> np.ndarray:
    base = 30.0 + 5.0 * rng.standard_normal(num_subcarriers)
    return base.astype(np.float32)


def _phase_baseline(num_subcarriers: int, rng: np.random.Generator) -> np.ndarray:
    return rng.uniform(-math.pi, math.pi, num_subcarriers).astype(np.float32)


def _step(
    mode: Mode,
    t_seconds: float,
    base_amp: np.ndarray,
    base_phase: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    n = base_amp.shape[0]
    if mode == "idle":
        amp_noise = 0.3 * rng.standard_normal(n)
        phase_noise = 0.02 * rng.standard_normal(n)
    elif mode == "presence":
        amp_noise = 2.0 * rng.standard_normal(n)
        phase_noise = 0.1 * rng.standard_normal(n)
    elif mode == "breathing":
        modulation = 1.5 * math.sin(2 * math.pi * 0.3 * t_seconds)
        amp_noise = modulation + 0.3 * rng.standard_normal(n)
        phase_noise = 0.05 * math.sin(2 * math.pi * 0.3 * t_seconds) + 0.02 * rng.standard_normal(n)
    elif mode == "walking":
        amp_noise = 6.0 * rng.standard_normal(n)
        phase_noise = 0.4 * rng.standard_normal(n)
    else:
        raise ValueError(f"unknown mode {mode!r}")

    amps = (base_amp + amp_noise).astype(np.float32)
    phases = ((base_phase + phase_noise + math.pi) % (2 * math.pi) - math.pi).astype(np.float32)
    return amps, phases


def _format_line(
    timestamp_us: int,
    rssi: int,
    channel: int,
    amps: np.ndarray,
    phases: np.ndarray,
) -> str:
    interleaved: list[str] = []
    for a, p in zip(amps, phases):
        interleaved.append(f"{a:.3f}")
        interleaved.append(f"{p:.4f}")
    return ",".join(
        [str(timestamp_us), str(rssi), str(channel), str(amps.shape[0]), *interleaved]
    )


def stream(
    *,
    mode: Mode = "idle",
    rate_hz: float = 100.0,
    duration_s: float = 5.0,
    num_subcarriers: int = 52,
    channel: int = 6,
    rssi: int = -55,
    seed: int | None = None,
    sink: TextIO = sys.stdout,
    realtime: bool = False,
) -> int:
    """Generate synthetic CSI lines into `sink`. Returns total lines emitted."""
    rng = np.random.default_rng(seed)
    base_amp = _amplitude_baseline(num_subcarriers, rng)
    base_phase = _phase_baseline(num_subcarriers, rng)

    n_packets = int(rate_hz * duration_s)
    period_us = int(1_000_000 / rate_hz)
    start_us = 0
    wall_start = time.monotonic()

    for i in range(n_packets):
        t_seconds = i / rate_hz
        amps, phases = _step(mode, t_seconds, base_amp, base_phase, rng)
        line = _format_line(start_us + i * period_us, rssi, channel, amps, phases)
        sink.write(line + "\n")
        if realtime:
            target = wall_start + (i + 1) / rate_hz
            now = time.monotonic()
            if target > now:
                time.sleep(target - now)
    return n_packets


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Synthetic CSI stream generator.")
    p.add_argument("--mode", choices=MODES, default="idle")
    p.add_argument("--rate", type=float, default=100.0, help="packets per second")
    p.add_argument("--duration", type=float, default=5.0, help="seconds")
    p.add_argument("--subcarriers", type=int, default=52, help="HT20=52, HT40=56")
    p.add_argument("--channel", type=int, default=6)
    p.add_argument("--rssi", type=int, default=-55)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--output", type=str, default=None, help="write to file (default stdout)")
    p.add_argument(
        "--realtime",
        action="store_true",
        help="pace emission to wall clock (default: emit as fast as possible)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    sink = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    try:
        n = stream(
            mode=args.mode,
            rate_hz=args.rate,
            duration_s=args.duration,
            num_subcarriers=args.subcarriers,
            channel=args.channel,
            rssi=args.rssi,
            seed=args.seed,
            sink=sink,
            realtime=args.realtime,
        )
    finally:
        if args.output:
            sink.close()
    if args.output:
        print(f"wrote {n} CSI frames to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
