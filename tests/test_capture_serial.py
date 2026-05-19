from __future__ import annotations

import io

import pytest

from scripts.capture_serial import capture_stream


def test_capture_stream_keeps_only_parseable_lines_in_non_strict_mode():
    lines = [
        "1,-55,6,2,10.0,0.1,11.0,0.2\n",
        "boot log\n",
        "2,-55,6,2,12.0,0.3,13.0,0.4\n",
    ]
    sink = io.StringIO()

    stats = capture_stream(lines, sink, strict=False)

    assert stats.total_lines == 3
    assert stats.valid_lines == 2
    assert stats.invalid_lines == 1
    assert stats.first_timestamp_us == 1
    assert stats.last_timestamp_us == 2
    assert sink.getvalue().splitlines() == [
        "1,-55,6,2,10.0,0.1,11.0,0.2",
        "2,-55,6,2,12.0,0.3,13.0,0.4",
    ]


def test_capture_stream_raises_in_strict_mode():
    lines = ["1,-55,6,2,10.0,0.1,11.0,0.2\n", "bad\n"]

    with pytest.raises(ValueError):
        capture_stream(lines, io.StringIO(), strict=True)


def test_capture_stream_stops_after_max_valid_lines():
    lines = [
        "1,-55,6,2,10.0,0.1,11.0,0.2\n",
        "2,-55,6,2,12.0,0.3,13.0,0.4\n",
        "3,-55,6,2,14.0,0.5,15.0,0.6\n",
    ]
    sink = io.StringIO()

    stats = capture_stream(lines, sink, max_lines=2)

    assert stats.valid_lines == 2
    assert stats.total_lines == 2
    assert sink.getvalue().splitlines() == [
        "1,-55,6,2,10.0,0.1,11.0,0.2",
        "2,-55,6,2,12.0,0.3,13.0,0.4",
    ]
