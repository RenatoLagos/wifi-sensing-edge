"""Motion state estimation from a window of CSI amplitudes.

Complementary to breath rate: same input (time x subcarriers), different
question. Breath rate asks "what is the dominant periodic component" and
needs a long window. Motion asks "how much is the channel changing" and
works on much shorter windows — useful for things like presence gating
and as a coarse pre-filter for downstream tasks (e.g. don't run breath
rate inference if no one is in the room).

Algorithm:
  1. Per-subcarrier temporal variance over the input window.
  2. Pick the top-K subcarriers by variance (those carry the motion).
  3. Score = mean of those top-K variances.
  4. Bucket into IDLE / PRESENCE / MOVEMENT against two thresholds.

The thresholds below are calibrated against the synthetic CSI simulator.
Real CSI will require recalibration — that is one of the things the
hardware-arrival milestone is for.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class MotionState(StrEnum):
    IDLE = "idle"
    PRESENCE = "presence"
    MOVEMENT = "movement"


@dataclass(frozen=True)
class MotionEstimate:
    state: MotionState
    motion_score: float
    n_subcarriers_used: int


def estimate_motion(
    amps: np.ndarray,
    *,
    top_k_subcarriers: int = 10,
    presence_threshold: float = 1.0,
    movement_threshold: float = 15.0,
) -> MotionEstimate:
    """Classify motion state from a window of CSI amplitudes.

    Args:
        amps: shape (n_packets, n_subcarriers).
        top_k_subcarriers: number of highest-variance subcarriers to average.
        presence_threshold: score >= this -> PRESENCE (or higher).
        movement_threshold: score >= this -> MOVEMENT.

    Returns:
        MotionEstimate with the score, bucket label, and how many
        subcarriers contributed.
    """
    if amps.ndim != 2:
        raise ValueError(f"amps must be 2D (time, subcarriers), got shape {amps.shape}")

    n_packets, n_subcarriers = amps.shape
    if n_packets < 2:
        raise ValueError(f"need at least 2 packets to compute variance, got {n_packets}")
    if presence_threshold <= 0 or movement_threshold <= presence_threshold:
        raise ValueError(
            f"invalid thresholds: presence={presence_threshold}, "
            f"movement={movement_threshold} (need 0 < presence < movement)"
        )

    temporal_var = amps.var(axis=0)
    k = int(min(top_k_subcarriers, n_subcarriers))
    top_idx = np.argsort(temporal_var)[-k:]
    score = float(temporal_var[top_idx].mean())

    if score >= movement_threshold:
        state = MotionState.MOVEMENT
    elif score >= presence_threshold:
        state = MotionState.PRESENCE
    else:
        state = MotionState.IDLE

    return MotionEstimate(state=state, motion_score=score, n_subcarriers_used=k)
