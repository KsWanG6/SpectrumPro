"""HORIBA LabSpec 6 binary spectrum file (.l6s) and map file (.l6m, same container).

Map (.l6m): one "Intens" array holding n_points x n_channels values (spectrum after spectrum, row by row with X fastest),
plus the stage grid as "X"/"Y" arrays in µm. Later arrays (Max height images etc.) are LabSpec's derived maps and are ignored.

Layout found by comparing .l6s files with LabSpec's own TXT export (LabRAM Soleil):
* the file starts with b"LabSpec6"
* every numeric array is a record tagged b"\\xe3tam" + b"\\xf7\\x7f\\0\\0", followed by 4 bytes (id) + 4 bytes (type),
  then little-endian float32 values
* the point count sits in the preceding size record tagged b"\\xdb\\xd4l}" + b"\\xf7\\x7f\\0\\0" (uint32 at +12)
* the array's quantity / unit are the strings after the nearest preceding b"typm" / b"uni|" tags
  ("Intens"/"Cnt" = Y counts, "Spectr"/"1/cm" or "nm" = X axis)
Y matches the TXT export exactly; X matches to the 6 significant digits the TXT is written with.
"""
from __future__ import annotations
import re, struct
import numpy as np

_TAM = b"\xe3tam\xf7\x7f\x00\x00"
_SZ = b"\xdb\xd4l}\xf7\x7f\x00\x00"
_TYP = b"typm\xf7\x7f\x00\x00"
_UNI = b"uni|\xf7\x7f\x00\x00"


def is_l6s(path):
    try:
        with open(path, "rb") as f: return f.read(8) == b"LabSpec6"
    except OSError: return False


def _cstr(b, i, n=24):
    return b[i:i + n].split(b"\x00")[0].decode("latin-1", "replace")


def arrays(b):
    """-> [(quantity, unit, np.ndarray float64)] for every data array in the file."""
    out, prev = [], 0
    for m in re.finditer(re.escape(_TAM), b):
        p = m.start(); seg = b[prev:p]
        if p < prev: continue
        t = seg.rfind(_TYP); u = seg.rfind(_UNI)
        name = _cstr(seg, t + 8) if t >= 0 else ""
        unit = _cstr(seg, u + 8) if u >= 0 else ""
        sizes = [struct.unpack_from("<I", seg, q.start() + 12)[0] for q in re.finditer(re.escape(_SZ), seg)]
        if not sizes: continue
        start = p + 16; n = int(np.prod(sizes))
        if n <= 0 or start + 4 * n > len(b): n = sizes[-1]
        if n <= 0 or start + 4 * n > len(b): continue
        out.append((name, unit, np.frombuffer(b, "<f4", n, start).astype(float)))
        prev = start + 4 * n
    return out


def _meta(b):
    """Acquisition info LabSpec stores as text (title, date, instrument, objective, grating, laser...)."""
    meta = {}
    for mt in re.finditer(rb"Title\x00", b):            # maps repeat the field; the first copy may only point to the text
        i = mt.start()
        j = b.find(b"\xdbal}\xf7\x7f\x00\x00", i, i + 64)
        if j < 0: continue
        n = struct.unpack_from("<I", b, j + 12)[0]
        if not 0 < n < 512: continue
        try: t = b[j + 16:j + 16 + 2 * n].decode("utf-16-le").strip("\x00 ")
        except UnicodeDecodeError: continue
        if t and t.isprintable() and all(ord(c) < 0x3000 or 0x4e00 <= ord(c) <= 0x9fff for c in t):
            meta["Title"] = t; break
    m = re.search(rb"Date\x00.{0,40}?(\d\d\.\d\d\.\d{4} \d\d:\d\d)", b, re.S)
    if m: meta["Date"] = m.group(1).decode()
    for key in (b"Instrument", b"Detector", b"Objective", b"ND Filter", b"Laser mode"):
        m = re.search(re.escape(key) + rb"\x00([ -~]{1,40})\x00", b)
        if m: meta[key.decode()] = m.group(1).decode("latin-1")
    m = re.search(rb"\x00(\d+ \(\d+ ?nm\))\x00", b)
    if m: meta["Grating"] = m.group(1).decode()
    m = re.search(rb"\x00(\d{3,4} ?nm[ -~]{0,20})\x00", b)
    if m: meta["Laser"] = m.group(1).decode("latin-1")
    return meta


def read(path):
    """-> (x, [y, ...], xunit, ylabel, meta). Several Y arrays = several spectra on the same X (maps / multi-acquisitions)."""
    b = open(path, "rb").read()
    if b[:8] != b"LabSpec6": raise ValueError("不是 LabSpec 6 (.l6s) 檔")
    arr = arrays(b)
    if not arr: raise ValueError("L6S 檔中找不到光譜資料")
    spatial = [a for a in arr if a[0] in ("X", "Y", "Z") and a[1].replace("\xb5", "u").lower() in ("um", "mm")]   # map stage axes
    arr = [a for a in arr if not any(a is s for s in spatial)]
    xs = [a for a in arr if a[0].lower().startswith(("spectr", "wave", "raman", "x"))]
    ys = [a for a in arr if a[0].lower().startswith(("intens", "y", "count"))]
    if not xs:                                       # fall back: the monotonic array is X
        xs = [a for a in arr if len(a[2]) > 2 and (np.all(np.diff(a[2]) > 0) or np.all(np.diff(a[2]) < 0))][:1]
    if not xs: raise ValueError("L6S 檔中找不到 X 軸")
    xq, xu, x = xs[0]
    if not ys: ys = [a for a in arr if a is not xs[0]]
    if not ys: raise ValueError("L6S 檔中找不到強度資料")
    yq, yu, yall = ys[0]
    n = len(x)
    if len(yall) % n: raise ValueError(f"L6S 資料長度不符（X {n} 點、Y {len(yall)} 點）")
    yl = [yall[k * n:(k + 1) * n] for k in range(len(yall) // n)]
    ul = xu.lower().replace(" ", "")
    xunit = "cm-1" if ul in ("1/cm", "cm-1", "cm^-1") else ("nm" if ul == "nm" else None)
    ylabel = "Intensity (counts)" if yu.lower() in ("cnt", "cnts", "counts") else None
    meta = _meta(b); meta["X"] = f"{xq} ({xu})"; meta["Y"] = f"{yq} ({yu})"
    if len(yl) > 1:
        meta["map"] = _map_coords(spatial, len(yl))
        if meta["map"]: meta["map"]["stored"] = stored_maps(b, len(yl))
    return x, yl, xunit, ylabel, meta


_FROM = b"\xd2\xe7\xe6\xea\xf7\x7f\x00\x00"        # float64 band limits of a LabSpec map definition
_TO = b"AU\xd9\xed\xf7\x7f\x00\x00"


def stored_maps(b, n):
    """Images LabSpec computed and saved in a map file (e.g. "Max height" over a band): [(label, values[n])], point order
    = spectrum order. LabSpec's own baseline handling is applied (values differ slightly from a plain linear baseline)."""
    out, seen = [], set()
    for m in re.finditer(re.escape(_TAM), b):
        p = m.start(); s = p + 16
        e = b.find(b"\x00", s, s + 48)
        if e <= s: continue
        name = b[s:e]
        if not all(32 <= c < 127 for c in name): continue
        seg = b[max(0, p - 64):p]
        szs = [struct.unpack_from("<I", seg, q.start() + 12)[0] for q in re.finditer(re.escape(_SZ), seg)]
        if not szs or szs[-1] != n or e + 1 + 4 * n > len(b): continue
        v = np.frombuffer(b, "<f4", n, e + 1).astype(float)
        if not np.all(np.isfinite(v)) or not np.any(v) or np.max(np.abs(v)) > 1e12: continue
        win = b[max(0, p - 2000):p]
        lo, hi = win.rfind(_FROM), win.rfind(_TO)
        label = name.decode()
        if lo >= 0 and hi >= 0:
            a, c = sorted((struct.unpack_from("<d", win, lo + 8)[0], struct.unpack_from("<d", win, hi + 8)[0]))
            if 0 < a < c < 1e5: label += f" ({a:.1f}–{c:.1f})"
        if label in seen: continue
        seen.add(label); out.append((label, v))
    return out


def _map_coords(spatial, n):
    """Stage position of each spectrum in a map (.l6m) / line scan: points are stored row by row, X fastest.
    -> {"nx", "ny", "unit", "xy": [(x, y), ...]} or None when the axes don't add up to n spectra."""
    ax = {}
    for q, u, a in spatial: ax.setdefault(q, (u, a))       # first occurrence = the acquisition grid
    gx, gy = ax.get("X"), ax.get("Y")
    unit = (gx or gy or ("µm", None))[0]
    if gx is not None and gy is not None and len(gx[1]) * len(gy[1]) == n:
        X, Y = gx[1], gy[1]
        return {"nx": len(X), "ny": len(Y), "unit": unit, "xy": [(float(X[k % len(X)]), float(Y[k // len(X)])) for k in range(n)]}
    for q, other in (("X", "Y"), ("Y", "X")):              # line scan along one axis
        g = ax.get(q)
        if g is not None and len(g[1]) == n:
            v = [float(t) for t in g[1]]
            return {"nx": n if q == "X" else 1, "ny": n if q == "Y" else 1, "unit": unit,
                    "xy": [(t, 0.0) if q == "X" else (0.0, t) for t in v]}
    return None
