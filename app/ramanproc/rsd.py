"""Reproducibility (RSD) of a characteristic band across replicate spectra.

feature modes
  height_local : baseline-corrected peak height (linear baseline between the window edges), parabolic apex
  height_max   : maximum Y inside the window (use on spectra whose background was already removed)
  area_local   : area under the curve over [lo, hi] minus the straight edge-to-edge baseline
  area_direct  : area under the curve over [lo, hi] as is (natural-spline integral, same as Analysis -> Bands)
RSD% = 100 * s / |mean|, with s the sample standard deviation (n-1)."""
from __future__ import annotations
import numpy as np
from scipy import stats
from .core import Spectrum
from .ops import integral
from . import peakanalysis as PA

MODES = {"height_local": "峰高（局部基線扣除）", "height_max": "峰高（視窗內最大值；光譜已去背景）",
         "area_local": "區域面積（局部基線扣除）", "area_direct": "區域曲線下面積（直接積分）"}


def feature(s: Spectrum, center: float, hw: float, mode: str = "height_local", lo: float | None = None, hi: float | None = None) -> float:
    """One number per spectrum. The band is [center-hw, center+hw] unless lo/hi are given (area modes)."""
    if mode not in MODES: raise ValueError(f"unknown mode {mode!r}")
    a, b = (center - hw, center + hw) if lo is None or hi is None else (min(lo, hi), max(lo, hi))
    if b < s.x[0] or a > s.x[-1]: raise ValueError("特徵區間在光譜範圍之外")
    if mode == "height_max":
        m = (s.x >= a) & (s.x <= b)
        if m.sum() < 1: raise ValueError("視窗內沒有資料點")
        return float(np.nanmax(s.y[m]))
    if mode == "area_direct":
        return float(integral(s, a, b))
    r = PA.measure_peak(s, 0.5 * (a + b), 0.5 * (b - a), "linear", pos_hw=0.5 * (b - a))
    return float(r["height"] if mode == "height_local" else r["area"])


def rsd_stats(values, ci=0.95) -> dict:
    """n, mean, sample SD, RSD%, SEM, min, max and a t-based CI of the mean. NaNs are excluded (counted in n_failed)."""
    v = np.asarray(values, float); ok = np.isfinite(v); n_failed = int((~ok).sum()); v = v[ok]; n = len(v)
    out = {"n": n, "n_failed": n_failed, "mean": float("nan"), "sd": float("nan"), "rsd": float("nan"), "sem": float("nan"),
           "min": float("nan"), "max": float("nan"), "ci": (float("nan"), float("nan")), "warning": ""}
    if n == 0: out["warning"] = "沒有可用數值"; return out
    out["mean"] = float(v.mean()); out["min"], out["max"] = float(v.min()), float(v.max())
    if n < 2: out["warning"] = "n < 2，無法計算標準差與 RSD"; return out
    sd = float(v.std(ddof=1)); out["sd"] = sd; out["sem"] = sd / np.sqrt(n)
    if abs(out["mean"]) < 1e-12 * max(1.0, abs(v).max()): out["warning"] = "平均值接近 0，RSD 無意義"
    else: out["rsd"] = 100.0 * sd / abs(out["mean"])
    t = stats.t.ppf(0.5 + ci / 2, n - 1); out["ci"] = (out["mean"] - t * out["sem"], out["mean"] + t * out["sem"])
    if n < 3: out["warning"] = (out["warning"] + "；" if out["warning"] else "") + "n < 3，RSD 的不確定度很大"
    return out


def analyze(specs, names=None, groups=None, **kw) -> dict:
    """Feature of every spectrum + statistics overall and per group. `kw` goes to `feature`.
    Returns {"values": [...], "errors": {index: message}, "overall": stats, "groups": {name: stats}, "order": [...] }"""
    vals, errs = [], {}
    for i, s in enumerate(specs):
        try: vals.append(feature(s, **kw))
        except Exception as ex: vals.append(float("nan")); errs[i] = str(ex)
    vals = np.array(vals); out = {"values": vals, "errors": errs, "overall": rsd_stats(vals), "groups": {}, "order": []}
    if groups is not None:
        for g in dict.fromkeys(groups):
            idx = [i for i, gg in enumerate(groups) if gg == g]; out["order"].append(g); out["groups"][g] = rsd_stats(vals[idx])
    return out
