"""Spectrum quality checks: missing values, saturation, spikes, flat/empty spectra."""
import numpy as np
from .core import Spectrum


def check_spectrum(s: Spectrum, saturation: float | None = None, spike_sigma: float = 8.0, sat_run: int = 3) -> dict:
    """Returns {'issues': [(kind, text)], 'nan_idx', 'sat_idx', 'spike_idx'} (indices into s.x / s.y).
    saturation: detector maximum (None -> auto: a flat top of >= sat_run identical values at the global maximum)."""
    y = np.asarray(s.y, float); out = {"issues": [], "nan_idx": np.array([], int), "sat_idx": np.array([], int), "spike_idx": np.array([], int)}
    bad = ~np.isfinite(y)
    if bad.any():
        out["nan_idx"] = np.nonzero(bad)[0]; out["issues"].append(("missing", f"{int(bad.sum())} 個缺失值（NaN/Inf）"))
    yy = np.where(bad, np.nanmedian(y[~bad]) if (~bad).any() else 0.0, y)
    if np.ptp(yy) == 0:
        out["issues"].append(("flat", "光譜為常數（無訊號）")); return out
    if saturation is not None and saturation > 0:
        sat = np.nonzero(yy >= saturation)[0]
    else:
        mx = yy.max(); idx = np.nonzero(yy == mx)[0]
        sat = np.array([], int)
        if len(idx) >= sat_run:
            runs = np.split(idx, np.nonzero(np.diff(idx) != 1)[0] + 1)
            keep = [r for r in runs if len(r) >= sat_run]
            if keep: sat = np.concatenate(keep)
    if len(sat):
        out["sat_idx"] = sat; out["issues"].append(("saturation", f"疑似飽和（{len(sat)} 點達到最大值 {yy.max():.6g}）"))
    # spikes: a block of 1-3 points that stands > spike_sigma*noise above BOTH neighbouring points
    # (a block on a peak apex or flank does not satisfy this, a cosmic-ray spike does)
    dd = np.diff(yy); sig = 1.4826 * np.median(np.abs(dd - np.median(dd))) / np.sqrt(2)
    if sig > 0 and len(yy) > 6:
        from numpy.lib.stride_tricks import sliding_window_view as swv
        hit = np.zeros(len(yy), bool)
        for w in (1, 2, 3):
            mn = swv(yy, w).min(axis=1)[1:len(yy) - w]            # blocks starting at 1 .. n-w-1
            left, right = yy[0:len(yy) - w - 1], yy[w + 1:]
            ok = mn > np.maximum(left, right) + spike_sigma * sig
            for st in np.nonzero(ok)[0] + 1: hit[st:st + w] = True
        sp = np.nonzero(hit)[0]
        if len(sp):
            out["spike_idx"] = sp; out["issues"].append(("spike", f"疑似尖峰/宇宙射線（{len(sp)} 點，高於鄰點 > {spike_sigma:g}σ）"))
    return out
