"""Rolling history of fused WiFi telemetry for chart rendering.

This module is intentionally free of cv2/mediapipe imports so it can be
unit-tested without the camera stack installed. `pc/visualizer.py` owns all
drawing; this module only tracks samples and converts them to pixel-space
polyline coordinates.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class HistoryPoint:
    t_mono: float
    breath_bpm: float | None
    breath_confidence: float | None
    motion_score: float | None
    motion_state: str | None


@dataclass(frozen=True)
class PolylineSeries:
    points: tuple[tuple[int, int], ...]
    value_min: float
    value_max: float


class SignalHistory:
    """Fixed-capacity ring buffer of fused telemetry samples over time."""

    def __init__(self, *, capacity: int = 200) -> None:
        if capacity <= 0:
            raise ValueError(f"capacity must be > 0, got {capacity}")
        self._capacity = capacity
        self._points: deque[HistoryPoint] = deque(maxlen=capacity)

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        return len(self._points)

    def append(
        self,
        *,
        t_mono: float,
        breath_bpm: float | None,
        breath_confidence: float | None,
        motion_score: float | None,
        motion_state: str | None,
    ) -> None:
        if self._points and self._points[-1].t_mono == t_mono:
            return
        self._points.append(
            HistoryPoint(
                t_mono=t_mono,
                breath_bpm=breath_bpm,
                breath_confidence=breath_confidence,
                motion_score=motion_score,
                motion_state=motion_state,
            )
        )

    def points(self) -> tuple[HistoryPoint, ...]:
        return tuple(self._points)


def to_polyline(
    values: Sequence[float | None],
    *,
    width: int,
    height: int,
    fallback_range: tuple[float, float] = (0.0, 1.0),
) -> PolylineSeries:
    """Map a value series onto integer pixel coordinates for a polyline.

    The value range is derived from the non-None samples (min/max). When the
    series is empty or flat (max - min below tolerance), `fallback_range` is
    used to pad the range so the chart stays legible instead of collapsing
    onto a single horizontal line. `None` samples are skipped (no point is
    emitted for them) while their index still counts toward the x spacing;
    points are spaced by sample index, not by elapsed time.
    """
    indexed = [(idx, value) for idx, value in enumerate(values) if value is not None]
    if not indexed:
        value_min, value_max = fallback_range
        return PolylineSeries(points=(), value_min=value_min, value_max=value_max)

    observed = [value for _, value in indexed]
    value_min = min(observed)
    value_max = max(observed)
    if value_max - value_min < 1e-9:
        pad = max(abs(fallback_range[1] - fallback_range[0]), 1.0) / 2.0
        value_min -= pad
        value_max += pad

    span = value_max - value_min
    x_denominator = max(len(values) - 1, 1)
    points: list[tuple[int, int]] = []
    for idx, value in indexed:
        x = round(idx * (width - 1) / x_denominator)
        normalized = min(max((value - value_min) / span, 0.0), 1.0)
        y = round((1.0 - normalized) * (height - 1))
        points.append((int(x), int(y)))
    return PolylineSeries(
        points=tuple(points), value_min=value_min, value_max=value_max
    )
