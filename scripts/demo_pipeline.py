"""End-to-end pipeline demo: simulator -> ingest -> pipeline -> emitter.

This is the demo the dashboard runs once real ESP32 hardware is attached.
Until then it drives the same code path from the synthetic CSI simulator.

Examples:
    python -m scripts.demo_pipeline                                # default: dashboard, breathing, 60s
    python -m scripts.demo_pipeline --mode walking --duration 20
    python -m scripts.demo_pipeline --emitter stdout --no-realtime
    python -m scripts.demo_pipeline --emitter jsonl > stream.jsonl
    python -m scripts.demo_pipeline --source serial --serial-port /dev/ttyUSB0
"""

from __future__ import annotations

import argparse
import sys
import time

from jetson.ingest import iter_serial_frames, open_serial_port, parse_line
from jetson.pipeline import (
    JSONLinesEmitter,
    LiveDashboardEmitter,
    Pipeline,
    StdoutEmitter,
)
from scripts import csi_simulator


def _iter_simulator_frames(
    *,
    mode: str,
    rate_hz: float,
    duration_s: float,
    num_subcarriers: int,
    seed: int,
    realtime: bool,
):
    """Stream synthetic CSI frames as if they were arriving from UART."""
    import io

    buf = io.StringIO()
    csi_simulator.stream(
        mode=mode,  # type: ignore[arg-type]
        rate_hz=rate_hz,
        duration_s=duration_s,
        num_subcarriers=num_subcarriers,
        seed=seed,
        sink=buf,
    )
    buf.seek(0)
    period_s = 1.0 / rate_hz
    start = time.monotonic()
    for i, line in enumerate(buf):
        yield parse_line(line)
        if realtime:
            target = start + (i + 1) * period_s
            now = time.monotonic()
            if target > now:
                time.sleep(target - now)


def _iter_live_serial_frames(
    *,
    port: str,
    baudrate: int,
    timeout: float,
    strict: bool,
):
    with open_serial_port(port, baudrate=baudrate, timeout=timeout) as conn:
        yield from iter_serial_frames(conn, strict=strict)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", choices=["simulator", "serial"], default="simulator")
    p.add_argument("--mode", choices=csi_simulator.MODES, default="breathing")
    p.add_argument("--rate", type=float, default=100.0)
    p.add_argument("--duration", type=float, default=60.0)
    p.add_argument("--subcarriers", type=int, default=52)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--serial-port", type=str, default=None)
    p.add_argument("--baudrate", type=int, default=921600)
    p.add_argument("--serial-timeout", type=float, default=1.0)
    p.add_argument(
        "--strict-serial",
        action="store_true",
        help="fail on malformed serial lines instead of skipping them",
    )
    p.add_argument(
        "--emitter",
        choices=["dashboard", "stdout", "jsonl"],
        default="dashboard",
    )
    p.add_argument(
        "--no-realtime",
        action="store_true",
        help="run as fast as possible (default: dashboard paces to wall clock)",
    )
    args = p.parse_args(argv)

    if args.source == "serial" and not args.serial_port:
        p.error("--serial-port is required when --source serial")

    pipeline = Pipeline(
        sample_rate_hz=args.rate,
        process_every_frames=int(args.rate),
    )

    if args.source == "simulator":
        realtime_default = args.emitter == "dashboard"
        realtime = realtime_default and not args.no_realtime
        frames = _iter_simulator_frames(
            mode=args.mode,
            rate_hz=args.rate,
            duration_s=args.duration,
            num_subcarriers=args.subcarriers,
            seed=args.seed,
            realtime=realtime,
        )
    else:
        frames = _iter_live_serial_frames(
            port=args.serial_port,
            baudrate=args.baudrate,
            timeout=args.serial_timeout,
            strict=args.strict_serial,
        )

    if args.emitter == "dashboard":
        with LiveDashboardEmitter() as dash:
            for frame in frames:
                result = pipeline.feed(frame)
                if result is not None:
                    dash.emit(result)
        return 0

    emitter = StdoutEmitter() if args.emitter == "stdout" else JSONLinesEmitter()
    try:
        for frame in frames:
            result = pipeline.feed(frame)
            if result is not None:
                emitter.emit(result)
    finally:
        emitter.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
