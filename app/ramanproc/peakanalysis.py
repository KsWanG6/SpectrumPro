"""Peak analysis: peak finding + position / height / area / FWHM, peak fitting, and peak ratios.

Baseline options for height/area: 'none', 'linear' (line through the window edges, edges averaged over a few points),
'min' (horizontal line at the window minimum).
Peak ratio kinds: 'height' (H_A/H_B), 'area' (A_A/A_B), 'fit_area' (fitted areas, pseudo-Voigt family).
Uncertainty: sigma_R/R = sqrt((sA/A)^2 + (sB/B)^2 - 2 cov(A,B)/(A B)); the covariance term is only non-zero when A and B
come from one joint fit (overlapping peaks), otherwise A and B are treated as independent.
"""
import numpy as np
from scipy.optimize import curve_fit
from .core import Spectrum
from .ops import integral
from .peaks import find_raman_peaks

BASELINES = ("none", "linear", "min")
_LN2 = np.log(2.0)


# ------------------------------------------------------------------ noise
def noise_sigma(s: Spectrum, region=None) -> float:
    """Robust white-noise sigma from the first difference (MAD); `region` = (x_lo, x_hi) of a peak-free zone."""
    x, y = s.x, s.y
    if region is not None:
        m = (x >= min(region)) & (x <= max(region)); y = y[m]
    if len(y) < 4: raise ValueError("noise region contains too few points")
    d = np.diff(y)
    return float(1.4826 * np.median(np.abs(d - np.median(d))) / np.sqrt(2))


# ------------------------------------------------------------------ baseline + measurement
def _baseline(x, y, kind):
    """Baseline array for the points (x, y) of one window."""
    if kind == "none": return np.zeros_like(y), (0.0, 0.0)
    if kind == "min": return np.full_like(y, y.min()), (y.min(), y.min())
    if kind == "linear":
        k = max(1, int(0.05 * len(x)))
        xl, yl, xr, yr = x[:k].mean(), y[:k].mean(), x[-k:].mean(), y[-k:].mean()
        if xr == xl: return np.full_like(y, yl), (yl, yl)
        return yl + (yr - yl) * (x - xl) / (xr - xl), (yl + (yr - yl) * (x[0] - xl) / (xr - xl), yl + (yr - yl) * (x[-1] - xl) / (xr - xl))
    raise ValueError(f"unknown baseline {kind!r}")


def measure_peak(s: Spectrum, center: float, hw: float, baseline: str = "linear", pos_hw: float | None = None,
                 noise: float | None = None) -> dict:
    """Position, height, area, FWHM of the peak near `center`.
    hw = half width of the integration/baseline window; pos_hw = half width of the zone searched for the maximum (default hw)."""
    lo, hi = max(center - hw, s.x[0]), min(center + hw, s.x[-1])
    m = (s.x >= lo) & (s.x <= hi)
    if m.sum() < 5: raise ValueError("window has fewer than 5 points")
    x, y = s.x[m], s.y[m]
    base, (b_lo, b_hi) = _baseline(x, y, baseline)
    corr = y - base
    pm = np.abs(x - center) <= (hw if pos_hw is None else pos_hw)
    if not pm.any(): raise ValueError("no data in the position search zone")
    idx = np.nonzero(pm)[0]; i = int(idx[np.argmax(corr[idx])])
    pos, height = float(x[i]), float(corr[i])
    if 0 < i < len(x) - 1:
        a, b, c = corr[i - 1], corr[i], corr[i + 1]; den = a - 2 * b + c
        if den != 0:
            d = 0.5 * (a - c) / den; step = 0.5 * (x[i + 1] - x[i - 1]); pos = float(x[i] + d * step); height = float(b - 0.25 * (a - c) * d)
    area = float(integral(s, x[0], x[-1])) - 0.5 * (b_lo + b_hi) * (x[-1] - x[0])
    # FWHM by linear interpolation of the half-height crossings
    fwhm = float("nan"); half = height / 2
    if height > 0:
        j = i
        while j > 0 and corr[j] > half: j -= 1
        k = i
        while k < len(x) - 1 and corr[k] > half: k += 1
        if corr[j] <= half < corr[j + 1] and corr[k] <= half < corr[k - 1]:
            xl = x[j] + (half - corr[j]) / (corr[j + 1] - corr[j]) * (x[j + 1] - x[j])
            xr = x[k - 1] + (corr[k - 1] - half) / (corr[k - 1] - corr[k]) * (x[k] - x[k - 1])
            fwhm = float(xr - xl)
    sig = noise_sigma(s) if noise is None else noise
    dx = float(np.median(np.diff(x)))
    # area noise = noise inside the window + noise of the baseline estimate (dominant for a linear / minimum baseline)
    W_ = float(x[-1] - x[0]); k_ = max(1, int(0.05 * len(x))); var_base = 0.0
    if baseline == "linear":
        xl, xr = x[:k_].mean(), x[-k_:].mean()
        t = (0.5 * (x[0] + x[-1]) - xl) / (xr - xl) if xr != xl else 0.5
        var_base = (sig ** 2 / k_) * ((1 - t) ** 2 + t ** 2) * W_ ** 2         # line through two k-point means, integrated over the window
    elif baseline == "min":
        var_base = (0.5 * sig * W_) ** 2                                       # sd of the minimum of N noisy points ~ 0.5 sigma (empirical)
    sigma_area = float(np.sqrt((sig * dx) ** 2 * len(x) + var_base))
    return {"position": pos, "height": height, "area": area, "fwhm": fwhm, "baseline": baseline, "window": (float(x[0]), float(x[-1])),
            "sigma_height": sig, "sigma_area": sigma_area, "snr": height / sig if sig > 0 else float("inf"),
            "x": x, "base": base}


def analyze_peaks(s: Spectrum, prominence=None, rel_prominence=0.02, min_distance=5.0, baseline="linear",
                  width_factor=2.0, fit_model: str | None = None, min_snr: float = 0.0) -> list:
    """Find peaks and measure each one. Window = +-width_factor*FWHM around the peak (at least +-4 points)."""
    dx = float(np.median(np.diff(s.x))); sig = noise_sigma(s); out = []
    for p in find_raman_peaks(s, prominence, min_distance, rel_prominence):
        fw = p["fwhm"] if np.isfinite(p["fwhm"]) and p["fwhm"] > 0 else 6 * dx
        hw = max(width_factor * fw, 4 * dx)
        try:
            r = measure_peak(s, p["x"], hw, baseline, pos_hw=max(0.5 * fw, 2 * dx), noise=sig)
        except ValueError:
            continue
        if r["snr"] < min_snr:
            continue
        r.update({"prominence": p["prominence"], "fit": None}); r.pop("x"); r.pop("base")
        if fit_model:
            try:
                f = fit_peaks(s, [p["x"]], hw, fit_model, baseline)
                r["fit"] = {k: f["peaks"][0][k] for k in ("position", "height", "fwhm", "area", "area_sd")}; r["fit"]["r2"] = f["r2"]
            except Exception:
                r["fit"] = None
        out.append(r)
    return out


# ------------------------------------------------------------------ peak fitting
def _shape(x, h, c, w, eta):
    t = (x - c) / w
    return h * (eta / (1 + 4 * t ** 2) + (1 - eta) * np.exp(-4 * _LN2 * t ** 2))


def shape_area(h, w, eta):
    return h * w * (eta * np.pi / 2 + (1 - eta) * np.sqrt(np.pi / (4 * _LN2)))


def fit_peaks(s: Spectrum, centers, hw: float, model: str = "pseudovoigt", baseline: str = "linear", maxfev: int = 20000,
              max_shift: float | None = None, min_width: float | None = None, max_width: float | None = None) -> dict:
    """Joint fit of one or more peaks in [min(centers)-hw, max(centers)+hw] plus a linear (or no) baseline.
    model: gaussian | lorentzian | pseudovoigt. Returns peaks (position, height, fwhm, eta, area, area_sd, ...), the area
    covariance matrix, R^2 and the fitted curve."""
    centers = [float(c) for c in centers]
    # optional limits: max_shift = largest centre movement, min_width / max_width = FWHM bounds (same units as x)
    lo, hi = max(min(centers) - hw, s.x[0]), min(max(centers) + hw, s.x[-1])
    m = (s.x >= lo) & (s.x <= hi); x, y = s.x[m], s.y[m]
    npk = len(centers); free_eta = model == "pseudovoigt"; per = 4 if free_eta else 3
    if model not in ("gaussian", "lorentzian", "pseudovoigt"): raise ValueError(f"unknown model {model!r}")
    if len(x) < per * npk + 3: raise ValueError("too few points for this fit")
    eta_fixed = 1.0 if model == "lorentzian" else 0.0
    fit_base = baseline != "none"; dx = float(np.median(np.diff(x)))
    p0, lb, ub = [], [], []
    yr = float(np.ptp(y)) or 1.0
    for c in centers:
        near = np.abs(x - c) <= max(hw / 2, 2 * dx)
        h0 = max(float(y[near].max() - np.percentile(y, 10)), 1e-9 * yr)
        p0 += [h0, c, hw / 3] + ([0.5] if free_eta else [])
        ms = hw if not max_shift else float(max_shift)
        wlo = max(dx, float(min_width)) if min_width else dx; whi = float(max_width) if max_width else 3 * hw
        if whi <= wlo: raise ValueError("max width must be larger than min width")
        p0[-3 - (1 if free_eta else 0) + 2] = min(max(p0[-3 - (1 if free_eta else 0) + 2], wlo * 1.01), whi * 0.99)
        lb += [0, c - ms, wlo] + ([0.0] if free_eta else []); ub += [10 * yr + abs(h0) * 10, c + ms, whi] + ([1.0] if free_eta else [])
    if fit_base:
        p0 += [float(y.min()), 0.0]; lb += [-np.inf, -np.inf]; ub += [np.inf, np.inf]

    def unpack(p):
        pk = [(p[i * per], p[i * per + 1], p[i * per + 2], p[i * per + 3] if free_eta else eta_fixed) for i in range(npk)]
        b = (p[npk * per], p[npk * per + 1]) if fit_base else (0.0, 0.0)
        return pk, b

    xm = x.mean()
    def f(xx, *p):
        pk, b = unpack(p)
        return sum(_shape(xx, *q) for q in pk) + b[0] + b[1] * (xx - xm)
    popt, pcov = curve_fit(f, x, y, p0=p0, bounds=(lb, ub), maxfev=int(maxfev))
    if not np.all(np.isfinite(pcov)): raise RuntimeError("fit did not converge (covariance not finite)")
    pk, b = unpack(popt)

    def areas(p):
        q, _ = unpack(p); return np.array([shape_area(h, w, e) for h, c, w, e in q])
    J = np.empty((npk, len(popt)))
    for j in range(len(popt)):
        d = 1e-6 * max(abs(popt[j]), 1.0); pp = popt.copy(); pm_ = popt.copy(); pp[j] += d; pm_[j] -= d
        J[:, j] = (areas(pp) - areas(pm_)) / (2 * d)
    acov = J @ pcov @ J.T
    res = y - f(x, *popt); sst = float(np.sum((y - y.mean()) ** 2))
    peaks = []
    for i, (h, c, w, e) in enumerate(pk):
        sd = np.sqrt(np.diag(pcov))
        peaks.append({"position": float(c), "height": float(h), "fwhm": float(w), "eta": float(e), "area": float(shape_area(h, w, e)),
                      "area_sd": float(np.sqrt(max(acov[i, i], 0))), "height_sd": float(sd[i * per]), "position_sd": float(sd[i * per + 1])})
    base_arr = b[0] + b[1] * (x - xm)
    comps = [_shape(x, *q) for q in pk]
    return {"peaks": peaks, "components": comps, "area_cov": acov, "r2": 1 - float(np.sum(res ** 2)) / sst if sst > 0 else 1.0, "x": x, "y": y,
            "yfit": f(x, *popt), "base": base_arr, "model": model, "window": (float(x[0]), float(x[-1]))}


# ------------------------------------------------------------------ ratios
def peak_ratio(s: Spectrum, A: dict, B: dict, kind: str = "height", fit_model: str = "pseudovoigt", min_den: float = 0.0,
               on_fail: str = "nan", noise: float | None = None) -> dict:
    """R = feature(A) / feature(B) with the SAME feature type for both peaks.
    A, B: {'center','hw','baseline'}.  on_fail (denominator <= min_den, non-finite value or failed fit):
    'nan' -> R = nan, status 'failed'; 'min' -> denominator replaced by min_den (status 'replaced', needs min_den>0);
    'error' -> raise ValueError.  Failure handling 'skip' is the caller's job (status 'failed')."""
    if kind not in ("height", "area", "fit_area"): raise ValueError(f"unknown ratio kind {kind!r}")
    if on_fail not in ("nan", "min", "error"): raise ValueError(f"unknown on_fail {on_fail!r}")
    sig = noise_sigma(s) if noise is None else noise
    info = {"kind": kind, "correlated": False, "status": "ok", "reason": "", "R": float("nan"), "sigma_R": float("nan")}
    try:
        if kind in ("height", "area"):
            ma = measure_peak(s, A["center"], A["hw"], A.get("baseline", "linear"), noise=sig)
            mb = measure_peak(s, B["center"], B["hw"], B.get("baseline", "linear"), noise=sig)
            key = "height" if kind == "height" else "area"
            a, b, sa, sb, cov = ma[key], mb[key], ma["sigma_" + key], mb["sigma_" + key], 0.0
            info.update(A_pos=ma["position"], B_pos=mb["position"])
        else:
            overlap = abs(A["center"] - B["center"]) <= A["hw"] + B["hw"]
            bl = A.get("baseline", "linear")
            if overlap:
                f = fit_peaks(s, [A["center"], B["center"]], max(A["hw"], B["hw"]), fit_model, bl)
                pa, pb = f["peaks"]; cov = float(f["area_cov"][0, 1]); info["correlated"] = True
            else:
                pa = fit_peaks(s, [A["center"]], A["hw"], fit_model, A.get("baseline", "linear"))["peaks"][0]
                pb = fit_peaks(s, [B["center"]], B["hw"], fit_model, B.get("baseline", "linear"))["peaks"][0]; cov = 0.0
            a, b, sa, sb = pa["area"], pb["area"], pa["area_sd"], pb["area_sd"]
            info.update(A_pos=pa["position"], B_pos=pb["position"])
    except (ValueError, RuntimeError) as ex:
        if on_fail == "error": raise ValueError(f"peak ratio failed: {ex}")
        info.update(status="failed", reason=str(ex)); return info
    info.update(a=a, b=b, sigma_a=sa, sigma_b=sb, cov_ab=cov)
    if not (np.isfinite(a) and np.isfinite(b)) or b <= min_den:
        why = f"分母 {b:.4g} ≤ 下限 {min_den:g}"
        if on_fail == "error": raise ValueError(why)
        if on_fail == "min" and min_den > 0 and np.isfinite(a):
            b = min_den; info.update(status="replaced", reason=why + "，以下限取代")
        else:
            info.update(status="failed", reason=why); return info
    R = a / b
    rel2 = (sa / a) ** 2 + (sb / b) ** 2 - 2 * cov / (a * b) if a != 0 else float("nan")
    info.update(R=float(R), sigma_R=float(abs(R) * np.sqrt(max(rel2, 0.0))) if np.isfinite(rel2) else float("nan"), b=b)
    return info
