"""XY Scale bar (Origin "Add XY Scale"): an L-shaped scale object drawn over the plot.

* length is in data units; blank / "Auto" / "X3" / "Y3" = linked to the axis major-tick increment (Figure/axis settings)
* title "$(Scale)" is replaced by the length (so it follows the major tick setting)
* drag with the mouse to move, right-click for Properties / Delete
"""
import copy
import pyqtgraph as pg
from PySide6 import QtWidgets as W, QtCore as C, QtGui as G

POS_X = ("Bottom", "Top")
POS_Y = ("Left", "Right")


def default_side(key):
    return {"pos": "Bottom" if key == "x" else "Left", "length": "", "width": 1.0, "title": "$(Scale)", "rot": 0.0,
            "color": None, "dx": 0.0, "dy": 0.0, "cap": 7.0}


def default_state():
    return {"mode": "XY Scales", "color": "#000000", "font": "Arial", "size": 14, "bold": False, "italic": False, "underline": False,
            "x": default_side("x"), "y": default_side("y"), "fx": 0.08, "fy": 0.82}


def fmt_value(v):
    return f"{v:.6g}"


class ScaleBar(pg.GraphicsObject):
    GAP = 3.0

    def __init__(self, win, state=None):
        super().__init__()
        self.win = win; self.st = state or default_state()
        self.vb = win.pi.vb
        self.setParentItem(self.vb); self.setZValue(200)
        self._rects = []
        self.vb.sigRangeChanged.connect(self.refresh); self.vb.sigResized.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------ geometry
    def major(self, key):
        """Major-tick increment of axis key ('x'/'y'): the value set in the axis dialog, else what the axis shows now."""
        try:
            a = self.win.figstyle.st["axes"][key]
            if a.get("major_step") and not a.get("log"): return abs(float(a["major_step"]))
        except Exception: pass
        try:
            ax = self.win.pi.getAxis("bottom" if key == "x" else "left"); lo, hi = ax.range
            size = float(ax.width() if key == "x" else ax.height())
            return abs(float(ax.tickSpacing(lo, hi, max(size, 50.0))[0][0]))
        except Exception:
            r = self.vb.viewRange()[0 if key == "x" else 1]; return abs(r[1] - r[0]) / 5.0

    def length(self, key):
        t = str(self.st[key]["length"]).strip()
        if t == "" or t.lower() in ("auto", "x3", "y3"): return self.major(key)
        try: return abs(float(t))
        except ValueError: return self.major(key)

    def linked(self, key):
        t = str(self.st[key]["length"]).strip().lower()
        return t in ("", "auto", "x3", "y3")

    def title(self, key):
        return str(self.st[key]["title"]).replace("$(Scale)", fmt_value(self.length(key)))

    def _font(self):
        s = self.st; f = G.QFont(s["font"] or "Arial"); f.setPointSizeF(float(s["size"]))
        f.setBold(bool(s["bold"])); f.setItalic(bool(s["italic"])); f.setUnderline(bool(s["underline"])); return f

    def _lens(self):
        (x0, x1), (y0, y1) = self.vb.viewRange(); w, h = max(self.vb.width(), 1.0), max(self.vb.height(), 1.0)
        return self.length("x") / max(abs(x1 - x0), 1e-300) * w, self.length("y") / max(abs(y1 - y0), 1e-300) * h

    def _layout(self):
        """-> dict with line segments, cap segments and text boxes, all in item coordinates (corner at 0,0)."""
        s = self.st; m = s["mode"]; showx = m in ("XY Scales", "X Scale"); showy = m in ("XY Scales", "Y Scale")
        lx, ly = self._lens(); xs, ys = s["x"], s["y"]
        sx = 1.0 if ys["pos"] == "Left" else -1.0            # the horizontal bar runs away from the vertical bar
        sy = -1.0 if xs["pos"] == "Bottom" else 1.0           # the vertical bar runs away from the horizontal bar
        if not showy: sx = 1.0
        if not showx: sy = -1.0 if xs["pos"] == "Bottom" else 1.0
        lines = []; texts = []; fm = G.QFontMetricsF(self._font())
        if showx:
            lines.append((xs, C.QLineF(0, 0, sx * lx, 0)))
            for xx in (0.0, sx * lx): lines.append((xs, C.QLineF(xx, -xs["cap"] / 2, xx, xs["cap"] / 2)))
            t = self.title("x"); r = fm.boundingRect(t); w, h = r.width(), fm.height()
            cx = sx * lx / 2 + xs["dx"] * self.vb.width() / 100.0; down = xs["pos"] == "Bottom"
            top = (xs["cap"] / 2 + self.GAP) if down else -(xs["cap"] / 2 + self.GAP + h)
            texts.append((xs, t, C.QRectF(cx - w / 2, top + xs["dy"] * self.vb.height() / 100.0, w, h)))
        if showy:
            lines.append((ys, C.QLineF(0, 0, 0, sy * ly)))
            for yy in (0.0, sy * ly): lines.append((ys, C.QLineF(-ys["cap"] / 2, yy, ys["cap"] / 2, yy)))
            t = self.title("y"); r = fm.boundingRect(t); w, h = r.width(), fm.height()
            cy = sy * ly / 2 + ys["dy"] * self.vb.height() / 100.0; left = ys["pos"] == "Left"
            lft = -(ys["cap"] / 2 + self.GAP + w) if left else (ys["cap"] / 2 + self.GAP)
            texts.append((ys, t, C.QRectF(lft + ys["dx"] * self.vb.width() / 100.0, cy - h / 2, w, h)))
        return lines, texts

    def _text_path_rect(self, side, rect):
        tr = G.QTransform(); c = rect.center(); tr.translate(c.x(), c.y()); tr.rotate(float(side["rot"])); tr.translate(-c.x(), -c.y())
        return tr.mapRect(rect)

    def refresh(self, *_):
        self.prepareGeometryChange()
        w, h = max(self.vb.width(), 1.0), max(self.vb.height(), 1.0)
        self.setPos(self.st["fx"] * w, self.st["fy"] * h)
        self._cache = self._layout()
        self.update()

    def boundingRect(self):
        lines, texts = getattr(self, "_cache", ([], []))
        r = C.QRectF(-4, -4, 8, 8)
        for side, l in lines: r = r.united(C.QRectF(l.p1(), l.p2()).normalized())
        for side, t, rc in texts: r = r.united(self._text_path_rect(side, rc))
        return r.adjusted(-8, -8, 8, 8)

    def shape(self):
        p = G.QPainterPath(); lines, texts = getattr(self, "_cache", ([], []))
        for side, l in lines: p.addRect(C.QRectF(l.p1(), l.p2()).normalized().adjusted(-5, -5, 5, 5))
        for side, t, rc in texts: p.addRect(self._text_path_rect(side, rc).adjusted(-2, -2, 2, 2))
        return p

    def paint(self, p, *_):
        lines, texts = getattr(self, "_cache", ([], []))
        p.setRenderHint(G.QPainter.Antialiasing, True)
        base = G.QColor(self.st["color"])
        for side, l in lines:
            pen = G.QPen(G.QColor(side["color"] or base)); pen.setWidthF(float(side["width"])); pen.setCapStyle(C.Qt.FlatCap); pen.setCosmetic(False)
            p.setPen(pen); p.drawLine(l)
        p.setFont(self._font())
        for side, t, rc in texts:
            p.save(); c = rc.center(); p.translate(c); p.rotate(float(side["rot"])); p.translate(-c.x(), -c.y())
            p.setPen(G.QColor(side["color"] or base)); p.drawText(rc, C.Qt.AlignCenter | C.Qt.TextDontClip, t); p.restore()

    # ------------------------------------------------------------------ interaction
    def mouseDragEvent(self, ev):
        if ev.button() != C.Qt.LeftButton: ev.ignore(); return
        ev.accept()
        d = self.mapToParent(ev.pos()) - self.mapToParent(ev.lastPos())
        w, h = max(self.vb.width(), 1.0), max(self.vb.height(), 1.0)
        self.st["fx"] += d.x() / w; self.st["fy"] += d.y() / h; self.refresh()

    def mouseClickEvent(self, ev):
        if ev.button() == C.Qt.RightButton:
            ev.accept(); m = W.QMenu(self.win)
            m.addAction("Scale Properties…").triggered.connect(lambda: self.win.open_scale_dialog())
            m.addAction("刪除 Scale").triggered.connect(lambda: self.win.remove_scalebar())
            m.exec(ev.screenPos().toPoint())
        else:
            ev.ignore()

    def hoverEvent(self, ev): pass


class ColorBtn(W.QPushButton):
    changed = C.Signal()

    def __init__(self, color="#000000", allow_none=False):
        super().__init__(); self.color = color; self.allow_none = allow_none; self.setFixedHeight(24)
        self.clicked.connect(self._pick); self._paint()

    def _paint(self):
        c = self.color
        self.setText("Auto" if c is None else c); self.setStyleSheet(f"text-align:left;padding-left:6px;background:{c or '#ffffff'};color:{'#000' if (c is None or G.QColor(c).lightness() > 128) else '#fff'};")

    def set(self, c): self.color = c; self._paint()

    def _pick(self):
        q = W.QColorDialog.getColor(G.QColor(self.color or "#000000"), self, "Color")
        if q.isValid(): self.color = q.name(); self._paint(); self.changed.emit()


class ScaleDialog(W.QDialog):
    def __init__(self, win):
        super().__init__(win); self.win = win; self.setWindowTitle("Scaler Properties"); self.setMinimumWidth(380)
        lay = W.QVBoxLayout(self); f = W.QFormLayout()
        self.mode = W.QComboBox(); self.mode.addItems(["XY Scales", "X Scale", "Y Scale"])
        self.color = ColorBtn("#000000")
        self.font = W.QFontComboBox(); self.font.setEditable(False)
        self.size = W.QSpinBox(); self.size.setRange(4, 96)
        self.bold = W.QCheckBox(); self.italic = W.QCheckBox(); self.underline = W.QCheckBox()
        for a, b in (("Scales", self.mode), ("Color", self.color), ("Font", self.font), ("Font Size", self.size), ("Bold", self.bold), ("Italic", self.italic), ("Underline", self.underline)): f.addRow(a, b)
        lay.addLayout(f)
        self.sec = {}
        for key, nm, poss in (("x", "X", POS_X), ("y", "Y", POS_Y)):
            g = W.QGroupBox(nm); gf = W.QFormLayout(g); d = {}
            d["pos"] = W.QComboBox(); d["pos"].addItems(poss)
            d["length"] = W.QLineEdit(); d["length"].setPlaceholderText("Auto = major tick increment")
            d["hint"] = W.QLabel(); d["hint"].setStyleSheet("color:#1d4ed8;font-weight:bold;")
            d["width"] = W.QDoubleSpinBox(); d["width"].setRange(0.1, 30); d["width"].setSingleStep(0.5)
            d["title"] = W.QLineEdit()
            d["rot"] = W.QDoubleSpinBox(); d["rot"].setRange(-360, 360)
            d["color"] = ColorBtn(None, True)
            d["dx"] = W.QDoubleSpinBox(); d["dy"] = W.QDoubleSpinBox()
            for k in ("dx", "dy"): d[k].setRange(-100, 100); d[k].setDecimals(1); d[k].setSingleStep(0.5); d[k].setSuffix(" %")
            d["cap"] = W.QDoubleSpinBox(); d["cap"].setRange(0, 60)
            rb = W.QPushButton("Auto"); rb.setFixedWidth(50); rb.clicked.connect(lambda _=False, e=d["length"]: e.setText(""))
            lr = W.QHBoxLayout(); lr.addWidget(d["length"]); lr.addWidget(rb)
            gf.addRow("Position", d["pos"]); gf.addRow("Length (Scale)", lr); gf.addRow("", d["hint"]); gf.addRow("Width", d["width"])
            gf.addRow("Title", d["title"]); gf.addRow("Rotation Angle", d["rot"]); gf.addRow("Title Color", d["color"])
            gf.addRow("Offset X (% of Layer)", d["dx"]); gf.addRow("Offset Y (% of Layer)", d["dy"]); gf.addRow("Arrow (cap) Width", d["cap"])
            d["length"].textChanged.connect(self._hint)
            self.sec[key] = d; lay.addWidget(g)
        tip = W.QLabel("Length 留空＝連動座標軸 Major tick 設定值；Title 的 $(Scale) 會換成目前長度。圖上可拖曳移動，右鍵＝Properties。")
        tip.setWordWrap(True); tip.setStyleSheet("color:#666;"); lay.addWidget(tip)
        bb = W.QDialogButtonBox(W.QDialogButtonBox.Ok | W.QDialogButtonBox.Cancel | W.QDialogButtonBox.Apply)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject); bb.button(W.QDialogButtonBox.Apply).clicked.connect(self.apply)
        lay.addWidget(bb)

    def _hint(self, *_):
        sb = self.win.scalebar
        if sb is None: return
        for key, nm in (("x", "X3=X axis increment"), ("y", "Y3=Y axis increment")):
            d = self.sec[key]; t = d["length"].text().strip(); linked = t == "" or t.lower() in ("auto", "x3", "y3")
            d["hint"].setText(f"{nm} = {fmt_value(sb.major(key))}" + ("  (linked)" if linked else ""))

    def open_dialog(self):
        self.snap = copy.deepcopy(self.win.scalebar.st); self.load(); self.show(); self.raise_(); self.activateWindow()

    def load(self):
        s = self.win.scalebar.st
        self.mode.setCurrentText(s["mode"]); self.color.set(s["color"]); self.font.setCurrentFont(G.QFont(s["font"] or "Arial")); self.size.setValue(int(s["size"]))
        self.bold.setChecked(bool(s["bold"])); self.italic.setChecked(bool(s["italic"])); self.underline.setChecked(bool(s["underline"]))
        for key, d in self.sec.items():
            a = s[key]; d["pos"].setCurrentText(a["pos"]); d["length"].setText(str(a["length"])); d["width"].setValue(float(a["width"])); d["title"].setText(a["title"])
            d["rot"].setValue(float(a["rot"])); d["color"].set(a["color"]); d["dx"].setValue(float(a["dx"])); d["dy"].setValue(float(a["dy"])); d["cap"].setValue(float(a["cap"]))
        self._hint()

    def apply(self):
        sb = self.win.scalebar
        if sb is None: return
        s = sb.st
        s.update(mode=self.mode.currentText(), color=self.color.color, font=self.font.currentFont().family(), size=self.size.value(),
                 bold=self.bold.isChecked(), italic=self.italic.isChecked(), underline=self.underline.isChecked())
        for key, d in self.sec.items():
            s[key].update(pos=d["pos"].currentText(), length=d["length"].text().strip(), width=d["width"].value(), title=d["title"].text(), rot=d["rot"].value(),
                          color=d["color"].color, dx=d["dx"].value(), dy=d["dy"].value(), cap=d["cap"].value())
        sb.refresh(); self._hint()

    def _ok(self): self.apply(); self.accept()

    def reject(self):
        if self.win.scalebar is not None and getattr(self, "snap", None): self.win.scalebar.st.update(copy.deepcopy(self.snap)); self.win.scalebar.refresh()
        super().reject()
