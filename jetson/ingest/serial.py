from __future__ import annotations

from typing import Iterator, Protocol

from jetson.ingest.parser import parse_stream
from jetson.ingest.types import CSIFrame


class BinaryLineSource(Protocol):
    def readline(self) -> bytes: ...


def open_serial_port(
    port: str,
    *,
    baudrate: int = 115200,
    timeout: float = 1.0,
):
    try:
        import serial
    except ImportError as exc:
        raise RuntimeError(
            "pyserial is required for live ESP32 ingest; install requirements.txt"
        ) from exc

    return serial.Serial(port=port, baudrate=baudrate, timeout=timeout)


def iter_decoded_lines(
    source: BinaryLineSource,
    *,
    stop_on_empty: bool = False,
) -> Iterator[str]:
    while True:
        raw = source.readline()
        if raw == b"":
            if stop_on_empty:
                return
            continue
        yield raw.decode("utf-8", errors="replace")


def iter_serial_frames(
    source: BinaryLineSource,
    *,
    strict: bool = False,
    stop_on_empty: bool = False,
) -> Iterator[CSIFrame]:
    yield from parse_stream(
        iter_decoded_lines(source, stop_on_empty=stop_on_empty),
        strict=strict,
    )
