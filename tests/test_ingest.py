from __future__ import annotations

import io

import numpy as np
import pytest

from jetson.ingest import CSIFrame, ParseError, parse_line, parse_stream
from scripts import csi_simulator


def test_parse_line_round_trip_small():
    line = "1000,-55,6,2,30.0,0.1,28.5,-0.2"
    frame = parse_line(line)
    assert frame.timestamp_us == 1000
    assert frame.rssi == -55
    assert frame.channel == 6
    assert frame.num_subcarriers == 2
    np.testing.assert_allclose(frame.amps, [30.0, 28.5])
    np.testing.assert_allclose(frame.phases, [0.1, -0.2])


def test_parse_line_wrong_field_count_raises():
    line = "1000,-55,6,2,30.0,0.1,28.5"  # missing one phase
    with pytest.raises(ParseError):
        parse_line(line)


def test_parse_line_non_numeric_raises():
    line = "1000,-55,6,1,abc,0.1"
    with pytest.raises(ParseError):
        parse_line(line)


def test_parse_stream_skips_in_non_strict_mode():
    text = "1000,-55,6,1,30.0,0.1\nMALFORMED\n2000,-55,6,1,29.0,0.2\n"
    frames = list(parse_stream(io.StringIO(text), strict=False))
    assert len(frames) == 2
    assert frames[0].timestamp_us == 1000
    assert frames[1].timestamp_us == 2000


def test_simulator_to_parser_round_trip():
    buf = io.StringIO()
    n = csi_simulator.stream(
        mode="presence",
        rate_hz=100.0,
        duration_s=0.1,
        num_subcarriers=52,
        seed=42,
        sink=buf,
    )
    buf.seek(0)
    frames = list(parse_stream(buf))
    assert len(frames) == n == 10
    for f in frames:
        assert isinstance(f, CSIFrame)
        assert f.num_subcarriers == 52
        assert f.channel == 6
        assert f.rssi == -55


def test_simulator_modes_have_distinct_temporal_variance():
    """Sanity: walking shows much larger over-time amplitude variance than idle.

    We measure variance over time for each subcarrier, then average over
    subcarriers. This isolates the motion signal from the static per-subcarrier
    baseline offset (which is what a real CSI deployment cares about anyway).
    """
    def temporal_variance(mode: str) -> float:
        buf = io.StringIO()
        csi_simulator.stream(
            mode=mode,  # type: ignore[arg-type]
            rate_hz=100.0,
            duration_s=1.0,
            num_subcarriers=52,
            seed=7,
            sink=buf,
        )
        buf.seek(0)
        amps = np.stack([f.amps for f in parse_stream(buf)])
        return float(amps.var(axis=0).mean())

    assert temporal_variance("walking") > temporal_variance("idle") * 5
