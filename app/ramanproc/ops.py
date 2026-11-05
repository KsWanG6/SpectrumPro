"""Arithmetic / grid operations. None of these have reference data yet: standard definitions."""
import numpy as np
from scipy.interpolate import CubicSpline
from .core import Spectrum


def crop(s: Spectrum, xmin: float, xmax: float) -> Spectrum:
    m = (s.x >= xmin) & (s.x <= xmax)
    if m.sum() < 2:
        raise ValueError("crop range contains fewer than 2 points")
    return Spectrum(s.x[m], s.y[m], s.name, s.history + [f"crop({xmin},{xmax})"])


def ayb(s: Spectrum, a: float = 1.0, b: float = 0.0) -> Spectrum:
    return s.with_y(a * s.y + b, f"a*y+b(a={a},b={b})")


def _common_grid(s1, s2):
    lo, hi = max(s1.x[0], s2.x[0]), min(s1.x[-1], s2.x[-1])
    if lo >= hi:
        raise ValueError("spectra do not overlap in x")
    x = s1.x[(s1.x >= lo) & (s1.x <= hi)]
    return x, np.interp(x, s1.x, s1.y), np.interp(x, s2.x, s2.y)


def ay1_by2_c(s1: Spectrum, s2: Spectrum, a=1.0, b=1.0, c=0.0, op="+") -> Spectrum:
    """a*y1 (+|-|*|/) b*y2 + c on the overlapping x-range (s2 linearly interpolated onto s1's x)."""
    x, y1, y2 = _common_grid(s1, s2)
    ops = {"+": np.add, "-": np.subtract, "*": np.multiply, "/": np.divide}
    return Spectrum(x, ops[op](a * y1, b * y2) + c, s1.name, s1.history + [f"a*y1{op}b*y2+c"])


def log_y(s: Spectrum, base: float = 10.0) -> Spectrum:
    if np.any(s.y <= 0):
        raise ValueError("log requires strictly positive intensities")
    return s.with_y(np.log(s.y) / np.log(base), f"logy(base={base})")


def uniform_grid(x0: float, x1: float, step: float) -> np.ndarray:
    """Grid of multiples of `step` from round(x0/step)*step to round(x1/step)*step (may extend slightly
    beyond the data, in which case the spline is extrapolated - matches the reference software)."""
    a, b = round(x0 / step), round(x1 / step)
    return np.arange(a, b + 1) * step


def uniform_x(s: Spectrum, step: float, kind: str = "cubic") -> Spectrum:
    xg = uniform_grid(s.x[0], s.x[-1], step)
    if kind == "cubic":
        yg = CubicSpline(s.x, s.y, bc_type="natural")(xg)
    else:
        yg = np.interp(xg, s.x, s.y)
    return Spectrum(xg, yg, s.name, s.history + [f"uniform_x({step},{kind})"])


def average(spectra, name="average") -> Spectrum:
    ref = spectra[0]
    ys = [ref.y] + [np.interp(ref.x, t.x, t.y) for t in spectra[1:]]
    return Spectrum(ref.x, np.mean(ys, axis=0), name, [f"average(n={len(spectra)})"])


def std_curve(spectra, name="std") -> Spectrum:
    ref = spectra[0]
    ys = [ref.y] + [np.interp(ref.x, t.x, t.y) for t in spectra[1:]]
    return Spectrum(ref.x, np.std(ys, axis=0, ddof=1), name, [f"std_curve(n={len(spectra)})"])


def standardize(s: Spectrum) -> Spectrum:
    """z-score: (y-mean)/std (ddof=1). Definition assumed, not verified."""
    sd = s.y.std(ddof=1)
    if sd == 0:
        raise ValueError("zero variance")
    return s.with_y((s.y - s.y.mean()) / sd, "standardize(zscore)")


def integral(s: Spectrum, xmin=None, xmax=None, cumulative=False):
    """Definite integral of the natural cubic spline through the data over [xmin, xmax], clipped to the
    data range (no extrapolation). Matches the reference software. `cumulative=True` returns a trapezoid
    running integral as a Spectrum (not validated)."""
    lo = s.x[0] if xmin is None else max(xmin, s.x[0])
    hi = s.x[-1] if xmax is None else min(xmax, s.x[-1])
    if cumulative:
        m = (s.x >= lo) & (s.x <= hi)
        x, y = s.x[m], s.y[m]
        c = np.concatenate([[0], np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(x))])
        return Spectrum(x, c, s.name, s.history + ["integral(cumulative)"])
    if hi <= lo:
        return 0.0
    return float(CubicSpline(s.x, s.y, bc_type="natural").integrate(lo, hi))


def auto_stacking(spectra, gap_fraction: float = 0.1):
    """Return copies vertically offset so they do not overlap (for display)."""
    out, top = [], 0.0
    for s in spectra:
        lo, hi = s.y.min(), s.y.max()
        off = top - lo
        out.append(s.with_y(s.y + off, f"stack(offset={off:.6g})"))
        top = hi + off + gap_fraction * (hi - lo)
    return out


def add_point(s: Spectrum, x: float, y: float) -> Spectrum:
    i = np.searchsorted(s.x, x)
    if i < len(s.x) and s.x[i] == x:
        raise ValueError("x already exists")
    return Spectrum(np.insert(s.x, i, x), np.insert(s.y, i, y), s.name, s.history + [f"add_point({x})"])


def remove_point(s: Spectrum, x: float) -> Spectrum:
    i = int(np.argmin(np.abs(s.x - x)))
    return Spectrum(np.delete(s.x, i), np.delete(s.y, i), s.name, s.history + [f"remove_point({s.x[i]})"])
