from __future__ import annotations

from dataclasses import dataclass
import json
import socket
from threading import Event, Lock, Thread
import time
from typing import Callable


@dataclass(frozen=True)
class WifiTelemetrySample:
    timestamp_us: int
    received_monotonic_us: int
    breath_rate_bpm: float | None
    breath_confidence: float | None
    motion_state: str | None
    motion_score: float | None


@dataclass(frozen=True)
class TelemetryServerStatus:
    host: str
    port: int
    connected: bool
    connections_accepted: int
    disconnects: int
    samples_received: int
    parse_errors: int
    last_sample_monotonic_us: int | None
    last_error: str | None


def parse_telemetry_payload(
    payload: dict[str, object],
    *,
    received_monotonic_us: int,
) -> WifiTelemetrySample:
    timestamp_raw = payload.get("timestamp_us")
    if not isinstance(timestamp_raw, int):
        raise ValueError(f"timestamp_us must be an integer, got {timestamp_raw!r}")

    def _float_or_none(key: str) -> float | None:
        value = payload.get(key)
        if value is None:
            return None
        if not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be numeric or null, got {value!r}")
        return float(value)

    motion_state = payload.get("motion_state")
    if motion_state is not None and not isinstance(motion_state, str):
        raise ValueError(f"motion_state must be a string or null, got {motion_state!r}")

    return WifiTelemetrySample(
        timestamp_us=timestamp_raw,
        received_monotonic_us=received_monotonic_us,
        breath_rate_bpm=_float_or_none("breath_rate_bpm"),
        breath_confidence=_float_or_none("breath_confidence"),
        motion_state=motion_state,
        motion_score=_float_or_none("motion_score"),
    )


class TelemetryServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        on_sample: Callable[[WifiTelemetrySample], None],
    ) -> None:
        self._host = host
        self._port = port
        self._on_sample = on_sample
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._listener: socket.socket | None = None
        self._lock = Lock()
        self._connected = False
        self._connections_accepted = 0
        self._disconnects = 0
        self._samples_received = 0
        self._parse_errors = 0
        self._last_sample_monotonic_us: int | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("telemetry server already started")
        self._thread = Thread(target=self._run, name="telemetry-server", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def status(self) -> TelemetryServerStatus:
        with self._lock:
            return TelemetryServerStatus(
                host=self._host,
                port=self._port,
                connected=self._connected,
                connections_accepted=self._connections_accepted,
                disconnects=self._disconnects,
                samples_received=self._samples_received,
                parse_errors=self._parse_errors,
                last_sample_monotonic_us=self._last_sample_monotonic_us,
                last_error=self._last_error,
            )

    def _run(self) -> None:
        try:
            with socket.create_server(
                (self._host, self._port), reuse_port=False
            ) as server:
                server.settimeout(0.5)
                self._listener = server
                while not self._stop_event.is_set():
                    try:
                        conn, _addr = server.accept()
                    except TimeoutError:
                        continue
                    except OSError as exc:
                        if self._stop_event.is_set():
                            break
                        self._set_error(str(exc))
                        continue
                    with conn:
                        self._register_connect()
                        try:
                            self._serve_connection(conn)
                        finally:
                            self._register_disconnect()
        except OSError as exc:
            if not self._stop_event.is_set():
                self._set_error(str(exc))
        finally:
            self._listener = None
            self._set_connected(False)

    def _serve_connection(self, conn: socket.socket) -> None:
        # Raw recv with manual line splitting: unlike makefile readers, a
        # recv timeout consumes no data and the socket stays readable, so an
        # idle link can be polled without tearing down the connection.
        conn.settimeout(0.5)
        buffer = b""
        while not self._stop_event.is_set():
            try:
                chunk = conn.recv(4096)
            except TimeoutError:
                # An idle link is healthy; keep waiting for the next line.
                continue
            except OSError as exc:
                self._set_error(str(exc))
                return
            if not chunk:
                if buffer:
                    self._handle_payload_line(buffer)
                return
            buffer += chunk
            while True:
                line, newline, rest = buffer.partition(b"\n")
                if not newline:
                    buffer = line
                    break
                buffer = rest
                self._handle_payload_line(line)

    def _handle_payload_line(self, line: bytes) -> None:
        received_monotonic_us = time.monotonic_ns() // 1_000
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
            sample = parse_telemetry_payload(
                payload,
                received_monotonic_us=received_monotonic_us,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            self._increment_parse_errors(str(exc))
            return
        self._on_sample(sample)
        with self._lock:
            self._samples_received += 1
            self._last_sample_monotonic_us = received_monotonic_us
            self._last_error = None

    def _increment_parse_errors(self, message: str) -> None:
        with self._lock:
            self._parse_errors += 1
            self._last_error = message

    def _set_connected(self, connected: bool) -> None:
        with self._lock:
            self._connected = connected

    def _register_connect(self) -> None:
        with self._lock:
            self._connected = True
            self._connections_accepted += 1

    def _register_disconnect(self) -> None:
        with self._lock:
            self._connected = False
            self._disconnects += 1

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message
