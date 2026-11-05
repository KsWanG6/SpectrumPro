"""RSD module: pick a characteristic band, get one number per spectrum, bar chart + mean / SD / RSD%."""
import csv
import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets as W, QtCore as C, QtGui as G

from ramanproc import rsd as R
from . import theme as TH

NOGROUP = "（未分組）"


def _spin(v, dec=1, lo=-1e6, hi=1e6, step=1.0):
    s = W.QDoubleSpinBox(); s.setDecimals(dec); s.setRange(lo, hi); s.setValue(v); s.setSingleStep(step); return s


def export_plot_widget(pw, path, width=2000):
    """PNG (raster) / SVG / PDF (vector) of a PlotWidget exactly as shown."""
    low = path.lower()
    if low.endswith(".svg"):
        from PySide6.QtSvg import QSvgGenerator
        g = QSvgGenerator(); g.setFileName(path); g.setSize(pw.size()); g.setViewBox(C.QRect(0, 0, pw.width(), pw.height()))
        p = G.QPainter(g); pw.render(p); p.end()
    elif low.endswith(".pdf"):
        w_ = G.QPdfWriter(path); w_.setResolution(96)
        w_.setPageSize(G.QPageSize(C.QSizeF(pw.width() * 72 / 96 + 20, pw.height() * 72 / 96 + 20), G.QPageSize.Point)); w_.setPageMargins(C.QMarginsF(0, 0, 0, 0))
        p = G.QPainter(w_); p.translate(10 * 96 / 72, 10 * 96 / 72); pw.render(p); p.end()
    else:
        import pyqtgraph.exporters as ex
        e = ex.ImageExporter(pw.getPlotItem()); e.parameters()["width"] = width; e.export(path)


class RsdPanel(W.QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win; self.result = None; self.rows = []; self.overlay = []
        split = W.QSplitter(C.Qt.Horizontal); lay = W.QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.addWidget(split)

        host = W.QWidget(); ll = W.QVBoxLayout(host); ll.setContentsMargins(4, 4, 4, 4); ll.setSpacing(2)
        sec = TH.Section("特徵峰 / 特徵區間"); f = W.QFormLayout()
        self.scope = W.QComboBox(); self.scope.addItem("選取的光譜", "sel"); self.scope.addItem("所有顯示中的光譜", "vis")
        self.mode = W.QComboBox()
        for k, v in R.MODES.items(): self.mode.addItem(v, k)
        self.center = _spin(1075.0, 1); self.hw = _spin(15.0, 1, 0.5, 1e4, 0.5)
        f.addRow("對象", self.scope); f.addRow("特徵量", self.mode); f.addRow("峰位 (cm⁻¹)", self.center); f.addRow("半窗寬 ±(cm⁻¹)", self.hw)
        w = W.QWidget(); w.setLayout(f); sec.add(w)
        r = W.QHBoxLayout(); bx = W.QPushButton("峰位取自 X 標線"); bx.clicked.connect(self._from_xline)
        bp = W.QPushButton("先找最高峰"); bp.setToolTip("在選取光譜的平均上找視窗內最高點作為峰位"); bp.clicked.connect(self.snap_center)
        r.addWidget(bx); r.addWidget(bp); rw = W.QWidget(); rw.setLayout(r); sec.add(rw)
        self.use_region = W.QCheckBox("面積模式使用自訂區間 From–To（取代峰位±窗寬）")
        f2 = W.QFormLayout(); self.lo = _spin(1050.0, 1); self.hi = _spin(1100.0, 1); f2.addRow("From", self.lo); f2.addRow("To", self.hi)
        sec.add(self.use_region); w2 = W.QWidget(); w2.setLayout(f2); sec.add(w2)
        bs = W.QPushButton("區間取自圖上第一個 Strip"); bs.clicked.connect(self._from_strip); sec.add(bs)
        ll.addWidget(sec)

        sec2 = TH.Section("分組與圖表"); f3 = W.QFormLayout()
        self.group_mode = W.QComboBox(); self.group_mode.addItem("全部視為同一組重複", "none"); self.group_mode.addItem("依光譜清單的「群組」分別計算", "group")
        self.chart = W.QComboBox(); self.chart.addItem("逐條光譜長條圖", "each"); self.chart.addItem("各組平均 ± SD 長條圖", "groups")
        self.target = _spin(10.0, 1, 0.1, 100, 1.0); self.target.setSuffix(" %")
        self.show_pts = W.QCheckBox("各組圖上疊加個別數據點"); self.show_pts.setChecked(True)
        f3.addRow("分組", self.group_mode); f3.addRow("圖表", self.chart); f3.addRow("目標 RSD", self.target); f3.addRow(self.show_pts)
        w3 = W.QWidget(); w3.setLayout(f3); sec2.add(w3)
        nt = W.QLabel("RSD% = 100 × s / |平均|，s 為樣本標準差（n−1）。建議至少 n ≥ 3（最好 ≥ 5）；n 很小時 RSD 本身不確定度很大。"
                      "「目標 RSD」只用來給結果著色（綠＝達標、紅＝超過），不是判定標準。")
        nt.setWordWrap(True); nt.setStyleSheet("color:#6e6e73;font-size:9pt"); sec2.add(nt)
        r = W.QHBoxLayout(); bc = W.QPushButton("計算並繪圖"); bc.setObjectName("Apply"); bc.clicked.connect(lambda: self.compute()); r.addWidget(bc)
        rw = W.QWidget(); rw.setLayout(r); sec2.add(rw)
        r = W.QHBoxLayout()
        for t, fn in (("複製表格", self.copy), ("儲存 CSV…", self.save_csv), ("匯出長條圖…", self.export_chart)):
            b_ = W.QPushButton(t); b_.clicked.connect(lambda _=False, f_=fn: f_()); r.addWidget(b_)
        rw = W.QWidget(); rw.setLayout(r); sec2.add(rw); ll.addWidget(sec2); ll.addStretch(1)
        self.mode.currentIndexChanged.connect(self._mode_changed); self._mode_changed()
        sa = W.QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(host); sa.setHorizontalScrollBarPolicy(C.Qt.ScrollBarAlwaysOff)
        split.addWidget(sa)

        right = W.QSplitter(C.Qt.Vertical)
        self.prev = pg.PlotWidget(); self.prev.showGrid(x=True, y=True, alpha=0.25)
        self.prev.setLabel("bottom", "Raman Shift (cm⁻¹)"); self.prev.setLabel("left", "Intensity"); self.prev.setTitle("特徵區間預覽", size="10pt")
        self.bar = pg.PlotWidget(); self.bar.showGrid(y=True, alpha=0.25); self.bar.setTitle("RSD 長條圖", size="10pt")
        self.summary = W.QTableWidget(0, 9)
        self.summary.setHorizontalHeaderLabels(["組別", "n", "平均", "SD", "RSD (%)", "SEM", "95% CI 下", "95% CI 上", "備註"])
        self.table = W.QTableWidget(0, 4); self.table.setHorizontalHeaderLabels(["光譜", "組別", "特徵值", "狀態"])
        for t in (self.summary, self.table): t.horizontalHeader().setStretchLastSection(True); t.setAlternatingRowColors(True)
        for w_ in (self.prev, self.bar, self.summary, self.table): right.addWidget(w_)
        right.setSizes([220, 330, 120, 150]); split.addWidget(right); split.setStretchFactor(1, 1); split.setSizes([400, 980])

    # ---------------- helpers ----------------
    def _mode_changed(self):
        self.use_region.setEnabled(self.mode.currentData().startswith("area"))

    def _from_xline(self):
        xl = getattr(self.win, "xline", None)
        if xl is None: self.win.statusBar().showMessage("請先用左側「X 標線」工具在圖上點一下"); return
        self.center.setValue(float(xl.value()))

    def _from_strip(self):
        if not self.win.strips: self.win.statusBar().showMessage("圖上沒有 Strip：請先用「框選區間」工具拉一段"); return
        a, b = sorted(self.win.strips[0].getRegion()); self.lo.setValue(a); self.hi.setValue(b); self.use_region.setChecked(True)

    def _targets(self):
        w = self.win
        idx = (w.selected_idx() or [i for i, it in enumerate(w.items) if it.visible]) if self.scope.currentData() == "sel" else [i for i, it in enumerate(w.items) if it.visible]
        if not idx: W.QMessageBox.warning(self, "RSD", "請先開啟並選取光譜。")
        return idx

    def snap_center(self):
        idx = self._targets()
        if not idx: return
        c, hw = self.center.value(), self.hw.value(); best = []
        for i in idx:
            s = self.win.items[i].spec; m = (s.x >= c - hw) & (s.x <= c + hw)
            if m.any(): best.append(float(s.x[m][np.nanargmax(s.y[m])]))
        if best: self.center.setValue(round(float(np.median(best)), 1)); self.win.statusBar().showMessage(f"峰位設為視窗內最高點的中位數 {self.center.value():.1f}")

    def kwargs(self):
        kw = dict(center=self.center.value(), hw=self.hw.value(), mode=self.mode.currentData())
        if self.use_region.isEnabled() and self.use_region.isChecked(): kw.update(lo=self.lo.value(), hi=self.hi.value())
        return kw

    # ---------------- compute + draw ----------------
    def compute(self, idx=None):
        idx = idx if idx is not None else self._targets()
        if not idx: return None
        items = [self.win.items[i] for i in idx]
        groups = [(it.group or NOGROUP) if self.group_mode.currentData() == "group" else None for it in items]
        kw = self.kwargs()
        res = R.analyze([it.spec for it in items], groups=groups if self.group_mode.currentData() == "group" else None, **kw)
        self.result = res; self.items_used = items; self.group_of = [g or "" for g in groups]; self.kw = kw
        self._fill_tables(); self._draw_preview(); self._draw_bar()
        o = res["overall"]
        self.win.statusBar().showMessage(f"RSD：n={o['n']}  平均={o['mean']:.5g}  SD={o['sd']:.4g}  RSD={o['rsd']:.2f}%" + (f"；{len(res['errors'])} 條失敗" if res["errors"] else ""))
        return res

    def _stat_rows(self):
        r = self.result; rows = []
        if self.group_mode.currentData() == "group":
            for g in r["order"]: rows.append((g, r["groups"][g]))
        else:
            rows.append(("全部", r["overall"]))
        return rows

    def _fill_tables(self):
        r = self.result; rows = self._stat_rows(); tgt = self.target.value()
        self.summary.setRowCount(len(rows))
        for k, (g, st) in enumerate(rows):
            vals = [g, str(st["n"]), f"{st['mean']:.5g}", f"{st['sd']:.4g}", f"{st['rsd']:.2f}", f"{st['sem']:.4g}", f"{st['ci'][0]:.5g}", f"{st['ci'][1]:.5g}", st["warning"] or ("失敗 %d 條" % st["n_failed"] if st["n_failed"] else "")]
            for c, v in enumerate(vals):
                cell = W.QTableWidgetItem(v)
                if c == 4 and np.isfinite(st["rsd"]): cell.setForeground(G.QColor("#1e8e3e" if st["rsd"] <= tgt else "#c5221f")); f_ = cell.font(); f_.setBold(True); cell.setFont(f_)
                self.summary.setItem(k, c, cell)
        self.table.setRowCount(len(self.items_used))
        for i, it in enumerate(self.items_used):
            v = r["values"][i]; err = r["errors"].get(i)
            vals = [it.spec.name, self.group_of[i], "—" if not np.isfinite(v) else f"{v:.6g}", "失敗：" + err if err else "OK"]
            for c, t in enumerate(vals):
                cell = W.QTableWidgetItem(t)
                if err: cell.setForeground(G.QColor("#c5221f"))
                self.table.setItem(i, c, cell)
        self.rows = [(g, st) for g, st in rows]

    def _draw_preview(self):
        self.prev.clear(); kw = self.kw
        for it in self.items_used[:12]: self.prev.plot(it.spec.x, it.spec.y, pen=pg.mkPen(it.color, width=1.2))
        if kw.get("lo") is not None: a, b = kw["lo"], kw["hi"]
        else: a, b = kw["center"] - kw["hw"], kw["center"] + kw["hw"]
        reg = pg.LinearRegionItem((a, b), brush=pg.mkBrush(29, 124, 212, 40), movable=False); reg.setZValue(-10); self.prev.addItem(reg)
        self.prev.addItem(pg.InfiniteLine(pos=kw["center"], angle=90, pen=pg.mkPen("#d62728", style=C.Qt.DashLine)))
        self.prev.setXRange(a - 2 * (b - a), b + 2 * (b - a), padding=0)

    def _draw_bar(self):
        pw = self.bar; pw.clear(); r = self.result; tgt = self.target.value()
        ylab = "峰高" if self.mode.currentData().startswith("height") else "面積"; pw.setLabel("left", ylab)
        if self.chart.currentData() == "groups" and self.group_mode.currentData() == "group":
            names = [g for g, _ in self.rows]; means = np.array([st["mean"] for _, st in self.rows]); sds = np.nan_to_num(np.array([st["sd"] for _, st in self.rows]))
            cols = [pg.mkBrush(self.win._next_color_for(k) if hasattr(self.win, "_next_color_for") else A_PALETTE[k % len(A_PALETTE)]) for k in range(len(names))]
            pw.addItem(pg.BarGraphItem(x=np.arange(len(names)), height=np.nan_to_num(means), width=0.6, brushes=cols, pen=pg.mkPen("#333")))
            pw.addItem(pg.ErrorBarItem(x=np.arange(len(names)), y=np.nan_to_num(means), height=2 * sds, beam=0.15, pen=pg.mkPen("#1d1d1f", width=2)))
            if self.show_pts.isChecked():
                for k, (g, st) in enumerate(self.rows):
                    vv = [r["values"][i] for i in range(len(self.items_used)) if (self.group_of[i] or "全部") == g or self.group_mode.currentData() == "none"]
                    vv = [v for v in vv if np.isfinite(v)]; jit = (np.random.default_rng(k).random(len(vv)) - 0.5) * 0.3
                    pw.addItem(pg.ScatterPlotItem(k + jit, vv, size=7, brush=pg.mkBrush(255, 255, 255, 220), pen=pg.mkPen("#1d1d1f")))
            pw.getAxis("bottom").setTicks([[(k, f"{n}\nRSD {st['rsd']:.1f}%") for k, (n, st) in enumerate(self.rows)]])
            pw.setTitle("各組平均 ± SD（點＝個別光譜）", size="10pt")
        else:
            vals = np.nan_to_num(r["values"]); n = len(vals)
            pw.addItem(pg.BarGraphItem(x=np.arange(n), height=vals, width=0.7, brushes=[pg.mkBrush(it.color) for it in self.items_used], pen=pg.mkPen("#333")))
            st = r["overall"]
            if np.isfinite(st["mean"]):
                pw.addItem(pg.InfiniteLine(pos=st["mean"], angle=0, pen=pg.mkPen("#1d1d1f", width=2, style=C.Qt.DashLine)))
                if np.isfinite(st["sd"]):
                    band = pg.LinearRegionItem((st["mean"] - st["sd"], st["mean"] + st["sd"]), orientation="horizontal", brush=pg.mkBrush(29, 124, 212, 45), movable=False)
                    band.setZValue(-5)
                    for ln in band.lines: ln.setPen(pg.mkPen("#1d7cd4", style=C.Qt.DotLine))
                    pw.addItem(band)
            pw.getAxis("bottom").setTicks([[(k, it.spec.name[:14]) for k, it in enumerate(self.items_used)]])
            col = "#1e8e3e" if np.isfinite(st["rsd"]) and st["rsd"] <= tgt else "#c5221f"
            t = pg.TextItem(html=f"<div style='font-size:10pt'>n = {st['n']}　平均 = {st['mean']:.5g}　SD = {st['sd']:.4g}　<b style='color:{col}'>RSD = {st['rsd']:.2f}%</b></div>", anchor=(0, 0), fill=pg.mkBrush(255, 255, 255, 220))
            pw.addItem(t, ignoreBounds=True); self._label = t
            pw.setTitle("逐條光譜特徵值（虛線＝平均，淡藍帶＝±1 SD）", size="10pt")
            vb = pw.getPlotItem().vb; vb.sigRangeChanged.connect(self._place_label)
        pw.getPlotItem().vb.enableAutoRange(); pw.autoRange(); self._place_label()

    def _place_label(self, *_):
        t = getattr(self, "_label", None)
        if t is None or self.chart.currentData() == "groups" and self.group_mode.currentData() == "group": return
        try:
            (x0, x1), (y0, y1) = self.bar.getPlotItem().vb.viewRange(); t.setPos(x0 + 0.01 * (x1 - x0), y1 - 0.01 * (y1 - y0))
        except Exception: pass

    # ---------------- export ----------------
    def _table_text(self):
        lines = ["組別\tn\t平均\tSD\tRSD(%)\tSEM\tCI下\tCI上"]
        for g, st in self.rows: lines.append("\t".join([g, str(st["n"]), f"{st['mean']:.6g}", f"{st['sd']:.6g}", f"{st['rsd']:.4f}", f"{st['sem']:.6g}", f"{st['ci'][0]:.6g}", f"{st['ci'][1]:.6g}"]))
        lines.append(""); lines.append("光譜\t組別\t特徵值")
        for i, it in enumerate(self.items_used): lines.append(f"{it.spec.name}\t{self.group_of[i]}\t{self.result['values'][i]:.8g}")
        return "\n".join(lines)

    def copy(self):
        if self.result is None: self.compute()
        if self.result is None: return
        G.QGuiApplication.clipboard().setText(self._table_text()); self.win.statusBar().showMessage("已複製到剪貼簿")

    def save_csv(self):
        if self.result is None: self.compute()
        if self.result is None: return
        p, _ = W.QFileDialog.getSaveFileName(self, "儲存 CSV", "rsd.csv", "CSV (*.csv)")
        if p: self.write_csv(p)

    def write_csv(self, p):
        from ramanproc.safeio import atomic_write
        def w_(t):
            with open(t, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                for line in self._table_text().splitlines(): w.writerow(line.split("\t"))
        atomic_write(p, w_)

    def export_chart(self, path=None):
        if self.result is None: self.compute()
        if self.result is None: return
        p = path or W.QFileDialog.getSaveFileName(self, "匯出長條圖", "rsd_bar.png", "PNG (*.png);;SVG 向量 (*.svg);;PDF 向量 (*.pdf)")[0]
        if p: export_plot_widget(self.bar, p); self.win.statusBar().showMessage(f"已匯出 {p}")


A_PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22"]
