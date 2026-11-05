"""Reliable file handling: tolerant import with explicit notes, atomic writes, crash-recovery sessions.

Nothing here changes data silently: every correction (sorting, merging duplicates, dropping bad rows) is returned as a
note that the GUI shows to the user and that is written into the spectrum's history."""
from __future__ import annotations
import os, re, sys, json, tempfile
import numpy as np
from .core import Spectrum


# ------------------------------------------------------------------ tolerant reading
def _read_text(path):
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):                   # UTF-16 with BOM (some UV-Vis software)
        try: return raw.decode("utf-16")
        except UnicodeDecodeError: pass
    for enc in ("utf-8-sig", "cp950", "cp936", "latin-1"):
        try: return raw.decode(enc)
        except UnicodeDecodeError: continue
    return raw.decode("latin-1", "replace")


def _numeric_rows(text):
    """Parse every line that is purely numeric (space/tab/comma/semicolon separated). Returns (rows, skipped_lines)."""
    rows, skipped = [], 0
    for line in text.splitlines():
        s = line.strip()
        if not s or s[0] in "#%":
            continue
        if "\t" in line:                                        # tab-separated: an empty cell is an empty column, not nothing
            cells = [c.strip() for c in line.rstrip("\r\n").split("\t")]
            if any(cells):
                try: rows.append([float(c) if c else np.nan for c in cells]); continue
                except ValueError: pass
        parts = s.replace(",", " ").replace(";", " ").split()
        if not parts: continue                                  # e.g. ",,"
        try: vals = [float(p) for p in parts]
        except ValueError:
            skipped += 1; continue
        rows.append(vals)
    return rows, skipped


def _split_labels(line):
    return [t.strip() for t in re.split(r"[,;\t]", line.strip())]


def parse_header(text, width):
    """Instrument-style header before the numbers. Returns (labels, meta):
    labels = column titles (only if the title line has exactly `width` fields), meta = {"key": "value"} lines such as
    'Mode,ABS' / 'Lower,400' (GENESYS, Cary, Lambda... exports)."""
    labels, meta, last_text = None, {}, []
    for line in text.splitlines():
        s = line.strip()
        if not s or s[0] in "#%": continue
        parts = s.replace(",", " ").replace(";", " ").split()
        if not parts: continue
        try: [float(p) for p in parts]; break                   # first numeric row -> header is over
        except ValueError: last_text.append(s)
    kv_style = width == 2 and sum(len(_split_labels(s)) == 2 for s in last_text) > 2     # many "key,value" lines (Edinburgh FS5/FLS): no column-title line
    for s in last_text:
        f = [t for t in _split_labels(s)]
        if len(f) == width and not kv_style and (all(t for t in f) or (width >= 3 and f[0] and sum(map(bool, f)) >= 2)): labels = f   # empty titles allowed for blank columns
        elif len(f) >= 2 and f[0] and f[1] and not any(t for t in f[2:]): meta[f[0]] = f[1]
    return labels, meta


def _axis_info(labels):
    """(x unit, [per-column quantity]) guessed from column titles."""
    xu = None
    if labels:
        t = labels[0].lower()
        if "(nm)" in t or "wavelength" in t: xu = "nm"
        elif "cm-1" in t or "cm⁻¹" in t or "wavenumber" in t or "raman" in t: xu = "cm-1"
    return xu


def _unit_of(label):
    """Y quantity named by a column title, e.g. '0.5M(Abs)' -> Absorbance, 'Sample (%T)' -> Transmittance (%); None if not recognisable."""
    t = label.lower().replace(" ", "")
    m = re.search(r"[(\[]([^)\]]*)[)\]]$", t)
    u = m.group(1) if m else t
    if u in ("abs", "a", "absorbance", "od") or u.startswith("abs"): return "Absorbance"
    if u in ("%t", "t%", "transmittance", "trans") or u.startswith("trans"): return "Transmittance (%)"
    if u in ("%r", "r%", "reflectance", "refl") or u.startswith("refl"): return "Reflectance (%)"
    return None


def _quantity(label):
    u = _unit_of(label)
    if u: return u
    t = label.lower().replace(" ", "")
    if t.startswith("abs") or t in ("a", "absorbance"): return "Absorbance"
    if "%t" in t or t.startswith("trans"): return "Transmittance (%)"
    if "%r" in t or t.startswith("refl"): return "Reflectance (%)"
    return label


def clean_xy(x, y, name="spectrum"):
    """Make (x, y) a valid Spectrum input. Returns (x, y, notes). Raises ValueError with a readable reason if unusable."""
    x = np.asarray(x, float); y = np.asarray(y, float); notes = []
    bad = ~np.isfinite(x)
    if bad.any():
        x, y = x[~bad], y[~bad]; notes.append(f"移除 {int(bad.sum())} 列（X 為空白或非數字）")
    if len(x) < 3: raise ValueError("可用資料點少於 3 點")
    d = np.diff(x)
    if (d < 0).sum() > 0.9 * len(d):
        x, y = x[::-1], y[::-1]; notes.append("X 軸為遞減，已反轉為遞增")
    elif (d < 0).any():
        o = np.argsort(x, kind="stable"); x, y = x[o], y[o]; notes.append("X 軸未排序，已依 X 排序")
    if (np.diff(x) == 0).any():
        ux, inv = np.unique(x, return_inverse=True)
        fin = np.isfinite(y); cnt = np.bincount(inv, weights=fin.astype(float))
        ys = np.where(cnt > 0, np.bincount(inv, weights=np.where(fin, y, 0.0)) / np.maximum(cnt, 1.0), np.nan)       # NaN must not count as 0
        notes.append(f"{len(x) - len(ux)} 個重複的 X 值，已合併（Y 取平均）"); x, y = ux, ys
    if len(x) < 3 or np.ptp(x) <= 0: raise ValueError("X 範圍為零或資料點不足")
    nn = int((~np.isfinite(y)).sum())
    if nn: notes.append(f"Y 有 {nn} 個缺值（NaN/無窮大），已保留並在品質檢查標示")
    return x, y, notes


def load_spectra(path, base=None):
    """Read a text spectrum file (2 columns, or x1 y1 x2 y2 ... multi-spectrum). Returns [(Spectrum, notes), ...]."""
    base = base or os.path.splitext(os.path.basename(path))[0]
    rows, skipped = _numeric_rows(_read_text(path))
    if not rows: raise ValueError("檔案中找不到任何數值資料")
    width = max(set(map(len, rows)), key=list(map(len, rows)).count)       # most common column count
    n_all = len(rows); rows = [r for r in rows if len(r) == width]
    if width < 2: raise ValueError("至少需要兩欄（X、Y）")
    d = np.array(rows, float)
    pre = []
    if skipped: pre.append(f"略過 {skipped} 行非數字文字（標題或說明）")
    if len(rows) != n_all: pre.append(f"略過 {n_all - len(rows)} 列欄數不一致的資料")
    labels, meta = parse_header(_read_text(path), width)
    keep = ~np.all(np.isnan(d), axis=0)                           # columns with no data at all (blank column between samples)
    if not keep.all():
        d = d[:, keep]
        if labels: labels = [l for l, k_ in zip(labels, keep) if k_]
        width = d.shape[1]
        pre.append(f"略過 {int((~keep).sum())} 個空白欄")
        if width < 2: raise ValueError("至少需要兩欄（X、Y）")
    xunit = _axis_info(labels)
    ir_tag = None                                                 # JASCO / generic FT-IR export: "XUNITS 1/CM", "YUNITS TRANSMITTANCE"
    mu = {k.strip().upper(): v.strip().upper() for k, v in meta.items()}
    if width == 2 and (mu.get("XUNITS", "").replace(" ", "") in ("1/CM", "CM-1", "CM^-1") or "INFRARED" in mu.get("DATA TYPE", "")):
        yu = mu.get("YUNITS", "")
        ir_tag = "T" if "TRANS" in yu else ("A" if "ABS" in yu else None)
        xunit = "cm-1"
        if ir_tag is None:
            from . import ir as _ir
            ir_tag = _ir.guess_mode(d[:, 1])
    if not xunit and meta.get("Xaxis"):                            # Edinburgh/FLS-style "Xaxis,Wavelength" header (photoluminescence)
        xunit = _axis_info([meta["Xaxis"]])
    if width >= 3 and (labels or width % 2 == 1):                  # X, Y1, Y2, ... (shared X; e.g. GENESYS: wavelength, ABS, %T)
        pairs = [(d[:, 0], d[:, k], (labels[k] if labels else f"Y{k}")) for k in range(1, width)]
    elif width >= 4 and width % 2 == 0:                             # x1 y1 x2 y2 ...
        pairs = [(d[:, k], d[:, k + 1], None) for k in range(0, width - 1, 2)]
    else:
        pairs = [(d[:, -2], d[:, -1], (labels[-1] if labels else None))]
    mode = (meta.get("Mode") or "").strip().lower()
    prim = 0
    if labels and mode:
        for k, (_, _, lb) in enumerate(pairs):
            if lb and _quantity(lb).lower().startswith(mode[:3]) or (lb and lb.lower().replace(" ", "") == mode): prim = k; break
    out = []
    for k, (x, y, lb) in enumerate(pairs):
        m = np.isfinite(x) | np.isfinite(y)
        xx, yy, notes = clean_xy(x[m], y[m], base)
        nm = base if len(pairs) == 1 else (f"{base}_{lb}" if lb else f"{base}_{k + 1}")
        s = Spectrum(xx, yy, nm)
        s.history = [f"import({os.path.basename(path)})"] + ([f"xunit={xunit}"] if xunit else []) + [f"import-note: {n}" for n in pre + notes]
        if ir_tag: s.history.append(f"ir={ir_tag}")
        if meta: s.history.append("import-note: 檔頭 " + ", ".join(f"{a}={b}" for a, b in meta.items()))
        q, q0 = (_unit_of(lb) if lb else None), (_unit_of(pairs[prim][2]) if pairs[prim][2] else None)
        other_axis = k != prim and bool(labels) and q is not None and q0 is not None and q != q0     # a different Y quantity (e.g. %T next to Abs) is kept but hidden
        s.meta = {"xunit": xunit, "ylabel": ({"T": "Transmittance (%)", "A": "Absorbance"}[ir_tag] if ir_tag else (_quantity(lb) if lb else None)), "ir": ir_tag, "hidden": len(pairs) > 1 and (other_axis if q0 else k != prim and bool(labels))}
        nts = pre + notes
        if k == 0 and labels and width >= 3: nts = [f"偵測到檔頭欄位：{' / '.join(labels)}，已拆成 {len(pairs)} 條光譜"] + nts
        out.append((s, nts))
    if out and labels and width >= 3 and any(sp.meta["hidden"] for sp, _ in out):
        out[0][1][0] += f"（Y 軸量不同者先隱藏，預設顯示 {pairs[prim][2]}）"
    return out


# ------------------------------------------------------------------ atomic writes
def atomic_write(path, write_fn):
    """write_fn(tmp_path) writes the file; it is moved over `path` only after it succeeded (no half-written files)."""
    d = os.path.dirname(os.path.abspath(path)); os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=os.path.splitext(path)[1])
    os.close(fd)
    try:
        write_fn(tmp); os.replace(tmp, path)
    except BaseException:
        try: os.remove(tmp)
        except OSError: pass
        raise


# ------------------------------------------------------------------ sessions (no pickle)
def app_dir():
    if os.environ.get("RAMANPROC_HOME"): base = os.environ["RAMANPROC_HOME"]
    elif os.environ.get("LOCALAPPDATA"): base = os.path.join(os.environ["LOCALAPPDATA"], "SpectrumPro")                    # Windows
    elif sys.platform == "darwin": base = os.path.expanduser("~/Library/Application Support/SpectrumPro")                 # macOS
    else: base = os.path.join(os.path.expanduser("~/.local/share"), "SpectrumPro")
    os.makedirs(base, exist_ok=True); return base


def recovery_path():
    return os.path.join(app_dir(), "recovery.ramansession")


def save_session(path, workspaces, current=0):
    """workspaces: [{"name", "items": [Item-like(spec,color,visible,group,raw)]}]"""
    arrays, meta = {}, {"version": 1, "current": current, "workspaces": []}
    n = 0
    for ws in workspaces:
        rec = {"name": ws["name"], "items": []}
        for it in ws["items"]:
            arrays[f"x{n}"], arrays[f"y{n}"] = it.spec.x, it.spec.y
            has_raw = it.raw is not None and it.raw is not it.spec
            if has_raw: arrays[f"rx{n}"], arrays[f"ry{n}"] = it.raw.x, it.raw.y
            rec["items"].append({"k": n, "name": it.spec.name, "color": it.color, "visible": bool(it.visible), "group": it.group,
                                 "history": [str(h) for h in it.spec.history], "raw": has_raw, "raw_name": it.raw.name if has_raw else ""})
            n += 1
        meta["workspaces"].append(rec)
    arrays["meta"] = np.frombuffer(json.dumps(meta, ensure_ascii=False).encode("utf-8"), np.uint8)
    def _w(t):
        with open(t, "wb") as f: np.savez_compressed(f, **arrays)      # handle closed before the atomic replace (Windows)
    atomic_write(path, _w)


def load_session(path):
    """Returns (workspaces, current) where each workspace is {"name", "items": [dict(spec, color, visible, group, raw)]}."""
    with np.load(path, allow_pickle=False) as z:
        meta = json.loads(bytes(z["meta"]).decode("utf-8"))
        out = []
        for ws in meta["workspaces"]:
            items = []
            for r in ws["items"]:
                k = r["k"]; spec = Spectrum(z[f"x{k}"], z[f"y{k}"], r["name"], list(r["history"]))
                raw = Spectrum(z[f"rx{k}"], z[f"ry{k}"], r.get("raw_name") or r["name"]) if r["raw"] else spec
                items.append({"spec": spec, "color": r["color"], "visible": r["visible"], "group": r["group"], "raw": raw})
            out.append({"name": ws["name"], "items": items})
    return out, int(meta.get("current", 0))
