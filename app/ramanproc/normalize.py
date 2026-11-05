import numpy as np
from .core import Spectrum

METHODS = ("minmax", "area", "max", "l2", "peak_height", "peak_area")


def normalize(s: Spectrum, method: str = "minmax", center: float | None = None, hw: float | None = None, baseline: bool = False) -> Spectrum:
    """'minmax'      : (y-min)/(max-min) -> [0,1].
    'area'        : y / trapezoid area of the (baseline-shifted, y-min) curve.
    'max'         : y / max(y)  (no offset removed: the baseline level is kept, the maximum becomes 1).
    'l2'          : y / sqrt(sum(y^2))  (unit vector; for spectral matching / classification).
    'peak_height' : y / height of the peak in [center-hw, center+hw] (internal-standard band = 1). baseline=True subtracts the straight
                    line joining the window edges before taking the height (the whole spectrum is still only scaled, not shifted).
    'peak_area'   : y / area of the band [center-hw, center+hw] (spline integral); baseline=True subtracts the edge-to-edge line."""
    y = s.y
    if method == "minmax":
        rng = y.max() - y.min()
        if rng == 0:
            raise ValueError("constant spectrum cannot be min-max normalised")
        out = (y - y.min()) / rng; tag = "minmax"
    elif method == "area":
        area = np.trapezoid(y - y.min(), s.x)
        if area == 0:
            raise ValueError("zero area")
        out = y / area; tag = "area"
    elif method == "max":
        m = float(np.max(y))
        if not np.isfinite(m) or m <= 0:
            raise ValueError("最大值必須為正數才能以最大值均一化")
        out = y / m; tag = "max"
    elif method == "l2":
        n = float(np.sqrt(np.sum(y ** 2)))
        if not np.isfinite(n) or n == 0:
            raise ValueError("光譜的 L2 範數為 0 或不是有限值")
        out = y / n; tag = "L2"
    elif method in ("peak_height", "peak_area"):
        if center is None or hw is None or hw <= 0:
            raise ValueError("峰均一化需要峰位（center）與正的視窗半寬（hw）")
        from .lod import peak_response
        what = "height" if method == "peak_height" else "area"
        try: ref = peak_response(s, float(center), float(hw), what, bool(baseline))
        except ValueError as ex:
            raise ValueError(f"{center:g}±{hw:g} 的峰視窗無法計算（{'視窗不在光譜範圍內' if 'outside' in str(ex) else '視窗內資料點少於 2 點'}）") from None
        if not np.isfinite(ref) or ref <= 0:
            raise ValueError(f"{center:g}±{hw:g} 的{'峰高' if what == 'height' else '峰面積'}為 {ref:.4g}（≤ 0），無法作為均一化基準；請檢查峰位、視窗或基線")
        out = y / ref; tag = f"{method}@{center:g}±{hw:g}" + (",baseline" if baseline else "")
    else:
        raise ValueError(f"unknown method {method!r}")
    return s.with_y(out, f"normalize({tag})")
