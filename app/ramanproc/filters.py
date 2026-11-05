"""Smoothing & filtering (LabSpec-style): Methods x Mode (Automatic / Manual).

Methods: Polynomial (Savitzky-Golay), Median, FFT (low-pass), DeNoise (Wiener), 1st derivative, 2nd derivative, Despike, SVD.
Manual : Window (points, odd) and Order are used as given.
Automatic: Window is chosen as the LARGEST odd window whose strongest peak loses at most Factor % of its height
  (relative to a lightly smoothed copy). FFT-Automatic cuts at the noise floor of the power spectrum; FFT-Manual keeps the lowest
  Factor % of the frequencies. SVD keeps Order components (Manual) or the components above the noise level (Automatic).
These parameter meanings are our own definitions of the panel's controls."""
from __future__ import annotations
import numpy as np
from scipy.signal import savgol_filter, wiener, medfilt
from .core import Spectrum
from .cosmic import running_median

METHODS = ["Polynomial", "Median", "FFT", "DeNoise", "1st derivative", "2nd derivative", "Despike", "SVD"]
MODES = ["Automatic", "Manual"]


def _odd(w, lo=3):
    w = int(round(w)); w = max(w, lo)
    return w if w % 2 else w + 1


def _smooth_by(method, y, w, order):
    w = _odd(w)
    if method == "Median": return running_median(y, w)
    if method == "DeNoise":
        d = np.diff(y); sig = 1.4826 * np.median(np.abs(d - np.median(d))) / np.sqrt(2)
        return wiener(y, mysize=w, noise=max(sig, 1e-12) ** 2)           # noise power from the robust first-difference estimate
    o = int(min(max(order, 1), w - 1))
    return savgol_filter(y, w, o, mode="interp")


def auto_window(y, method="Polynomial", order=3, factor=10.0, w_max=None):
    """Largest odd window with peak-height loss <= factor % (see module doc)."""
    n = len(y); w_max = _odd(min(w_max or n // 4, n // 2 - 1, 301), 5)
    ref = _smooth_by("Polynomial", y, 5, 2); med = float(np.median(ref)); h0 = float(ref.max()) - med
    if h0 <= 0: return 5
    best = 5
    for w in range(7, w_max + 1, 2):
        sm = _smooth_by(method if method in ("Median", "DeNoise") else "Polynomial", y, w, order)
        if (h0 - (float(sm.max()) - med)) / h0 <= factor / 100.0: best = w
        else: break
    return best


def _fft_lowpass(y, keep_fraction=None):
    n = len(y); trend = np.linspace(y[0], y[-1], n); d = y - trend       # remove the end-to-end line: no wrap-around ringing
    F = np.fft.rfft(d); m = len(F)
    if keep_fraction is None:                                              # automatic: noise floor of the power spectrum
        P = uniform = np.abs(F) ** 2
        floor = float(np.median(P[m // 2:])) or 1e-30
        sm = np.convolve(P, np.ones(5) / 5, mode="same")
        above = np.nonzero(sm > 4 * floor)[0]
        kc = int(above.max()) + 2 if len(above) else 3
    else:
        kc = max(int(round(keep_fraction * m)), 3)
    kc = min(max(kc, 3), m)
    taper = np.ones(m); t = max(kc // 5, 1); taper[kc:] = 0
    taper[max(kc - t, 0):kc] = 0.5 * (1 + np.cos(np.linspace(0, np.pi, len(taper[max(kc - t, 0):kc]), endpoint=False)))
    return np.fft.irfft(F * taper, n) + trend, kc


def svd_denoise(specs, order=None, window=50):
    """Several spectra: truncated SVD of the stacked matrix (common X grid = first spectrum). One spectrum: singular spectrum
    analysis with embedding length `window`. order=None -> automatic (singular values above the noise bulk)."""
    if len(specs) > 1:
        x = specs[0].x
        M = np.vstack([np.interp(x, s.x, s.y) for s in specs]); m, n = M.shape
        U, S, Vt = np.linalg.svd(M, full_matrices=False)
        sig = 1.4826 * np.median(np.abs(np.diff(M, axis=1) - np.median(np.diff(M, axis=1)))) / np.sqrt(2)
        k = int(order) if order else max(int(np.sum(S > sig * (np.sqrt(m) + np.sqrt(n)))), 1)
        k = int(min(max(k, 1), len(S)))
        R = (U[:, :k] * S[:k]) @ Vt[:k]
        return [s.with_y(np.interp(s.x, x, R[i]) if len(s.x) != len(x) or not np.array_equal(s.x, x) else R[i], f"SVD(k={k})") for i, s in enumerate(specs)]
    s = specs[0]; y = s.y; n = len(y); L = int(min(max(window, 4), n // 2))
    if order and order + 1 >= L: raise ValueError("SVD（單條光譜）：Window 必須大於 Order + 1")
    K = n - L + 1; X = np.lib.stride_tricks.sliding_window_view(y, L)          # K x L trajectory matrix
    U, S, Vt = np.linalg.svd(X, full_matrices=False)
    sig = 1.4826 * np.median(np.abs(np.diff(y) - np.median(np.diff(y)))) / np.sqrt(2)
    k = int(order) if order else max(int(np.sum(S > sig * (np.sqrt(K) + np.sqrt(L)))), 1)
    k = int(min(max(k, 1), len(S)))
    R = (U[:, :k] * S[:k]) @ Vt[:k]
    out = np.zeros(n); cnt = np.zeros(n)
    for j in range(L): out[j:j + K] += R[:, j]; cnt[j:j + K] += 1                  # diagonal averaging
    return [s.with_y(out / cnt, f"SVD(SSA,L={L},k={k})")]


def apply_filter(specs, method="Polynomial", mode="Manual", window=5, order=3, factor=10.0):
    """specs: list of Spectrum. Returns a list of new Spectrum (same length)."""
    if method not in METHODS: raise ValueError(f"unknown method {method!r}")
    auto = mode == "Automatic"
    if method == "SVD": return svd_denoise(specs, None if auto else int(order), window)
    out = []
    for s in specs:
        y = s.y.astype(float)
        if not np.isfinite(y).all(): raise ValueError(f"「{s.name}」含 NaN / 無窮大，請先處理缺值")
        if len(y) < 7: raise ValueError(f"「{s.name}」資料點太少")
        if method == "FFT":
            new, kc = _fft_lowpass(y, None if auto else max(min(factor, 100.0), 0.5) / 100.0)
            out.append(s.with_y(new, f"filter(FFT,{'auto' if auto else f'keep={factor:g}%'},cut={kc})")); continue
        if method == "Despike":
            w = 7 if auto else _odd(window); out.append(s.with_y(running_median(y, w), f"filter(Despike,{w})")); continue
        o = max(int(order), 1)
        w = auto_window(y, "Polynomial" if method not in ("Median", "DeNoise") else method, o, factor, w_max=31 if method == "DeNoise" else None) if auto else _odd(window)
        w = min(w, _odd(len(y) // 2 - 1, 3))
        if method in ("1st derivative", "2nd derivative"):
            d = 1 if method.startswith("1") else 2; oo = max(o, d + 1 if o <= d else o); oo = min(oo, w - 1)
            if oo < d: w = _odd(d + 2); oo = d + 1
            dx = float(np.median(np.diff(s.x)))
            new = savgol_filter(y, w, oo, deriv=d, delta=dx, mode="interp")
            out.append(s.with_y(new, f"filter({method},w={w},order={oo})")); continue
        if method == "Polynomial" and o >= w: w = _odd(o + 1)
        out.append(s.with_y(_smooth_by(method, y, w, o), f"filter({method},{'auto ' if auto else ''}w={w}" + (f",order={o})" if method == "Polynomial" else ")")))
    return out
