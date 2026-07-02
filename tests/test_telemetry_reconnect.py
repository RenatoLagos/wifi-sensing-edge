from __future__ import annotations

import json
import socket
import time
from threading import Thread
from typing import Callable

import pytest

from jetson.pipeline import PipelineResult, TCPSocketEmitter
from jetson.preprocess import BreathRateEstimate, MotionEstimate, MotionState
from pc.telemetry import TelemetryServer


def _free_port() -> int:
    with socket.create_server(("127.0.0.1", 0)) as probe:
        return probe.getsockname()[1]


def _result(timestamp_us: int = 123) -> PipelineResult:
    return PipelineResult(
        timestamp_us=timestamp_us,
        breath_rate=BreathRateEstimate(
            rate_bpm=12.5,
            frequency_hz=12.5 / 60.0,
            confidence=9.0,
            n_subcarriers_used=8,
        ),
        motion=MotionEstimate(
            state=MotionState.PRESENCE,
            motion_score=1.75,
            n_subcarriers_used=6,
        ),
    )


def _line(timestamp_us: int) -> bytes:
    return (
        json.dumps(
            {
                "timestamp_us": timestamp_us,
                "breath_rate_bpm": 12.0,
                "breath_confidence": 8.0,
                "motion_state": "idle",
                "motion_score": 0.2,
            }
        )
        + "\n"
    ).encode("utf-8")


def _wait_until(predicate: Callable[[], bool], timeout_s: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def _pump_until(
    emitter: TCPSocketEmitter,
    predicate: Callable[[], bool],
    *,
    timestamp_us: int,
    timeout_s: float = 5.0,
) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        emitter.emit(_result(timestamp_us))
        time.sleep(0.005)
    return predicate()


def _accept_and_read_line(server: socket.socket, sink: list[str]) -> None:
    with server:
        conn, _addr = server.accept()
        with conn:
            with conn.makefile("r", encoding="utf-8") as stream:
                sink.append(stream.readline())


def _connect_with_retry(port: int, timeout_s: float = 2.0) -> socket.socket:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=1.0)
        except OSError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.01)


def test_emitter_drops_without_raising_when_no_server_listening():
    emitter = TCPSocketEmitter(
        host="127.0.0.1",
        port=_free_port(),
        connect_timeout=0.5,
        reconnect_initial_delay_s=0.2,
        reconnect_backoff_multiplier=2.0,
        reconnect_max_delay_s=0.4,
        reconnect_jitter_s=0.0,
    )
    try:
        for _ in range(3):
            emitter.emit(_result())
        assert _wait_until(lambda: emitter.stats().last_backoff_s > 0.0)
        stats = emitter.stats()
    finally:
        emitter.close()
    assert not stats.connected
    assert stats.dropped_results == 3
    assert stats.connect_attempts >= 1
    assert stats.reconnects == 0
    assert 0.0 < stats.last_backoff_s <= 0.4 + 1e-9


def test_emitter_backoff_schedule_grows_to_cap():
    emitter = TCPSocketEmitter(
        host="127.0.0.1",
        port=_free_port(),
        connect_timeout=0.5,
        reconnect_initial_delay_s=0.01,
        reconnect_backoff_multiplier=2.0,
        reconnect_max_delay_s=0.04,
        reconnect_jitter_s=0.0,
    )
    observed: list[float] = []
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            stats = emitter.stats()
            backoff = stats.last_backoff_s
            if backoff > 0.0 and (not observed or observed[-1] != backoff):
                observed.append(backoff)
            if stats.connect_attempts >= 4 and backoff >= 0.04 - 1e-9:
                break
            time.sleep(0.002)
        stats = emitter.stats()
    finally:
        emitter.close()
    assert stats.connect_attempts >= 4
    assert not stats.connected
    assert stats.reconnects == 0
    assert observed == sorted(observed)
    assert observed[-1] == pytest.approx(0.04)
    assert all(0.01 - 1e-9 <= backoff <= 0.04 + 1e-9 for backoff in observed)


def test_emitter_reconnects_after_connection_loss():
    port = _free_port()
    emitter = TCPSocketEmitter(
        host="127.0.0.1",
        port=port,
        connect_timeout=1.0,
        reconnect_initial_delay_s=0.01,
        reconnect_backoff_multiplier=2.0,
        reconnect_max_delay_s=0.05,
        reconnect_jitter_s=0.0,
    )
    try:
        emitter.emit(_result())
        assert emitter.stats().dropped_results == 1

        first: list[str] = []
        server_a = socket.create_server(("127.0.0.1", port))
        worker_a = Thread(
            target=_accept_and_read_line, args=(server_a, first), daemon=True
        )
        worker_a.start()
        assert _pump_until(emitter, lambda: bool(first), timestamp_us=111)
        worker_a.join(timeout=2.0)
        stats = emitter.stats()
        assert stats.connected
        assert stats.reconnects == 0

        second: list[str] = []
        server_b = socket.create_server(("127.0.0.1", port))
        worker_b = Thread(
            target=_accept_and_read_line, args=(server_b, second), daemon=True
        )
        worker_b.start()
        assert _pump_until(emitter, lambda: bool(second), timestamp_us=222)
        worker_b.join(timeout=2.0)
        stats = emitter.stats()
    finally:
        emitter.close()

    assert json.loads(first[0])["timestamp_us"] == 111
    assert json.loads(second[0])["timestamp_us"] == 222
    assert stats.reconnects == 1
    assert stats.dropped_results >= 1


def test_connect_success_after_close_is_discarded(monkeypatch):
    with socket.create_server(("127.0.0.1", 0)) as listener:
        host, port = listener.getsockname()
        emitter_holder: list[TCPSocketEmitter] = []
        handed_over: list[socket.socket] = []
        real_create_connection = socket.create_connection

        def _stop_then_connect(address, timeout=None):
            deadline = time.monotonic() + 2.0
            while not emitter_holder and time.monotonic() < deadline:
                time.sleep(0.001)
            # Simulate close() winning the race against an in-flight connect.
            emitter_holder[0]._stop_event.set()
            sock = real_create_connection(address, timeout=timeout)
            handed_over.append(sock)
            return sock

        monkeypatch.setattr(socket, "create_connection", _stop_then_connect)
        emitter = TCPSocketEmitter(
            host=host,
            port=port,
            connect_timeout=0.5,
            reconnect_initial_delay_s=0.01,
            reconnect_backoff_multiplier=2.0,
            reconnect_max_delay_s=0.05,
            reconnect_jitter_s=0.0,
        )
        emitter_holder.append(emitter)
        try:
            assert _wait_until(
                lambda: bool(handed_over) and handed_over[0].fileno() == -1
            )
            stats = emitter.stats()
        finally:
            emitter.close()
        assert not stats.connected
        assert stats.connect_attempts == 1
        assert stats.reconnects == 0
        assert not emitter._connector.is_alive()


def test_close_stops_connector_thread():
    emitter = TCPSocketEmitter(
        host="127.0.0.1",
        port=_free_port(),
        connect_timeout=0.5,
        reconnect_initial_delay_s=0.05,
        reconnect_backoff_multiplier=2.0,
        reconnect_max_delay_s=0.2,
        reconnect_jitter_s=0.0,
    )
    assert _wait_until(lambda: emitter.stats().connect_attempts >= 1)
    emitter.close()
    assert not emitter._connector.is_alive()


def test_server_accepts_next_client_after_disconnect():
    port = _free_port()
    samples = []
    server = TelemetryServer(host="127.0.0.1", port=port, on_sample=samples.append)
    server.start()
    try:
        client_a = _connect_with_retry(port)
        with client_a:
            client_a.sendall(_line(timestamp_us=1_000_000))
            assert _wait_until(lambda: len(samples) == 1)
        assert _wait_until(lambda: server.status().disconnects == 1)

        client_b = _connect_with_retry(port)
        with client_b:
            client_b.sendall(_line(timestamp_us=2_000_000))
            assert _wait_until(lambda: len(samples) == 2)
            status = server.status()
            assert status.connected
            assert status.connections_accepted == 2
            assert status.disconnects == 1
    finally:
        server.stop()


def test_server_keeps_idle_connection_across_read_timeouts():
    port = _free_port()
    samples = []
    server = TelemetryServer(host="127.0.0.1", port=port, on_sample=samples.append)
    server.start()
    try:
        client = _connect_with_retry(port)
        with client:
            client.sendall(_line(timestamp_us=1_000_000))
            assert _wait_until(lambda: len(samples) == 1)
            time.sleep(0.7)
            status = server.status()
            assert status.connected
            assert status.disconnects == 0
            client.sendall(_line(timestamp_us=2_000_000))
            assert _wait_until(lambda: len(samples) == 2)
            status = server.status()
            assert status.connections_accepted == 1
            assert status.disconnects == 0
    finally:
        server.stop()
