"""End-to-end pipeline demo: simulator -> ingest -> pipeline -> emitter.

This is the demo the dashboard runs once real ESP32 hardware is attached.
Until then it drives the same code path from the synthetic CSI simulator.

Examples:
    python -m scripts.demo_pipeline                                # default: dashboard, breathing, 60s
    python -m scripts.demo_pipeline --mode walking --duration 20
    python -m scripts.demo_pipeline --emitter stdout --no-realtime
    python -m scripts.demo_pipeline --emitter jsonl > stream.jsonl
    python -m scripts.demo_pipeline --source serial --serial-port /dev/ttyUSB0
    python -m scripts.demo_pipeline --source capture --capture-file data/clean_capture_64.csv --rate 12.5 --emitter stdout
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

from jetson.ingest import iter_serial_frames, open_serial_port, parse_line, parse_stream
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


def _iter_capture_frames(*, path: str, strict: bool):
    with Path(path).open(encoding="utf-8") as source:
        yield from parse_stream(source, strict=strict)


def _iter_subcarrier_filtered_frames(frames, *, expected_subcarriers: int | None):
    for frame in frames:
        if (
            expected_subcarriers is None
            or frame.num_subcarriers == expected_subcarriers
        ):
            yield frame


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--source", choices=["simulator", "serial", "capture"], default="simulator"
    )
    p.add_argument("--mode", choices=csi_simulator.MODES, default="breathing")
    p.add_argument("--rate", type=float, default=100.0)
    p.add_argument("--duration", type=float, default=60.0)
    p.add_argument("--subcarriers", type=int, default=52)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--serial-port", type=str, default=None)
    p.add_argument("--capture-file", type=str, default=None)
    p.add_argument("--baudrate", type=int, default=115200)
    p.add_argument("--serial-timeout", type=float, default=1.0)
    p.add_argument(
        "--subcarrier-filter",
        type=int,
        default=None,
        help="drop frames whose subcarrier count does not match this value",
    )
    p.add_argument(
        "--strict-input",
        dest="strict_input",
        action="store_true",
        help="fail on malformed serial or capture lines instead of skipping them",
    )
    p.add_argument(
        "--strict-serial",
        dest="strict_input",
        action="store_true",
        help=argparse.SUPPRESS,
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
    if args.source == "capture" and not args.capture_file:
        p.error("--capture-file is required when --source capture")

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
    elif args.source == "serial":
        frames = _iter_live_serial_frames(
            port=args.serial_port,
            baudrate=args.baudrate,
            timeout=args.serial_timeout,
            strict=args.strict_input,
        )
    else:
        frames = _iter_capture_frames(path=args.capture_file, strict=args.strict_input)

    frames = _iter_subcarrier_filtered_frames(
        frames,
        expected_subcarriers=args.subcarrier_filter,
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
