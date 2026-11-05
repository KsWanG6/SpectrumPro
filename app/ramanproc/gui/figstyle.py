"""Figure formatting: title / axis-label / tick-label fonts, Major & Minor tick style (Out/In/Both/None, length, colour, thickness),
an independently styled box frame (top / right edges: on/off, thickness, colour, ticks), and the export aspect ratio. Layout follows the usual 'Major Ticks / Minor Ticks' panel."""
from __future__ import annotations
import copy
import pyqtgraph as pg
import PySide6.QtWidgets as W
import PySide6.QtCore as C
import PySide6.QtGui as G
from . import theme as TH

STYLES = ["Out", "In", "Both", "None"]
LENGTHS = ["Auto", "2", "3", "4", "5", "6", "8", "10", "12", "16"]
THICKS = ["Auto", "0.5", "1", "1.5", "2", "3", "4"]
ASPECTS = [("6:5（同範例圖）", 6 / 5), ("4:3", 4 / 3), ("3:2", 3 / 2), ("1:1", 1.0), ("16:9", 16 / 9), ("維持目前視窗比例", None)]
EXPORT_BASE_W = 720          # logical px width used for fixed-ratio export (fonts are laid out for this size)

DEFAULT_TICK = {"major": {"style": "Out", "length": "6", "color": None, "width": "Auto"},
                "minor": {"style": "None", "length": "Auto", "color": None, "width": "Auto"}}


def default_state():
    return {"title": "", "title_size": 14, "label_size": 12, "label_bold": False, "tick_bold": False, "box": False, "axis_width": "Auto",
            "frame_top": True, "frame_right": True, "frame_width": "Auto", "frame_color": None, "frame_ticks": True,
            "x_tick_size": 10, "y_tick_size": 10, "x": copy.deepcopy(DEFAULT_TICK), "y": copy.deepcopy(DEFAULT_TICK)}


class StyledAxis(pg.AxisItem):
    """AxisItem that draws its own tick marks (independent of the grid) with separate Major / Minor style."""

    def __init__(self, orientation, **kw):
        super().__init__(orientation, **kw)
        self.cfg = None; self._marks = []; self._base = 0.0
        self.setStyle(maxTickLevel=1)

    def setGrid(self, grid):
        """Only the bottom / left axes draw grid lines. The top / right axes are the frame: their own grid would duplicate the
        lines (double opacity) and take the frame colour."""
        super().setGrid(False if self.orientation in ("top", "right") else grid)

    def set_cfg(self, cfg):
        """cfg: {'major': {...}, 'minor': {...}} or None for pyqtgraph's own ticks."""
        self.cfg = cfg
        if cfg is not None:
            out = 0
            for k in ("major", "minor"):
                c = cfg[k]
                if c["style"] in ("Out", "Both"): out = max(out, self._len(c, k))
            self.setStyle(tickLength=int(round(out)))            # reserves space for outward ticks / pushes the labels
        self.picture = None; self.update()

    def _len(self, c, kind):
        major = self.cfg["major"]["length"]; major = 6.0 if major == "Auto" else float(major)
        if c["length"] == "Auto": return major if kind == "major" else major * 0.5
        return float(c["length"])

    def generateDrawSpecs(self, p):
        if self.cfg is None: return super().generateDrawSpecs(p)
        grid = self.grid; real_len = self.style["tickLength"]
        try:                                         # pass 1: tick positions with a probe length so the level can be decoded from the length
            self.grid = False; self.style["tickLength"] = -100
            probe = super().generateDrawSpecs(p)
        finally:
            self.grid = grid; self.style["tickLength"] = real_len
        spec = super().generateDrawSpecs(p)
        if spec is None or probe is None: return spec
        horiz = self.orientation in ("bottom", "top")
        self._marks = []
        for pen, a, b in probe[1]:
            ln = (b - a).manhattanLength() if hasattr(b - a, "manhattanLength") else abs(b[0] - a[0]) + abs(b[1] - a[1])
            lvl = int(round((100.0 / max(ln, 1e-6) - 1) / 0.5))
            self._marks.append(((a.x() if horiz else a.y()), lvl))
        self._base = spec[0][1].y() if horiz else spec[0][1].x()
        return (spec[0], spec[1] if grid is not False else [], spec[2])

    def drawPicture(self, p, axisSpec, tickSpecs, textSpecs):
        if self.cfg is not None:
            horiz = self.orientation in ("bottom", "top")
            sign = {"bottom": 1, "top": -1, "left": -1, "right": 1}[self.orientation]      # direction pointing away from the plot
            base_pen = axisSpec[0]
            for pos, lvl in self._marks:
                kind = "major" if lvl == 0 else "minor"
                c = self.cfg[kind]
                if c["style"] == "None" or lvl > 1: continue
                L = self._len(c, kind)
                col = G.QColor(c["color"]) if c["color"] else G.QColor(base_pen.color())
                w = float(c["width"]) if c["width"] not in (None, "Auto") else max(base_pen.widthF(), 1.0)
                pen = G.QPen(col); pen.setWidthF(w); pen.setCosmetic(False); pen.setCapStyle(C.Qt.FlatCap)
                p.setPen(pen)
                lo = -L if c["style"] in ("In", "Both") else 0.0
                hi = L if c["style"] in ("Out", "Both") else 0.0
                a = self._base + sign * lo; b = self._base + sign * hi
                if horiz: p.drawLine(C.QPointF(pos, a), C.QPointF(pos, b))
                else: p.drawLine(C.QPointF(a, pos), C.QPointF(b, pos))
        super().drawPicture(p, axisSpec, tickSpecs, textSpecs)


class FigureStyleSection(W.QWidget):
    def __init__(self, win):
        super().__init__(); self.win = win; self.st = default_state(); self._loading = False
        lay = W.QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
        # ---- text
        sec = TH.Section("Figure 標題與字體", expanded=False); f = W.QFormLayout(); f.setContentsMargins(0, 0, 0, 0)
        self.title = W.QLineEdit(); self.title.setPlaceholderText("（無標題）")
        self.title_size = self._spin(4, 60, 14); self.label_size = self._spin(4, 60, 12)
        self.x_size = self._spin(4, 60, 10); self.y_size = self._spin(4, 60, 10)
        self.label_bold = W.QCheckBox("軸標題粗體"); self.tick_bold = W.QCheckBox("刻度數字粗體")
        self.xlabel = W.QLineEdit(); self.xlabel.setPlaceholderText("自動")
        self.axis_w = self._combo(THICKS)
        for lab, w_ in (("標題文字", self.title), ("標題大小 (pt)", self.title_size), ("X 軸標題文字", self.xlabel), ("軸標題大小 (pt)", self.label_size),
                        ("X 刻度字體大小 (pt)", self.x_size), ("Y 刻度字體大小 (pt)", self.y_size)):
            f.addRow(lab, w_)
        f.addRow(self.label_bold); f.addRow(self.tick_bold); f.addRow("X/Y 軸線粗細", self.axis_w)
        w = W.QWidget(); w.setLayout(f); sec.add(w); lay.addWidget(sec)
        # ---- frame (box) : separate from the axis lines
        sf = TH.Section("Frame 外框", expanded=False); ff = W.QFormLayout(); ff.setContentsMargins(0, 0, 0, 0)
        self.box = W.QCheckBox("顯示外框（上、右邊線，與 X/Y 軸圍成方框）")
        self.frame_top = W.QCheckBox("上邊"); self.frame_right = W.QCheckBox("右邊"); self.frame_top.setChecked(True); self.frame_right.setChecked(True)
        sides = W.QHBoxLayout(); sides.setContentsMargins(0, 0, 0, 0); sides.addWidget(self.frame_top); sides.addWidget(self.frame_right); sides.addStretch(1)
        sw = W.QWidget(); sw.setLayout(sides)
        self.frame_w = self._combo(THICKS); self.frame_ticks = W.QCheckBox("外框上顯示刻度線"); self.frame_ticks.setChecked(True)
        self.frame_c = {"_c": None, "color": None}
        fb = W.QPushButton("Auto"); fb.setFixedHeight(24); fm = W.QMenu(fb)
        fm.addAction("Auto（同軸線）").triggered.connect(lambda: self._set_color(self.frame_c, fb, None))
        fm.addAction("選擇顏色…").triggered.connect(lambda: self._pick_color(self.frame_c, fb)); fb.setMenu(fm); self.frame_c["color"] = fb
        ff.addRow(self.box); ff.addRow("邊", sw); ff.addRow("Thickness", self.frame_w); ff.addRow("Color", fb); ff.addRow(self.frame_ticks)
        w = W.QWidget(); w.setLayout(ff); sf.add(w); lay.addWidget(sf)
        # ---- ticks
        st = TH.Section("Ticks 刻度線", expanded=False)
        top = W.QHBoxLayout(); self.axis_sel = W.QComboBox(); self.axis_sel.addItems(["X 軸", "Y 軸"])
        self.same = W.QCheckBox("X、Y 套用相同設定"); self.same.setChecked(True)
        top.addWidget(self.axis_sel); top.addWidget(self.same, 1); tw = W.QWidget(); tw.setLayout(top); st.add(tw)
        self.maj = self._tick_box(st, "Major Ticks"); self.mnr = self._tick_box(st, "Minor Ticks")
        lay.addWidget(st)
        # ---- export
        se = TH.Section("Export 匯出圖片比例", expanded=False); f2 = W.QFormLayout(); f2.setContentsMargins(0, 0, 0, 0)
        self.aspect = W.QComboBox(); [self.aspect.addItem(a, r) for a, r in ASPECTS]
        self.png_w = W.QSpinBox(); self.png_w.setRange(400, 12000); self.png_w.setValue(2400); self.png_w.setSuffix(" px")
        f2.addRow("長寬比", self.aspect); f2.addRow("PNG 寬度", self.png_w)
        nt = W.QLabel("匯出（PNG／SVG／PDF）時圖面會依此比例重新排版，與視窗大小無關；字體大小以上方設定為準。")
        nt.setWordWrap(True); nt.setStyleSheet("color:#6e6e73;font-size:9pt")
        w = W.QWidget(); w.setLayout(f2); se.add(w); se.add(nt); lay.addWidget(se)
        # ---- signals
        for w_ in (self.title,): w_.textChanged.connect(self._changed)
        self.xlabel.editingFinished.connect(self._changed)
        for w_ in (self.title_size, self.label_size, self.x_size, self.y_size): w_.valueChanged.connect(self._changed)
        for w_ in (self.label_bold, self.tick_bold, self.box, self.frame_top, self.frame_right, self.frame_ticks): w_.toggled.connect(self._changed)
        self.axis_w.currentTextChanged.connect(self._changed); self.frame_w.currentTextChanged.connect(self._changed)
        self.axis_sel.currentIndexChanged.connect(self._load_ticks)
        self.same.toggled.connect(self._changed)
        self._load_ticks(); self.apply()

    # ---- widgets
    def _spin(self, lo, hi, v):
        s = W.QSpinBox(); s.setRange(lo, hi); s.setValue(v); return s

    def _combo(self, items):
        c = W.QComboBox(); c.addItems(items); c.setEditable(False); return c

    def _tick_box(self, sec, title):
        sec.add(W.QLabel(f"<b>{title}</b>")); f = W.QFormLayout(); f.setContentsMargins(0, 0, 0, 0)
        d = {"style": self._combo(STYLES), "length": self._combo(LENGTHS), "width": self._combo(THICKS), "color": None, "_c": None}
        d["length"].setEditable(True)
        btn = W.QPushButton("Auto"); btn.setFixedHeight(24); m = W.QMenu(btn)
        m.addAction("Auto").triggered.connect(lambda: self._set_color(d, btn, None))
        m.addAction("選擇顏色…").triggered.connect(lambda: self._pick_color(d, btn)); btn.setMenu(m); d["color"] = btn
        f.addRow("Style", d["style"]); f.addRow("Length", d["length"]); f.addRow("Color", btn); f.addRow("Thickness", d["width"])
        w = W.QWidget(); w.setLayout(f); sec.add(w)
        d["style"].currentTextChanged.connect(self._changed); d["length"].currentTextChanged.connect(self._changed); d["width"].currentTextChanged.connect(self._changed)
        return d

    def _pick_color(self, d, btn):
        c = W.QColorDialog.getColor(G.QColor(d["_c"] or "#000000"), self, "刻度顏色")
        if c.isValid(): self._set_color(d, btn, c.name())

    def _set_color(self, d, btn, col):
        d["_c"] = col; btn.setText("Auto" if col is None else col)
        btn.setStyleSheet("" if col is None else f"QPushButton{{border-left:16px solid {col};}}"); self._changed()

    # ---- state <-> widgets
    def _load_ticks(self, *_):
        key = "x" if self.axis_sel.currentIndex() == 0 else "y"; self._loading = True
        for d, k in ((self.maj, "major"), (self.mnr, "minor")):
            c = self.st[key][k]
            d["style"].setCurrentText(c["style"]); d["length"].setCurrentText(str(c["length"])); d["width"].setCurrentText(str(c["width"]))
            d["_c"] = c["color"]; d["color"].setText("Auto" if c["color"] is None else c["color"])
            d["color"].setStyleSheet("" if c["color"] is None else f"QPushButton{{border-left:16px solid {c['color']};}}")
        self._loading = False

    def _read(self):
        if self._loading: return
        s = self.st
        s["title"] = self.title.text(); s["title_size"] = self.title_size.value(); s["label_size"] = self.label_size.value()
        s["x_tick_size"] = self.x_size.value(); s["y_tick_size"] = self.y_size.value()
        s["label_bold"] = self.label_bold.isChecked(); s["tick_bold"] = self.tick_bold.isChecked(); s["box"] = self.box.isChecked(); s["axis_width"] = self.axis_w.currentText()
        s["frame_top"] = self.frame_top.isChecked(); s["frame_right"] = self.frame_right.isChecked(); s["frame_ticks"] = self.frame_ticks.isChecked()
        s["frame_width"] = self.frame_w.currentText(); s["frame_color"] = self.frame_c["_c"]
        key = "x" if self.axis_sel.currentIndex() == 0 else "y"
        for d, k in ((self.maj, "major"), (self.mnr, "minor")):
            s[key][k] = {"style": d["style"].currentText(), "length": d["length"].currentText().strip() or "Auto", "color": d["_c"], "width": d["width"].currentText()}
            try:
                if s[key][k]["length"] != "Auto": float(s[key][k]["length"])
            except ValueError: s[key][k]["length"] = "Auto"
        if self.same.isChecked(): s["y" if key == "x" else "x"] = copy.deepcopy(s[key])

    def _changed(self, *_):
        if self._loading: return
        self._read(); self.apply()

    # ---- apply to the plot
    def apply(self):
        s = self.st; pi = self.win.pi
        pi.setTitle(s["title"] or None, size=f"{s['title_size']}pt", bold=s["label_bold"]) if s["title"] else pi.setTitle(None)
        for name in ("bottom", "top", "left", "right"):
            ax = pi.getAxis(name); xaxis = name in ("bottom", "top")
            sz = s["x_tick_size"] if xaxis else s["y_tick_size"]
            f = G.QFont(self.win.font()); f.setPointSize(sz); f.setBold(s["tick_bold"]); ax.setTickFont(f)
            frame = name in ("top", "right")
            cfg = s["x" if xaxis else "y"]
            if frame and not s["frame_ticks"]: cfg = {k: dict(v, style="None") for k, v in cfg.items()}
            if hasattr(ax, "set_cfg"): ax.set_cfg(cfg)
            wsel = s["frame_width"] if frame and s["frame_width"] != "Auto" else s["axis_width"]
            pen = G.QPen(ax.pen()); pen.setWidthF(float(wsel) if wsel != "Auto" else 1.0); pen.setCosmetic(False)
            if frame: pen.setColor(G.QColor(s["frame_color"]) if s["frame_color"] else G.QColor(pi.getAxis("bottom").pen().color()))
            ax.setPen(pen)
        style = {"font-size": f"{s['label_size']}pt", "font-weight": "bold" if s["label_bold"] else "normal"}
        xt = self.xlabel.text().strip()
        if xt: self.win.x_label_override = xt
        else: self.win.x_label_override = None
        for name in ("bottom", "left"):
            ax = pi.getAxis(name); ax.labelStyle = dict(style)
            ax.setLabel(ax.labelText, ax.labelUnits, **style)
        if xt: pi.getAxis("bottom").setLabel(xt, None, **style)
        else: pi.getAxis("bottom").setLabel(self.win.default_xlabel(), None, **style)
        pi.showAxis("top", bool(s["box"] and s["frame_top"])); pi.showAxis("right", bool(s["box"] and s["frame_right"]))
        for name in ("top", "right"):
            pi.getAxis(name).setStyle(showValues=False); pi.getAxis(name).setLabel(None)
