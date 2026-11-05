import numpy as np
from scipy.signal import find_peaks, peak_widths
from .core import Spectrum


def find_raman_peaks(s: Spectrum, prominence: float | None = None, min_distance: float = 5.0,
                     rel_prominence: float = 0.02, refine: bool = True):
    """Return list of dicts (x, y, prominence, fwhm). Peak position refined by parabolic interpolation.
    Defaults: prominence = rel_prominence * (max-min). Standard method, not matched to the reference."""
    y = s.y
    step = float(np.median(np.diff(s.x)))
    prom = prominence if prominence is not None else rel_prominence * (y.max() - y.min())
    idx, props = find_peaks(y, prominence=prom, distance=max(int(round(min_distance / step)), 1))
    if len(idx) == 0:
        return []
    w = peak_widths(y, idx, rel_height=0.5)[0] * step
    out = []
    for k, i in enumerate(idx):
        xp, yp = s.x[i], y[i]
        if refine and 0 < i < len(y) - 1:
            a, b, c = y[i - 1], y[i], y[i + 1]
            den = a - 2 * b + c
            if den != 0:
                d = 0.5 * (a - c) / den
                xp = s.x[i] + d * step
                yp = b - 0.25 * (a - c) * d
        out.append({"x": float(xp), "y": float(yp), "prominence": float(props["prominences"][k]), "fwhm": float(w[k])})
    return out
