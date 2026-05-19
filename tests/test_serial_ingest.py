from __future__ import annotations

import io

from jetson.ingest import iter_serial_frames
from jetson.ingest.serial import iter_decoded_lines
from scripts import csi_simulator


def test_iter_decoded_lines_stops_on_empty_for_finite_stream():
    source = io.BytesIO(b"first\nsecond\n")
    assert list(iter_decoded_lines(source, stop_on_empty=True)) == [
        "first\n",
        "second\n",
    ]


def test_iter_serial_frames_round_trip_from_binary_stream():
    text_buf = io.StringIO()
    csi_simulator.stream(
        mode="breathing",
        rate_hz=10.0,
        duration_s=0.5,
        num_subcarriers=8,
        seed=7,
        sink=text_buf,
    )
    binary = io.BytesIO(text_buf.getvalue().encode("utf-8"))

    frames = list(iter_serial_frames(binary, stop_on_empty=True, strict=True))

    assert len(frames) == 5
    assert frames[0].amps.shape == (8,)
    assert frames[0].phases.shape == (8,)


def test_iter_serial_frames_skips_bad_lines_in_non_strict_mode():
    source = io.BytesIO(
        b"1,-55,6,2,10.0,0.1,11.0,0.2\ngarbage\n2,-55,6,2,12.0,0.3,13.0,0.4\n"
    )

    frames = list(iter_serial_frames(source, stop_on_empty=True, strict=False))

    assert len(frames) == 2
    assert frames[0].timestamp_us == 1
    assert frames[1].timestamp_us == 2
