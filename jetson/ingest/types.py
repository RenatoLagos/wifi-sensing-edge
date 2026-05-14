from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class CSIFrame:
    timestamp_us: int
    rssi: int
    channel: int
    amps: np.ndarray
    phases: np.ndarray

    @property
    def num_subcarriers(self) -> int:
        return int(self.amps.shape[0])

    def __post_init__(self) -> None:
        if self.amps.shape != self.phases.shape:
            raise ValueError(
                f"amps and phases must have the same shape, "
                f"got {self.amps.shape} vs {self.phases.shape}"
            )
        if self.amps.ndim != 1:
            raise ValueError(f"amps must be 1D, got shape {self.amps.shape}")
