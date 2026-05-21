from __future__ import annotations

import json
import socket
from threading import Thread

from jetson.pipeline import PipelineResult, TCPSocketEmitter
from jetson.preprocess import BreathRateEstimate, MotionEstimate, MotionState
from pc.fusion import TelemetryBuffer, TimestampAligner
from pc.telemetry import parse_telemetry_payload


def test_timestamp_aligner_smooths_transport_offset():
    aligner = TimestampAligner(smoothing=0.5)
    offset_a = aligner.observe(1_000_000, 1_120_000)
    offset_b = aligner.observe(1_100_000, 1_215_000)
    assert offset_a == 120_000
    assert offset_b == 117_500
    assert aligner.to_local_us(1_200_000) == 1_317_500


def test_telemetry_buffer_matches_nearest_fresh_sample():
    buffer = TelemetryBuffer()
    sample_a = parse_telemetry_payload(
        {
            "timestamp_us": 1_000_000,
            "breath_rate_bpm": 12.0,
            "breath_confidence": 8.0,
            "motion_state": "presence",
            "motion_score": 1.5,
        },
        received_monotonic_us=1_120_000,
    )
    sample_b = parse_telemetry_payload(
        {
            "timestamp_us": 1_080_000,
            "breath_rate_bpm": 13.0,
            "breath_confidence": 9.0,
            "motion_state": "movement",
            "motion_score": 4.0,
        },
        received_monotonic_us=1_205_000,
    )
    buffer.add(sample_a)
    buffer.add(sample_b)

    fused = buffer.match(1_206_000, max_age_ms=400.0, max_skew_ms=50.0)
    assert fused is not None
    assert fused.sample.motion_state == "movement"
    assert fused.sample.breath_rate_bpm == 13.0
    assert fused.skew_ms <= 10.0


def test_parse_telemetry_payload_validates_shape():
    sample = parse_telemetry_payload(
        {
            "timestamp_us": 42,
            "breath_rate_bpm": 18,
            "breath_confidence": 7.5,
            "motion_state": "idle",
            "motion_score": 0.2,
        },
        received_monotonic_us=100,
    )
    assert sample.timestamp_us == 42
    assert sample.breath_rate_bpm == 18.0
    assert sample.motion_state == "idle"


def test_tcp_socket_emitter_streams_one_json_payload():
    server = socket.create_server(("127.0.0.1", 0))
    host, port = server.getsockname()
    received: list[str] = []

    def _accept_once() -> None:
        with server:
            conn, _addr = server.accept()
            with conn:
                with conn.makefile("r", encoding="utf-8") as stream:
                    received.append(stream.readline())

    worker = Thread(target=_accept_once, daemon=True)
    worker.start()

    emitter = TCPSocketEmitter(host=host, port=port)
    result = PipelineResult(
        timestamp_us=123,
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
    emitter.emit(result)
    emitter.close()
    worker.join(timeout=2.0)

    payload = json.loads(received[0])
    assert payload["timestamp_us"] == 123
    assert payload["breath_rate_bpm"] == 12.5
    assert payload["motion_state"] == "presence"
