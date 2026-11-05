import numpy as np
from scipy.signal import savgol_coeffs, medfilt
from .core import Spectrum
from .cosmic import running_median


def _apply_interior(y, kernel_fn, w):
    """Apply a centred window of odd length w; the w//2 points at each end are left unchanged."""
    h = w // 2
    out = y.copy()
    if len(y) > 2 * h:
        out[h:len(y) - h] = kernel_fn(y)[h:len(y) - h]
    return out


def smooth(s: Spectrum, method: str = "savgol", frame_length: int = 5, polyorder: int = 2) -> Spectrum:
    """method: 'savgol' | 'moving_average' | 'moving_median'. frame_length must be odd.
    Edge points (frame_length//2 at each end) are passed through unchanged."""
    w = int(frame_length)
    if w < 3 or w % 2 == 0:
        raise ValueError("frame_length must be an odd integer >= 3")
    y = s.y
    if method == "savgol":
        if polyorder >= w:
            raise ValueError("polyorder must be < frame_length")
        c = savgol_coeffs(w, polyorder)
        fn = lambda v: np.convolve(v, c, mode="same")
    elif method == "moving_average":
        fn = lambda v: np.convolve(v, np.ones(w) / w, mode="same")
    elif method == "moving_median":
        fn = lambda v: running_median(v, w)
    else:
        raise ValueError(f"unknown method {method!r}")
    out = fn(y) if method == "moving_median" else _apply_interior(y, fn, w)
    return s.with_y(out, f"smooth({method},{w})")
