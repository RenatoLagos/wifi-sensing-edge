from __future__ import annotations

import io
from collections import Counter

import pytest

from scripts.filter_capture import (
    choose_target_subcarriers,
    filter_capture_lines,
    scan_capture_lines,
)


def test_scan_capture_lines_counts_valid_invalid_and_widths():
    lines = [
        "1,-55,6,2,10.0,0.1,11.0,0.2\n",
        "2,-55,6,3,10.0,0.1,11.0,0.2,12.0,0.3\n",
        "bad\n",
    ]

    scan = scan_capture_lines(lines, strict=False)

    assert scan.total_lines == 3
    assert scan.valid_lines == 2
    assert scan.invalid_lines == 1
    assert scan.counts == Counter({2: 1, 3: 1})


def test_choose_target_subcarriers_prefers_most_common_then_larger_width():
    counts = Counter({64: 5, 128: 5, 192: 2})
    assert choose_target_subcarriers(counts) == 128


def test_choose_target_subcarriers_rejects_missing_requested_width():
    with pytest.raises(ValueError, match="not present"):
        choose_target_subcarriers(Counter({64: 3}), preferred=128)


def test_filter_capture_lines_keeps_only_requested_width():
    lines = [
        "1,-55,6,2,10.0,0.1,11.0,0.2\n",
        "2,-55,6,3,10.0,0.1,11.0,0.2,12.0,0.3\n",
        "bad\n",
        "3,-55,6,2,12.0,0.3,13.0,0.4\n",
    ]
    sink = io.StringIO()

    result = filter_capture_lines(lines, sink, target_subcarriers=2, strict=False)

    assert result.total_lines == 4
    assert result.valid_lines == 3
    assert result.invalid_lines == 1
    assert result.kept_lines == 2
    assert sink.getvalue().splitlines() == [
        "1,-55,6,2,10.0,0.1,11.0,0.2",
        "3,-55,6,2,12.0,0.3,13.0,0.4",
    ]
