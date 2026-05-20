"""Capture parseable CSI lines from a live ESP32 serial stream.

Examples:
    python -m scripts.capture_serial --port /dev/ttyUSB0 --out data/session.csv
    python -m scripts.capture_serial --port /dev/ttyUSB0 --out data/session.csv --duration 30
    python -m scripts.capture_serial --port /dev/ttyUSB0 --out data/session.csv --max-lines 3000
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
import time
from typing import Iterable, TextIO

from jetson.ingest import ParseError, open_serial_port, parse_line
from jetson.ingest.serial import iter_decoded_lines


@dataclass(frozen=True)
class CaptureStats:
    total_lines: int
    valid_lines: int
    invalid_lines: int
    first_timestamp_us: int | None
    last_timestamp_us: int | None


def capture_stream(
    lines: Iterable[str],
    sink: TextIO,
    *,
    strict: bool = False,
    max_lines: int | None = None,
    duration_s: float | None = None,
) -> CaptureStats:
    if max_lines is not None and max_lines <= 0:
        raise ValueError(f"max_lines must be > 0, got {max_lines}")
    if duration_s is not None and duration_s <= 0:
        raise ValueError(f"duration_s must be > 0, got {duration_s}")

    deadline = None if duration_s is None else time.monotonic() + duration_s
    total_lines = 0
    valid_lines = 0
    invalid_lines = 0
    first_timestamp_us: int | None = None
    last_timestamp_us: int | None = None

    for line in lines:
        if deadline is not None and time.monotonic() >= deadline:
            break
        total_lines += 1
        try:
            frame = parse_line(line)
        except ParseError:
            invalid_lines += 1
            if strict:
                raise
            continue

        normalized = line.strip()
        sink.write(normalized + "\n")
        valid_lines += 1
        if first_timestamp_us is None:
            first_timestamp_us = frame.timestamp_us
        last_timestamp_us = frame.timestamp_us

        if max_lines is not None and valid_lines >= max_lines:
            break

    sink.flush()
    return CaptureStats(
        total_lines=total_lines,
        valid_lines=valid_lines,
        invalid_lines=invalid_lines,
        first_timestamp_us=first_timestamp_us,
        last_timestamp_us=last_timestamp_us,
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", required=True, help="serial device, e.g. /dev/ttyUSB0")
    p.add_argument("--out", required=True, help="output CSV path")
    p.add_argument("--baudrate", type=int, default=115200)
    p.add_argument("--serial-timeout", type=float, default=1.0)
    p.add_argument(
        "--duration", type=float, default=None, help="capture duration in seconds"
    )
    p.add_argument(
        "--max-lines", type=int, default=None, help="stop after N valid CSI lines"
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="fail on the first malformed line instead of skipping it",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"capturing serial CSI from {args.port} -> {out_path}",
        file=sys.stderr,
    )
    if args.duration is None and args.max_lines is None:
        print("stop with Ctrl+C", file=sys.stderr)

    try:
        with (
            open_serial_port(
                args.port,
                baudrate=args.baudrate,
                timeout=args.serial_timeout,
            ) as conn,
            out_path.open("w", encoding="utf-8") as sink,
        ):
            stats = capture_stream(
                iter_decoded_lines(conn),
                sink,
                strict=args.strict,
                max_lines=args.max_lines,
                duration_s=args.duration,
            )
    except KeyboardInterrupt:
        print("capture interrupted", file=sys.stderr)
        return 130

    span_s = None
    if stats.first_timestamp_us is not None and stats.last_timestamp_us is not None:
        span_s = (stats.last_timestamp_us - stats.first_timestamp_us) / 1_000_000.0

    print(f"valid lines      {stats.valid_lines}")
    print(f"invalid lines    {stats.invalid_lines}")
    print(f"total lines      {stats.total_lines}")
    if span_s is not None and span_s > 0:
        print(f"capture span s   {span_s:.2f}")
        print(f"valid rate hz    {stats.valid_lines / span_s:.2f}")
    print(f"output           {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
