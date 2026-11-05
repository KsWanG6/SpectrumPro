"""Peak Analysis module: find peaks, position / height / area / FWHM (+ fit), and peak ratios."""
import csv
import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets as W, QtCore as C, QtGui as G

import ramanproc as rp
from ramanproc import peakanalysis as PA
from . import theme as TH

BASE_ITEMS = [("線性（窗口兩端）", "linear"), ("無基線", "none"), ("水平（窗口最低點）", "min")]
FIT_ITEMS = [("不擬合", None), ("Gaussian", "gaussian"), ("Lorentzian", "lorentzian"), ("pseudo-Voigt", "pseudovoigt")]
RATIO_ITEMS = [("高度比  R = H_A / H_B", "height"), ("面積比  R = A_A / A_B", "area"),
               ("擬合面積比  R = A_A^fit / A_B^fit", "fit_area"), ("內標比  R = I_analyte / I_IS", "is")]
FAIL_ITEMS = [("標記為失敗（R = NaN）", "nan"), ("以下限取代分母", "min"), ("遇到失敗就報錯並停止", "error")]


def _spin(v, dec=1, lo=-1e6, hi=1e6, step=1.0):
    s = W.QDoubleSpinBox(); s.setDecimals(dec); s.setRange(lo, hi); s.setValue(v); s.setSingleStep(step); return s


def _combo(items):
    c = W.QComboBox(); [c.addItem(a, k) for a, k in items]; return c


class PeakPanel(W.QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win; self.overlay = []; self.ratio_rows = []; self.peak_rows = []
        split = W.QSplitter(C.Qt.Horizontal); lay = W.QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.addWidget(split)

        # ---------------- left controls ----------------
        host = W.QWidget(); ll = W.QVBoxLayout(host); ll.setContentsMargins(4, 4, 4, 4); ll.setSpacing(2)
        sec = TH.Section("尋峰 / 峰位 / 峰高 / 峰面積"); f = W.QFormLayout()
        self.scope = _combo([("選取的光譜", "sel"), ("所有顯示中的光譜", "vis")])
        self.rel = _spin(2.0, 2, 0.01, 100, 0.5); self.dist = _spin(5.0, 1, 0.1, 1000)
        self.snr = _spin(3.0, 1, 0, 1000, 0.5); self.base = _combo(BASE_ITEMS); self.wf = _spin(2.0, 1, 0.5, 20, 0.5); self.fit = _combo(FIT_ITEMS)
        for lab, w_ in (("對象", self.scope), ("最小 prominence (Y 範圍 %)", self.rel), ("最小峰間距 (cm⁻¹)", self.dist), ("最小 S/N（過濾雜訊峰）", self.snr),
                        ("高度 / 面積基線", self.base), ("積分窗 ±N×FWHM", self.wf), ("同時擬合", self.fit)):
            f.addRow(lab, w_)
        w = W.QWidget(); w.setLayout(f); sec.add(w)
        r = W.QHBoxLayout()
        b = W.QPushButton("尋峰並計算"); b.setObjectName("Apply"); b.clicked.connect(lambda: self.find())
        b2 = W.QPushButton("清除標示"); b2.clicked.connect(self.clear_overlay)
        r.addWidget(b); r.addWidget(b2); rw = W.QWidget(); rw.setLayout(r); sec.add(rw)
        bfv = W.QPushButton("擬合檢視…（選表中一個峰）"); bfv.clicked.connect(lambda: self.fit_view()); sec.add(bfv)
        r = W.QHBoxLayout()
        for t, fn in (("複製表格", lambda: self._copy(self.table)), ("儲存 CSV…", lambda: self._csv(self.table, "peaks.csv"))):
            b_ = W.QPushButton(t); b_.clicked.connect(fn); r.addWidget(b_)
        rw = W.QWidget(); rw.setLayout(r); sec.add(rw); ll.addWidget(sec)

        sec2 = TH.Section("峰比值 Peak Ratio", expanded=False)
        f2 = W.QFormLayout()
        self.kind = _combo(RATIO_ITEMS); self.is_feat = _combo([("高度", "height"), ("面積", "area"), ("擬合面積", "fit_area")])
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.rfit = _combo(FIT_ITEMS[1:]); self.rfit.setCurrentIndex(2)
        f2.addRow("比值類型", self.kind); f2.addRow("內標比所用特徵", self.is_feat); f2.addRow("擬合模型（擬合面積用）", self.rfit)
        w2 = W.QWidget(); w2.setLayout(f2); sec2.add(w2)
        self.A = self._peak_box(sec2, "分子峰 A（待測）", 1075.0); self.B = self._peak_box(sec2, "分母峰 B", 1580.0)
        f3 = W.QFormLayout()
        self.min_den = _spin(0.0, 6, 0, 1e12, 0.1); self.fail = _combo(FAIL_ITEMS)
        self.noise_on = W.QCheckBox("指定無峰區間估計雜訊（否則用全譜 MAD）")
        self.n_lo = _spin(1700, 1, -1e6, 1e6); self.n_hi = _spin(1800, 1, -1e6, 1e6)
        f3.addRow("分母下限（≤ 此值視為失敗）", self.min_den); f3.addRow("失敗處理", self.fail); f3.addRow(self.noise_on)
        f3.addRow("無峰區間 從", self.n_lo); f3.addRow("到", self.n_hi)
        w3 = W.QWidget(); w3.setLayout(f3); sec2.add(w3)
        note = W.QLabel("兩峰一律使用同一種特徵（高度對高度、面積對面積）。誤差傳遞：σ_R/R = √[(σ_A/A)² + (σ_B/B)²]，"
                        "假設 A、B 獨立；當兩峰視窗重疊並以聯合擬合求面積時，改用協方差：−2·cov(A,B)/(A·B)。")
        note.setWordWrap(True); note.setStyleSheet("color:#27506f;font-size:9pt"); sec2.add(note)
        r = W.QHBoxLayout()
        bc = W.QPushButton("計算比值"); bc.setObjectName("Apply"); bc.clicked.connect(self.ratios)
        for t, fn in (("複製結果", lambda: self._copy(self.rtable)), ("儲存 CSV…", lambda: self._csv(self.rtable, "peak_ratio.csv"))):
            b_ = W.QPushButton(t); b_.clicked.connect(fn); r.addWidget(b_)
        r.insertWidget(0, bc); rw = W.QWidget(); rw.setLayout(r); sec2.add(rw)
        ll.addWidget(sec2); ll.addStretch(1)
        sa = W.QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(host); sa.setHorizontalScrollBarPolicy(C.Qt.ScrollBarAlwaysOff)
        split.addWidget(sa); self._kind_changed()

        # ---------------- right: plot + tables ----------------
        right = W.QSplitter(C.Qt.Vertical)
        self.plot = pg.PlotWidget(); self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("bottom", "Raman Shift (cm⁻¹)"); self.plot.setLabel("left", "Intensity"); right.addWidget(self.plot)
        self.table = W.QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(["光譜", "峰位", "高度", "面積", "FWHM", "Prominence", "S/N", "擬合峰位", "擬合高度", "擬合面積 ± SD", "擬合 R²"])
        self.rtable = W.QTableWidget(0, 9)
        self.rtable.setHorizontalHeaderLabels(["光譜", "A", "σ_A", "B", "σ_B", "R", "σ_R", "A–B 相關", "狀態"])
        self.table.cellDoubleClicked.connect(lambda r, c: self.fit_view(r))
        self.table.setToolTip("雙擊一列開啟擬合檢視；紅字＝擬合失敗")
        for t in (self.table, self.rtable): t.horizontalHeader().setStretchLastSection(True); t.setAlternatingRowColors(True)
        right.addWidget(self.table); right.addWidget(self.rtable); right.setSizes([380, 220, 170])
        split.addWidget(right); split.setStretchFactor(1, 1); split.setSizes([430, 960])

    def _peak_box(self, sec, title, center):
        lab = W.QLabel(f"<b>{title}</b>"); sec.add(lab)
        f = W.QFormLayout(); c = _spin(center, 1); hw = _spin(15.0, 1, 0.5, 1e4, 0.5); bl = _combo(BASE_ITEMS)
        f.addRow("峰位 (cm⁻¹)", c); f.addRow("搜尋範圍 ±(cm⁻¹)", hw); f.addRow("基線方式", bl)
        w = W.QWidget(); w.setLayout(f); sec.add(w)
        bx = W.QPushButton("峰位取自 X 標線"); bx.clicked.connect(lambda: self._from_xline(c)); sec.add(bx)
        return {"label": lab, "c": c, "hw": hw, "bl": bl}

    def _from_xline(self, spin):
        xl = getattr(self.win, "xline", None)
        if xl is None: self.win.statusBar().showMessage("請先用左側「X 標線」工具在圖上點一下"); return
        spin.setValue(float(xl.value()))

    def _kind_changed(self):
        is_ = self.kind.currentData() == "is"
        self.is_feat.setEnabled(is_)
        self.B["label"].setText("<b>內標峰 IS</b>" if is_ else "<b>分母峰 B</b>")
        self.A["label"].setText("<b>分析物峰</b>" if is_ else "<b>分子峰 A（待測）</b>")

    # ---------------- helpers ----------------
    def _targets(self):
        if self.scope.currentData() == "sel":
            idx = self.win.selected_idx() or [i for i, it in enumerate(self.win.items) if it.visible][-1:]
        else:
            idx = [i for i, it in enumerate(self.win.items) if it.visible]
        if not idx: W.QMessageBox.warning(self, "Peak Analysis", "請先開啟並選取光譜。")
        return idx

    def clear_overlay(self):
        for it in self.overlay: self.plot.removeItem(it)
        self.overlay = []; self.win.clear_labels()

    def _draw_spectrum(self, idx):
        self.plot.clear(); self.overlay = []
        for i in idx[:6]:
            it = self.win.items[i]; self.plot.plot(it.spec.x, it.spec.y, pen=pg.mkPen(it.color, width=1.5), name=it.spec.name)

    def _add(self, item):
        self.plot.addItem(item); self.overlay.append(item)

    # ---------------- find ----------------
    def find(self, rel_pct=None, dist=None):
        if rel_pct is not None: self.rel.setValue(rel_pct)
        if dist is not None: self.dist.setValue(dist)
        idx = self._targets()
        if not idx: return []
        self.win.clear_labels(); self._draw_spectrum(idx)
        rows = []
        try:
            for i in idx:
                it = self.win.items[i]
                for p in PA.analyze_peaks(it.spec, rel_prominence=self.rel.value() / 100, min_distance=self.dist.value(),
                                          baseline=self.base.currentData(), width_factor=self.wf.value(), fit_model=self.fit.currentData(), min_snr=self.snr.value()):
                    rows.append((it, p))
        except Exception as ex:
            W.QMessageBox.warning(self, "尋峰", str(ex)); return []
        self.peak_rows = rows
        self.table.setRowCount(len(rows))
        for r, (it, p) in enumerate(rows):
            fit = p.get("fit")
            vals = [it.spec.name, f"{p['position']:.2f}", f"{p['height']:.5g}", f"{p['area']:.5g}", f"{p['fwhm']:.3g}", f"{p['prominence']:.4g}", f"{p['snr']:.3g}",
                    *( [f"{fit['position']:.2f}", f"{fit['height']:.5g}", f"{fit['area']:.5g} ± {fit['area_sd']:.2g}", f"{fit['r2']:.4f}"] if fit else ["—"] * 4)]
            failed = bool(self.fit.currentData()) and fit is None
            if failed: vals[7] = "擬合失敗"
            for c, v in enumerate(vals):
                cell = W.QTableWidgetItem(v)
                if failed: cell.setForeground(G.QColor("#b02020"))
                self.table.setItem(r, c, cell)
            if failed:
                x_ = p["position"]; mk = pg.ScatterPlotItem([x_], [float(np.interp(x_, it.spec.x, it.spec.y))], symbol="x", size=14, pen=pg.mkPen("#d62728", width=2))
                self._add(mk)
                m2 = pg.ScatterPlotItem([x_], [float(np.interp(x_, it.spec.x, it.spec.y))], symbol="x", size=14, pen=pg.mkPen("#d62728", width=2))
                self.win.pi.addItem(m2); self.win.labels.append(m2)
            # plot marker + main-plot label
            ls = getattr(self, "label_style", {"dec": 1, "color": True, "attach": True}); col = it.color if ls["color"] else "#222222"
            yy = float(np.interp(p["position"], it.spec.x, it.spec.y)) if ls["attach"] else float(it.spec.y.max()) * 1.04
            t = pg.TextItem(f"{p['position']:.{ls['dec']}f}", color=col, anchor=(0.5, 1.2)); t.setPos(p["position"], yy); self._add(t)
            t2 = pg.TextItem(f"{p['position']:.{ls['dec']}f}", color=col, anchor=(0.5, 1.2)); t2.setPos(t.pos()); self.win.pi.addItem(t2); self.win.labels.append(t2)
            lo, hi = p["window"]; reg = pg.LinearRegionItem((lo, hi), brush=pg.mkBrush(255, 165, 0, 28), movable=False); reg.setZValue(-10)
            for ln in reg.lines: ln.setPen(pg.mkPen(None))
            self._add(reg)
        nfail = sum(1 for _, p_ in rows if self.fit.currentData() and p_.get("fit") is None)
        self.win.statusBar().showMessage(f"找到 {len(rows)} 個峰" + (f"；{nfail} 個擬合失敗（紅 ×）" if nfail else ""))
        return rows

    # ---------------- fit viewer ----------------
    def fit_curves(self, row=None):
        """Fit the peak in table row `row` (with neighbours inside its window); returns the fit dict + spectrum name."""
        if not self.peak_rows: raise ValueError("請先按「尋峰並計算」")
        row = self.table.currentRow() if row is None else row
        row = 0 if row < 0 else row
        it, p = self.peak_rows[row]
        lo, hi = p["window"]; hw = (hi - lo) / 2
        centers = [q["position"] for it2, q in self.peak_rows if it2 is it and abs(q["position"] - p["position"]) <= hw]
        model = self.fit.currentData() or "pseudovoigt"
        f = PA.fit_peaks(it.spec, centers, hw, model, self.base.currentData())
        return f, it, p

    def fit_view(self, row=None):
        """Dialog: raw data, total fit, individual sub-peaks (+ baseline) and residual, X axes linked."""
        try: f, it, p = self.fit_curves(row)
        except Exception as ex:
            W.QMessageBox.warning(self, "擬合檢視", f"擬合失敗：{ex}"); return None
        dlg = W.QDialog(self); dlg.setWindowTitle(f"擬合檢視 — {it.spec.name} @ {p['position']:.1f}"); dlg.resize(820, 620)
        lay = W.QVBoxLayout(dlg)
        top = pg.PlotWidget(); res = pg.PlotWidget(); res.setMaximumHeight(170)
        top.showGrid(x=True, y=True, alpha=0.25); res.showGrid(x=True, y=True, alpha=0.25)
        top.setLabel("left", "Intensity"); res.setLabel("left", "Residual"); res.setLabel("bottom", "Raman Shift (cm⁻¹)")
        x, y, yf, base = f["x"], f["y"], f["yfit"], f["base"]
        top.addLegend()
        top.plot(x, y, pen=None, symbol="o", symbolSize=5, symbolBrush=(80, 80, 80), name="raw")
        top.plot(x, yf, pen=pg.mkPen("#d62728", width=2), name="total fit")
        cols = ["#1d7cd4", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf"]
        for k, comp in enumerate(f["components"]):
            top.plot(x, comp + base, pen=pg.mkPen(cols[k % 5], width=1.5, style=C.Qt.DashLine), name=f"peak {k + 1} @ {f['peaks'][k]['position']:.1f}")
        top.plot(x, base, pen=pg.mkPen("#888", width=1, style=C.Qt.DotLine), name="baseline")
        resid = y - yf
        res.plot(x, resid, pen=pg.mkPen("#555", width=1)); res.addItem(pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen("#d62728", style=C.Qt.DashLine)))
        res.setXLink(top)
        lay.addWidget(top, 3); lay.addWidget(res, 1)
        txt = "；".join(f"峰{k + 1}: 位置 {q['position']:.2f}, 高 {q['height']:.4g}, FWHM {q['fwhm']:.3g}, 面積 {q['area']:.4g} ± {q['area_sd']:.2g}" for k, q in enumerate(f["peaks"]))
        info = W.QLabel(f"模型 {f['model']}　R² = {f['r2']:.5f}　殘差 RMS = {float(np.sqrt(np.mean(resid ** 2))):.4g}<br>{txt}"); info.setWordWrap(True); lay.addWidget(info)
        bt = W.QPushButton("關閉"); bt.clicked.connect(dlg.accept); lay.addWidget(bt)
        self.fit_dialog = dlg
        if not getattr(self, "_no_exec", False): dlg.exec()
        return f

    # ---------------- ratios ----------------
    def ratios(self):
        idx = self._targets()
        if not idx: return
        kind = self.kind.currentData(); kind = self.is_feat.currentData() if kind == "is" else kind
        A = {"center": self.A["c"].value(), "hw": self.A["hw"].value(), "baseline": self.A["bl"].currentData()}
        B = {"center": self.B["c"].value(), "hw": self.B["hw"].value(), "baseline": self.B["bl"].currentData()}
        on_fail = self.fail.currentData(); res = []
        for i in idx:
            it = self.win.items[i]
            try:
                noise = PA.noise_sigma(it.spec, (self.n_lo.value(), self.n_hi.value())) if self.noise_on.isChecked() else None
                r = PA.peak_ratio(it.spec, A, B, kind, self.rfit.currentData(), self.min_den.value(), on_fail, noise)
            except ValueError as ex:
                W.QMessageBox.warning(self, "峰比值", f"「{it.spec.name}」：{ex}"); break
            res.append((it, r))
        self.ratio_rows = res; self.rtable.setRowCount(len(res))
        for r_, (it, r) in enumerate(res):
            def g(k, fmt="{:.5g}"): return fmt.format(r[k]) if k in r and np.isfinite(r[k]) else "—"
            corr = "是（聯合擬合）" if r.get("correlated") else "否（假設獨立）"
            st = {"ok": "OK", "failed": "失敗：" + r["reason"], "replaced": "已取代：" + r["reason"]}[r["status"]]
            vals = [it.spec.name, g("a"), g("sigma_a", "{:.3g}"), g("b"), g("sigma_b", "{:.3g}"), g("R"), g("sigma_R", "{:.3g}"), corr, st]
            for c, v in enumerate(vals):
                cell = W.QTableWidgetItem(v)
                if r["status"] != "ok": cell.setForeground(G.QColor("#b02020"))
                self.rtable.setItem(r_, c, cell)
        # picture of the first spectrum: windows + baseline-corrected peaks
        if res:
            it, r = res[0]; self._draw_spectrum([self.win.items.index(it)])
            for P, col in ((A, (255, 140, 0, 50)), (B, (44, 160, 44, 50))):
                reg = pg.LinearRegionItem((P["center"] - P["hw"], P["center"] + P["hw"]), brush=pg.mkBrush(*col), movable=False); reg.setZValue(-10); self._add(reg)
            for key, col in (("A_pos", "#ff7f0e"), ("B_pos", "#2ca02c")):
                if key in r: self._add(pg.InfiniteLine(pos=r[key], angle=90, pen=pg.mkPen(col, width=2)))
        ok = sum(1 for _, r in res if r["status"] == "ok")
        self.win.statusBar().showMessage(f"峰比值：{ok}/{len(res)} 條成功")

    # ---------------- export ----------------
    def _copy(self, t):
        rows = ["\t".join(t.horizontalHeaderItem(c).text() for c in range(t.columnCount()))]
        for r in range(t.rowCount()): rows.append("\t".join(t.item(r, c).text() if t.item(r, c) else "" for c in range(t.columnCount())))
        G.QGuiApplication.clipboard().setText("\n".join(rows)); self.win.statusBar().showMessage("已複製到剪貼簿")

    def _csv(self, t, name):
        p, _ = W.QFileDialog.getSaveFileName(self, "儲存 CSV", name, "CSV (*.csv)")
        if not p: return
        with open(p, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh); w.writerow([t.horizontalHeaderItem(c).text() for c in range(t.columnCount())])
            for r in range(t.rowCount()): w.writerow([t.item(r, c).text() if t.item(r, c) else "" for c in range(t.columnCount())])
