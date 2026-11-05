"""Quantification module: calibration, inverse prediction with uncertainty, LOD/LOQ with a full audit record.

Roles of samples: blank, standard, unknown, lod_check (low-concentration verification sample).
Models: 'linear' (OLS), 'linear_w1x' (weights 1/C), 'linear_w1x2' (weights 1/C^2), 'loglinear' (response vs log10 C).
"""
import numpy as np
from scipy import stats
from .core import Spectrum
from .lod import peak_response

MODELS = {"linear": (False, 0), "linear_w1x": (False, 1), "linear_w1x2": (False, 2), "loglinear": (True, 0)}
SIGMA_SOURCES = ("blank", "low_conc", "residual", "intercept", "multi_intercept")
SIGMA_LABELS = {"blank": "空白重複的標準差", "low_conc": "最低濃度重複樣品的標準差", "residual": "迴歸殘差 Sy.x",
                "intercept": "單條檢量線的截距標準誤", "multi_intercept": "多條檢量線截距的變異（SD）"}


# ------------------------------------------------------------------ features
def feature_value(s: Spectrum, feat: dict) -> float:
    """feat: kind in height|area|ratio_height|ratio_area, center, hw, baseline, (ref_center, ref_hw for ratios)."""
    kind = feat["kind"]; mode = "height" if kind.endswith("height") else "area"; bl = bool(feat.get("baseline", False))
    a = peak_response(s, feat["center"], feat["hw"], mode, bl)
    if kind.startswith("ratio"):
        r = peak_response(s, feat["ref_center"], feat["ref_hw"], mode, bl)
        if r <= 0: raise ValueError("reference peak response must be positive for ratio features")
        return a / r
    return a


# ------------------------------------------------------------------ calibration
def fit_calibration(conc, resp, model="linear") -> dict:
    if model not in MODELS: raise ValueError(f"unknown model {model!r}")
    log, p = MODELS[model]
    c = np.asarray(conc, float); y = np.asarray(resp, float)
    if len(c) < 3: raise ValueError("need at least 3 calibration points")
    if (log or p) and np.any(c <= 0): raise ValueError("this model needs all standard concentrations > 0")
    x = np.log10(c) if log else c
    w = c ** (-float(p)) if p else np.ones_like(c)
    sw = w.sum(); xb = (w * x).sum() / sw; yb = (w * y).sum() / sw
    sxx = float((w * (x - xb) ** 2).sum())
    if sxx == 0: raise ValueError("calibration concentrations are all equal")
    S = float((w * (x - xb) * (y - yb)).sum() / sxx); b = float(yb - S * xb)
    res = y - (S * x + b); n = len(x); dof = n - 2
    sy = float(np.sqrt((w * res ** 2).sum() / dof))
    sst = float((w * (y - yb) ** 2).sum())
    return {"model": model, "log": log, "p": p, "slope": S, "intercept": b, "n": n, "dof": dof, "sy": sy,
            "se_slope": sy / np.sqrt(sxx), "se_intercept": float(sy * np.sqrt(1 / sw + xb ** 2 / sxx)),
            "r2": 1 - float((w * res ** 2).sum()) / sst if sst > 0 else 1.0, "residuals": res, "x": x, "conc": c, "resp": y,
            "xbar": float(xb), "ybar": float(yb), "sxx": sxx, "sumw": float(sw),
            "c_low": float(c[c > 0].min()) if np.any(c > 0) else None,
            "sy_resp": float(np.sqrt((res ** 2).sum() / dof)),
            "conc_range": (float(c.min()), float(c.max())), "resp_range": (float(y.min()), float(y.max()))}


def predict_conc(fit, y0, m=1, conf=0.95) -> dict:
    """Inverse prediction of concentration from response y0 (mean of m replicate measurements) with a confidence interval."""
    S = fit["slope"]
    if S == 0: raise ValueError("slope is zero")
    xh = (y0 - fit["intercept"]) / S
    conc = float(10 ** xh) if fit["log"] else float(xh)
    w0 = 1.0 if not fit["p"] else max(conc, 1e-300) ** (-fit["p"])
    sx = fit["sy"] / abs(S) * np.sqrt(1 / (w0 * m) + 1 / fit["sumw"] + (y0 - fit["ybar"]) ** 2 / (S ** 2 * fit["sxx"]))
    t = stats.t.ppf(0.5 + conf / 2, fit["dof"])
    lo, hi = xh - t * sx, xh + t * sx
    if fit["log"]: lo, hi = 10 ** lo, 10 ** hi
    return {"conc": conc, "lo": float(lo), "hi": float(hi), "sx": float(sx)}


def range_flag(fit, y0, conc) -> str:
    """'' if inside the calibrated range, else 'low' / 'high'."""
    lo, hi = fit["conc_range"]; rl, rh = fit["resp_range"]
    if conc < lo or y0 < rl and fit["slope"] > 0 or y0 > rh and fit["slope"] < 0: return "low"
    if conc > hi or y0 > rh and fit["slope"] > 0 or y0 < rl and fit["slope"] < 0: return "high"
    return ""


# ------------------------------------------------------------------ LOD / LOQ
def lod_record(fit, method, blank_resp=None, low_conc_resp=None, curves=None, k_lod=3.0, k_loq=10.0,
               slope_source="", preprocessing="", validation=None) -> dict:
    """Full LOD/LOQ record: result + everything needed to reproduce / audit it."""
    if method not in SIGMA_SOURCES: raise ValueError(f"unknown sigma source {method!r}")
    notes = []; blank = None if blank_resp is None else np.asarray(blank_resp, float)
    if method == "blank":
        if blank is None or len(blank) < 2: raise ValueError("空白法需要至少 2 個空白重複")
        sigma, n_eff = float(blank.std(ddof=1)), len(blank)
    elif method == "low_conc":
        v = None if low_conc_resp is None else np.asarray(low_conc_resp, float)
        if v is None or len(v) < 2: raise ValueError("低濃度重複法需要最低濃度標準品至少 2 個重複")
        sigma, n_eff = float(v.std(ddof=1)), len(v)
    elif method == "residual":
        # fit["sy"] is the WEIGHTED residual SD (units: response * C^(-p/2)); using it directly makes the LOD depend on the
        # concentration unit. The response-unit sigma at concentration C is sy * C^(p/2); take it at the lowest standard.
        p = fit.get("p", 0)
        if p and fit.get("c_low"):
            sigma = fit["sy"] * fit["c_low"] ** (p / 2.0)
            notes.append(f"加權模型：σ = Sy.x(加權) × C_low^{p / 2:g}，取最低標準品濃度 {fit['c_low']:.3g} 處的響應標準差")
        else:
            sigma = fit["sy"]
        n_eff = fit["n"]
    elif method == "intercept":
        sigma, n_eff = fit["se_intercept"], fit["n"]
    else:
        ints = [fit_calibration(c, r, fit["model"])["intercept"] for c, r in (curves or []) if len(c) >= 3]
        if len(ints) < 2: raise ValueError("多條檢量線法需要至少 2 條（每條 ≥3 點）檢量線")
        sigma, n_eff = float(np.std(ints, ddof=1)), len(ints)
    S = fit["slope"]
    y_blank = float(blank.mean()) if blank is not None and len(blank) else None
    if not fit["log"]:
        lod, loq = k_lod * sigma / abs(S), k_loq * sigma / abs(S)
        y0 = y_blank if y_blank is not None else fit["intercept"]
        y_lod = y0 + np.sign(S) * k_lod * sigma
        scale = "線性濃度"
    else:
        if y_blank is None:
            raise ValueError("對數濃度檢量線需要空白樣品平均值才能換算 LOD")
        yl, yq = y_blank + np.sign(S) * k_lod * sigma, y_blank + np.sign(S) * k_loq * sigma
        lod, loq = float(10 ** ((yl - fit["intercept"]) / S)), float(10 ** ((yq - fit["intercept"]) / S))
        y_lod = yl; scale = "對數濃度（log₁₀ C）"
        notes.append("對數尺度：以空白平均 + kσ 的響應代回檢量線換算濃度")
    return {"method": method, "sigma_source": SIGMA_LABELS[method], "sigma": sigma, "n_eff": n_eff, "k_lod": k_lod, "k_loq": k_loq,
            "slope": S, "slope_source": slope_source, "preprocessing": preprocessing, "scale": scale, "model": fit["model"],
            "lod": float(lod), "loq": float(loq), "y_lod": float(y_lod), "notes": notes,
            "validation": validation or {"status": "formula", "text": "僅由公式估算（尚未以低濃度樣品確認）"}}


def verify_lod(check_resp, y_lod, slope_sign=1, min_n=3, min_rate=0.95) -> dict:
    """Confirm an LOD estimate with low-concentration samples: they must exceed the response limit y_lod."""
    v = np.asarray(check_resp, float); n = len(v)
    det = int(np.sum(v * slope_sign > y_lod * slope_sign)); rate = det / n if n else 0.0
    if n < min_n:
        return {"status": "formula", "text": f"僅由公式估算（低濃度驗證樣品只有 {n} 個，需 ≥{min_n}）", "n": n, "detected": det, "rate": rate}
    ok = rate >= min_rate
    return {"status": "confirmed" if ok else "failed", "n": n, "detected": det, "rate": rate,
            "text": (f"已以低濃度樣品確認（{det}/{n} 檢出，{rate:.0%}）" if ok else f"低濃度驗證未通過（{det}/{n} 檢出，{rate:.0%} < {min_rate:.0%}）")}
