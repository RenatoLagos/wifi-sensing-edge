"""End-to-end synthetic demo: simulator -> ingest parser -> motion estimator.

Examples:
    python -m scripts.demo_motion
    python -m scripts.demo_motion --mode walking --duration 2
    python -m scripts.demo_motion --sweep
"""
from __future__ import annotations

import argparse
import io
import sys

import numpy as np

from jetson.ingest import parse_stream
from jetson.preprocess import estimate_motion
from scripts import csi_simulator


def _amps_for(mode: str, duration_s: float, rate_hz: float, seed: int) -> np.ndarray:
    buf = io.StringIO()
    csi_simulator.stream(
        mode=mode,  # type: ignore[arg-type]
        rate_hz=rate_hz,
        duration_s=duration_s,
        num_subcarriers=52,
        seed=seed,
        sink=buf,
    )
    buf.seek(0)
    return np.stack([f.amps for f in parse_stream(buf)])


def _print_estimate(mode: str, est) -> None:
    print(
        f"  mode={mode:9s}  state={est.state.value:9s}  "
        f"score={est.motion_score:8.3f}  subcarriers={est.n_subcarriers_used}"
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=csi_simulator.MODES, default="presence")
    p.add_argument("--rate", type=float, default=100.0)
    p.add_argument("--duration", type=float, default=2.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--sweep",
        action="store_true",
        help="run all four modes and print scores side by side",
    )
    args = p.parse_args(argv)

    if args.sweep:
        print(
            f"sweep: {args.duration}s @ {args.rate} Hz, 52 subcarriers, seed={args.seed}"
        )
        for mode in csi_simulator.MODES:
            amps = _amps_for(mode, args.duration, args.rate, args.seed)
            _print_estimate(mode, estimate_motion(amps))
        return 0

    amps = _amps_for(args.mode, args.duration, args.rate, args.seed)
    est = estimate_motion(amps)
    print(f"mode               {args.mode}")
    print(f"window             {args.duration}s @ {args.rate} Hz")
    print(f"state              {est.state.value}")
    print(f"motion score       {est.motion_score:.3f}")
    print(f"subcarriers used   {est.n_subcarriers_used}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
