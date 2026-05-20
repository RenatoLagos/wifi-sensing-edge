"""Filter a captured CSI CSV down to one subcarrier width.

Examples:
    python -m scripts.filter_capture --input data/clean_capture.csv --out data/clean_capture_64.csv
    python -m scripts.filter_capture --input data/clean_capture.csv --out data/clean_capture_128.csv --subcarriers 128
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Iterable, TextIO

from jetson.ingest import ParseError, parse_line


@dataclass(frozen=True)
class CaptureScan:
    total_lines: int
    valid_lines: int
    invalid_lines: int
    counts: Counter[int]


@dataclass(frozen=True)
class FilterResult:
    total_lines: int
    valid_lines: int
    invalid_lines: int
    kept_lines: int
    target_subcarriers: int


def scan_capture_lines(lines: Iterable[str], *, strict: bool = False) -> CaptureScan:
    counts: Counter[int] = Counter()
    total_lines = 0
    valid_lines = 0
    invalid_lines = 0

    for raw in lines:
        total_lines += 1
        try:
            frame = parse_line(raw)
        except ParseError:
            invalid_lines += 1
            if strict:
                raise
            continue
        valid_lines += 1
        counts[frame.num_subcarriers] += 1

    return CaptureScan(
        total_lines=total_lines,
        valid_lines=valid_lines,
        invalid_lines=invalid_lines,
        counts=counts,
    )


def choose_target_subcarriers(
    counts: Counter[int], preferred: int | None = None
) -> int:
    if preferred is not None:
        if counts[preferred] == 0:
            raise ValueError(f"requested subcarrier count {preferred} not present")
        return preferred
    if not counts:
        raise ValueError("no valid CSI lines found")
    return max(counts.items(), key=lambda item: (item[1], item[0]))[0]


def filter_capture_lines(
    lines: Iterable[str],
    sink: TextIO,
    *,
    target_subcarriers: int,
    strict: bool = False,
) -> FilterResult:
    total_lines = 0
    valid_lines = 0
    invalid_lines = 0
    kept_lines = 0

    for raw in lines:
        total_lines += 1
        try:
            frame = parse_line(raw)
        except ParseError:
            invalid_lines += 1
            if strict:
                raise
            continue
        valid_lines += 1
        if frame.num_subcarriers != target_subcarriers:
            continue
        sink.write(raw.strip() + "\n")
        kept_lines += 1

    sink.flush()
    return FilterResult(
        total_lines=total_lines,
        valid_lines=valid_lines,
        invalid_lines=invalid_lines,
        kept_lines=kept_lines,
        target_subcarriers=target_subcarriers,
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, help="input capture CSV path")
    p.add_argument("--out", required=True, help="output filtered CSV path")
    p.add_argument(
        "--subcarriers",
        type=int,
        default=None,
        help="target subcarrier count; defaults to the dominant width",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="fail on malformed lines instead of skipping them",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    input_path = Path(args.input)
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open(encoding="utf-8") as source:
        scan = scan_capture_lines(source, strict=args.strict)

    target = choose_target_subcarriers(scan.counts, preferred=args.subcarriers)

    with (
        input_path.open(encoding="utf-8") as source,
        output_path.open("w", encoding="utf-8") as sink,
    ):
        result = filter_capture_lines(
            source,
            sink,
            target_subcarriers=target,
            strict=args.strict,
        )

    print(f"target_subcarriers: {target}")
    print(f"counts: {dict(sorted(scan.counts.items()))}")
    print(f"kept_lines: {result.kept_lines}")
    print(f"valid_lines: {result.valid_lines}")
    print(f"invalid_lines: {result.invalid_lines}")
    print(f"output: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
