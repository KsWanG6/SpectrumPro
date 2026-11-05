"""Peaks section of the Processing tab (LabSpec-style): Find / Fit / Conv on the selected spectra, drawn on the Spectra plot.
Level (%) = minimum prominence as a % of the Y range; Window (pnt) = minimum distance between peaks in data points.
Shape: Gaussian, Lorentzian, GaussLor (= pseudo-Voigt with free mixing). These meanings are our own definitions."""
from __future__ import annotations
import numpy as np
import pyqtgraph as pg
import PySide6.QtWidgets as W
import PySide6.QtCore as C
from ramanproc import peakanalysis as PA
from ramanproc import baselines as BL
from ramanproc.core import Spectrum
from . import theme as TH
from . import icons as IC
from .dialogs import SliderSpin

SHAPES = {"Gaussian": "gaussian", "Lorentzian": "lorentzian", "GaussLor": "pseudovoigt"}
HELP = ("Find：在選取的光譜上尋峰，峰位標在 Spectra 圖上，結果列在 Peak table。\n"
        "Level (%)：最小 prominence，佔 Y 範圍的百分比（越大＝只留明顯的峰）。Window (pnt)：兩峰之間至少相隔幾個資料點。\n"
        "Fit：把找到的峰（相近的峰一起）以 Shape 擬合，加上線性基線（可在 Options 關掉），在圖上畫出總和與各峰；"
        "Error＝殘差 RMS，Red. χ²＝殘差平方和 /（雜訊² × 自由度），雜訊由相鄰點差的 MAD 估計。\n"
        "Conv：把擬合出的各峰加總（不含基線）存成新光譜。\n"
        "Options：擬合的限制（迭代、最大位移、寬度上下限、是否擬合基線）。Display options：標示小數位、顏色、是否畫總和 / 各峰。\n"
        "（參數定義是本軟體自行訂定，未與其他軟體比對。）")


class PeakSection(W.QWidget):
    def __init__(self, win):
        super().__init__(); self.win = win; self.rows = []; self.fits = []
        lay = W.QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
        sec = TH.Section("Peaks 峰", help=HELP)
        g = W.QGridLayout(); g.setContentsMargins(0, 0, 0, 0); g.setHorizontalSpacing(8)
        self.level = SliderSpin(1, 100, 5); self.window = SliderSpin(3, 301, 15, odd=True)
        self.shape = W.QComboBox(); self.shape.addItems(list(SHAPES)); self.shape.setCurrentText("GaussLor")
        g.addWidget(W.QLabel("Level (%)"), 0, 0); g.addWidget(self.level, 0, 1)
        g.addWidget(W.QLabel("Window (pnt)"), 1, 0); g.addWidget(self.window, 1, 1)
        g.addWidget(W.QLabel("Shape"), 2, 0); g.addWidget(self.shape, 2, 1)
        self.err = W.QLineEdit(); self.chi = W.QLineEdit()
        for e in (self.err, self.chi): e.setReadOnly(True)
        g.addWidget(W.QLabel("Error"), 3, 0); g.addWidget(self.err, 3, 1)
        g.addWidget(W.QLabel("Red. χ²"), 4, 0); g.addWidget(self.chi, 4, 1)
        g.setColumnStretch(1, 1)
        w = W.QWidget(); w.setLayout(g); sec.add(w)
        r = W.QHBoxLayout(); r.setContentsMargins(0, 0, 0, 0)
        self.find_btn = W.QPushButton("Find"); self.find_btn.setObjectName("Apply")
        self.fit_btn = W.QPushButton("Fit"); self.conv_btn = W.QPushButton("Conv")
        self.find_btn.setToolTip("尋峰並標示"); self.fit_btn.setToolTip("擬合找到的峰"); self.conv_btn.setToolTip("把擬合出的峰存成新光譜")
        self.find_btn.clicked.connect(lambda: self.find()); self.fit_btn.clicked.connect(lambda: self.fit()); self.conv_btn.clicked.connect(lambda: self.conv())
        for b in (self.find_btn, self.fit_btn, self.conv_btn): r.addWidget(b)
        rw = W.QWidget(); rw.setLayout(r); sec.add(rw)
        r = W.QHBoxLayout(); r.setContentsMargins(0, 0, 0, 0)
        for nm, tip, fn in (("bl_copy", "複製峰表", self.copy_table), ("bl_trash", "清除圖上所有標記", lambda: self.win.clear_all_marks())):
            b = W.QToolButton(); b.setIcon(IC.ICONS[nm]()); b.setIconSize(C.QSize(18, 18)); b.setToolTip(tip); b.setFixedSize(28, 26)
            b.clicked.connect(lambda _=False, f=fn: f()); r.addWidget(b)
        r.addStretch(1); rw = W.QWidget(); rw.setLayout(r); sec.add(rw)
        lay.addWidget(sec)

        so = TH.Section("Options 擬合選項", expanded=False)
        f = W.QFormLayout(); f.setContentsMargins(0, 0, 0, 0)
        self.iters = W.QSpinBox(); self.iters.setRange(1, 1000); self.iters.setValue(100); self.iters.setToolTip("最大函數評估次數 = 迭代 × 參數數 × 10")
        self.max_shift = W.QDoubleSpinBox(); self.max_shift.setRange(0, 1e4); self.max_shift.setDecimals(1); self.max_shift.setValue(0); self.max_shift.setSpecialValueText("自動")
        self.min_w = W.QDoubleSpinBox(); self.min_w.setRange(0, 1e4); self.min_w.setDecimals(2); self.min_w.setSpecialValueText("自動")
        self.max_w = W.QDoubleSpinBox(); self.max_w.setRange(0, 1e4); self.max_w.setDecimals(1); self.max_w.setSpecialValueText("自動")
        for lab, w_ in (("Iterations", self.iters), ("Max shift (cm⁻¹)", self.max_shift), ("Min width (cm⁻¹)", self.min_w), ("Max width (cm⁻¹)", self.max_w)): f.addRow(lab, w_)
        self.fit_base = W.QCheckBox("Fit baseline（線性）"); self.fit_base.setChecked(True); f.addRow(self.fit_base)
        w = W.QWidget(); w.setLayout(f); so.add(w); lay.addWidget(so)

        sd = TH.Section("Display options 顯示選項", expanded=False)
        f = W.QFormLayout(); f.setContentsMargins(0, 0, 0, 0)
        self.dec = W.QSpinBox(); self.dec.setRange(0, 6); self.dec.setValue(1)
        self.attach = W.QCheckBox("Attach to curve（標示貼在曲線上）"); self.attach.setChecked(True)
        self.use_color = W.QCheckBox("Use data color"); self.use_color.setChecked(True)
        self.show_sum = W.QCheckBox("Sum 總和曲線"); self.show_sum.setChecked(True)
        self.show_sub = W.QCheckBox("各峰曲線"); self.show_sub.setChecked(True)
        f.addRow("Decimals", self.dec)
        for c in (self.attach, self.use_color, self.show_sum, self.show_sub): f.addRow(c)
        w = W.QWidget(); w.setLayout(f); sd.add(w); lay.addWidget(sd)
        for c in (self.dec,): c.valueChanged.connect(lambda *_: None)

        st = TH.Section("Peak table 峰表")
        self.table = W.QTableWidget(0, 5); self.table.setHorizontalHeaderLabels(["光譜", "峰位", "高度", "面積", "FWHM"])
        self.table.horizontalHeader().setStretchLastSection(True); self.table.setMinimumHeight(150); self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(W.QAbstractItemView.NoEditTriggers); self.table.verticalHeader().setVisible(False)
        st.add(self.table); lay.addWidget(st)

    # ---- helpers
    def _targets(self):
        idx = self.win.selected_idx() or [i for i, it in enumerate(self.win.items) if it.visible][-1:]
        if not idx: W.QMessageBox.warning(self, "Peaks", "請先開啟並選取光譜。")
        return idx

    def _set_row(self, r, vals):
        for c, v in enumerate(vals): self.table.setItem(r, c, W.QTableWidgetItem(v))

    # ---- Find
    def find(self):
        idx = self._targets()
        if not idx: return []
        pk = self.win.peaks; sp = self.win.items[idx[0]].spec; dx = float(np.median(np.diff(sp.x)))
        pk.scope.setCurrentIndex(0); pk.rel.setValue(float(self.level.value())); pk.dist.setValue(max(0.1, self.window.value() * dx))
        pk.fit.setCurrentIndex(0)
        pk.label_style = {"dec": self.dec.value(), "color": self.use_color.isChecked(), "attach": self.attach.isChecked()}
        rows = pk.find(); self.rows = rows; self.clear_fit_marks()
        self.err.clear(); self.chi.clear(); self.table.setRowCount(len(rows)); d = self.dec.value()
        for r, (it, p) in enumerate(rows):
            self._set_row(r, [it.spec.name, f"{p['position']:.{d}f}", f"{p['height']:.5g}", f"{p['area']:.5g}", f"{p['fwhm']:.3g}"])
        return rows

    # ---- Fit
    def clear_fit_marks(self):
        for m in self.win.marks: self.win.pi.removeItem(m)
        self.win.marks = []

    def _clusters(self):
        """Group the found peaks per spectrum into clusters whose integration windows overlap."""
        out = []; by = {}
        for it, p in self.rows: by.setdefault(id(it), (it, []))[1].append(p)
        for it, ps in by.values():
            ps = sorted(ps, key=lambda q: q["position"]); cur = [ps[0]]
            for q in ps[1:]:
                if q["window"][0] <= cur[-1]["window"][1]: cur.append(q)
                else: out.append((it, cur)); cur = [q]
            out.append((it, cur))
        return out

    def fit(self):
        if not self.rows:
            self.find()
            if not self.rows: return None
        model = SHAPES[self.shape.currentText()]; res = []; fails = 0
        ms, mn, mx = self.max_shift.value() or None, self.min_w.value() or None, self.max_w.value() or None
        self.clear_fit_marks(); self.fits = []
        sse = 0.0; chi = 0.0; n = 0; dof = 0
        for it, ps in self._clusters():
            hw = max((ps[0]["window"][1] - ps[0]["window"][0]) / 2, 1.0)
            cs = [q["position"] for q in ps]
            try:
                f = PA.fit_peaks(it.spec, cs, hw, model, "linear" if self.fit_base.isChecked() else "none", maxfev=self.iters.value() * 10 * (len(cs) * 4 + 2),
                                 max_shift=ms, min_width=mn, max_width=mx)
            except Exception as ex:
                fails += 1; continue
            self.fits.append((it, f))
            r = f["y"] - f["yfit"]; sg = max(BL.noise_sigma(it.spec.y), 1e-12)
            sse += float(r @ r); chi += float(r @ r) / sg ** 2; n += len(r); dof += max(len(r) - (len(cs) * (4 if model == "pseudovoigt" else 3) + (2 if self.fit_base.isChecked() else 0)), 1)
            col = it.color if self.use_color.isChecked() else "#222222"
            if self.show_sum.isChecked():
                m = pg.PlotDataItem(f["x"], f["yfit"], pen=pg.mkPen(col, width=2.2, style=C.Qt.DashLine)); m.setZValue(15); self.win.pi.addItem(m); self.win.marks.append(m)
            if self.show_sub.isChecked():
                for comp in f["components"]:
                    m = pg.PlotDataItem(f["x"], comp + f["base"], pen=pg.mkPen(col, width=1.2)); m.setZValue(14); self.win.pi.addItem(m); self.win.marks.append(m)
            res.append(f)
        if not res:
            self.win.statusBar().showMessage(f"擬合失敗（{fails} 組）"); return None
        self.err.setText(f"{np.sqrt(sse / n):.5g}"); self.chi.setText(f"{chi / dof:.5g}")
        # table: fitted values replace the raw ones for fitted peaks
        d = self.dec.value(); r_ = 0
        self.table.setRowCount(sum(len(f["peaks"]) for _, f in self.fits) + 0)
        for it, f in self.fits:
            for q in f["peaks"]:
                self._set_row(r_, [it.spec.name, f"{q['position']:.{d}f}", f"{q['height']:.5g}", f"{q['area']:.5g} ± {q['area_sd']:.2g}", f"{q['fwhm']:.3g}"]); r_ += 1
        self.win.statusBar().showMessage(f"Fit：{self.shape.currentText()}，{r_} 個峰" + (f"；{fails} 組擬合失敗" if fails else ""))
        return res

    def conv(self):
        if not self.fits:
            if self.fit() is None: return None
        self.win.push_undo(); made = []; by = {}
        for it, f in self.fits: by.setdefault(id(it), (it, []))[1].extend(f["peaks"])
        for it, pks in by.values():
            sp = it.spec; y = np.zeros_like(sp.x, dtype=float)
            for q in pks: y += PA._shape(sp.x, q["height"], q["position"], q["fwhm"], q["eta"])
            new = Spectrum(sp.x.copy(), y, f"Peaks_{sp.name}", sp.history + [f"peakfit({self.shape.currentText()},{len(pks)} peaks)"])
            made.append(self.win.add_spectrum(new, group=it.group))
        self.win.refresh(); self.win.statusBar().showMessage(f"Conv：新增 {len(made)} 條擬合峰光譜"); return made

    def copy_table(self):
        self.win.peaks._copy(self.table)
