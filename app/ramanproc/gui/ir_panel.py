"""IR tab (right panel): %T <-> Abs, CO2 elimination, base correction, characteristic-peak prediction."""
import csv
import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets as W, QtCore as C, QtGui as G

from ramanproc import ir as IR
from . import theme as TH


def _spin(v, dec=1, lo=-1e6, hi=1e6, step=1.0):
    s = W.QDoubleSpinBox(); s.setDecimals(dec); s.setRange(lo, hi); s.setValue(v); s.setSingleStep(step); return s


class IrPanel(W.QScrollArea):
    def __init__(self, win):
        super().__init__()
        self.win = win; self.rows = []          # rows: dicts from ir.predict_peaks + "spec"
        self.setWidgetResizable(True); self.setHorizontalScrollBarPolicy(C.Qt.ScrollBarAlwaysOff)
        host = W.QWidget(); lay = W.QVBoxLayout(host); lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(2)
        self.setWidget(host)

        # ---- mode ----
        sec = TH.Section("IR 光譜模式（%T ／ Abs）"); self.mode_lbl = W.QLabel(); self.mode_lbl.setWordWrap(True); sec.add(self.mode_lbl)
        r = W.QHBoxLayout()
        b1 = W.QPushButton("→ 吸收度 Abs"); b1.setToolTip("A = −log₁₀(T/100)；產生新光譜，原光譜保留"); b1.clicked.connect(lambda: self.convert("A"))
        b2 = W.QPushButton("→ 穿透率 %T"); b2.setToolTip("T = 100 × 10⁻ᴬ"); b2.clicked.connect(lambda: self.convert("T"))
        b3 = W.QPushButton("設為 %T"); b3.setToolTip("只改標記（不改數值）：自動判斷錯誤時使用"); b3.clicked.connect(lambda: self.tag("T"))
        b4 = W.QPushButton("設為 Abs"); b4.clicked.connect(lambda: self.tag("A"))
        for b in (b1, b2): r.addWidget(b)
        w = W.QWidget(); w.setLayout(r); sec.add(w)
        r = W.QHBoxLayout()
        for b in (b3, b4): r.addWidget(b)
        w = W.QWidget(); w.setLayout(r); sec.add(w); lay.addWidget(sec)

        # ---- CO2 ----
        sec = TH.Section("CO₂ 消除 CO₂ elimination", help=(
            "大氣 CO₂ 在 2349 cm⁻¹（反對稱伸縮，約 2280–2400）與 667 cm⁻¹（彎曲，約 645–690）產生干擾峰。\n"
            "做法：把區間內的資料，換成區間兩端外側各 4 點平均值之間的直線（%T 與 Abs 都適用）。\n"
            "注意：667 cm⁻¹ 區間可能與樣品本身的吸收（例如碳酸鹽 ν₄）重疊，預設不勾選。\n"
            "建議先按「偵測」看 CO₂ 帶高度；如果接近 0，代表光譜已經扣過背景，不需要處理。"))
        self.c1 = W.QCheckBox("伸縮帶 ~2349 cm⁻¹"); self.c1.setChecked(True)
        self.c1lo = _spin(2280, 1, 0, 1e5); self.c1hi = _spin(2400, 1, 0, 1e5)
        self.c2 = W.QCheckBox("彎曲帶 ~667 cm⁻¹"); self.c2.setChecked(False)
        self.c2lo = _spin(645, 1, 0, 1e5); self.c2hi = _spin(690, 1, 0, 1e5)
        g = W.QGridLayout()
        g.addWidget(self.c1, 0, 0, 1, 3); g.addWidget(W.QLabel("From"), 1, 0); g.addWidget(self.c1lo, 1, 1); g.addWidget(self.c1hi, 1, 2)
        g.addWidget(self.c2, 2, 0, 1, 3); g.addWidget(W.QLabel("From"), 3, 0); g.addWidget(self.c2lo, 3, 1); g.addWidget(self.c2hi, 3, 2)
        w = W.QWidget(); w.setLayout(g); sec.add(w)
        self.co2_lbl = W.QLabel(""); self.co2_lbl.setWordWrap(True); sec.add(self.co2_lbl)
        r = W.QHBoxLayout()
        bd = W.QPushButton("偵測 CO₂ 帶"); bd.clicked.connect(self.detect_co2)
        ba = W.QPushButton("套用 CO₂ 消除"); ba.setObjectName("Apply"); ba.clicked.connect(self.apply_co2)
        r.addWidget(bd); r.addWidget(ba); w = W.QWidget(); w.setLayout(r); sec.add(w); lay.addWidget(sec)

        # ---- base correction ----
        sec = TH.Section("基線校正 Base correction", help=(
            "一律在吸收度域計算基線再扣除；輸入是 %T 時，結果會轉回 %T（= T ÷ T基線 × 100）。\n"
            "橡皮筋 Rubberband：取光譜下凸包絡線當基線（IR 最常用，不需設定）。\n"
            "多項式 Poly：迭代式多項式擬合（階數 2–5），適合平滑漂移的基線。\n"
            "自訂錨點 Anchors：在你指定的波數（基線上沒有吸收的位置）取局部最低值，用直線連接。\n"
            "兩端直線 Ends：連接光譜兩端平均值。\n"
            "可限定只校正某個波數區間。"))
        self.bc_method = W.QComboBox()
        for t, k in (("橡皮筋 Rubberband", "rubberband"), ("多項式 Polynomial", "poly"), ("自訂錨點 Anchors", "anchors"), ("兩端直線 Ends", "ends")):
            self.bc_method.addItem(t, k)
        self.bc_order = _spin(3, 0, 1, 8, 1); self.bc_anchor = W.QLineEdit("4000, 2000, 1850, 900, 450")
        self.bc_hw = _spin(6.0, 1, 0.5, 100, 1.0); self.bc_limit = W.QCheckBox("只校正區間")
        self.bc_lo = _spin(400, 1, 0, 1e5); self.bc_hi = _spin(4000, 1, 0, 1e5)
        f = W.QFormLayout(); f.addRow("方法", self.bc_method); f.addRow("多項式階數", self.bc_order); f.addRow("錨點波數 (cm⁻¹)", self.bc_anchor)
        f.addRow("錨點半窗 ±(cm⁻¹)", self.bc_hw); f.addRow(self.bc_limit); f.addRow("區間 From", self.bc_lo); f.addRow("區間 To", self.bc_hi)
        w = W.QWidget(); w.setLayout(f); sec.add(w)
        ba = W.QPushButton("套用基線校正"); ba.setObjectName("Apply"); ba.clicked.connect(self.apply_bc); sec.add(ba)
        self.bc_method.currentIndexChanged.connect(self._bc_vis); self._bc_vis(); lay.addWidget(sec)

        # ---- peaks ----
        sec = TH.Section("特徵峰預測 Peak prediction", help=(
            "在吸收度域找吸收帶（%T 的向下峰會自動轉成向上），並依常見官能基的紅外特徵頻率表，列出『可能歸屬』。\n"
            "這只是候選清單：同一個波數常對應多種官能基，請搭配化學背景與其他峰（例如 C=O 與 C–O 一起出現）判斷。\n"
            "強度分級依各峰突出度（prominence）相對最強峰：≥60% 強 s、25–60% 中 m、其餘弱 w；半高寬 ≥50 cm⁻¹ 視為寬峰。"))
        self.pk_prom = _spin(5.0, 1, 0.1, 100, 0.5); self.pk_prom.setSuffix(" %"); self.pk_dist = _spin(8.0, 1, 1, 500, 1)
        self.pk_lo = _spin(400, 0, 0, 1e5); self.pk_hi = _spin(4000, 0, 0, 1e5); self.pk_sm = _spin(0, 0, 0, 51, 2)
        f = W.QFormLayout(); f.addRow("最小突出度（佔全幅）", self.pk_prom); f.addRow("最小峰間距 (cm⁻¹)", self.pk_dist)
        f.addRow("範圍 From", self.pk_lo); f.addRow("範圍 To", self.pk_hi); f.addRow("先平滑（點數，0=不平滑）", self.pk_sm)
        w = W.QWidget(); w.setLayout(f); sec.add(w)
        r = W.QHBoxLayout(); bp = W.QPushButton("預測特徵峰"); bp.setObjectName("Apply"); bp.clicked.connect(self.predict); r.addWidget(bp)
        self.pk_mark = W.QCheckBox("在圖上標示"); self.pk_mark.setChecked(True); self.pk_mark.toggled.connect(lambda _: self.win.redraw()); r.addWidget(self.pk_mark)
        w = W.QWidget(); w.setLayout(r); sec.add(w)
        self.pk_note = W.QLabel(""); self.pk_note.setWordWrap(True); sec.add(self.pk_note)
        self.table = W.QTableWidget(0, 5); self.table.setHorizontalHeaderLabels(["波數", "強度", "分級", "寬(cm⁻¹)", "可能歸屬（候選）"])
        self.table.verticalHeader().setVisible(False); self.table.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(W.QAbstractItemView.SelectRows); self.table.setWordWrap(True)
        hh = self.table.horizontalHeader(); hh.setStretchLastSection(True)
        for i in range(4): hh.setSectionResizeMode(i, W.QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(260); self.table.cellDoubleClicked.connect(self._zoom_row); sec.add(self.table)
        r = W.QHBoxLayout()
        for t, fn in (("複製表格", self.copy), ("儲存 CSV…", self.save_csv), ("清除標示", self.clear)):
            b = W.QPushButton(t); b.clicked.connect(lambda _=False, f_=fn: f_()); r.addWidget(b)
        w = W.QWidget(); w.setLayout(r); sec.add(w); lay.addWidget(sec)
        lay.addStretch(1)
        win.listw.itemSelectionChanged.connect(self.update_mode)
        self.update_mode()

    # ---------------- helpers ----------------
    def _bc_vis(self):
        k = self.bc_method.currentData(); self.bc_order.setEnabled(k == "poly"); self.bc_anchor.setEnabled(k == "anchors"); self.bc_hw.setEnabled(k == "anchors")

    def _targets(self):
        idx = self.win.targets()
        return idx or []

    def update_mode(self):
        w = self.win
        idx = w.selected_idx() or [i for i, it in enumerate(w.items) if it.visible]
        n_t = sum(1 for i in idx if IR.ir_mode(w.items[i].spec) == "T"); n_a = sum(1 for i in idx if IR.ir_mode(w.items[i].spec) == "A")
        n_o = len(idx) - n_t - n_a
        self.mode_lbl.setText(f"目前對象：穿透率 %T × {n_t}，吸收度 Abs × {n_a}" + (f"，非 IR（未標記）× {n_o}" if n_o else "") +
                              ("<br>非 IR 光譜請用「設為 %T／設為 Abs」標記後再使用下列功能。" if n_o else ""))

    def _need_ir(self, idx):
        bad = [w for w in (self.win.items[i].spec.name for i in idx if IR.ir_mode(self.win.items[i].spec) is None)]
        if bad:
            W.QMessageBox.warning(self.win, "IR", "這些光譜尚未標記為 IR（%T 或 Abs）：\n" + "\n".join(bad[:8]) + "\n\n請先按「設為 %T」或「設為 Abs」。")
            return False
        return True

    def _add(self, idx, fn, suffix):
        w = self.win; w.push_undo(); ok = 0; errs = []
        for i in idx:
            src = w.items[i]
            try: new = fn(src.spec)
            except Exception as ex: errs.append(f"{src.spec.name}：{ex}"); continue
            new.name = src.spec.name + suffix; w.add_spectrum(new, group=src.group); ok += 1
        if not ok: w.undo.pop(); w._refresh_actions()
        w.refresh()
        if errs: W.QMessageBox.warning(w, "IR", "\n".join(errs))
        w.statusBar().showMessage(f"已產生 {ok} 條新光譜（{suffix.strip('_')}）")
        self.update_mode()
        return ok

    # ---------------- actions ----------------
    def convert(self, to):
        idx = self._targets()
        if not idx or not self._need_ir(idx): return
        fn = IR.to_absorbance if to == "A" else IR.to_transmittance
        self._add([i for i in idx if IR.ir_mode(self.win.items[i].spec) != to], fn, "_Abs" if to == "A" else "_T")
        self.win.cb_yunit.setCurrentText("Absorbance" if to == "A" else "Transmittance (%)")

    def tag(self, mode):
        idx = self._targets()
        if not idx: return
        w = self.win; w.push_undo()
        for i in idx:
            w.items[i].spec.history.append(f"ir={mode}")
        w.refresh(); self.update_mode()
        w.cb_yunit.setCurrentText("Absorbance" if mode == "A" else "Transmittance (%)")

    def _co2_regions(self):
        r = []
        if self.c1.isChecked(): r.append((self.c1lo.value(), self.c1hi.value()))
        if self.c2.isChecked(): r.append((self.c2lo.value(), self.c2hi.value()))
        return r

    def detect_co2(self):
        idx = self._targets()
        if not idx: return
        lines = []
        for i in idx:
            sp = self.win.items[i].spec
            if IR.ir_mode(sp) is None: lines.append(f"{sp.name}：未標記 IR"); continue
            h = IR.co2_band_height(sp, self.c1lo.value(), self.c1hi.value())
            lines.append(f"{sp.name}：2349 帶高度 ≈ {h:.4f} Abs" + ("（可忽略）" if abs(h) < 0.002 else "（明顯，建議消除）"))
        self.co2_lbl.setText("<br>".join(lines))

    def apply_co2(self):
        idx = self._targets()
        if not idx or not self._need_ir(idx): return
        reg = self._co2_regions()
        if not reg: W.QMessageBox.information(self.win, "IR", "請至少勾選一個 CO₂ 區間。"); return
        self._add(idx, lambda s: IR.co2_eliminate(s, reg), "_noCO2")

    def apply_bc(self):
        idx = self._targets()
        if not idx or not self._need_ir(idx): return
        k = self.bc_method.currentData(); anchors = None
        if k == "anchors":
            try: anchors = [float(t) for t in self.bc_anchor.text().replace("，", ",").replace(";", ",").split(",") if t.strip()]
            except ValueError: W.QMessageBox.warning(self.win, "IR", "錨點請輸入以逗號分隔的數字，例如 4000, 2000, 900"); return
        region = (self.bc_lo.value(), self.bc_hi.value()) if self.bc_limit.isChecked() else None
        self._add(idx, lambda s: IR.base_correct(s, k, int(self.bc_order.value()), anchors, self.bc_hw.value(), region), "_BC")

    def predict(self):
        idx = self._targets()
        if not idx: return
        w = self.win; self.rows = []
        for i in idx[:1]:                                       # one spectrum at a time (the first selected / visible one)
            sp = w.items[i].spec
            if IR.ir_mode(sp) is None: continue
            try:
                rows = IR.predict_peaks(sp, (self.pk_lo.value(), self.pk_hi.value()), self.pk_prom.value() / 100.0, self.pk_dist.value(), int(self.pk_sm.value()))
            except Exception as ex:
                W.QMessageBox.warning(w, "IR", f"{sp.name}：{ex}"); return
            for r in rows: r["spec"] = sp; r["name"] = sp.name
            self.rows += rows
        if not self.rows and not any(IR.ir_mode(w.items[i].spec) for i in idx):
            self._need_ir(idx); return
        self._fill(); w.redraw()
        self.pk_note.setText(f"{w.items[idx[0]].spec.name}：找到 {len(self.rows)} 個吸收帶" + ("（只分析選取的第一條光譜）" if len(idx) > 1 else "") +
                             "。歸屬只是候選，請搭配化學背景判斷。")

    def _fill(self):
        t = self.table; t.setRowCount(len(self.rows))
        for k, r in enumerate(self.rows):
            unit = f"{r['t']:.1f} %T" if r["t"] is not None else f"{r['a']:.4f} A"
            cells = [f"{r['x']:.1f}", unit, IR.CLS_TEXT[r["cls"]] + (" 寬" if r["broad"] else ""), f"{r['fwhm']:.0f}", "；".join(r["guess"][:3]) or "（表中無對應）"]
            for c, txt in enumerate(cells):
                it = W.QTableWidgetItem(txt); it.setToolTip(r["name"] + "\n" + "\n".join(r["guess"])); t.setItem(k, c, it)
        t.resizeRowsToContents()

    def _zoom_row(self, row, _col):
        if 0 <= row < len(self.rows):
            x = self.rows[row]["x"]; self.win.pi.setXRange(x - 150, x + 150, padding=0)

    def text(self):
        lines = ["波數(cm-1)\t強度\t分級\t半高寬(cm-1)\t可能歸屬"]
        for r in self.rows:
            unit = f"{r['t']:.2f} %T" if r["t"] is not None else f"{r['a']:.5f} A"
            lines.append(f"{r['x']:.1f}\t{unit}\t{r['cls']}{'-br' if r['broad'] else ''}\t{r['fwhm']:.0f}\t" + "; ".join(r["guess"]))
        return "\n".join(lines)

    def copy(self):
        G.QGuiApplication.clipboard().setText(self.text()); self.win.statusBar().showMessage("已複製特徵峰表")

    def save_csv(self):
        if not self.rows: return
        p, _ = W.QFileDialog.getSaveFileName(self.win, "儲存特徵峰", "ir_peaks.csv", "CSV (*.csv)")
        if not p: return
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            wr = csv.writer(f); wr.writerow(["spectrum", "wavenumber_cm-1", "absorbance", "transmittance_pct", "class", "broad", "fwhm_cm-1", "assignments"])
            for r in self.rows:
                wr.writerow([r["name"], f"{r['x']:.2f}", f"{r['a']:.5f}", "" if r["t"] is None else f"{r['t']:.3f}", r["cls"], int(r["broad"]), f"{r['fwhm']:.1f}", "; ".join(r["guess"])])

    def clear(self):
        self.rows = []; self.table.setRowCount(0); self.pk_note.setText(""); self.win.redraw()

    # ---------------- plot marks (called from MainWindow.redraw) ----------------
    def draw_marks(self):
        w = self.win
        if not self.rows or not self.pk_mark.isChecked(): return
        vis = {id(it.spec) for it in w.items if it.visible}
        for r in self.rows:
            sp = r["spec"]
            if id(sp) not in vis: continue
            y = float(np.interp(r["x"], sp.x, sp.y)); is_t = IR.ir_mode(sp) == "T"
            tx = pg.TextItem(f"{r['x']:.0f}", color="#b00020", anchor=(0.5, 0.0 if is_t else 1.0))
            tx.setFont(G.QFont("", 8)); tx.setPos(float(w._xmap(r["x"])), y + (0 if is_t else 0)); w._add_extra(tx, True)
