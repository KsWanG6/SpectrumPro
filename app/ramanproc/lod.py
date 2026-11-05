"""Limit of detection / quantification from a calibration series.

Definitions (ICH Q2(R1) / IUPAC style):
    LOD = k_lod * sigma / S      LOQ = k_loq * sigma / S      (S = calibration slope)
Methods reported:
    blank      sigma = sample std (ddof=1) of replicate blank responses, k = 3 / 10
    residual   sigma = standard error of the regression (Sy.x),          k = 3.3 / 10
    intercept  sigma = standard error of the regression intercept,       k = 3.3 / 10
For a log-linear calibration (response vs log10 C, common in SERS) the response limits
y_LOD = mean(blank) + 3*sd(blank), y_LOQ = mean(blank) + 10*sd(blank) are converted back through the fit.
"""
import numpy as np
from .core import Spectrum
from .ops import integral


def peak_response(s: Spectrum, center: float, half_width: float, mode: str = "height", baseline: bool = False) -> float:
    """Response of one spectrum in [center-hw, center+hw]: 'height' (max) or 'area' (spline integral).
    baseline=True subtracts the straight line joining the window edges."""
    lo, hi = center - half_width, center + half_width
    if hi <= s.x[0] or lo >= s.x[-1]:
        raise ValueError("window outside the spectrum range")
    lo, hi = max(lo, s.x[0]), min(hi, s.x[-1])
    m = (s.x >= lo) & (s.x <= hi)
    if m.sum() < 2:
        raise ValueError("window contains fewer than 2 points")
    ylo, yhi = np.interp([lo, hi], s.x, s.y)
    if mode == "height":
        y = s.y[m] - (np.interp(s.x[m], [lo, hi], [ylo, yhi]) if baseline else 0.0)
        return float(np.max(y))
    if mode == "area":
        a = float(integral(s, lo, hi))
        return a - (0.5 * (ylo + yhi) * (hi - lo) if baseline else 0.0)
    raise ValueError(f"unknown mode {mode!r}")


def calibration(conc, resp, log: bool = False) -> dict:
    """Least-squares line resp = slope * x + intercept, with x = conc (or log10 conc)."""
    c = np.asarray(conc, float); r = np.asarray(resp, float)
    x = np.log10(c) if log else c
    n = len(x)
    if n < 3:
        raise ValueError("need at least 3 calibration points")
    if np.ptp(x) == 0:
        raise ValueError("calibration concentrations are all equal")
    slope, intercept = np.polyfit(x, r, 1)
    fit = slope * x + intercept
    sse = float(np.sum((r - fit) ** 2)); sst = float(np.sum((r - r.mean()) ** 2))
    sy = np.sqrt(sse / (n - 2))
    sxx = float(np.sum((x - x.mean()) ** 2))
    return {"slope": float(slope), "intercept": float(intercept), "r2": 1.0 - sse / sst if sst > 0 else 1.0,
            "sy": float(sy), "se_slope": float(sy / np.sqrt(sxx)),
            "se_intercept": float(sy * np.sqrt(1.0 / n + x.mean() ** 2 / sxx)), "n": n, "log": log}


def lod_loq(conc, resp, blank_resp=None, log: bool = False, k_lod: float = 3.0, k_loq: float = 10.0) -> dict:
    """Returns {'fit': calibration dict, 'methods': {name: {'sigma','lod','loq'}}, 'notes': [...]}."""
    fit = calibration(conc, resp, log)
    out, notes = {}, []
    S = fit["slope"]
    if S == 0:
        raise ValueError("calibration slope is zero")
    blank = None if blank_resp is None else np.asarray(blank_resp, float)
    sd_b = float(np.std(blank, ddof=1)) if blank is not None and len(blank) >= 2 else None
    if not log:
        if sd_b is not None:
            out["blank"] = {"sigma": sd_b, "lod": k_lod * sd_b / S, "loq": k_loq * sd_b / S}
        else:
            notes.append("空白法需要至少 2 個空白重複")
        out["residual"] = {"sigma": fit["sy"], "lod": 3.3 * fit["sy"] / S, "loq": 10 * fit["sy"] / S}
        out["intercept"] = {"sigma": fit["se_intercept"], "lod": 3.3 * fit["se_intercept"] / S, "loq": 10 * fit["se_intercept"] / S}
    else:
        if sd_b is None:
            notes.append("log 校正曲線需要至少 2 個空白重複才能算 LOD")
        else:
            mb = float(blank.mean())
            conv = lambda y: float(10 ** ((y - fit["intercept"]) / S))
            out["blank"] = {"sigma": sd_b, "lod": conv(mb + k_lod * sd_b), "loq": conv(mb + k_loq * sd_b)}
    return {"fit": fit, "methods": out, "notes": notes}
