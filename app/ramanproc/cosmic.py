import numpy as np
from .core import Spectrum


def running_median(y: np.ndarray, window: int) -> np.ndarray:
    """Centred running median; windows are truncated (not padded) at the ends, so an even number of
    samples there gives the mean of the two middle values."""
    h = window // 2
    n = len(y)
    out = np.empty(n)
    for i in range(n):
        out[i] = np.median(y[max(0, i - h):min(n, i + h + 1)])
    return out


def remove_cosmic_ray(s: Spectrum, window: int = 7) -> Spectrum:
    """Cosmic-ray (spike) removal by running median, default window 7.
    Reproduces the reference software's default output exactly on two test spectra."""
    if window < 3 or window % 2 == 0:
        raise ValueError("window must be an odd integer >= 3")
    return s.with_y(running_median(s.y, window), f"remove_cosmic_ray(median,{window})")
