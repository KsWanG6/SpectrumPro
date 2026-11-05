"""Quantification & LOD module (separate tab)."""
import re, html, csv
import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets as W, QtCore as C, QtGui as G

import ramanproc as rp
from ramanproc import quant as Q
from . import theme as TH

ROLES = ["略過", "空白", "標準品", "未知樣品", "低濃度驗證"]
ROLE_KEY = {"略過": None, "空白": "blank", "標準品": "standard", "未知樣品": "unknown", "低濃度驗證": "check"}
MODEL_ITEMS = [("線性（OLS）", "linear"), ("線性・加權 1/C", "linear_w1x"), ("線性・加權 1/C²", "linear_w1x2"), ("對數濃度（響應 vs log₁₀C）", "loglinear")]
FEATURES = [("峰高", "height"), ("峰面積", "area"), ("峰比值（峰高 / 內標峰高）", "ratio_height"), ("峰比值（峰面積 / 內標峰面積）", "ratio_area")]
COLORS = ["#1d7cd4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf"]


class QuantPanel(W.QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win; self.rows = []; self.last = None
        split = W.QSplitter(C.Qt.Horizontal); lay = W.QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.addWidget(split)

        # ---------------- left: setup ----------------
        left = W.QWidget(); ll = W.QVBoxLayout(left); ll.setContentsMargins(6, 6, 6, 6)
        t = W.QLabel("① 指定樣品  ② 選特徵  ③ 選尺度與模型  ④ 選 LOD 方法  ⑤ 計算"); t.setWordWrap(True); ll.addWidget(t)
        self.table = W.QTableWidget(0, 4); self.table.setHorizontalHeaderLabels(["光譜", "角色", "濃度", "曲線"])
        self.table.horizontalHeader().setStretchLastSection(True); self.table.setMinimumHeight(190); ll.addWidget(self.table, 1)
        r = W.QHBoxLayout(); b = W.QPushButton("載入目前工作區光譜"); b.clicked.connect(self.load); r.addWidget(b)
        self.role_set = W.QComboBox(); self.role_set.addItems(ROLES[1:]); r.addWidget(self.role_set)
        b2 = W.QPushButton("選取列設為此角色"); b2.clicked.connect(self.set_role_selected); r.addWidget(b2); ll.addLayout(r)

        sec = TH.Section("定量特徵 Feature"); f = W.QFormLayout()
        self.feat = W.QComboBox(); [self.feat.addItem(a, k) for a, k in FEATURES]
        self.center = self._spin(1075.0, 1); self.hw = self._spin(10.0, 1, 0.1, 1e4)
        self.ref_center = self._spin(1580.0, 1); self.ref_hw = self._spin(10.0, 1, 0.1, 1e4)
        self.bl = W.QCheckBox("扣窗口兩端直線基線")
        f.addRow("特徵", self.feat); f.addRow("峰位置 (cm⁻¹)", self.center); f.addRow("半窗寬 ±", self.hw)
        f.addRow("內標峰位置（比值用）", self.ref_center); f.addRow("內標半窗寬", self.ref_hw); f.addRow(self.bl)
        self.feat.currentIndexChanged.connect(self._feat_changed); self._feat_changed()
        w = W.QWidget(); w.setLayout(f); sec.add(w); ll.addWidget(sec)

        sec2 = TH.Section("濃度尺度與迴歸 Model"); f2 = W.QFormLayout()
        self.model = W.QComboBox(); [self.model.addItem(a, k) for a, k in MODEL_ITEMS]
        self.unit = W.QLineEdit("µM"); self.blank_in_fit = W.QCheckBox("空白（濃度 0）也納入迴歸（僅線性 OLS）")
        f2.addRow("模型 / 尺度", self.model); f2.addRow("濃度單位", self.unit); f2.addRow(self.blank_in_fit)
        w2 = W.QWidget(); w2.setLayout(f2); sec2.add(w2); ll.addWidget(sec2)

        sec3 = TH.Section("LOD / LOQ 設定"); f3 = W.QFormLayout()
        self.sigma = W.QComboBox(); [self.sigma.addItem(Q.SIGMA_LABELS[k], k) for k in Q.SIGMA_SOURCES]
        self.k_lod = self._spin(3.0, 2, 1, 10, 0.1); self.k_loq = self._spin(10.0, 2, 1, 30, 0.5)
        self.verify_rate = self._spin(0.95, 2, 0.5, 1.0, 0.01)
        f3.addRow("σ 來源", self.sigma); f3.addRow("LOD 係數 k", self.k_lod); f3.addRow("LOQ 係數 k", self.k_loq); f3.addRow("驗證檢出率門檻", self.verify_rate)
        w3 = W.QWidget(); w3.setLayout(f3); sec3.add(w3); ll.addWidget(sec3)
        r = W.QHBoxLayout()
        bc = W.QPushButton("計算 Calculate"); bc.setObjectName("Apply"); bc.clicked.connect(self.compute)
        bcopy = W.QPushButton("複製報告"); bcopy.clicked.connect(self.copy_report)
        bsave = W.QPushButton("儲存 CSV…"); bsave.clicked.connect(self.save_csv)
        for b_ in (bc, bcopy, bsave): r.addWidget(b_)
        ll.addLayout(r)
        sa = W.QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(left); sa.setHorizontalScrollBarPolicy(C.Qt.ScrollBarAlwaysOff)
        split.addWidget(sa)

        # ---------------- right: results ----------------
        right = W.QWidget(); rl = W.QVBoxLayout(right); rl.setContentsMargins(6, 6, 6, 6)
        pl = W.QHBoxLayout()
        self.p_cal = pg.PlotWidget(title="檢量線"); self.p_res = pg.PlotWidget(title="殘差")
        for p in (self.p_cal, self.p_res): p.showGrid(x=True, y=True, alpha=0.25); p.setMinimumHeight(240)
        pl.addWidget(self.p_cal, 3); pl.addWidget(self.p_res, 2); rl.addLayout(pl)
        self.report = W.QTextBrowser(); self.report.setMinimumHeight(200); rl.addWidget(self.report, 1)
        self.utable = W.QTableWidget(0, 6); self.utable.setHorizontalHeaderLabels(["未知樣品", "響應", "濃度", "95% 區間", "狀態", "備註"])
        self.utable.horizontalHeader().setStretchLastSection(True); self.utable.setMinimumHeight(130); rl.addWidget(self.utable, 1)
        split.addWidget(right); split.setStretchFactor(1, 1); split.setSizes([560, 900])

    @staticmethod
    def _spin(v, dec, lo=-1e6, hi=1e6, step=1.0):
        s = W.QDoubleSpinBox(); s.setDecimals(dec); s.setRange(lo, hi); s.setValue(v); s.setSingleStep(step); return s

    def _feat_changed(self):
        ratio = self.feat.currentData().startswith("ratio")
        self.ref_center.setEnabled(ratio); self.ref_hw.setEnabled(ratio)

    # ---------------- table ----------------
    def load(self):
        old = {self.table.item(r, 0).text(): self._row_state(r) for r in range(self.table.rowCount())}
        items = self.win.items; self.rows = list(range(len(items)))
        self.table.setRowCount(len(items))
        for r, it in enumerate(items):
            name = it.spec.name
            a = W.QTableWidgetItem(name); a.setFlags(a.flags() & ~C.Qt.ItemIsEditable); self.table.setItem(r, 0, a)
            cb = W.QComboBox(); cb.addItems(ROLES); self.table.setCellWidget(r, 1, cb)
            role, conc, curve = old.get(name, (self._guess(name), "", "1"))
            cb.setCurrentText(role); self.table.setItem(r, 2, W.QTableWidgetItem(conc)); self.table.setItem(r, 3, W.QTableWidgetItem(curve))

    @staticmethod
    def _guess(name):
        return "空白" if re.search(r"blank|空白", name, re.I) else "略過"

    def _row_state(self, r):
        return (self.table.cellWidget(r, 1).currentText(), self.table.item(r, 2).text(), self.table.item(r, 3).text())

    def set_role_selected(self):
        role = self.role_set.currentText()
        for idx in {i.row() for i in self.table.selectedIndexes()}:
            self.table.cellWidget(idx, 1).setCurrentText(role)

    # ---------------- compute ----------------
    def _feature(self):
        return {"kind": self.feat.currentData(), "center": self.center.value(), "hw": self.hw.value(), "baseline": self.bl.isChecked(),
                "ref_center": self.ref_center.value(), "ref_hw": self.ref_hw.value()}

    def compute(self):
        if self.table.rowCount() != len(self.win.items): self.load()
        try:
            self._compute()
        except Exception as ex:
            W.QMessageBox.warning(self, "定量", str(ex))

    def _compute(self):
        feat = self._feature(); model = self.model.currentData(); u = self.unit.text()
        data = {"blank": [], "standard": [], "unknown": [], "check": []}
        for r in range(self.table.rowCount()):
            role, ctxt, cur = self._row_state(r); key = ROLE_KEY[role]
            if key is None: continue
            it = self.win.items[r]
            try: y = Q.feature_value(it.spec, feat)
            except Exception as ex: raise ValueError(f"「{it.spec.name}」：{ex}")
            conc = None
            if key in ("standard", "check"):
                try: conc = float(ctxt)
                except ValueError: raise ValueError(f"「{it.spec.name}」需要填濃度")
            try: curve = int(float(cur or 1))
            except ValueError: curve = 1
            data[key].append({"name": it.spec.name, "y": y, "c": conc, "curve": curve, "spec": it.spec})
        std = data["standard"]
        if len(std) < 3: raise ValueError("標準品至少需要 3 點")
        log = Q.MODELS[model][0]
        fit_rows = list(std)
        if self.blank_in_fit.isChecked() and model == "linear":
            fit_rows += [{"name": b["name"], "y": b["y"], "c": 0.0, "curve": 1, "spec": b["spec"]} for b in data["blank"]]
        fit = Q.fit_calibration([d["c"] for d in fit_rows], [d["y"] for d in fit_rows], model)

        # --- LOD record
        method = self.sigma.currentData(); blank_y = [b["y"] for b in data["blank"]] or None
        cmin = min(d["c"] for d in std if d["c"] > 0) if any(d["c"] > 0 for d in std) else None
        low = [d["y"] for d in std if cmin is not None and abs(d["c"] - cmin) <= 1e-9 * cmin]
        curves = {}
        for d in std: curves.setdefault(d["curve"], []).append(d)
        curve_list = [([x["c"] for x in v], [x["y"] for x in v]) for v in curves.values()]
        hist = sorted({"→".join(map(str, d["spec"].history)) or "（無前處理）" for d in std})
        pre = "；".join(hist) if len(hist) == 1 else f"⚠ 標準品前處理不一致：{' | '.join(hist)}"
        slope_src = (f"{len(std)} 個標準品、曲線 {sorted(curves)}，濃度 {fit['conc_range'][0]:.3g}–{fit['conc_range'][1]:.3g} {u}，"
                     f"特徵 {self.feat.currentText()}（{self.center.value():g}±{self.hw.value():g} cm⁻¹）")
        try:
            rec = Q.lod_record(fit, method, blank_y, low, curve_list, self.k_lod.value(), self.k_loq.value(), slope_src, pre)
        except ValueError as ex:
            rec = None; lod_err = str(ex)
        if rec and data["check"]:
            sign = 1 if fit["slope"] > 0 else -1
            rec["validation"] = Q.verify_lod([d["y"] for d in data["check"]], rec["y_lod"], sign, min_rate=self.verify_rate.value())

        # --- unknowns
        unk = []
        for d in data["unknown"]:
            p = Q.predict_conc(fit, d["y"]); flag = Q.range_flag(fit, d["y"], p["conc"]); status, note = "OK", ""
            if flag == "low": status, note = "⚠ 低於校正範圍", "結果為外推，不可靠"
            elif flag == "high": status, note = "⚠ 超出校正範圍（高）", "請稀釋後重測"
            if rec:
                if p["conc"] < rec["lod"]: status, note = "< LOD", "未檢出"
                elif p["conc"] < rec["loq"] and not flag: status, note = "LOD–LOQ", "僅可判定檢出，不宜定量"
            unk.append((d, p, status, note))
        self.last = {"fit": fit, "rec": rec, "unknown": unk, "data": data, "feat": feat, "unit": u, "err": None if rec else lod_err}
        self._render(fit, rec, unk, data, u, log, lod_err if not rec else None)

    # ---------------- rendering ----------------
    def _render(self, fit, rec, unk, data, u, log, lod_err):
        x = fit["x"]; xs = np.linspace(x.min(), x.max(), 50)
        self.p_cal.clear(); self.p_res.clear()
        self.p_cal.setLabel("bottom", "log₁₀(濃度)" if log else f"濃度 ({u})"); self.p_cal.setLabel("left", "響應")
        self.p_res.setLabel("bottom", "log₁₀(濃度)" if log else f"濃度 ({u})"); self.p_res.setLabel("left", "殘差")
        cur_ids = sorted({d["curve"] for d in data["standard"]})
        for k, cid in enumerate(cur_ids):
            pts = [d for d in data["standard"] if d["curve"] == cid]
            px = [np.log10(d["c"]) if log else d["c"] for d in pts]
            self.p_cal.plot(px, [d["y"] for d in pts], pen=None, symbol="o", symbolSize=9, symbolBrush=COLORS[k % 6], name=f"曲線 {cid}")
        self.p_cal.plot(xs, fit["slope"] * xs + fit["intercept"], pen=pg.mkPen("#d62728", width=2))
        if rec:
            self.p_cal.addItem(pg.InfiniteLine(pos=rec["y_lod"], angle=0, pen=pg.mkPen("#888", style=C.Qt.DashLine), label="LOD 響應", labelOpts={"position": 0.1}))
        ux = [(np.log10(p["conc"]) if log else p["conc"]) for d, p, *_ in unk if p["conc"] > 0 or not log]
        uy = [d["y"] for d, p, *_ in unk if p["conc"] > 0 or not log]
        if ux: self.p_cal.plot(ux, uy, pen=None, symbol="t", symbolSize=12, symbolBrush="#2ca02c")
        self.p_res.plot(x, fit["residuals"], pen=None, symbol="o", symbolSize=9, symbolBrush="#1d7cd4")
        self.p_res.addItem(pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen("#d62728")))

        e = html.escape; L = []
        eq_x = "log₁₀C" if log else "C"
        L.append(f"<h3>檢量線</h3>模型：{e(self.model.currentText())}　特徵：{e(self.feat.currentText())}<br>"
                 f"y = ({fit['slope']:.6g} ± {fit['se_slope']:.3g})·{eq_x} + ({fit['intercept']:.6g} ± {fit['se_intercept']:.3g})<br>"
                 f"R² = {fit['r2']:.5f}　Sy.x = {fit['sy_resp']:.4g}　n = {fit['n']}（自由度 {fit['dof']}）　"
                 f"校正範圍 {fit['conc_range'][0]:.3g}–{fit['conc_range'][1]:.3g} {e(u)}")
        L.append("<h3>LOD / LOQ 記錄</h3>")
        if rec:
            rows = [("計算方法", f"LOD = {rec['k_lod']:g}σ/S，LOQ = {rec['k_loq']:g}σ/S" + ("（對數尺度：以響應限值代回檢量線）" if fit["log"] else "")),
                    ("σ 來源", rec["sigma_source"]), ("σ 值", f"{rec['sigma']:.5g}"), ("有效重複數 / 樣本數", str(rec["n_eff"])),
                    ("斜率 S 與來源", f"{rec['slope']:.6g}　（{rec['slope_source']}）"), ("前處理流程", rec["preprocessing"]),
                    ("濃度尺度", rec["scale"]), ("LOD", f"<b>{rec['lod']:.4g} {u}</b>"), ("LOQ", f"<b>{rec['loq']:.4g} {u}</b>"),
                    ("驗證狀態", rec["validation"]["text"])]
            rows += [("備註", n) for n in rec["notes"]]
            L.append("<table border='1' cellpadding='4' style='border-collapse:collapse'>" + "".join(
                f"<tr><td bgcolor='#aad7e3'><b>{e(a)}</b></td><td>{b if a in ('LOD', 'LOQ') else e(b)}</td></tr>" for a, b in rows) + "</table>")
        else:
            L.append(f"<span style='color:#a33'>無法計算 LOD/LOQ：{e(lod_err)}</span>")
        self.report.setHtml("".join(L))
        self.utable.setRowCount(len(unk))
        for r, (d, p, status, note) in enumerate(unk):
            vals = [d["name"], f"{d['y']:.5g}", f"{p['conc']:.4g} {u}", f"{p['lo']:.3g} – {p['hi']:.3g}", status, note]
            for c, v in enumerate(vals):
                it = W.QTableWidgetItem(v)
                if status.startswith("⚠"): it.setForeground(G.QColor("#b02020"))
                self.utable.setItem(r, c, it)
        self.win.statusBar().showMessage("定量計算完成" + (f"：LOD = {rec['lod']:.3g} {u}" if rec else ""))

    # ---------------- export ----------------
    def copy_report(self):
        if not self.last: return
        L = self.last; f = L["fit"]; u = L["unit"]; out = []
        out.append(f"模型\t{self.model.currentText()}\n特徵\t{self.feat.currentText()}")
        out.append(f"斜率\t{f['slope']:.6g} ± {f['se_slope']:.3g}\n截距\t{f['intercept']:.6g} ± {f['se_intercept']:.3g}\nR²\t{f['r2']:.5f}\nSy.x\t{f['sy_resp']:.5g}\nn\t{f['n']}")
        r = L["rec"]
        if r:
            for a, b in (("計算方法", f"LOD={r['k_lod']:g}σ/S; LOQ={r['k_loq']:g}σ/S"), ("σ來源", r["sigma_source"]), ("σ", f"{r['sigma']:.5g}"),
                         ("有效重複數", r["n_eff"]), ("斜率來源", r["slope_source"]), ("前處理", r["preprocessing"]), ("濃度尺度", r["scale"]),
                         ("LOD", f"{r['lod']:.4g} {u}"), ("LOQ", f"{r['loq']:.4g} {u}"), ("驗證狀態", r["validation"]["text"])):
                out.append(f"{a}\t{b}")
        out.append("\n未知樣品\t響應\t濃度\t區間下限\t區間上限\t狀態")
        for d, p, st, note in L["unknown"]:
            out.append(f"{d['name']}\t{d['y']:.5g}\t{p['conc']:.4g}\t{p['lo']:.3g}\t{p['hi']:.3g}\t{st}")
        G.QGuiApplication.clipboard().setText("\n".join(out)); self.win.statusBar().showMessage("報告已複製到剪貼簿")

    def save_csv(self):
        if not self.last: return
        p, _ = W.QFileDialog.getSaveFileName(self, "儲存定量結果", "quantification.csv", "CSV (*.csv)")
        if not p: return
        L = self.last; r = L["rec"]
        with open(p, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh); f = L["fit"]
            w.writerow(["item", "value"]); w.writerows([["model", f["model"]], ["slope", f["slope"]], ["intercept", f["intercept"]], ["r2", f["r2"]], ["sy", f["sy"]], ["n", f["n"]]])
            if r: w.writerows([["lod_method", f"{r['k_lod']}sigma/S"], ["sigma_source", r["sigma_source"]], ["sigma", r["sigma"]], ["n_eff", r["n_eff"]],
                               ["slope_source", r["slope_source"]], ["preprocessing", r["preprocessing"]], ["scale", r["scale"]],
                               ["LOD", r["lod"]], ["LOQ", r["loq"]], ["validation", r["validation"]["text"]]])
            w.writerow([]); w.writerow(["unknown", "response", "conc", "ci_low", "ci_high", "status"])
            for d, p, st, note in L["unknown"]: w.writerow([d["name"], d["y"], p["conc"], p["lo"], p["hi"], st])
