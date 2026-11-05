from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass
class Spectrum:
    """x: Raman shift (cm-1), y: intensity. `history` records applied steps."""
    x: np.ndarray
    y: np.ndarray
    name: str = "spectrum"
    history: list = field(default_factory=list)

    def __post_init__(self):
        self.x = np.asarray(self.x, dtype=float)
        self.y = np.asarray(self.y, dtype=float)
        if self.x.shape != self.y.shape or self.x.ndim != 1:
            raise ValueError("x and y must be 1-D arrays of equal length")
        if np.any(np.diff(self.x) <= 0):
            raise ValueError("x must be strictly increasing")

    def with_y(self, y, step, x=None) -> "Spectrum":
        return Spectrum(self.x if x is None else x, y, self.name, self.history + [step])
