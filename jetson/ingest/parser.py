from __future__ import annotations

from typing import Iterable, Iterator, TextIO
import numpy as np

from jetson.ingest.types import CSIFrame


class ParseError(ValueError):
    pass


def parse_line(line: str) -> CSIFrame:
    """Parse one CSV line in the ESP32 -> Jetson UART format.

    Format (see docs/architecture.md):
        timestamp_us,rssi,channel,subcarrier_count,
        csi_amp_0,csi_phase_0,csi_amp_1,csi_phase_1,...
    """
    stripped = line.strip()
    if not stripped:
        raise ParseError("empty line")

    parts = stripped.split(",")
    if len(parts) < 4:
        raise ParseError(f"expected at least 4 header fields, got {len(parts)}")

    try:
        timestamp_us = int(parts[0])
        rssi = int(parts[1])
        channel = int(parts[2])
        subcarrier_count = int(parts[3])
    except ValueError as e:
        raise ParseError(f"header fields not all integers: {e}") from e

    expected_fields = 4 + 2 * subcarrier_count
    if len(parts) != expected_fields:
        raise ParseError(
            f"declared {subcarrier_count} subcarriers => expected "
            f"{expected_fields} fields, got {len(parts)}"
        )

    body = parts[4:]
    try:
        amps = np.asarray(body[0::2], dtype=np.float32)
        phases = np.asarray(body[1::2], dtype=np.float32)
    except ValueError as e:
        raise ParseError(f"non-numeric CSI field: {e}") from e

    return CSIFrame(
        timestamp_us=timestamp_us,
        rssi=rssi,
        channel=channel,
        amps=amps,
        phases=phases,
    )


def parse_stream(
    source: TextIO | Iterable[str],
    *,
    strict: bool = True,
) -> Iterator[CSIFrame]:
    """Parse a line-delimited stream into a sequence of CSI frames.

    When `strict=False`, malformed lines are skipped silently instead of raising.
    """
    for raw in source:
        try:
            yield parse_line(raw)
        except ParseError:
            if strict:
                raise
            continue
