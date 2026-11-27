"""Map 影像: Raman mapping (HORIBA .l6m) shown as an image, like LabSpec's "Cursor image" + "Cursor spectrum".

Map spectra carry `map=<id>|k|nx|ny|x|y|unit` in their history (written by safeio on import, kept through processing and
saved sessions) and `mapval=<label>|value` for every image LabSpec stored in the file.
Image = LabSpec's stored map, or a value computed from the current spectra over a band (drag the band on the spectrum).
Click a pixel = select that spectrum.
"""
from __future__ import annotations
import csv
import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets as W, QtCore as C, QtGui as G

QUANTS = [("height", "峰高（線性基線）"), ("area", "面積（線性基線）"), ("max", "最大強度"),
          ("at", "強度 @ 起點 X"), ("pos", "峰位置（最大值的 X）")]
CMAPS = ["Red（LabSpec）", "viridis", "inferno", "plasma", "Gray"]


def map_info(spec):
    """-> (map_id, k, nx, ny, x, y, unit) or None."""
    for h in reversed(spec.history):
        if isinstance(h, str) and h.startswith("map="):
            p = h[4:].rsplit("|", 6)
            if len(p) == 7:
                try: return p[0], int(p[1]), int(p[2]), int(p[3]), float(p[4]), float(p[5]), p[6]
                except ValueError: return None
    return None


def stored_values(spec):
    out = {}
    for h in spec.history:
        if isinstance(h, str) and h.startswith("mapval="):
            lab, _, v = h[7:].rpartition("|")
            try: out[lab] = float(v)
            except ValueError: pass
    return out


def band_value(x, y, lo, hi, kind):
    """Value of one spectrum over [lo, hi] (x increasing)."""
    if kind == "at": return float(np.interp(lo, x, y)) if x[0] <= lo <= x[-1] else np.nan
    m = (x >= lo) & (x <= hi)
    if m.sum() < 2: return np.nan
    xs, ys = x[m], y[m]
    if kind == "max": return float(ys.max())
    if kind == "pos": return float(xs[int(np.argmax(ys))])
    base = ys[0] + (ys[-1] - ys[0]) * (xs - xs[0]) / (xs[-1] - xs[0])
    if kind == "height": return float((ys - base).max())
    return float(np.trapezoid(ys - base, xs) if hasattr(np, "trapezoid") else np.trapz(ys - base, xs))


def colormap(name):
    if name.startswith("Red"): return pg.ColorMap([0, 1], [(0, 0, 0), (255, 0, 0)])
    if name == "Gray": return pg.ColorMap([0, 1], [(0, 0, 0), (255, 255, 255)])
    return pg.colormap.get(name)


class MapPanel(W.QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win; self.cur = None; self.vals = None; self._busy = False
        lay = W.QVBoxLayout(self); lay.setContentsMargins(6, 6, 6, 6)
        bar = W.QHBoxLayout()
        self.cb_map = W.QComboBox(); self.cb_map.setMinimumWidth(220); self.cb_map.setToolTip("目前工作區裡的 mapping（每個匯入的 .l6m 一個）")
        self.cb_q = W.QComboBox(); self.cb_q.setMinimumWidth(230)
        self.sp_lo, self.sp_hi = W.QDoubleSpinBox(), W.QDoubleSpinBox()
        for s in (self.sp_lo, self.sp_hi): s.setRange(-1e6, 1e6); s.setDecimals(1); s.setKeyboardTracking(False)
        self.sp_lo.setValue(594.5); self.sp_hi.setValue(628.2)
        self.cb_cmap = W.QComboBox(); self.cb_cmap.addItems(CMAPS)
        self.b_png = W.QPushButton("匯出影像…"); self.b_csv = W.QPushButton("匯出數據 CSV…")
        for w_ in (W.QLabel("Map"), self.cb_map, W.QLabel("影像"), self.cb_q, W.QLabel("區間"), self.sp_lo, W.QLabel("–"), self.sp_hi,
                   W.QLabel("色彩"), self.cb_cmap):
            bar.addWidget(w_)
        bar.addStretch(1); bar.addWidget(self.b_png); bar.addWidget(self.b_csv)
        lay.addLayout(bar)

        split = W.QSplitter(C.Qt.Horizontal)
        self.img_plot = pg.PlotWidget(); self.ipi = self.img_plot.getPlotItem()
        self.ipi.setAspectLocked(True); self.ipi.invertY(True)               # LabSpec: Y grows downwards
        self.ipi.setLabel("bottom", "X (µm)"); self.ipi.setLabel("left", "Y (µm)")
        self.img = pg.ImageItem(); self.ipi.addItem(self.img)
        self.cbar = pg.ColorBarItem(values=(0, 1), colorMap=colormap(CMAPS[0]), interactive=False, width=18)
        self.cbar.setImageItem(self.img, insert_in=self.ipi)
        pen = pg.mkPen("#e8e800", width=1)
        self.vline, self.hline = pg.InfiniteLine(angle=90, pen=pen), pg.InfiniteLine(angle=0, pen=pen)
        for l in (self.vline, self.hline): l.setVisible(False); self.ipi.addItem(l, ignoreBounds=True)
        self.img_plot.scene().sigMouseClicked.connect(self._clicked)
        self.spec_plot = pg.PlotWidget(); self.spi = self.spec_plot.getPlotItem()
        self.spi.setLabel("left", "Intensity"); self.spi.showGrid(x=True, y=True, alpha=0.25)
        self.curve = self.spi.plot([], [], pen=pg.mkPen("#1f9ad6", width=1.5))
        self.region = pg.LinearRegionItem(values=(594.5, 628.2), brush=pg.mkBrush(255, 0, 0, 40)); self.spi.addItem(self.region)
        self.region.sigRegionChangeFinished.connect(self._region_moved)
        split.addWidget(self.img_plot); split.addWidget(self.spec_plot); split.setSizes([520, 620])
        lay.addWidget(split, 1)
        self.info = W.QLabel("匯入 HORIBA .l6m mapping 檔後，在這裡顯示影像；點影像中的像素＝選取該點的光譜。")
        self.info.setWordWrap(True); lay.addWidget(self.info)

        self.cb_map.currentIndexChanged.connect(lambda _: self._map_changed())
        self.cb_q.currentIndexChanged.connect(lambda _: self._quant_changed())
        self.sp_lo.valueChanged.connect(lambda _: self._band_edited()); self.sp_hi.valueChanged.connect(lambda _: self._band_edited())
        self.cb_cmap.currentIndexChanged.connect(lambda _: self.cbar.setColorMap(colormap(self.cb_cmap.currentText())))
        self.b_png.clicked.connect(self.export_png); self.b_csv.clicked.connect(self.export_csv)

    # ---------------------------------------------------------------- data
    def maps(self):
        """{map_id: {"nx", "ny", "unit", "pts": {k: item_index}}} for the current workspace."""
        out = {}
        for i, it in enumerate(self.win.items):
            mi = map_info(it.spec)
            if mi is None: continue
            mid, k, nx, ny, x, y, unit = mi
            d = out.setdefault(mid, {"nx": nx, "ny": ny, "unit": unit, "pts": {}, "xy": {}})
            d["pts"].setdefault(k, i); d["xy"][k] = (x, y)
        return out

    def rebuild(self):
        """Refill the map list (after import / delete / workspace switch) and redraw."""
        ms = self.maps(); keep = self.cb_map.currentText()
        self._busy = True
        self.cb_map.clear(); self.cb_map.addItems(list(ms))
        if keep in ms: self.cb_map.setCurrentText(keep)
        self._busy = False
        self._map_changed()

    def _q(self):
        d = self.cb_q.currentData()
        return tuple(d.split(":", 1)) if isinstance(d, str) and ":" in d else None

    def _map(self):
        return self.maps().get(self.cb_map.currentText())

    def _map_changed(self):
        if self._busy: return
        m = self._map(); keep = self.cb_q.currentData()
        self._busy = True; self.cb_q.clear()
        if m:
            labs = []
            for i in m["pts"].values():
                for lab in stored_values(self.win.items[i].spec):
                    if lab not in labs: labs.append(lab)
            for lab in labs: self.cb_q.addItem(f"LabSpec：{lab}", "stored:" + lab)
            for key, text in QUANTS: self.cb_q.addItem(text, "calc:" + key)
            idx = self.cb_q.findData(keep) if keep else -1
            self.cb_q.setCurrentIndex(idx if idx >= 0 else 0)
        self._busy = False
        self.cur = None
        self._quant_changed()

    def _quant_changed(self):
        if self._busy: return
        q = self._q()
        if q and q[0] == "stored":
            import re
            r = re.search(r"\(([-\d.]+)–([-\d.]+)\)", q[1])
            if r: self._set_band(float(r.group(1)), float(r.group(2)))
        self.update_image()

    def _set_band(self, lo, hi):
        self._busy = True
        self.sp_lo.setValue(lo); self.sp_hi.setValue(hi); self.region.setRegion((lo, hi))
        self._busy = False

    def _band_edited(self):
        if self._busy: return
        lo, hi = sorted((self.sp_lo.value(), self.sp_hi.value()))
        self._busy = True; self.region.setRegion((lo, hi)); self._busy = False
        self._to_calc(); self.update_image()

    def _region_moved(self):
        if self._busy: return
        lo, hi = self.region.getRegion()
        self._busy = True; self.sp_lo.setValue(lo); self.sp_hi.setValue(hi); self._busy = False
        self._to_calc(); self.update_image()

    def _to_calc(self):
        """Editing the band of a LabSpec map switches to the matching computed image (peak height)."""
        q = self._q()
        if q and q[0] == "stored":
            self._busy = True; self.cb_q.setCurrentIndex(self.cb_q.findData("calc:height")); self._busy = False

    def values(self):
        """-> (grid[nx, ny] with NaN for missing points, X centres, Y centres) or None."""
        m = self._map(); q = self._q()
        if not m or not q: return None
        nx, ny = m["nx"], m["ny"]
        grid = np.full((nx, ny), np.nan)
        X = np.full(nx, np.nan); Y = np.full(ny, np.nan)
        lo, hi = sorted((self.sp_lo.value(), self.sp_hi.value()))
        for k, i in m["pts"].items():
            ix, iy = k % nx, k // nx
            if iy >= ny: continue
            X[ix], Y[iy] = m["xy"][k]
            s = self.win.items[i].spec
            if q[0] == "stored": grid[ix, iy] = stored_values(s).get(q[1], np.nan)
            else: grid[ix, iy] = band_value(s.x, s.y, lo, hi, q[1])
        X, Y = _fill_axis(X), _fill_axis(Y)
        return grid, X, Y

    # ---------------------------------------------------------------- drawing
    def update_image(self):
        r = self.values()
        if r is None:
            self.img.clear(); self.vals = None; self.curve.setData([], []); self._cross(None)
            self.info.setText("目前工作區沒有 mapping 光譜。匯入 HORIBA .l6m 檔後會在這裡顯示影像；點像素＝選取該點的光譜。")
            return
        grid, X, Y = r; self.vals = r
        dx = (X[-1] - X[0]) / (len(X) - 1) if len(X) > 1 else 1.0
        dy = (Y[-1] - Y[0]) / (len(Y) - 1) if len(Y) > 1 else 1.0
        self.img.setImage(grid, autoLevels=False)
        self.img.setRect(C.QRectF(X[0] - dx / 2, Y[0] - dy / 2, dx * len(X), dy * len(Y)))
        fin = grid[np.isfinite(grid)]
        lv = (float(fin.min()), float(fin.max())) if fin.size else (0.0, 1.0)
        if lv[1] <= lv[0]: lv = (lv[0], lv[0] + 1)
        self.cbar.setLevels(lv)
        m = self._map(); self.ipi.setLabel("bottom", f"X ({m['unit']})"); self.ipi.setLabel("left", f"Y ({m['unit']})")
        self.ipi.autoRange()
        if self.cur is None or self.cur not in m["pts"]:
            self.cur = int(np.nanargmax(np.where(np.isfinite(grid), grid, -np.inf).T.ravel())) if fin.size else min(m["pts"])
        self.show_point(self.cur, select=False)

    def _cross(self, xy):
        for l in (self.vline, self.hline): l.setVisible(xy is not None)
        if xy is not None: self.vline.setPos(xy[0]); self.hline.setPos(xy[1])

    def show_point(self, k, select=True):
        m = self._map()
        if not m or k not in m["pts"]: return
        self.cur = k; i = m["pts"][k]; s = self.win.items[i].spec
        self.curve.setData(s.x, s.y)
        self.spi.setLabel("bottom", self.win.default_xlabel() if hasattr(self.win, "default_xlabel") else "X")
        self._cross(m["xy"][k])
        g = self.vals[0] if self.vals else None
        v = g[k % m["nx"], k // m["nx"]] if g is not None and k // m["nx"] < m["ny"] else np.nan
        x, y = m["xy"][k]
        self.info.setText(f"點 {k + 1}/{m['nx'] * m['ny']}　X = {x:.3f}、Y = {y:.3f} {m['unit']}　{self.cb_q.currentText()} = {v:.5g}　（{s.name}）")
        if select:
            lw = self.win.listw; it = lw.item(i)
            if it is not None:
                lw.blockSignals(True); lw.clearSelection(); it.setSelected(True); lw.blockSignals(False)
                self.win._selection_changed()

    def _clicked(self, ev):
        if ev.button() != C.Qt.LeftButton or self.vals is None: return
        p = self.ipi.vb.mapSceneToView(ev.scenePos())
        _, X, Y = self.vals; m = self._map()
        ix = int(np.argmin(np.abs(X - p.x()))); iy = int(np.argmin(np.abs(Y - p.y())))
        dx = abs(X[1] - X[0]) if len(X) > 1 else 1; dy = abs(Y[1] - Y[0]) if len(Y) > 1 else 1
        if abs(X[ix] - p.x()) > dx or abs(Y[iy] - p.y()) > dy: return           # outside the map
        self.show_point(iy * m["nx"] + ix)

    def sync_selection(self):
        """Browser selection -> crosshair (when the selected spectrum is a point of the shown map)."""
        idx = self.win.selected_idx(); m = self._map()
        if not idx or not m: return
        for k, i in m["pts"].items():
            if i == idx[0] and k != self.cur: self.show_point(k, select=False); return

    def apply_theme(self, dark):
        bg, fg = ("#101820", "#dddddd") if dark else ("w", "k")
        for pw in (self.img_plot, self.spec_plot):
            pw.setBackground(bg)
            for ax in ("left", "bottom"):
                pw.getPlotItem().getAxis(ax).setPen(fg); pw.getPlotItem().getAxis(ax).setTextPen(fg)

    # ---------------------------------------------------------------- export
    def export_png(self):
        if self.vals is None: return
        p, _ = W.QFileDialog.getSaveFileName(self, "匯出 Map 影像", self.cb_map.currentText() + "_map.png", "PNG (*.png)")
        if not p: return
        from pyqtgraph.exporters import ImageExporter
        ex = ImageExporter(self.ipi.scene()); ex.parameters()["width"] = max(1200, self.img_plot.width() * 2); ex.export(p)

    def export_csv(self):
        if self.vals is None: return
        p, _ = W.QFileDialog.getSaveFileName(self, "匯出 Map 數據", self.cb_map.currentText() + "_map.csv", "CSV (*.csv)")
        if not p: return
        grid, X, Y = self.vals; u = self._map()["unit"]
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([f"# {self.cb_q.currentText()}", f"band {self.sp_lo.value():g}–{self.sp_hi.value():g}"])
            w.writerow([f"Y \\ X ({u})"] + [f"{v:.6g}" for v in X])
            for iy, y in enumerate(Y): w.writerow([f"{y:.6g}"] + ["" if not np.isfinite(v) else f"{v:.6g}" for v in grid[:, iy]])


def _fill_axis(a):
    """Grid centres; points missing from the workspace (deleted spectra) are filled from the step."""
    a = np.asarray(a, float); ok = np.isfinite(a)
    if ok.all() or not ok.any(): return np.where(ok, a, np.arange(len(a), dtype=float))
    i = np.flatnonzero(ok)
    step = (a[i[-1]] - a[i[0]]) / (i[-1] - i[0]) if len(i) > 1 else 1.0
    return a[i[0]] + step * (np.arange(len(a)) - i[0])
