import numpy as np
from scipy.interpolate import CubicSpline
from .core import Spectrum
from .ops import uniform_grid


def _clip_iterative(v: np.ndarray, half_width: int) -> np.ndarray:
    """SNIP-style iterative clipping with a decreasing window (p = w..1), double-buffered."""
    v = v.copy()
    n = len(v)
    for p in range(min(half_width, (n - 1) // 2), 0, -1):
        a = v.copy()
        a[p:n - p] = np.minimum(v[p:n - p], 0.5 * (v[:n - 2 * p] + v[2 * p:]))
        v = a
    return v


def remove_baseline(s: Spectrum, method: str = "iterative_clipping", peak_width: float = 100.0,
                    step: float = 0.5, order: int = 2, n_iter: int = 20, return_baseline: bool = False,
                    lam: float = 1e5, p: float = 0.01, window: float = 100.0):
    """Subtract a baseline.

    iterative_clipping: resample onto a uniform grid of `step` cm-1 (natural cubic spline),
        clip iteratively with half-window = peak_width/(2*step) points, subtract, floor at 0.
        NOTE: output is on the resampled grid (this matches the reference software).
    als: asymmetric least squares (Eilers & Boelens 2005): `lam` smoothness, `p` asymmetry, `n_iter` iterations.
    arpls: asymmetrically reweighted penalised LS (Baek et al. 2015); `lam`, `n_iter` (max).
    morphological: opening (erosion+dilation) with `window` cm-1, then smoothed.
    linear: straight line through the two end points.
    als/arpls/morphological/linear keep the original x grid and do NOT floor at 0 (not validated against the reference software).
    polynomial: modified polynomial fit (see below), `order` default 2, `n_iter` default 20, no floor at 0.
    """
    if method == "iterative_clipping":
        xg = uniform_grid(s.x[0], s.x[-1], step)
        yg = CubicSpline(s.x, s.y, bc_type="natural")(xg)
        base = _clip_iterative(yg, int(round(peak_width / (2 * step))))
        out = np.clip(yg - base, 0, None)
        res = Spectrum(xg, out, s.name, s.history + [f"baseline(iterative_clipping,width={peak_width},step={step})"])
        return (res, base) if return_baseline else res
    if method == "polynomial":
        # Same resampling as iterative_clipping. Modified polynomial fit: fit, clip the data to the fit, repeat.
        # `n_iter` = number of fits (reference software matches n_iter=20, i.e. 19 clips + final fit).
        # Result is NOT floored at 0 (negative values are kept), matching the reference.
        xg = uniform_grid(s.x[0], s.x[-1], step)
        yg = CubicSpline(s.x, s.y, bc_type="natural")(xg)
        t = (xg - xg.mean()) / (0.5 * (xg[-1] - xg[0]))     # scaled to [-1, 1] for conditioning
        yy = yg.copy()
        for _ in range(n_iter - 1):
            yy = np.minimum(yy, np.polynomial.polynomial.polyval(t, np.polynomial.polynomial.polyfit(t, yy, order)))
        base = np.polynomial.polynomial.polyval(t, np.polynomial.polynomial.polyfit(t, yy, order))
        res = Spectrum(xg, yg - base, s.name, s.history + [f"baseline(polynomial,order={order},n_iter={n_iter})"])
        return (res, base) if return_baseline else res
    if method in ("als", "arpls", "morphological", "linear"):
        y = s.y.astype(float)
        if method == "als":
            base = _als(y, lam, p, n_iter)
        elif method == "arpls":
            base = _arpls(y, lam, n_iter)
        elif method == "morphological":
            from scipy.ndimage import grey_opening, uniform_filter1d
            dx = float(np.median(np.diff(s.x)))
            k = max(3, int(round(window / dx)) | 1)
            base = uniform_filter1d(grey_opening(y, size=k, mode="nearest"), size=k, mode="nearest")
            base = np.minimum(base, y)
        else:   # linear between the two end points
            base = np.interp(s.x, [s.x[0], s.x[-1]], [y[0], y[-1]])
        res = Spectrum(s.x.copy(), y - base, s.name, s.history + [f"baseline({method})"])
        return (res, base) if return_baseline else res
    raise ValueError(f"unknown method {method!r}")


def _penalty(n, lam):
    from scipy import sparse
    D = sparse.diags([1.0, -2.0, 1.0], [0, -1, -2], shape=(n, n - 2))
    return lam * (D @ D.T)


def _als(y, lam, p, n_iter):
    from scipy import sparse
    from scipy.sparse.linalg import spsolve
    n = len(y); H = _penalty(n, lam); w = np.ones(n)
    for _ in range(n_iter):
        z = spsolve((sparse.diags(w) + H).tocsc(), w * y)
        w = p * (y > z) + (1 - p) * (y < z)
    return z


def _arpls(y, lam, n_iter, tol=1e-6):
    from scipy import sparse
    from scipy.sparse.linalg import spsolve
    n = len(y); H = _penalty(n, lam); w = np.ones(n)
    for _ in range(max(n_iter, 1)):
        z = spsolve((sparse.diags(w) + H).tocsc(), w * y)
        d = y - z; dn = d[d < 0]
        if len(dn) < 2: break
        m, sd = dn.mean(), dn.std()
        if sd == 0: break
        wn = 1.0 / (1.0 + np.exp(np.clip(2.0 * (d - (2 * sd - m)) / sd, -50, 50)))
        done = np.linalg.norm(w - wn) / np.linalg.norm(w) < tol
        w = wn
        if done: break
    return z


def baseline_from_points(s: Spectrum, pts) -> np.ndarray:
    """Manual baseline: curve through user anchor points (>=2), evaluated at s.x.
    2 points -> straight line; >=3 -> natural cubic spline. Outside the anchor range the end values are held."""
    P = sorted((float(x), float(y)) for x, y in pts)
    xs, ys = [], []
    for x, y in P:
        if xs and abs(x - xs[-1]) < 1e-9: ys[-1] = y
        else: xs.append(x); ys.append(y)
    if len(xs) < 2:
        raise ValueError("need at least 2 distinct anchor points")
    xq = np.clip(s.x, xs[0], xs[-1])
    if len(xs) == 2:
        return np.interp(xq, xs, ys)
    return CubicSpline(xs, ys, bc_type="natural")(xq)


def remove_baseline_points(s: Spectrum, pts) -> Spectrum:
    """Subtract a manual baseline defined by anchor points (no resampling, no flooring)."""
    return s.with_y(s.y - baseline_from_points(s, pts), f"baseline(manual,{len(pts)} points)")
