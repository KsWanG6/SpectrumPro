"""Axis dialog (Origin-style): Scale / Title / Grids per axis (Horizontal, Vertical), Tick Labels and Line and Ticks per SIDE
(Bottom, Top, Left, Right), plus the Figure text and Frame sections.
All settings live in figstyle.st (so the export and the dialog always agree); this dialog only edits them."""
import copy
import numpy as np
from PySide6 import QtWidgets as W, QtCore as C, QtGui as G
from .figstyle import FONTS, STYLES, LENGTHS, THICKS

DISPLAY_MODES = [("自動 Auto", "auto"), ("Decimal  1000", "decimal"), ("Scientific  1e3", "scientific"), ("10 的次方  10³（適合 Log 軸）", "pow10")]
SIDES = [("Bottom（下）", "bottom"), ("Top（上）", "top"), ("Left（左）", "left"), ("Right（右）", "right")]
PARTNER = {"bottom": "top", "top": "bottom", "left": "right", "right": "left"}


def _fmt(v):
    return f"{v:.6g}"


def side_icon(side, size=56):
    """Origin-style icon: a small plot frame with the chosen side drawn in red."""
    pm = G.QPixmap(size, size); pm.fill(C.Qt.transparent)
    p = G.QPainter(pm); p.setRenderHint(G.QPainter.Antialiasing)
    m = 7; r = C.QRectF(m, m, size - 2 * m, size - 2 * m)
    p.setPen(G.QPen(G.QColor("#555555"), 1.6)); p.setBrush(G.QColor("#c9c9c9")); p.drawRoundedRect(r, 3, 3)
    p.setPen(G.QPen(G.QColor("#1f77b4"), 2.0)); p.setBrush(C.Qt.NoBrush)
    path = G.QPainterPath(); path.moveTo(r.left() + 5, r.bottom() - 9)
    for i, (dx, dy) in enumerate(((9, -6), (15, 2), (21, -11), (28, -3), (34, -7))): path.lineTo(r.left() + 5 + dx, r.bottom() - 9 + dy)
    p.drawPath(path)
    red = G.QPen(G.QColor("#e0201b"), 2.6); red.setCapStyle(C.Qt.FlatCap); p.setPen(red)
    if side == "bottom": p.drawLine(r.bottomLeft(), r.bottomRight())
    elif side == "top": p.drawLine(r.topLeft(), r.topRight())
    elif side == "left": p.drawLine(r.topLeft(), r.bottomLeft())
    else: p.drawLine(r.topRight(), r.bottomRight())
    red.setWidthF(1.6); p.setPen(red)
    for k in range(1, 6):                                       # little ticks on that side
        t = k / 6.0
        if side == "bottom": x = r.left() + r.width() * t; p.drawLine(C.QPointF(x, r.bottom()), C.QPointF(x, r.bottom() + 4))
        elif side == "top": x = r.left() + r.width() * t; p.drawLine(C.QPointF(x, r.top()), C.QPointF(x, r.top() - 4))
        elif side == "left": y = r.top() + r.height() * t; p.drawLine(C.QPointF(r.left(), y), C.QPointF(r.left() - 4, y))
        else: y = r.top() + r.height() * t; p.drawLine(C.QPointF(r.right(), y), C.QPointF(r.right() + 4, y))
    p.end(); return G.QIcon(pm)


class SideList(W.QListWidget):
    """Left-hand picture selector: Bottom / Top / Left / Right (same role as Origin's icon list)."""
    currentIndexChanged = C.Signal(int)

    def __init__(self):
        super().__init__()
        self.setIconSize(C.QSize(56, 56)); self.setFixedWidth(104); self.setMovement(W.QListView.Static); self.setSpacing(2)
        self.setHorizontalScrollBarPolicy(C.Qt.ScrollBarAlwaysOff); self.setVerticalScrollBarPolicy(C.Qt.ScrollBarAlwaysOff)
        for t, k in SIDES:
            it = W.QListWidgetItem(side_icon(k), t.split("（")[0]); it.setData(C.Qt.UserRole, k); it.setTextAlignment(C.Qt.AlignHCenter | C.Qt.AlignVCenter)
            it.setSizeHint(C.QSize(96, 84)); self.addItem(it)
        self.setCurrentRow(0); self.currentRowChanged.connect(self.currentIndexChanged.emit)

    def currentData(self):
        it = self.currentItem(); return it.data(C.Qt.UserRole) if it else "bottom"

    def setCurrentIndex(self, i):
        self.setCurrentRow(i)


def _side_combo():
    return SideList()


class ColorButton(W.QPushButton):
    changed = C.Signal()

    def __init__(self, auto_text="Auto"):
        super().__init__(auto_text); self.auto_text = auto_text; self.color = None; self.setFixedHeight(26)
        m = W.QMenu(self); m.addAction(auto_text).triggered.connect(lambda: self.set(None, True))
        m.addAction("選擇顏色…").triggered.connect(self._pick); self.setMenu(m)

    def _pick(self):
        c = W.QColorDialog.getColor(G.QColor(self.color or "#000000"), self, "顏色")
        if c.isValid(): self.set(c.name(), True)

    def set(self, col, emit=False):
        self.color = col; self.setText(self.auto_text if col is None else col)
        self.setStyleSheet("" if col is None else f"QPushButton{{border-left:18px solid {col};}}")
        if emit: self.changed.emit()


class AxisDialog(W.QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win; self.fs = win.figstyle; self.key = "x"; self._loading = False; self._range_dirty = False
        self._tl_cur = "bottom"; self._lt_cur = "bottom"; self._prev_tab = None
        self.setWindowTitle("座標軸 Axis"); self.setModal(False); self.resize(760, 720)
        root = W.QVBoxLayout(self); body = W.QHBoxLayout(); root.addLayout(body, 1)
        self.sel = W.QListWidget(); self.sel.setFixedWidth(110); self.sel.addItems(["Horizontal\n（X 軸）", "Vertical\n（Y 軸）"]); self.sel.setCurrentRow(0)
        self.sel.currentRowChanged.connect(self._axis_changed); body.addWidget(self.sel)
        self.tabs = W.QTabWidget(); body.addWidget(self.tabs, 1)

        # ---------- Scale
        t = W.QWidget(); f = W.QFormLayout(t)
        self.lo = W.QLineEdit(); self.hi = W.QLineEdit()
        self.type = W.QComboBox(); self.type.addItem("Linear", False); self.type.addItem("Log10", True)
        self.rev = W.QCheckBox("Reverse（反向）")
        self.mj_type = W.QComboBox(); self.mj_type.addItems(["Auto", "By Increment"]); self.mj_val = W.QLineEdit()
        self.mn_type = W.QComboBox(); self.mn_type.addItems(["Auto", "By Counts"]); self.mn_cnt = W.QSpinBox(); self.mn_cnt.setRange(0, 50); self.mn_cnt.setValue(4)
        f.addRow("From", self.lo); f.addRow("To", self.hi); f.addRow("Type", self.type); f.addRow(self.rev)
        f.addRow(W.QLabel("<b>Major Ticks</b>")); f.addRow("Type", self.mj_type); f.addRow("Value", self.mj_val)
        f.addRow(W.QLabel("<b>Minor Ticks</b>")); f.addRow("Type", self.mn_type); f.addRow("Count", self.mn_cnt)
        nt = W.QLabel("Log10 需要 X>0 的資料；Log 軸下標線／文字標註的位置僅供參考。"); nt.setWordWrap(True); nt.setStyleSheet("color:#27506f;font-size:9pt"); f.addRow(nt)
        self.lo.textEdited.connect(self._dirty); self.hi.textEdited.connect(self._dirty)
        self.tabs.addTab(t, "Scale")

        # ---------- Tick Labels (per side)
        t = W.QWidget(); outer = W.QHBoxLayout(t); outer.setContentsMargins(0, 0, 0, 0); f = W.QFormLayout()
        self.tl_side = _side_combo(); outer.addWidget(self.tl_side); outer.addLayout(f, 1)
        self.tl_same = W.QCheckBox("Use same options for Bottom and Top (Left and Right)")
        self.tl_show = W.QCheckBox("Show"); self.tl_mode = W.QComboBox()
        for a, k in DISPLAY_MODES: self.tl_mode.addItem(a, k)
        self.tl_dec_on = W.QCheckBox("Set Decimal Places"); self.tl_dec = W.QSpinBox(); self.tl_dec.setRange(0, 12); self.tl_dec.setValue(2)
        self.tl_div = W.QLineEdit(); self.tl_div.setPlaceholderText("例如 1000"); self.tl_pre = W.QLineEdit(); self.tl_suf = W.QLineEdit(); self.tl_plus = W.QCheckBox("Plus Sign")
        self.tl_size = W.QSpinBox(); self.tl_size.setRange(4, 60)
        f.addRow(self.tl_same); f.addRow(self.tl_show); f.addRow("Display", self.tl_mode); f.addRow(self.tl_dec_on, self.tl_dec)
        f.addRow("Divide by Factor", self.tl_div); f.addRow("Prefix", self.tl_pre); f.addRow("Suffix", self.tl_suf); f.addRow(self.tl_plus)
        f.addRow("字體大小 (pt)", self.tl_size)
        nt = W.QLabel("字體大小：Bottom／Top 共用、Left／Right 共用。Top、Right 要有圖面外框才看得到：勾選「Show」時會自動開啟外框。")
        nt.setWordWrap(True); nt.setStyleSheet("color:#6e6e73;font-size:9pt"); f.addRow(nt)
        self.tl_side.currentIndexChanged.connect(self._tl_side_changed)
        self.tabs.addTab(t, "Tick Labels")

        # ---------- Title
        t = W.QWidget(); f = W.QFormLayout(t)
        self.ti_show = W.QCheckBox("Show"); self.ti_text = W.QLineEdit(); self.ti_color = ColorButton("Black（預設）")
        self.ti_font = W.QComboBox(); self.ti_font.setEditable(True)
        for a_, fam in FONTS: self.ti_font.addItem(a_, fam)
        self.ti_size = W.QSpinBox(); self.ti_size.setRange(0, 80); self.ti_size.setSpecialValueText("同全域設定"); self.ti_bold = W.QCheckBox("粗體")
        f.addRow(self.ti_show); f.addRow("Text", self.ti_text); f.addRow("Color", self.ti_color); f.addRow("Font", self.ti_font); f.addRow("Size", self.ti_size); f.addRow(self.ti_bold)
        self.ti_dx = W.QDoubleSpinBox(); self.ti_dy = W.QDoubleSpinBox()
        for sp in (self.ti_dx, self.ti_dy): sp.setRange(-2000, 2000); sp.setDecimals(1); sp.setSingleStep(1.0); sp.setSuffix(" px")
        rb = W.QPushButton("Reset position"); rb.clicked.connect(lambda: (self.ti_dx.setValue(0), self.ti_dy.setValue(0)))
        f.addRow("Offset X", self.ti_dx); f.addRow("Offset Y", self.ti_dy); f.addRow(rb)
        nt = W.QLabel("X 軸文字留空＝依資料自動命名；Y 軸文字即 Display 的「Y 軸單位」。軸標題也可以直接在圖上用滑鼠拖曳，或點一下標題後用方向鍵移動（Shift＝10 px，Esc 取消選取）。"); nt.setWordWrap(True); nt.setStyleSheet("color:#6e6e73;font-size:9pt"); f.addRow(nt)
        self.tabs.addTab(t, "Title")

        # ---------- Grids
        t = W.QWidget(); f = W.QFormLayout(t)
        self.gr_show = W.QCheckBox("顯示此軸的格線（Major）"); self.gr_alpha = W.QDoubleSpinBox(); self.gr_alpha.setRange(0.02, 1.0); self.gr_alpha.setSingleStep(0.05); self.gr_alpha.setValue(0.25)
        f.addRow(self.gr_show); f.addRow("Opacity (0–1)", self.gr_alpha); self.tabs.addTab(t, "Grids")

        # ---------- Line and Ticks (per side)
        t = W.QWidget(); f = W.QFormLayout(t)
        self.lt_side = _side_combo(); self.lt_same = W.QCheckBox("Use same options for Bottom and Top (Left and Right)")
        self.lt_master = W.QCheckBox("Show Line and Ticks"); self.lt_line = W.QCheckBox("Line → Show")
        self.ln_color = ColorButton("Black（預設）"); self.ln_w = W.QComboBox(); self.ln_w.addItems(THICKS)
        f.addRow(self.lt_same); f.addRow(self.lt_master); f.addRow(W.QLabel("<b>Line</b>")); f.addRow(self.lt_line)
        f.addRow("Color", self.ln_color); f.addRow("Thickness", self.ln_w)
        self.tk = {}
        for kind, title in (("major", "Major Ticks"), ("minor", "Minor Ticks")):
            f.addRow(W.QLabel(f"<b>{title}</b>"))
            d = {"style": W.QComboBox(), "length": W.QComboBox(), "color": ColorButton("Auto"), "width": W.QComboBox()}
            d["style"].addItems(STYLES); d["length"].setEditable(True); d["length"].addItems(LENGTHS); d["width"].addItems(THICKS)
            f.addRow("Style", d["style"]); f.addRow("Length", d["length"]); f.addRow("Color", d["color"]); f.addRow("Thickness", d["width"]); self.tk[kind] = d
        sa = W.QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(t); sa.setFrameShape(W.QFrame.NoFrame)
        host = W.QWidget(); hl = W.QHBoxLayout(host); hl.setContentsMargins(0, 0, 0, 0); hl.addWidget(self.lt_side); hl.addWidget(sa, 1)
        self.lt_side.currentIndexChanged.connect(self._lt_side_changed)
        self.tabs.addTab(host, "Line and Ticks")

        # ---------- Figure text + Frame (fixed sections, not collapsible)
        for sec, name in ((self.fs.sec_text, "Figure"), (self.fs.sec_frame, "Frame")):
            host = W.QWidget(); hl = W.QVBoxLayout(host); hl.setContentsMargins(4, 4, 4, 4); hl.addWidget(sec); hl.addStretch(1)
            sa = W.QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(host); sa.setFrameShape(W.QFrame.NoFrame); self.tabs.addTab(sa, name)
        self.tabs.currentChanged.connect(self._tab_changed)

        # ---------- buttons
        bb = W.QDialogButtonBox(W.QDialogButtonBox.Ok | W.QDialogButtonBox.Cancel | W.QDialogButtonBox.Apply); root.addWidget(bb)
        bb.button(W.QDialogButtonBox.Ok).clicked.connect(lambda: (self.apply(), self.accept()))
        bb.button(W.QDialogButtonBox.Apply).clicked.connect(self.apply)
        bb.button(W.QDialogButtonBox.Cancel).clicked.connect(self.reject)

    # ---------------- helpers
    def _tab_changed(self, i):
        if not self._loading and self._prev_tab is not None and self._prev_tab != i:
            self.apply(self.tabs.tabText(self._prev_tab))       # keep what was typed on the tab we are leaving
        self._prev_tab = i
        self.sel.setVisible(self.tabs.tabText(i) in ("Scale", "Title", "Grids"))
        if self.isVisible() or True: self.load()               # show the current state (other tabs may have changed it)

    def _dirty(self, *_):
        self._range_dirty = True

    def _axis_changed(self, row):
        if self._loading: return
        self.apply(); self.key = "x" if row == 0 else "y"; self.load()

    def _tl_side_changed(self, _):
        if self._loading: return
        self.apply(); self._tl_cur = self.tl_side.currentData(); self.load()

    def _lt_side_changed(self, _):
        if self._loading: return
        self.apply(); self._lt_cur = self.lt_side.currentData(); self.load()

    def open_dialog(self):
        self._snap = (copy.deepcopy(self.fs.st), self.win.pi.viewRange(), self.win.cb_invx.isChecked(), self.win.cb_yunit.currentText(), self.fs.xlabel.text())
        self._prev_tab = None; self._tab_changed(self.tabs.currentIndex()); self.show(); self.raise_(); self.activateWindow()

    def reject(self):                       # Cancel: put everything back as it was when the dialog opened
        st, vr, inv, yu, xl = self._snap
        self.fs.xlabel.blockSignals(True); self.fs.xlabel.setText(xl); self.fs.xlabel.blockSignals(False)
        self.fs.st = st; self.win.cb_invx.setChecked(inv); self.win.cb_yunit.setCurrentText(yu)
        self.fs.sync_widgets(); self.fs.apply()
        self.win.pi.setXRange(*vr[0], padding=0); self.win.pi.setYRange(*vr[1], padding=0)
        super().reject()

    # ---------------- state -> widgets
    def load(self):
        self._loading = True
        try:
            k = self.key; s = self.fs.st; a = s["axes"][k]; pi = self.win.pi; lg = bool(a["log"])
            (x0, x1), (y0, y1) = pi.viewRange(); lo, hi = (x0, x1) if k == "x" else (y0, y1)
            if lg: lo, hi = 10.0 ** lo, 10.0 ** hi
            self.lo.setText(_fmt(lo)); self.hi.setText(_fmt(hi)); self._range_dirty = False
            self.type.setCurrentIndex(1 if lg else 0)
            self.rev.setChecked(self.win.cb_invx.isChecked() if k == "x" else bool(a["reverse"]))
            self.mj_type.setCurrentIndex(1 if a["major_step"] else 0); self.mj_val.setText("" if not a["major_step"] else _fmt(a["major_step"]))
            self.mn_type.setCurrentIndex(1 if a["minor_count"] is not None else 0); self.mn_cnt.setValue(4 if a["minor_count"] is None else int(a["minor_count"]))
            # tick labels (side)
            side = self._tl_cur; self.tl_side.setCurrentIndex([v for _, v in SIDES].index(side)); lab = s["sides"][side]["lab"]
            self.tl_show.setChecked(bool(lab["show_values"])); self.tl_mode.setCurrentIndex(max(0, [m for _, m in DISPLAY_MODES].index(lab["mode"])))
            self.tl_dec_on.setChecked(lab["decimals"] is not None); self.tl_dec.setValue(2 if lab["decimals"] is None else int(lab["decimals"]))
            self.tl_div.setText("" if not lab["factor"] else _fmt(lab["factor"])); self.tl_pre.setText(lab["prefix"]); self.tl_suf.setText(lab["suffix"]); self.tl_plus.setChecked(bool(lab["plus"]))
            self.tl_size.setValue(s["x_tick_size" if side in ("bottom", "top") else "y_tick_size"])
            # title
            self.ti_show.setChecked(bool(a["label_show"]))
            self.ti_text.setText((self.fs.xlabel.text() if k == "x" else self.win.cb_yunit.currentText()))
            self.ti_dx.setValue(float(a.get("label_dx", 0.0))); self.ti_dy.setValue(float(a.get("label_dy", 0.0)))
            self.ti_color.set(a["label_color"]); fam = a["label_font"] or s["font"]
            self.ti_font.setCurrentText(next((t for t, f_ in FONTS if f_ == fam), fam)); self.ti_size.setValue(a["label_size"] or 0)
            self.ti_bold.setChecked(s["label_bold"] if a["label_bold"] is None else bool(a["label_bold"]))
            g = a["grid"]; self.gr_show.setChecked(self.win.cb_grid.isChecked() if g is None else bool(g)); self.gr_alpha.setValue(a["grid_alpha"])
            # line and ticks (side)
            side = self._lt_cur; sd = s["sides"][side]; self.lt_side.setCurrentIndex([v for _, v in SIDES].index(side))
            self.lt_master.setChecked(bool(sd["lt_show"])); self.lt_line.setChecked(bool(sd["line_show"]))
            self.ln_color.set(sd["line_color"]); self.ln_w.setCurrentText(str(sd["line_width"] or "Auto"))
            cfg = self.fs.eff_cfg(side, honor_show=False)
            for kind, d in self.tk.items():
                c = cfg[kind]; d["style"].setCurrentText(c["style"]); d["length"].setCurrentText(str(c["length"])); d["width"].setCurrentText(str(c["width"])); d["color"].set(c["color"])
        finally:
            self._loading = False

    # ---------------- widgets -> state -> plot
    def apply(self, tab=None):
        """Write the widgets of ONE tab (default: the visible one) into the state and re-draw. Writing only the visible tab means a
        stale widget on another tab can never overwrite something changed elsewhere (Figure / Frame tabs edit the state live)."""
        if self._loading: return
        tab = tab or self.tabs.tabText(self.tabs.currentIndex())
        k = self.key; s = self.fs.st; a = s["axes"][k]; w = self.win
        def num(t):
            try: return float(t.replace(",", "").strip())
            except ValueError: return None
        was_log = bool(a["log"]); rng = None
        if tab == "Scale":
            a["log"] = bool(self.type.currentData())
            a["major_step"] = num(self.mj_val.text()) if self.mj_type.currentIndex() == 1 and (num(self.mj_val.text()) or 0) > 0 else None
            a["minor_count"] = int(self.mn_cnt.value()) if self.mn_type.currentIndex() == 1 else None
            if k == "x": w.cb_invx.setChecked(self.rev.isChecked())
            else: a["reverse"] = self.rev.isChecked(); w.pi.invertY(self.rev.isChecked())
            if self._range_dirty or was_log != a["log"]: rng = (num(self.lo.text()), num(self.hi.text()))
        elif tab == "Tick Labels":
            ts = self._tl_cur; lab = s["sides"][ts]["lab"]
            lab["show_values"] = self.tl_show.isChecked(); lab["mode"] = self.tl_mode.currentData()
            lab["decimals"] = int(self.tl_dec.value()) if self.tl_dec_on.isChecked() else None
            f_ = num(self.tl_div.text()); lab["factor"] = f_ if f_ and f_ > 0 else None
            lab["prefix"] = self.tl_pre.text(); lab["suffix"] = self.tl_suf.text(); lab["plus"] = self.tl_plus.isChecked()
            s["x_tick_size" if ts in ("bottom", "top") else "y_tick_size"] = self.tl_size.value()
            if self.tl_same.isChecked(): s["sides"][PARTNER[ts]]["lab"] = dict(lab)
            for side in ((ts, PARTNER[ts]) if self.tl_same.isChecked() else (ts,)):        # a visible Top / Right needs the frame
                if side in ("top", "right") and s["sides"][side]["lab"]["show_values"]:
                    s["box"] = True; s["frame_" + side] = True
        elif tab == "Title":
            a["label_dx"] = self.ti_dx.value(); a["label_dy"] = self.ti_dy.value()
            a["label_show"] = self.ti_show.isChecked(); a["label_color"] = self.ti_color.color; a["label_size"] = self.ti_size.value() or None
            fam = self.ti_font.currentData() if self.ti_font.currentText() == self.ti_font.itemText(self.ti_font.currentIndex()) else self.ti_font.currentText().strip()
            a["label_font"] = fam or None if fam != s["font"] else None
            a["label_bold"] = self.ti_bold.isChecked() if self.ti_bold.isChecked() != s["label_bold"] else None
            if k == "x":
                self.fs.xlabel.blockSignals(True); self.fs.xlabel.setText(self.ti_text.text().strip()); self.fs.xlabel.blockSignals(False)
            elif self.ti_text.text().strip(): w.cb_yunit.setCurrentText(self.ti_text.text().strip())
        elif tab == "Grids":
            a["grid"] = self.gr_show.isChecked(); a["grid_alpha"] = self.gr_alpha.value()
        elif tab == "Line and Ticks":
            ls = self._lt_cur; sd = s["sides"][ls]
            sd["lt_show"] = self.lt_master.isChecked(); sd["line_show"] = self.lt_line.isChecked(); sd["line_color"] = self.ln_color.color
            sd["line_width"] = None if self.ln_w.currentText() == "Auto" else self.ln_w.currentText()
            for kind, d in self.tk.items():
                ln = d["length"].currentText().strip() or "Auto"
                try:
                    if ln != "Auto": float(ln)
                except ValueError: ln = "Auto"
                sd[kind] = {"style": d["style"].currentText(), "length": ln, "color": d["color"].color, "width": d["width"].currentText()}
            if self.lt_same.isChecked():
                p = s["sides"][PARTNER[ls]]
                for key in ("lt_show", "line_show", "line_color", "line_width"): p[key] = sd[key]
                p["major"] = dict(sd["major"]); p["minor"] = dict(sd["minor"])
        else:
            return                                              # Figure / Frame: live
        self.fs.sync_widgets(); self.fs.apply()
        if rng is not None:
            lo, hi = rng
            if lo is not None and hi is not None and hi > lo and not (a["log"] and lo <= 0):
                if a["log"]: lo, hi = float(np.log10(lo)), float(np.log10(hi))
                (w.pi.setXRange if k == "x" else w.pi.setYRange)(lo, hi, padding=0)
        self._range_dirty = False
        w.redraw()
