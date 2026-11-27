"""Figure formatting: title / axis-label / tick-label fonts, Major & Minor tick style (Out/In/Both/None, length, colour, thickness),
an independently styled box frame (top / right edges: on/off, thickness, colour, ticks), and the export aspect ratio. Layout follows the usual 'Major Ticks / Minor Ticks' panel."""
from __future__ import annotations
import copy
import numpy as np
import pyqtgraph as pg
import PySide6.QtWidgets as W
import PySide6.QtCore as C
import PySide6.QtGui as G
from . import theme as TH

STYLES = ["Out", "In", "Both", "None"]
LENGTHS = ["Auto", "2", "3", "4", "5", "6", "8", "10", "12", "16"]
THICKS = ["Auto", "0.5", "1", "1.5", "2", "3", "4"]
ASPECTS = [("5:4（同範例圖）", 5 / 4), ("6:5", 6 / 5), ("4:3", 4 / 3), ("3:2", 3 / 2), ("1:1", 1.0), ("16:9", 16 / 9), ("維持目前視窗比例", None)]
EXPORT_BASE_W = 720          # logical px width used for fixed-ratio export (fonts are laid out for this size)

DEFAULT_TICK = {"major": {"style": "Out", "length": "8", "color": None, "width": "Auto"},
                "minor": {"style": "Out", "length": "5", "color": None, "width": "Auto"}}


FONTS = [("Default (jf open-huninn)", ""), ("Arial", "Arial"), ("Times New Roman", "Times New Roman"), ("Calibri", "Calibri"), ("Helvetica", "Helvetica"),
         ("Courier New", "Courier New"), ("Microsoft JhengHei", "Microsoft JhengHei")]
SUP = str.maketrans("0123456789-+.", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺·")


def default_axis():
    """Per-axis display options of the Axis dialog (Scale / Tick Labels / Title / Grids)."""
    return {"show_values": True, "mode": "auto", "decimals": None, "factor": None, "prefix": "", "suffix": "", "plus": False,
            "major_step": None, "minor_count": None, "grid": None, "grid_alpha": 0.25,
            "label_dx": 0.0, "label_dy": 0.0, "label_show": True, "label_color": None, "label_size": None, "label_bold": None, "label_font": None, "reverse": None, "log": False}


def default_side(frame):
    """Per-side (Bottom / Top / Left / Right) line, tick and tick-label overrides of the Axis dialog. None = inherit."""
    return {"lt_show": True, "line_show": True, "line_color": None, "line_width": None, "major": None, "minor": None,
            "lab": {"show_values": not frame, "mode": "auto", "decimals": None, "factor": None, "prefix": "", "suffix": "", "plus": False}}


def default_state():
    return {"sides": {n: default_side(n in ("top", "right")) for n in ("bottom", "top", "left", "right")}, "font": "Arial", "legend_size": 20, "legend_font": "", "legend_bold": False, "axis_color": None, "axes": {"x": default_axis(), "y": default_axis()}, "title": "", "title_size": 14, "label_size": 24, "label_bold": True, "tick_bold": True, "box": True, "axis_width": "3",
            "frame_top": True, "frame_right": True, "frame_width": "3", "frame_color": None, "frame_ticks": False,
            "x_tick_size": 18, "y_tick_size": 18, "x": copy.deepcopy(DEFAULT_TICK), "y": copy.deepcopy(DEFAULT_TICK)}


class StyledAxis(pg.AxisItem):
    """AxisItem that draws its own tick marks (independent of the grid) with separate Major / Minor style."""
    label_dx = 0.0; label_dy = 0.0; _sel_box = None; on_label_moved = None; on_label_click = None      # defaults: resizeEvent can fire inside AxisItem.__init__

    def __init__(self, orientation, **kw):
        super().__init__(orientation, **kw)
        self.cfg = None; self._marks = []; self._base = 0.0
        self.major_step = None; self.minor_count = None; self.frozen_levels = None
        self.label_dx = 0.0; self.label_dy = 0.0; self.on_label_moved = None; self.on_label_click = None; self._sel_box = None
        self.setStyle(maxTickLevel=1)

    # ---- axis title: drag with the mouse / nudge with the arrow keys (the offset lives in the figure state)
    def resizeEvent(self, ev=None):
        super().resizeEvent(ev)
        if self.label is not None:
            if self.label_dx or self.label_dy: self.label.moveBy(self.label_dx, self.label_dy)
            self._update_sel_box()

    def _label_rect(self):
        return self.label.mapRectToParent(self.label.boundingRect()) if self.label is not None else C.QRectF()

    def _hits_label(self, pos):
        return self.label is not None and self.label.isVisible() and self._label_rect().adjusted(-3, -3, 3, 3).contains(pos)

    def set_label_selected(self, on):
        if on and self._sel_box is None:
            self._sel_box = W.QGraphicsRectItem(self); pen = G.QPen(G.QColor("#1d7cd4")); pen.setStyle(C.Qt.DashLine); pen.setCosmetic(True); self._sel_box.setPen(pen)
        if self._sel_box is not None: self._sel_box.setVisible(bool(on))
        self._update_sel_box()

    def _update_sel_box(self):
        if self._sel_box is not None and self._sel_box.isVisible(): self._sel_box.setRect(self._label_rect().adjusted(-3, -3, 3, 3))

    def nudge_label(self, dx, dy, finish=True):
        self.label_dx += dx; self.label_dy += dy; self.resizeEvent(None)
        if finish and self.on_label_moved: self.on_label_moved(self)

    def mouseDragEvent(self, ev):
        if ev.button() == C.Qt.LeftButton and (self._hits_label(ev.buttonDownPos()) or getattr(self, "_dragging_label", False)):
            ev.accept(); self._dragging_label = not ev.isFinish()
            if ev.isStart() and self.on_label_click: self.on_label_click(self)
            d = ev.pos() - ev.lastPos(); self.nudge_label(d.x(), d.y(), finish=ev.isFinish()); return
        super().mouseDragEvent(ev)

    def mouseClickEvent(self, ev):
        if ev.button() == C.Qt.LeftButton and self._hits_label(ev.pos()):
            ev.accept()
            if self.on_label_click: self.on_label_click(self)
            return
        super().mouseClickEvent(ev)

    def tickSpacing(self, minVal, maxVal, size):
        """Auto spacing, or: custom major increment, minor count (also with an automatic major), or levels frozen during an export
        (so a copied / exported figure shows exactly the ticks you see on screen, whatever its pixel size)."""
        if self.frozen_levels is not None: return self.frozen_levels
        lv = super().tickSpacing(minVal, maxVal, size)
        if not lv or (self.major_step is None and self.minor_count is None): return lv
        major = float(self.major_step) if self.major_step else lv[0][0]
        cnt = self.minor_count if self.minor_count is not None else 4
        out = [(major, 0)]
        if cnt > 0: out.append((major / (cnt + 1), 0))
        return out

    def boundingRect(self):
        """pyqtgraph drops a tick label that sticks out of the axis item (the first / last one with big fonts): allow room for half a label."""
        r = super().boundingRect()
        try:
            fm = G.QFontMetricsF(self.style.get("tickFont") or self.font())
            if self.orientation in ("bottom", "top"): e = fm.horizontalAdvance("00000") / 2 + 4; return r.adjusted(-e, 0, e, 0)
            e = fm.height() / 2 + 4; return r.adjusted(0, -e, 0, e)
        except Exception:
            return r

    def tickStrings(self, values, scale, spacing):
        f = getattr(self, "fmt", None)
        if not f or (f["mode"] == "auto" and not (f["factor"] or f["prefix"] or f["suffix"] or f["plus"] or f["decimals"] is not None)):
            return super().tickStrings(values, scale, spacing)
        out = []
        for v in values:
            if getattr(self, "logMode", False): v = 10.0 ** v
            v = v * scale / (f["factor"] or 1.0)
            d = f["decimals"]
            if f["mode"] == "pow10" and v > 0:
                e = int(round(np.log10(v))); txt = "10" + str(e).translate(SUP) if abs(v - 10.0 ** e) < 1e-9 * abs(v) else f"{v:g}"
            elif f["mode"] == "scientific": txt = f"{v:.{d if d is not None else 1}e}".replace("e+0", "e").replace("e-0", "e-").replace("e+", "e")
            elif f["mode"] == "decimal" or d is not None: txt = f"{v:.{d if d is not None else 6}f}" if d is not None else f"{v:.6f}".rstrip("0").rstrip(".")
            else: txt = f"{v:g}"
            if f["plus"] and v > 0: txt = "+" + txt
            out.append(f["prefix"] + txt + f["suffix"])
        return out

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
        if grid is False: return (spec[0], [], spec[2])
        thin = []
        for pen, a_, b_ in spec[1]:                  # grid lines keep a hairline whatever the axis line thickness is
            pen = G.QPen(pen); pen.setWidthF(1.0); pen.setCosmetic(True); thin.append((pen, a_, b_))
        return (spec[0], thin, spec[2])

    def drawPicture(self, p, axisSpec, tickSpecs, textSpecs):
        if self.cfg is not None:
            horiz = self.orientation in ("bottom", "top")
            sign = {"bottom": 1, "top": -1, "left": -1, "right": 1}[self.orientation]      # direction pointing away from the plot
            base_pen = axisSpec[0]; base_col = getattr(self, "tick_col", None) or base_pen.color()
            for pos, lvl in self._marks:
                kind = "major" if lvl == 0 else "minor"
                c = self.cfg[kind]
                if c["style"] == "None" or lvl > 1: continue
                L = self._len(c, kind)
                col = G.QColor(c["color"]) if c["color"] else G.QColor(base_col)
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
        sec = TH.Section("Figure 標題與字體", expanded=True); f = W.QFormLayout(); f.setContentsMargins(0, 0, 0, 0)
        self.title = W.QLineEdit(); self.title.setPlaceholderText("(none)")
        self.title_size = self._spin(4, 60, 14); self.label_size = self._spin(4, 60, 24)
        self.x_size = self._spin(4, 60, 18); self.y_size = self._spin(4, 60, 18)
        self.label_bold = W.QCheckBox("Bold axis titles"); self.tick_bold = W.QCheckBox("Bold tick labels")
        self.xlabel = W.QLineEdit(); self.xlabel.setPlaceholderText("Auto")
        self.axis_w = self._combo(THICKS)
        self.font_cb = W.QComboBox(); self.font_cb.setEditable(True)
        for t, fam in FONTS: self.font_cb.addItem(t, fam)
        for lab, w_ in (("Font", self.font_cb), ("Title", self.title), ("Title size (pt)", self.title_size), ("X axis title", self.xlabel), ("Axis title size (pt)", self.label_size),
                        ("X tick label size (pt)", self.x_size), ("Y tick label size (pt)", self.y_size)):
            f.addRow(lab, w_)
        f.addRow(self.label_bold); f.addRow(self.tick_bold); f.addRow("Axis line thickness", self.axis_w)
        w = W.QWidget(); w.setLayout(f); sec.add(w); self.sec_text = sec; sec.head.hide()          # hosted by the Axis dialog (fixed, not collapsible)
        # ---- legend (hosted in the Display tab: font / size / bold)
        sl = TH.Section("Legend 圖例字體", expanded=True); fl = W.QFormLayout(); fl.setContentsMargins(0, 0, 0, 0)
        self.legend_font = W.QComboBox(); self.legend_font.setEditable(True)
        self.legend_font.addItem("同圖面字型", "")
        for t, fam in FONTS[1:]: self.legend_font.addItem(t, fam)
        self.legend_size = self._spin(4, 80, 20); self.legend_bold = W.QCheckBox("粗體")
        fl.addRow("字型", self.legend_font); fl.addRow("大小 (pt)", self.legend_size); fl.addRow(self.legend_bold)
        wl = W.QWidget(); wl.setLayout(fl); sl.add(wl); lay.addWidget(sl)
        # ---- frame (box) : separate from the axis lines
        sf = TH.Section("Frame 外框", expanded=True); ff = W.QFormLayout(); ff.setContentsMargins(0, 0, 0, 0)
        self.box = W.QCheckBox("Show frame (top and right lines)")
        self.frame_top = W.QCheckBox("Top"); self.frame_right = W.QCheckBox("Right"); self.frame_top.setChecked(True); self.frame_right.setChecked(True)
        sides = W.QHBoxLayout(); sides.setContentsMargins(0, 0, 0, 0); sides.addWidget(self.frame_top); sides.addWidget(self.frame_right); sides.addStretch(1)
        sw = W.QWidget(); sw.setLayout(sides)
        self.frame_w = self._combo(THICKS); self.frame_ticks = W.QCheckBox("Ticks on frame")
        self.frame_c = {"_c": None, "color": None}
        fb = W.QPushButton("Auto"); fb.setFixedHeight(24); fm = W.QMenu(fb)
        fm.addAction("Auto (same as axes)").triggered.connect(lambda: self._set_color(self.frame_c, fb, None))
        fm.addAction("Choose color…").triggered.connect(lambda: self._pick_color(self.frame_c, fb)); fb.setMenu(fm); self.frame_c["color"] = fb
        ff.addRow(self.box); ff.addRow("Sides", sw); ff.addRow("Thickness", self.frame_w); ff.addRow("Color", fb); ff.addRow(self.frame_ticks)
        w = W.QWidget(); w.setLayout(ff); sf.add(w); self.sec_frame = sf; sf.head.hide()          # hosted by the Axis dialog (fixed, not collapsible)
        # ---- ticks
        st = TH.Section("Ticks 刻度線", expanded=False)
        top = W.QHBoxLayout(); self.axis_sel = W.QComboBox(); self.axis_sel.addItems(["X 軸", "Y 軸"])
        self.same = W.QCheckBox("X、Y 套用相同設定"); self.same.setChecked(True)
        top.addWidget(self.axis_sel); top.addWidget(self.same, 1); tw = W.QWidget(); tw.setLayout(top); st.add(tw)
        self.maj = self._tick_box(st, "Major Ticks"); self.mnr = self._tick_box(st, "Minor Ticks")
        self.sec_ticks = st                    # kept only as the state holder; its UI lives in the Axis dialog (Line and Ticks tab)
        # ---- export
        se = TH.Section("Export 匯出圖片比例", expanded=False); f2 = W.QFormLayout(); f2.setContentsMargins(0, 0, 0, 0)
        self.aspect = W.QComboBox(); [self.aspect.addItem(a, r) for a, r in ASPECTS]
        self.png_w = W.QSpinBox(); self.png_w.setRange(400, 12000); self.png_w.setValue(2400); self.png_w.setSuffix(" px")
        self.transparent = W.QCheckBox("透明背景（複製／匯出圖片）"); self.transparent.setChecked(True)
        f2.addRow("長寬比", self.aspect); f2.addRow("PNG 寬度", self.png_w); f2.addRow(self.transparent)
        nt = W.QLabel("匯出（PNG／SVG／PDF）時圖面會依此比例重新排版，與視窗大小無關；字體大小以上方設定為準。")
        nt.setWordWrap(True); nt.setStyleSheet("color:#6e6e73;font-size:9pt")
        w = W.QWidget(); w.setLayout(f2); se.add(w); se.add(nt); lay.addWidget(se)
        # ---- signals
        for w_ in (self.title,): w_.textChanged.connect(self._changed)
        self.xlabel.editingFinished.connect(self._changed); self.font_cb.currentTextChanged.connect(self._changed)
        self.legend_font.currentTextChanged.connect(self._changed); self.legend_bold.toggled.connect(self._changed)
        for w_ in (self.title_size, self.label_size, self.x_size, self.y_size, self.legend_size): w_.valueChanged.connect(self._changed)
        for w_ in (self.label_bold, self.tick_bold, self.box, self.frame_top, self.frame_right, self.frame_ticks): w_.toggled.connect(self._changed)
        self.axis_w.currentTextChanged.connect(self._changed); self.frame_w.currentTextChanged.connect(self._changed)
        self.axis_sel.currentIndexChanged.connect(self._load_ticks)
        self.same.toggled.connect(self._changed)
        for name in ("bottom", "left"):
            ax = self.win.pi.getAxis(name); ax.on_label_moved = self._label_moved; ax.on_label_click = lambda a_: self.win.select_axis_label(a_)
        self._load_ticks(); self.sync_widgets(); self.apply()

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
        m.addAction("Choose color…").triggered.connect(lambda: self._pick_color(d, btn)); btn.setMenu(m); d["color"] = btn
        f.addRow("Style", d["style"]); f.addRow("Length", d["length"]); f.addRow("Color", btn); f.addRow("Thickness", d["width"])
        w = W.QWidget(); w.setLayout(f); sec.add(w)
        d["style"].currentTextChanged.connect(self._changed); d["length"].currentTextChanged.connect(self._changed); d["width"].currentTextChanged.connect(self._changed)
        return d

    def _pick_color(self, d, btn):
        c = W.QColorDialog.getColor(G.QColor(d["_c"] or "#000000"), self, "刻度顏色")
        if c.isValid(): self._set_color(d, btn, c.name())

    def _set_color_quiet(self, d, col):
        btn = d["color"]; d["_c"] = col; btn.setText("Auto" if col is None else col)
        btn.setStyleSheet("" if col is None else f"QPushButton{{border-left:16px solid {col};}}")

    def _set_color(self, d, btn, col):
        d["_c"] = col; btn.setText("Auto" if col is None else col)
        btn.setStyleSheet("" if col is None else f"QPushButton{{border-left:16px solid {col};}}"); self._changed()

    def eff_cfg(self, name, honor_show=True):
        """Effective tick configuration of one side: global base (x / y) -> frame rule -> the side's own override."""
        s = self.st; frame = name in ("top", "right")
        cfg = copy.deepcopy(s["x" if name in ("bottom", "top") else "y"])
        if frame and not s["frame_ticks"]:
            for k in cfg: cfg[k]["style"] = "None"
        sd = s["sides"][name]
        for k in ("major", "minor"):
            if sd[k] is not None: cfg[k] = dict(sd[k])
        if honor_show and not sd["lt_show"]:
            for k in cfg: cfg[k]["style"] = "None"
        return cfg

    def _label_moved(self, ax):
        key = "x" if ax.orientation == "bottom" else "y"; a = self.st["axes"][key]
        a["label_dx"], a["label_dy"] = round(ax.label_dx, 2), round(ax.label_dy, 2)
        dlg = getattr(self.win, "axis_dialog", None)
        if dlg is not None and dlg.isVisible(): dlg.load()

    def style_legend(self, scale=1.0):
        """Legend text: font (own, else the figure font), size and bold from the Display tab. `scale` > 1 only while exporting a raster image
        (the legend ignores the scene scaling, so its text is enlarged by hand to keep the on-screen look)."""
        st = self.st; fam = st.get("legend_font") or st.get("font"); pt = max(1, int(round(st.get("legend_size", 20) * scale))); bold = bool(st.get("legend_bold")); lg = self.win.legend
        try: lg.setLabelTextSize(f"{pt}pt")
        except Exception: pass
        try:
            for _smp, lab in lg.items:
                f = G.QFont(fam) if fam else G.QFont(lab.item.font()); f.setBold(bold); lab.item.setFont(f)
                try: lab.setText(lab.text, size=f"{pt}pt", bold=bold)
                except Exception: pass
            lg.updateSize()
        except Exception: pass

    def sync_widgets(self):
        """Refresh this tab's widgets from self.st (after the Axis dialog changed it) without re-triggering _changed."""
        s = self.st; self._loading = True
        try:
            self.font_cb.setCurrentText(next((t for t, f in FONTS if f == s["font"]), s["font"]))
            self.axis_w.setCurrentText(str(s["axis_width"]))
            self.title.setText(s["title"]); self.title_size.setValue(s["title_size"]); self.label_size.setValue(s["label_size"])
            self.x_size.setValue(s["x_tick_size"]); self.y_size.setValue(s["y_tick_size"]); self.legend_size.setValue(s["legend_size"]); self.legend_bold.setChecked(s["legend_bold"])
            lf = s["legend_font"]; self.legend_font.setCurrentText("同圖面字型" if not lf else next((t for t, f in FONTS if f == lf), lf))
            self.label_bold.setChecked(s["label_bold"]); self.tick_bold.setChecked(s["tick_bold"]); self.box.setChecked(s["box"])
            self.frame_top.setChecked(s["frame_top"]); self.frame_right.setChecked(s["frame_right"]); self.frame_ticks.setChecked(s["frame_ticks"])
            self.frame_w.setCurrentText(str(s["frame_width"])); self._set_color_quiet(self.frame_c, s["frame_color"])
        finally: self._loading = False
        self._load_ticks()

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
        s["font"] = self.font_cb.currentData() if self.font_cb.currentText() == self.font_cb.itemText(self.font_cb.currentIndex()) else self.font_cb.currentText().strip()
        s["title"] = self.title.text(); s["title_size"] = self.title_size.value(); s["label_size"] = self.label_size.value()
        s["x_tick_size"] = self.x_size.value(); s["y_tick_size"] = self.y_size.value(); s["legend_size"] = self.legend_size.value(); s["legend_bold"] = self.legend_bold.isChecked()
        s["legend_font"] = self.legend_font.currentData() if self.legend_font.currentText() == self.legend_font.itemText(self.legend_font.currentIndex()) else self.legend_font.currentText().strip()
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
            ax = pi.getAxis(name); xaxis = name in ("bottom", "top"); sd = s["sides"][name]; frame = name in ("top", "right")
            f = G.QFont(self.win.font()); f.setPointSize(s["x_tick_size"] if xaxis else s["y_tick_size"]); f.setBold(s["tick_bold"])
            if s["font"]: f.setFamily(s["font"])
            ax.setTickFont(f)
            if hasattr(ax, "set_cfg"): ax.set_cfg(self.eff_cfg(name))
            wsel = sd["line_width"] if sd["line_width"] not in (None, "Auto") else (s["frame_width"] if frame and s["frame_width"] != "Auto" else s["axis_width"])
            cur = ax.pen()
            if cur.color().alpha() > 0: ax._base_col = G.QColor(cur.color())
            base = getattr(ax, "_base_col", None) or G.QColor(cur.color())
            col = G.QColor(sd["line_color"] or ((s["frame_color"] or s["axis_color"]) if frame else s["axis_color"]) or base)
            ax.tick_col = G.QColor(col)
            pen = G.QPen(cur); pen.setWidthF(float(wsel) if wsel not in (None, "Auto") else 1.0); pen.setCosmetic(False)
            if not (sd["lt_show"] and sd["line_show"]): col.setAlpha(0)
            pen.setColor(col); ax.setPen(pen)
            ax.fmt = sd["lab"]; ax.setStyle(showValues=bool(sd["lab"]["show_values"])); ax.picture = None; ax.update()
        style = {"font-size": f"{s['label_size']}pt", "font-weight": "bold" if s["label_bold"] else "normal"}
        xt = self.xlabel.text().strip()
        if xt: self.win.x_label_override = xt
        else: self.win.x_label_override = None
        if s["font"]: style["font-family"] = s["font"]
        for key, name in (("x", "bottom"), ("y", "left")):
            ax = pi.getAxis(name); a = s["axes"][key]; st_ = dict(style)
            if a["label_size"]: st_["font-size"] = f"{a['label_size']}pt"
            if a["label_bold"] is not None: st_["font-weight"] = "bold" if a["label_bold"] else "normal"
            if a["label_font"]: st_["font-family"] = a["label_font"]
            if a["label_color"]: st_["color"] = a["label_color"]
            ax.labelStyle = dict(st_)
            text = (xt or self.win.default_xlabel()) if key == "x" else ax.labelText
            ax.setLabel(text, None if key == "x" else ax.labelUnits, **st_)
            ax.showLabel(bool(a["label_show"]))
            ax.label_dx = float(a.get("label_dx", 0.0)); ax.label_dy = float(a.get("label_dy", 0.0)); ax.resizeEvent(None)
            lg = bool(a["log"])
            for nm in ((name, "top") if key == "x" else (name, "right")):         # the frame axes follow their partner
                axx = pi.getAxis(nm)
                axx.major_step = float(a["major_step"]) if (a["major_step"] and not lg) else None
                axx.minor_count = int(a["minor_count"]) if (a["minor_count"] is not None and not lg) else None
                axx.picture = None; axx.update()
        if s["font"]:
            try: pi.titleLabel.item.setFont(G.QFont(s["font"]))
            except Exception: pass
        self.style_legend()
        sb_ = getattr(self.win, "scalebar", None)
        if sb_ is not None: sb_.refresh()                  # XY Scale follows the major tick settings
        ax_, ay_ = s["axes"]["x"], s["axes"]["y"]
        if ax_["log"] != getattr(self, "_log_x", False) or ay_["log"] != getattr(self, "_log_y", False):
            self._log_x, self._log_y = bool(ax_["log"]), bool(ay_["log"]); pi.setLogMode(x=self._log_x, y=self._log_y); pi.autoRange()
        for key, inv in (("x", pi.invertX), ("y", pi.invertY)):
            r = s["axes"][key]["reverse"]
            if r is not None: inv(bool(r))
        gx, gy = s["axes"]["x"]["grid"], s["axes"]["y"]["grid"]
        if gx is not None or gy is not None:
            cur = self.win.cb_grid.isChecked()
            pi.showGrid(x=cur if gx is None else gx, y=cur if gy is None else gy, alpha=s["axes"]["x"]["grid_alpha"])
        pi.showAxis("top", bool(s["box"] and s["frame_top"])); pi.showAxis("right", bool(s["box"] and s["frame_right"]))
        for name in ("top", "right"):
            pi.getAxis(name).setLabel(None)
