"""Infrared (FT-IR) tools: %T <-> absorbance, CO2 elimination, base correction, characteristic-peak prediction.

A spectrum carries its Y mode in `history` as the tag "ir=T" (percent transmittance) or "ir=A" (absorbance); the last tag wins.
All tools return NEW spectra (the original is untouched) in the SAME mode as the input.
Peak prediction works in absorbance (peaks up) whatever the input mode, and only LISTS candidate assignments from a
correlation table - it does not identify a compound.
"""
from __future__ import annotations
import numpy as np
from scipy.signal import find_peaks, peak_widths
from .core import Spectrum

_TMIN = 1e-3                      # %T floor before taking the logarithm


# ------------------------------------------------------------------ mode helpers
def ir_mode(s: Spectrum):
    """'T', 'A' or None (not an IR spectrum), from the history tags."""
    m = None
    for h in s.history:
        if h == "ir=T": m = "T"
        elif h == "ir=A": m = "A"
    return m


def guess_mode(y) -> str:
    y = np.asarray(y, float); y = y[np.isfinite(y)]
    if len(y) == 0: return "A"
    return "T" if (np.nanmax(y) > 5.0 and np.nanmin(y) >= -5.0 and np.nanmax(y) <= 130) else "A"


def t_to_a(t):
    return -np.log10(np.clip(np.asarray(t, float), _TMIN, None) / 100.0)


def a_to_t(a):
    return 100.0 * np.power(10.0, -np.asarray(a, float))


def to_absorbance(s: Spectrum) -> Spectrum:
    if ir_mode(s) == "A": return s
    return Spectrum(s.x.copy(), t_to_a(s.y), s.name, s.history + ["%T->Abs", "ir=A"])


def to_transmittance(s: Spectrum) -> Spectrum:
    if ir_mode(s) == "T": return s
    return Spectrum(s.x.copy(), a_to_t(s.y), s.name, s.history + ["Abs->%T", "ir=T"])


def _absorbance_y(s: Spectrum):
    return t_to_a(s.y) if ir_mode(s) == "T" else np.asarray(s.y, float)


def _from_absorbance(s: Spectrum, a, step: str) -> Spectrum:
    y = a_to_t(a) if ir_mode(s) == "T" else np.asarray(a, float)
    return Spectrum(s.x.copy(), y, s.name, s.history + [step])


# ------------------------------------------------------------------ CO2 elimination
CO2_REGIONS = {"stretch": (2280.0, 2400.0), "bend": (645.0, 690.0)}


def _edge_value(x, y, edge_x, side, n=4):
    """Mean of the n points just outside the region on `side` (-1 = left, +1 = right); also the x position of that mean."""
    i = int(np.searchsorted(x, edge_x))
    if side < 0: sl = slice(max(i - n, 0), max(i, 1))
    else: sl = slice(min(i, len(x) - 1), min(i + n, len(x)))
    return float(np.mean(x[sl])), float(np.mean(y[sl]))


def co2_band_height(s: Spectrum, lo=2280.0, hi=2400.0) -> float:
    """Height of the CO2 asymmetric-stretch band above the straight line joining the region edges, in absorbance units."""
    a = _absorbance_y(s); x = s.x
    if lo < x[0] or hi > x[-1]: return float("nan")
    x0, y0 = _edge_value(x, a, lo, -1); x1, y1 = _edge_value(x, a, hi, +1)
    m = (x >= lo) & (x <= hi)
    if not m.any(): return float("nan")
    base = y0 + (y1 - y0) * (x[m] - x0) / (x1 - x0)
    return float(np.max(a[m] - base))


def co2_eliminate(s: Spectrum, regions=((2280.0, 2400.0),), n_edge: int = 4) -> Spectrum:
    """Replace each region by the straight line joining the data just outside it (edge means of n_edge points)."""
    y = s.y.copy(); done = []
    for lo, hi in regions:
        lo, hi = min(lo, hi), max(lo, hi)
        if hi <= s.x[0] or lo >= s.x[-1]: continue
        m = (s.x >= lo) & (s.x <= hi)
        if m.sum() < 1 or lo <= s.x[0] or hi >= s.x[-1]: continue
        x0, y0 = _edge_value(s.x, y, lo, -1, n_edge); x1, y1 = _edge_value(s.x, y, hi, +1, n_edge)
        y[m] = y0 + (y1 - y0) * (s.x[m] - x0) / (x1 - x0)
        done.append(f"{lo:g}-{hi:g}")
    if not done: raise ValueError("CO2 區間不在光譜 X 範圍內（或貼著光譜邊緣）")
    return Spectrum(s.x.copy(), y, s.name, s.history + ["CO2-elim(" + ", ".join(done) + ")"])


# ------------------------------------------------------------------ base correction
def _lower_hull(x, y):
    """Indices of the lower convex hull of (x, y) (monotone chain)."""
    h = []
    for i in range(len(x)):
        while len(h) >= 2:
            a, b = h[-2], h[-1]
            if (x[b] - x[a]) * (y[i] - y[a]) - (y[b] - y[a]) * (x[i] - x[a]) <= 0: h.pop()
            else: break
        h.append(i)
    return h


def rubberband(x, a):
    h = _lower_hull(x, a)
    return np.interp(x, x[h], a[h])


def polybase(x, a, order=3, iters=60):
    """Iterative modified polynomial: clip the signal to the fit from below until stable."""
    xs = (x - x.mean()) / (np.ptp(x) / 2); w = a.copy()
    for _ in range(iters):
        c = np.polynomial.polynomial.polyfit(xs, w, order); f = np.polynomial.polynomial.polyval(xs, c)
        nw = np.minimum(w, f)
        if np.max(np.abs(nw - w)) < 1e-7 * (np.ptp(a) or 1): w = nw; break
        w = nw
    c = np.polynomial.polynomial.polyfit(xs, w, order)
    return np.polynomial.polynomial.polyval(xs, c)


def anchor_base(x, a, anchors, half_width=6.0):
    """Piecewise-linear baseline through the given wavenumbers (each anchor = LOWEST local median-free value within +-half_width)."""
    ax, ay = [], []
    for p in sorted(float(v) for v in anchors):
        if p < x[0] - 1e-9 or p > x[-1] + 1e-9: continue
        m = (x >= p - half_width) & (x <= p + half_width)
        if not m.any(): continue
        ax.append(float(p)); ay.append(float(np.min(a[m])))
    if len(ax) < 2: raise ValueError("錨點至少要 2 個，且要落在光譜範圍內")
    return np.interp(x, ax, ay)


def base_correct(s: Spectrum, method: str = "rubberband", order: int = 3, anchors=None, anchor_hw: float = 6.0,
                 region=None) -> Spectrum:
    """Subtract a baseline in the absorbance domain; %T input comes back as %T (= T / T_baseline x 100).
    method: 'rubberband' | 'poly' | 'anchors' | 'ends' (straight line between the two ends).  region=(lo, hi) limits the fit/output."""
    x = s.x; a = _absorbance_y(s)
    if not np.all(np.isfinite(a)): raise ValueError("光譜含缺值，請先處理 NaN")
    m = np.ones(len(x), bool) if region is None else (x >= min(region)) & (x <= max(region))
    if m.sum() < 5: raise ValueError("基線區間資料點太少")
    xm, am = x[m], a[m]
    if method == "rubberband": b = rubberband(xm, am); lab = "rubberband"
    elif method == "poly": b = polybase(xm, am, order); lab = f"poly{order}"
    elif method == "anchors": b = anchor_base(xm, am, anchors or [], anchor_hw); lab = "anchors(" + ",".join(f"{v:g}" for v in sorted(anchors)) + ")"
    elif method == "ends":
        k = max(3, len(xm) // 100); b = np.interp(xm, [xm[:k].mean(), xm[-k:].mean()], [am[:k].mean(), am[-k:].mean()]); lab = "ends"
    else: raise ValueError(f"unknown method {method!r}")
    out = a.copy(); out[m] = am - b
    rg = "" if region is None else f", {min(region):g}-{max(region):g}"
    return _from_absorbance(s, out, f"IR-baseline({lab}{rg})")


# ------------------------------------------------------------------ characteristic peak prediction
# (low, high, assignment, intensity class(es) typical: s/m/w, broad?)
GROUPS = [
    (3580, 3700, "O–H 伸縮（游離、不成氫鍵；金屬–OH）", "mw", False),
    (3200, 3600, "O–H 伸縮（醇／酚／水，氫鍵）", "sm", True),
    (3250, 3500, "N–H 伸縮（胺／醯胺）", "mw", False),
    (3260, 3330, "≡C–H 伸縮（末端炔）", "s", False),
    (3000, 3100, "=C–H 伸縮（烯／芳香 C–H）", "mw", False),
    (2500, 3300, "O–H 伸縮（羧酸二聚體，極寬）", "ms", True),
    (2400, 3200, "N–H⁺ 伸縮（銨鹽／胺鹽，寬）", "ms", True),
    (2915, 2975, "C–H 反對稱伸縮（CH₃／CH₂）", "ms", False),
    (2840, 2885, "C–H 對稱伸縮（CH₃／CH₂）", "ms", False),
    (2695, 2830, "醛基 C–H（Fermi 雙峰約 2720／2820）", "w", False),
    (2550, 2600, "S–H 伸縮（硫醇）", "w", False),
    (2300, 2400, "CO₂ 反對稱伸縮（大氣 CO₂ 或吸附 CO₂）", "m", False),
    (2210, 2260, "C≡N 伸縮（腈）", "m", False),
    (2100, 2260, "C≡C 伸縮（炔）", "w", False),
    (2080, 2160, "N₃ 反對稱伸縮（疊氮）", "s", False),
    (1650, 2000, "芳香環泛頻／組合帶", "w", False),
    (1770, 1820, "C=O 伸縮（醯氯／酸酐）", "s", False),
    (1735, 1750, "C=O 伸縮（酯）", "s", False),
    (1720, 1740, "C=O 伸縮（醛）", "s", False),
    (1705, 1725, "C=O 伸縮（酮）", "s", False),
    (1680, 1725, "C=O 伸縮（羧酸）", "s", False),
    (1630, 1690, "C=O 伸縮（醯胺 I）", "s", False),
    (1620, 1680, "C=C 伸縮（烯）", "mw", False),
    (1620, 1665, "H–O–H 彎曲（水）", "m", True),
    (1580, 1650, "N–H 彎曲（一級胺）", "m", False),
    (1550, 1650, "COO⁻ 反對稱伸縮（羧酸鹽）", "s", False),
    (1585, 1600, "芳香環 C=C 伸縮", "m", False),
    (1450, 1500, "芳香環 C=C 伸縮", "m", False),
    (1510, 1570, "N–H 彎曲＋C–N（醯胺 II）", "s", False),
    (1500, 1570, "N–O 反對稱伸縮（硝基）", "s", False),
    (1300, 1390, "N–O 對稱伸縮（硝基）", "s", False),
    (1430, 1470, "C–H 彎曲（CH₂／CH₃）", "m", False),
    (1365, 1385, "C–H 對稱彎曲（CH₃）", "m", False),
    (1380, 1500, "CO₃²⁻ ν₃ 反對稱伸縮（碳酸鹽，寬）", "s", True),
    (1300, 1450, "COO⁻ 對稱伸縮（羧酸鹽）", "ms", False),
    (1330, 1440, "O–H 面內彎曲（醇／酸）", "m", False),
    (1290, 1350, "S=O 反對稱伸縮（碸／磺酸鹽）", "s", False),
    (1120, 1180, "S=O 對稱伸縮（碸／磺酸鹽）", "s", False),
    (1180, 1260, "C–O 伸縮（酚／芳香酯）", "s", False),
    (1200, 1275, "C–O–C 反對稱（芳香醚）", "s", False),
    (1160, 1300, "C–O 伸縮（酯）", "s", False),
    (1070, 1150, "C–O–C 伸縮（醚）", "s", False),
    (1000, 1260, "C–O 伸縮（醇）", "s", False),
    (1020, 1250, "C–N 伸縮（胺）", "m", False),
    (1000, 1400, "C–F 伸縮", "s", False),
    (1000, 1130, "Si–O–Si 伸縮（矽氧烷／二氧化矽，寬）", "s", True),
    (1000, 1100, "PO₄³⁻ ν₃（磷酸鹽）", "s", True),
    (1080, 1130, "SO₄²⁻ ν₃（硫酸鹽）", "s", False),
    (960, 990, "=C–H 面外彎曲（反式烯）", "s", False),
    (905, 995, "=CH₂ 面外彎曲（乙烯基）", "s", False),
    (850, 890, "CO₃²⁻ ν₂ 面外彎曲（碳酸鹽）", "m", False),
    (675, 900, "芳香 C–H 面外彎曲（取代型態）", "s", False),
    (680, 750, "CO₃²⁻ ν₄ 面內彎曲（碳酸鹽）", "w", False),
    (720, 725, "CH₂ 搖擺（長鏈 ≥4 個 CH₂）", "m", False),
    (600, 800, "C–Cl 伸縮", "s", False),
    (515, 690, "C–Br 伸縮", "s", False),
    (600, 700, "≡C–H 彎曲（炔）", "s", True),
    (570, 705, "C–S 伸縮", "w", False),
    (630, 670, "CO₂ 彎曲（大氣 CO₂）", "m", False),
    (400, 700, "金屬–氧 M–O 伸縮／晶格振動", "ms", True),
    (440, 480, "Si–O–Si 彎曲", "s", False),
    (430, 550, "S–S 伸縮（雙硫鍵）", "w", False),
]


def _intensity_class(rel):
    return "s" if rel >= 0.6 else ("m" if rel >= 0.25 else "w")


def assign(pos: float, cls: str, broad: bool, tol: float = 8.0, top: int = 4):
    """Candidate assignments for a band: groups whose range contains `pos` (within tol), best fit first."""
    out = []
    for lo, hi, name, ints, br in GROUPS:
        if pos < lo - tol or pos > hi + tol: continue
        inside = lo <= pos <= hi
        score = (0 if inside else 1, 0 if br == broad else 1, 0 if cls in ints else 1, hi - lo, abs(pos - (lo + hi) / 2))   # specific (narrow range) first
        out.append((score, name))
    out.sort(key=lambda t: t[0])
    seen, res = set(), []
    for _, n in out:
        if n in seen: continue
        seen.add(n); res.append(n)
    return res[:top]


def predict_peaks(s: Spectrum, region=None, rel_prominence: float = 0.05, min_distance: float = 8.0,
                  smooth_pts: int = 0, max_peaks: int = 60) -> list:
    """Find absorption bands and attach candidate assignments.
    Returns dicts: x (cm-1), a (absorbance at the peak), t (%T at the peak if known), prominence (A), fwhm (cm-1),
    rel (prominence / strongest prominence), cls ('s'|'m'|'w'), broad (bool), guess (list of strings)."""
    x = s.x; a = _absorbance_y(s)
    if not np.all(np.isfinite(a)): raise ValueError("光譜含缺值，請先處理 NaN")
    if smooth_pts and smooth_pts >= 3:
        k = np.ones(int(smooth_pts)) / int(smooth_pts); a = np.convolve(a, k, mode="same")
    lo, hi = (x[0], x[-1]) if region is None else (min(region), max(region))
    step = float(np.median(np.diff(x)))
    thr = rel_prominence * float(np.ptp(a))
    idx, props = find_peaks(a, prominence=max(thr, 1e-12), distance=max(int(round(min_distance / step)), 1))
    if len(idx) == 0: return []
    widths = peak_widths(a, idx, rel_height=0.5)[0] * step
    maxprom = float(props["prominences"].max())
    rows = []
    for k, i in enumerate(idx):
        if not (lo <= x[i] <= hi): continue
        xp, ap = float(x[i]), float(a[i])
        if 0 < i < len(a) - 1:
            p0, p1, p2 = a[i - 1], a[i], a[i + 1]; den = p0 - 2 * p1 + p2
            if den != 0:
                d = 0.5 * (p0 - p2) / den; xp = float(x[i] + d * step); ap = float(p1 - 0.25 * (p0 - p2) * d)
        prom = float(props["prominences"][k]); rel = prom / maxprom; fw = float(widths[k]); cls = _intensity_class(rel); broad = fw >= 50.0
        rows.append({"x": xp, "a": ap, "t": float(a_to_t(ap)) if ir_mode(s) == "T" else None, "prominence": prom, "fwhm": fw,
                     "rel": rel, "cls": cls, "broad": broad, "guess": assign(xp, cls, broad)})
    rows.sort(key=lambda r: -r["prominence"]); rows = rows[:max_peaks]; rows.sort(key=lambda r: -r["x"])
    return rows


CLS_TEXT = {"s": "強 (s)", "m": "中 (m)", "w": "弱 (w)"}
