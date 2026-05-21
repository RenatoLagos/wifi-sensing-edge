from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock

from .telemetry import WifiTelemetrySample


@dataclass(frozen=True)
class BufferedTelemetry:
    sample: WifiTelemetrySample
    aligned_local_us: int


@dataclass(frozen=True)
class FusedTelemetry:
    sample: WifiTelemetrySample
    aligned_local_us: int
    age_ms: float
    skew_ms: float


class TimestampAligner:
    def __init__(
        self,
        *,
        smoothing: float = 0.2,
        hard_reset_delta_us: int = 2_000_000,
    ) -> None:
        if not 0.0 < smoothing <= 1.0:
            raise ValueError(f"smoothing must be in (0, 1], got {smoothing}")
        if hard_reset_delta_us <= 0:
            raise ValueError(
                f"hard_reset_delta_us must be > 0, got {hard_reset_delta_us}"
            )
        self._smoothing = smoothing
        self._hard_reset_delta_us = hard_reset_delta_us
        self._offset_us: float | None = None

    @property
    def offset_us(self) -> float | None:
        return self._offset_us

    def observe(self, source_timestamp_us: int, received_monotonic_us: int) -> int:
        observed_offset = received_monotonic_us - source_timestamp_us
        if self._offset_us is None:
            self._offset_us = float(observed_offset)
        elif abs(observed_offset - self._offset_us) > self._hard_reset_delta_us:
            self._offset_us = float(observed_offset)
        else:
            alpha = self._smoothing
            self._offset_us = (1.0 - alpha) * self._offset_us + alpha * observed_offset
        return int(round(self._offset_us))

    def to_local_us(self, source_timestamp_us: int) -> int | None:
        if self._offset_us is None:
            return None
        return int(round(source_timestamp_us + self._offset_us))


class TelemetryBuffer:
    def __init__(
        self,
        *,
        max_samples: int = 512,
        max_buffer_age_us: int = 30_000_000,
        aligner: TimestampAligner | None = None,
    ) -> None:
        if max_samples <= 0:
            raise ValueError(f"max_samples must be > 0, got {max_samples}")
        if max_buffer_age_us <= 0:
            raise ValueError(f"max_buffer_age_us must be > 0, got {max_buffer_age_us}")
        self._samples: deque[BufferedTelemetry] = deque(maxlen=max_samples)
        self._max_buffer_age_us = max_buffer_age_us
        self._aligner = aligner or TimestampAligner()
        self._lock = Lock()

    @property
    def aligner(self) -> TimestampAligner:
        return self._aligner

    def add(self, sample: WifiTelemetrySample) -> None:
        aligned_local_us = sample.received_monotonic_us
        with self._lock:
            aligned_local_us = sample.timestamp_us + self._aligner.observe(
                sample.timestamp_us,
                sample.received_monotonic_us,
            )
            self._samples.append(
                BufferedTelemetry(sample=sample, aligned_local_us=aligned_local_us)
            )
            self._trim_locked(sample.received_monotonic_us)

    def latest(self) -> BufferedTelemetry | None:
        with self._lock:
            if not self._samples:
                return None
            return self._samples[-1]

    def match(
        self,
        frame_local_us: int,
        *,
        max_age_ms: float = 1_500.0,
        max_skew_ms: float = 250.0,
    ) -> FusedTelemetry | None:
        max_age_us = int(max_age_ms * 1_000.0)
        max_skew_us = int(max_skew_ms * 1_000.0)

        best: BufferedTelemetry | None = None
        best_skew_us: int | None = None
        with self._lock:
            self._trim_locked(frame_local_us)
            for item in reversed(self._samples):
                age_us = frame_local_us - item.sample.received_monotonic_us
                if age_us > max_age_us:
                    break
                if age_us < 0:
                    continue
                skew_us = abs(item.aligned_local_us - frame_local_us)
                if skew_us > max_skew_us:
                    continue
                if best is None or best_skew_us is None or skew_us < best_skew_us:
                    best = item
                    best_skew_us = skew_us

        if best is None or best_skew_us is None:
            return None

        age_ms = (frame_local_us - best.sample.received_monotonic_us) / 1_000.0
        skew_ms = best_skew_us / 1_000.0
        return FusedTelemetry(
            sample=best.sample,
            aligned_local_us=best.aligned_local_us,
            age_ms=age_ms,
            skew_ms=skew_ms,
        )

    def _trim_locked(self, now_us: int) -> None:
        while self._samples:
            if (
                now_us - self._samples[0].sample.received_monotonic_us
                <= self._max_buffer_age_us
            ):
                break
            self._samples.popleft()
