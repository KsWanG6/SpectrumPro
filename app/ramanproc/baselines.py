"""LabSpec-style baseline correction: Fit (compute a baseline curve) then Sub (subtract it).

Types: Linear(Manual), Linear(Auto), Polynom(Manual), Polynom(Auto), Multi polynomial, Lorentzian,
       Rolling Ball, Rolling Ball Auto, Whittaker 1, Whittaker 2.
The parameter semantics below are our own definitions (the vendor algorithms are not public):
  Order         polynomial order; Multi polynomial: number of cubic pieces; Lorentzian: number of broad Lorentzians (1-3)
  Max points    auto types: the spectrum is cut into this many equal bins and one candidate anchor is taken per bin
  Noise points  auto types: width (points) of the moving average used to suppress noise before the anchors are picked
  Correct noise anchors use the smoothed height (True) or the raw height at the same position (False)
  Whittaker 1   asymmetric least squares (Eilers & Boelens 2005);  Whittaker 2 = arPLS (Baek et al. 2015)
Anchors that stay above the fitted baseline by more than one robust sigma are rejected and the fit is repeated.
All functions return the baseline on the spectrum's own X grid; nothing is resampled or clipped."""
from __future__ import annotations
import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.optimize import curve_fit
from .core import Spectrum
from .baseline import _als, _arpls, remove_baseline

TYPES = ["Linear(Manual)", "Linear(Auto)", "Polynom(Manual)", "Polynom(Auto)", "Multi polynomial", "Lorentzian",
         "Rolling Ball", "Rolling Ball Auto", "Whittaker 1", "Whittaker 2"]
MANUAL = ("Linear(Manual)", "Polynom(Manual)")
ANCHOR_AUTO = ("Linear(Auto)", "Polynom(Auto)", "Multi polynomial", "Lorentzian")
LEGACY = ("IterativeClipping", "PolynomialFitting")           # validated against the reference software (resample to 0.5 cm-1)


def _poly_model(order):
    def build(xa, ya):
        lo, hi = xa.min(), xa.max(); span = (hi - lo) or 1.0
        o = int(min(order, len(xa) - 1))
        c = np.polynomial.polynomial.polyfit((xa - lo) / span * 2 - 1, ya, o)
        return lambda x: np.polynomial.polynomial.polyval((np.asarray(x) - lo) / span * 2 - 1, c)
    return build


def _spline_model(pieces):
    from scipy.interpolate import LSQUnivariateSpline
    def build(xa, ya):
        k = 3; n_int = max(int(pieces) - 1, 0)
        n_int = min(n_int, max(len(xa) - k - 2, 0))
        knots = np.quantile(xa, np.linspace(0, 1, n_int + 2)[1:-1]) if n_int else []
        sp = LSQUnivariateSpline(xa, ya, knots, k=k if len(xa) > k else 1)
        lo, hi = xa.min(), xa.max()
        return lambda x: sp(np.clip(x, lo, hi))
    return build


def _lorentz_model(count):
    K = int(min(max(count, 1), 3))
    def f(x, c, *p):
        out = c + 0.0 * x
        for k in range(K):
            A, x0, w = p[3 * k:3 * k + 3]; out = out + A / (1 + ((x - x0) / w) ** 2)
        return out
    def build(xa, ya):
        lo, hi = xa.min(), xa.max(); span = (hi - lo) or 1.0
        p0 = [float(ya.min())]; lb = [-np.inf]; ub = [np.inf]
        for k in range(K):
            p0 += [float(ya.max() - ya.min()) / K, lo + span * (k + 1) / (K + 1), span / (2 * K + 2)]
            lb += [0, lo - span, span / 100]; ub += [np.inf, hi + span, span * 5]
        try: popt, _ = curve_fit(f, xa, ya, p0=p0, bounds=(lb, ub), maxfev=20000)
        except Exception as ex: raise ValueError(f"Lorentzian 擬合失敗（{ex}）。請改用其他基線類型") from None
        return lambda x: f(np.asarray(x, float), *popt)
    return build


def noise_sigma(y):
    d = np.diff(y)
    return float(1.4826 * np.median(np.abs(d - np.median(d))) / np.sqrt(2)) if len(d) else 0.0


def pick_anchors(x, y, model, max_points=123, noise_points=64, correct_noise=True, min_anchors=4, max_iter=15):
    """Lower-envelope anchors with iterative rejection. Returns (xa, ya, model_function)."""
    n = len(x)
    k = int(min(max(noise_points, 1), max(n // 10, 1))) | 1
    ys = uniform_filter1d(y.astype(float), size=k, mode="nearest") if k > 1 else y.astype(float)
    nb = int(min(max(max_points, min_anchors), n))
    edges = np.linspace(0, n, nb + 1).astype(int)
    idx = np.array([a + int(np.argmin(ys[a:b])) for a, b in zip(edges[:-1], edges[1:]) if b > a])
    xa, ya = x[idx], (ys[idx] if correct_noise else y[idx])
    keep = np.ones(len(xa), bool)
    for _ in range(max_iter):
        fn = model(xa[keep], ya[keep])
        r = ya - fn(xa)
        rk = r[keep]; sig = 1.4826 * np.median(np.abs(rk - np.median(rk))) or noise_sigma(y) or 1e-12
        new = r <= max(sig, 1e-12)
        if new.sum() < min_anchors or (new == keep).all(): break
        keep = new
    fn = model(xa[keep], ya[keep])
    return xa[keep], ya[keep], fn


def auto_ball_width(s: Spectrum) -> float:
    """Rolling-ball radius (cm-1) from the peak widths: 4 x median FWHM of the clear peaks; fallback 15 % of the range."""
    from scipy.signal import find_peaks, peak_widths
    y = uniform_filter1d(s.y, size=5, mode="nearest"); rng = float(np.ptp(y)) or 1.0
    dx = float(np.median(np.diff(s.x))); span = float(s.x[-1] - s.x[0])
    pk, pr = find_peaks(y, prominence=0.05 * rng)
    if len(pk):
        w = float(np.median(peak_widths(y, pk, rel_height=0.5)[0])) * dx
        if w > 0: return float(np.clip(4 * w, 10 * dx, 0.5 * span))
    return 0.15 * span


def fit_baseline(s: Spectrum, kind: str, order: int = 3, max_points: int = 123, noise_points: int = 64, correct_noise: bool = True,
                 points=None, width: float = 100.0, loglam: float = 5.0, asym: float = 0.01, iters: int = 20):
    """Returns (baseline, info) with baseline on s.x. `points` = [(x, y), ...] for the Manual types."""
    x, y = s.x, s.y.astype(float); info = {"notes": [], "anchors": None}
    if not np.isfinite(y).all(): raise ValueError("光譜含 NaN / 無窮大，請先處理缺值")
    if kind in MANUAL:
        P = sorted({(float(a), float(b)) for a, b in (points or [])})
        xs = []; ys = []
        for a, b in P:
            if xs and abs(a - xs[-1]) < 1e-9: ys[-1] = b
            else: xs.append(a); ys.append(b)
        if len(xs) < 2: raise ValueError("手動基線至少需要 2 個點（用左側「手動基線」工具在圖上點選）")
        xs, ys = np.array(xs), np.array(ys); info["anchors"] = (xs, ys)
        if kind == "Linear(Manual)":
            return np.interp(x, xs, ys), info
        o = int(min(order, len(xs) - 1))
        if o < order: info["notes"].append(f"點數不足，階數降為 {o}")
        return _poly_model(o)(xs, ys)(x), info
    if kind in ANCHOR_AUTO:
        model = {"Linear(Auto)": _poly_model(1), "Polynom(Auto)": _poly_model(order), "Multi polynomial": _spline_model(order),
                 "Lorentzian": _lorentz_model(order)}[kind]
        xa, ya, fn = pick_anchors(x, y, model, max_points, noise_points, correct_noise)
        info["anchors"] = (xa, ya)
        return np.asarray(fn(x), float), info
    if kind in ("Rolling Ball", "Rolling Ball Auto"):
        w = auto_ball_width(s) if kind.endswith("Auto") else width
        info["width"] = w
        return remove_baseline(s, "morphological", window=w, return_baseline=True)[1], info
    if kind == "Whittaker 1": return _als(y, 10 ** loglam, asym, iters), info
    if kind == "Whittaker 2": return _arpls(y, 10 ** loglam, iters), info
    raise ValueError(f"unknown baseline type {kind!r}")


def subtract(s: Spectrum, base, label: str) -> Spectrum:
    return s.with_y(s.y - np.asarray(base, float), f"baseline({label})")
