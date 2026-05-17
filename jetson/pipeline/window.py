"""Sliding window over CSI frames.

A fixed-capacity ring of the most recent N CSI frames. The pipeline
appends every incoming frame and the estimators read back the last K
frames as a (time, subcarriers) NumPy array.

The buffer holds enough frames for the *longest* downstream estimator
(breath rate at 30 s @ 100 Hz = 3000 frames). Shorter estimators (motion
at 2 s) read a smaller slice of the same buffer.
"""
from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

from jetson.ingest import CSIFrame


class SlidingWindow:
    def __init__(self, max_frames: int) -> None:
        if max_frames <= 0:
            raise ValueError(f"max_frames must be > 0, got {max_frames}")
        self._buffer: deque[CSIFrame] = deque(maxlen=max_frames)

    @property
    def max_frames(self) -> int:
        return int(self._buffer.maxlen or 0)

    def __len__(self) -> int:
        return len(self._buffer)

    def append(self, frame: CSIFrame) -> None:
        self._buffer.append(frame)

    def amps_last_n(self, n: int) -> Optional[np.ndarray]:
        """Return the last n frames as (n, num_subcarriers) array, or None if too few."""
        if n <= 0:
            raise ValueError(f"n must be > 0, got {n}")
        if len(self._buffer) < n:
            return None
        recent = list(self._buffer)[-n:]
        return np.stack([f.amps for f in recent])

    def latest_timestamp_us(self) -> Optional[int]:
        if not self._buffer:
            return None
        return self._buffer[-1].timestamp_us
