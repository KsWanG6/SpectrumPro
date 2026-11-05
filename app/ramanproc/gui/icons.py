"""Programmatically drawn toolbar icons (no external files)."""
import math
from PySide6 import QtGui as G, QtCore as C

BLUE, ORANGE, GRAY, RED, GREEN, DARK = "#1f77b4", "#ff7f0e", "#9aa0a6", "#d62728", "#2ca02c", "#333333"
N = 64


def _pm():
    pm = G.QPixmap(N, N); pm.fill(C.Qt.transparent)
    p = G.QPainter(pm); p.setRenderHint(G.QPainter.Antialiasing)
    return pm, p


def _pen(color, w=3, style=C.Qt.SolidLine):
    pen = G.QPen(G.QColor(color), w, style); pen.setCapStyle(C.Qt.RoundCap); pen.setJoinStyle(C.Qt.RoundJoin)
    return pen


def _curve(fn, x0=6, x1=58, base=50, amp=34, n=60, noise=None):
    path = G.QPainterPath()
    for i in range(n + 1):
        t = i / n
        y = fn(t) + (noise(t) if noise else 0)
        pt = C.QPointF(x0 + (x1 - x0) * t, base - amp * y)
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    return path


def _spec(t, shift=0.0, h=1.0):
    g = lambda c, w, a: a * math.exp(-0.5 * ((t - c) / w) ** 2)
    return h * (g(0.32 + shift, 0.045, 0.9) + g(0.62 + shift, 0.04, 0.6) + g(0.82 + shift, 0.05, 0.35))


def _axes(p):
    p.setPen(_pen("#bbbbbb", 1.5)); p.drawLine(6, 54, 60, 54); p.drawLine(6, 8, 6, 54)


def icon_average():
    pm, p = _pm(); _axes(p)
    for k, (sh, h, c) in enumerate([(-0.03, 1.1, GRAY), (0.025, 0.85, GRAY), (0.0, 0.7, GRAY)]):
        p.setPen(_pen(c, 1.8)); p.drawPath(_curve(lambda t, s=sh, hh=h: _spec(t, s, hh) * 0.9 + 0.05 * k, base=52, amp=36))
    p.setPen(_pen(BLUE, 4)); p.drawPath(_curve(lambda t: _spec(t, 0, 0.9) * 0.9, base=52, amp=36))
    p.end(); return G.QIcon(pm)


def icon_crop():
    pm, p = _pm()
    p.setPen(_pen(GRAY, 2)); p.drawPath(_curve(lambda t: _spec(t) * 0.9, base=50, amp=34))
    p.setPen(_pen(BLUE, 4)); p.drawPath(_curve(lambda t: _spec(t) * 0.9, x0=6, x1=58, base=50, amp=34, n=60))
    # shade kept region, cut marks
    p.setBrush(G.QColor(255, 127, 14, 45)); p.setPen(C.Qt.NoPen); p.drawRect(C.QRectF(20, 8, 26, 46))
    p.setPen(_pen(ORANGE, 3)); p.drawLine(20, 6, 20, 58); p.drawLine(46, 6, 46, 58)
    p.setPen(_pen(ORANGE, 3)); p.drawLine(14, 12, 20, 12); p.drawLine(46, 52, 52, 52)
    p.end(); return G.QIcon(pm)


def icon_smooth():
    pm, p = _pm(); _axes(p)
    import random
    rnd = random.Random(3); noise = [rnd.uniform(-0.09, 0.09) for _ in range(61)]
    idx = {"i": 0}
    def nz(t): return noise[int(round(t * 60))]
    p.setPen(_pen(GRAY, 1.8)); p.drawPath(_curve(lambda t: _spec(t) * 0.9 + 0.1, base=52, amp=34, noise=nz))
    p.setPen(_pen(BLUE, 4)); p.drawPath(_curve(lambda t: _spec(t) * 0.9 + 0.1, base=52, amp=34))
    p.end(); return G.QIcon(pm)


def icon_baseline():
    pm, p = _pm(); _axes(p)
    base = lambda t: 0.35 * (1 - t) + 0.08
    p.setBrush(G.QColor(154, 160, 166, 70)); p.setPen(C.Qt.NoPen)
    poly = G.QPolygonF([C.QPointF(6, 52), C.QPointF(58, 52)] + [C.QPointF(58 - 52 * i / 20, 52 - 34 * base(1 - i / 20)) for i in range(21)])
    p.drawPolygon(poly)
    p.setPen(_pen(GRAY, 2)); p.drawPath(_curve(lambda t: _spec(t) * 0.7 + base(t), base=52, amp=34))
    p.setPen(_pen(RED, 3, C.Qt.DashLine)); p.drawPath(_curve(base, base=52, amp=34))
    p.setPen(_pen(BLUE, 4)); p.drawPath(_curve(lambda t: _spec(t) * 0.7, base=52, amp=34))
    p.end(); return G.QIcon(pm)


def icon_normalize():
    pm, p = _pm()
    p.setPen(_pen("#bbbbbb", 1.5)); p.drawLine(8, 54, 60, 54); p.drawLine(8, 8, 8, 54)
    p.setPen(_pen(GREEN, 2, C.Qt.DashLine)); p.drawLine(8, 12, 60, 12)
    p.setPen(_pen(GRAY, 2)); p.drawPath(_curve(lambda t: _spec(t) * 0.45, x0=10, x1=58, base=54, amp=42))
    p.setPen(_pen(BLUE, 4)); p.drawPath(_curve(lambda t: _spec(t) / 0.9, x0=10, x1=58, base=54, amp=42))
    f = G.QFont("Sans", 9); f.setBold(True); p.setFont(f); p.setPen(G.QColor(GREEN)); p.drawText(C.QPointF(40, 24), "1")
    p.setPen(G.QColor(DARK)); p.drawText(C.QPointF(12, 50), "0")
    p.end(); return G.QIcon(pm)


ICONS = {"average": icon_average, "crop": icon_crop, "smooth": icon_smooth, "baseline": icon_baseline, "normalize": icon_normalize}


# ---------------- generic toolbar / tool icons ----------------
def content_bbox(pm):
    """Bounding box (x0, y0, x1, y1) of the non-transparent pixels, or None."""
    im = pm.toImage().convertToFormat(G.QImage.Format_ARGB32); w, h = im.width(), im.height()
    import numpy as np
    a = np.frombuffer(im.constBits(), np.uint8).reshape(h, im.bytesPerLine() // 4, 4)[:, :w, 3]
    ys, xs = np.nonzero(a > 8)
    return None if not len(xs) else (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def centered(pm, fit=54):
    """Re-centre the drawn content in the canvas (and shrink if larger than `fit`) so every icon is optically symmetric."""
    bb = content_bbox(pm)
    if bb is None: return pm
    x0, y0, x1, y1 = bb; w, h = x1 - x0, y1 - y0
    k = min(1.0, fit / max(w, h))
    out = G.QPixmap(N, N); out.fill(C.Qt.transparent)
    q = G.QPainter(out); q.setRenderHint(G.QPainter.SmoothPixmapTransform)
    q.translate(N / 2, N / 2); q.scale(k, k); q.translate(-(x0 + x1) / 2, -(y0 + y1) / 2)
    q.drawPixmap(0, 0, pm); q.end()
    return out


def _wrap(draw):
    def f():
        pm, p = _pm(); draw(p); p.end(); return G.QIcon(centered(centered(pm)))
    return f


def _open(p):
    p.setPen(_pen("#8a6d1d", 2)); p.setBrush(G.QColor("#f2c14e"))
    p.drawPolygon(G.QPolygonF([C.QPointF(6, 16), C.QPointF(24, 16), C.QPointF(29, 22), C.QPointF(56, 22), C.QPointF(56, 52), C.QPointF(6, 52)]))
    p.setBrush(G.QColor("#f7d98b")); p.drawPolygon(G.QPolygonF([C.QPointF(6, 52), C.QPointF(14, 30), C.QPointF(62, 30), C.QPointF(56, 52)]))

def _save(p):
    p.setPen(_pen("#12365f", 2)); p.setBrush(G.QColor("#2a6db3")); p.drawRoundedRect(8, 8, 48, 48, 4, 4)
    p.setBrush(G.QColor("#ffffff")); p.drawRect(16, 8, 30, 18); p.setBrush(G.QColor("#12365f")); p.drawRect(38, 11, 5, 12)
    p.setBrush(G.QColor("#dfe9f5")); p.drawRect(16, 36, 32, 20)

def _image(p):
    p.setPen(_pen("#12365f", 2)); p.setBrush(G.QColor("#ffffff")); p.drawRoundedRect(8, 12, 48, 40, 4, 4)
    p.setBrush(G.QColor("#2ca02c")); p.setPen(C.Qt.NoPen); p.drawPolygon(G.QPolygonF([C.QPointF(12, 48), C.QPointF(26, 28), C.QPointF(36, 40), C.QPointF(42, 33), C.QPointF(52, 48)]))
    p.setBrush(G.QColor("#ff7f0e")); p.drawEllipse(40, 17, 10, 10)

def _arrow(left):
    def d(p):
        p.setPen(_pen("#12365f", 5)); path = G.QPainterPath()
        if left:
            path.moveTo(18, 24); path.lineTo(8, 34); path.lineTo(18, 44); path.moveTo(8, 34); path.lineTo(40, 34); path.cubicTo(56, 34, 56, 14, 40, 14); path.lineTo(30, 14)
        else:
            path.moveTo(46, 24); path.lineTo(56, 34); path.lineTo(46, 44); path.moveTo(56, 34); path.lineTo(24, 34); path.cubicTo(8, 34, 8, 14, 24, 14); path.lineTo(34, 14)
        p.setBrush(C.Qt.NoBrush); p.drawPath(path)
    return d

def _fit(p):
    p.setPen(_pen("#12365f", 4)); p.setBrush(C.Qt.NoBrush)
    for (a, b, c, d) in [(10, 22, 10, 10), (54, 22, 54, 10), (10, 42, 10, 54), (54, 42, 54, 54)]:
        pass
    p.drawLine(10, 22, 10, 10); p.drawLine(10, 10, 22, 10); p.drawLine(54, 22, 54, 10); p.drawLine(54, 10, 42, 10)
    p.drawLine(10, 42, 10, 54); p.drawLine(10, 54, 22, 54); p.drawLine(54, 42, 54, 54); p.drawLine(54, 54, 42, 54)
    p.setPen(_pen(BLUE, 4)); p.drawPath(_curve(lambda t: _spec(t) * 0.8, x0=16, x1=48, base=46, amp=26))

def _peaks(p):
    _axes(p); p.setPen(_pen(BLUE, 3.5)); p.drawPath(_curve(lambda t: _spec(t) * 0.8, base=52, amp=34))
    p.setPen(_pen(RED, 2.5)); 
    for t in (0.32, 0.62, 0.82):
        x = 6 + 52 * t; y = 52 - 34 * _spec(t) * 0.8; p.drawLine(C.QPointF(x, y - 5), C.QPointF(x, y - 14))

def _integral(p):
    _axes(p); path = _curve(lambda t: _spec(t) * 0.8, base=52, amp=34)
    poly = G.QPolygonF([C.QPointF(6 + 52 * 0.2, 52)] + [C.QPointF(6 + 52 * (0.2 + 0.5 * i / 30), 52 - 34 * _spec(0.2 + 0.5 * i / 30) * 0.8) for i in range(31)] + [C.QPointF(6 + 52 * 0.7, 52)])
    p.setBrush(G.QColor(255, 127, 14, 120)); p.setPen(C.Qt.NoPen); p.drawPolygon(poly)
    p.setBrush(C.Qt.NoBrush); p.setPen(_pen(BLUE, 3.5)); p.drawPath(path)

def _cosmic(p):
    _axes(p); p.setPen(_pen(GRAY, 2)); p.drawPath(_curve(lambda t: 0.25 + 0.08 * math.sin(t * 25), base=52, amp=34))
    p.setPen(_pen(RED, 3)); p.drawLine(34, 52, 34, 8); p.setPen(_pen(BLUE, 3.5)); p.drawPath(_curve(lambda t: 0.25 + 0.08 * math.sin(t * 25) , base=52, amp=34))

def _tool(kind):
    def d(p):
        pen = _pen("#12365f", 3.5); p.setPen(pen); p.setBrush(C.Qt.NoBrush)
        if kind == "pointer":
            p.drawLine(32, 8, 32, 56); p.drawLine(8, 32, 56, 32); p.setBrush(G.QColor("#12365f"))
            for pts in ([(32, 4), (25, 14), (39, 14)], [(32, 60), (25, 50), (39, 50)], [(4, 32), (14, 25), (14, 39)], [(60, 32), (50, 25), (50, 39)]):
                p.drawPolygon(G.QPolygonF([C.QPointF(*q) for q in pts]))
        elif kind == "zoom":
            p.drawEllipse(10, 8, 30, 30); p.setPen(_pen("#12365f", 6)); p.drawLine(36, 36, 54, 54); p.setPen(_pen(BLUE, 3)); p.drawLine(18, 23, 32, 23); p.drawLine(25, 16, 25, 30)
        elif kind == "shift":
            p.drawLine(32, 10, 32, 54); p.setBrush(G.QColor("#12365f")); p.drawPolygon(G.QPolygonF([C.QPointF(32, 6), C.QPointF(22, 20), C.QPointF(42, 20)])); p.drawPolygon(G.QPolygonF([C.QPointF(32, 58), C.QPointF(22, 44), C.QPointF(42, 44)]))
        elif kind == "multiply":
            p.setPen(_pen(RED, 6)); p.drawLine(16, 16, 48, 48); p.drawLine(48, 16, 16, 48)
        elif kind == "xy":
            p.drawLine(32, 6, 32, 58); p.drawLine(6, 32, 58, 32); p.setPen(_pen(RED, 3)); p.drawEllipse(24, 24, 16, 16)
        elif kind == "cursor":
            p.setBrush(G.QColor(RED)); p.drawEllipse(22, 14, 20, 20); p.setBrush(C.Qt.NoBrush); p.drawLine(32, 34, 32, 56); p.drawLine(18, 56, 46, 56)
        elif kind == "text":
            f = G.QFont("Serif", 38); f.setBold(True); p.setFont(f); p.drawText(C.QRectF(8, 4, 48, 56), C.Qt.AlignCenter, "T")
        elif kind == "baseline_pts":
            p.setPen(_pen(BLUE, 3)); p.drawPath(_curve(lambda t: _spec(t) * 0.8, base=46, amp=30))
            p.setPen(_pen(RED, 2.5, C.Qt.DashLine)); p.drawLine(6, 46, 58, 40)
            p.setPen(_pen("#0b2540", 2)); p.setBrush(G.QColor(RED))
            for x, y in ((10, 45.5), (30, 43), (54, 40.5)): p.drawEllipse(C.QPointF(x, y), 5, 5)
        elif kind == "eraser":
            p.save(); p.translate(32, 34); p.rotate(-35)
            p.setPen(_pen("#12365f", 2.5)); p.setBrush(G.QColor("#f4a6b8")); p.drawRoundedRect(C.QRectF(-24, -11, 28, 22), 4, 4)
            p.setBrush(G.QColor("#ffffff")); p.drawRoundedRect(C.QRectF(4, -11, 20, 22), 4, 4); p.restore()
            p.setPen(_pen(GRAY, 3)); p.drawLine(8, 56, 56, 56)
        elif kind == "xline":
            p.setPen(_pen(RED, 3.5, C.Qt.DashLine)); p.drawLine(32, 6, 32, 58); p.setPen(_pen("#12365f", 3)); p.drawLine(10, 50, 54, 50)
            p.drawLine(32, 50, 32, 58)
        elif kind == "dxline":
            p.setPen(C.Qt.NoPen); p.setBrush(G.QColor(29, 124, 212, 45)); p.drawRect(16, 6, 32, 52)
            p.setBrush(C.Qt.NoBrush); p.setPen(_pen(RED, 3.5, C.Qt.DashLine)); p.drawLine(16, 6, 16, 58)
            p.setPen(_pen(BLUE, 3.5, C.Qt.DashLine)); p.drawLine(48, 6, 48, 58)
            p.setPen(_pen("#12365f", 3)); p.drawLine(16, 32, 48, 32)
            p.setBrush(G.QColor("#12365f"))
            p.drawPolygon(G.QPolygonF([C.QPointF(16, 32), C.QPointF(25, 26), C.QPointF(25, 38)])); p.drawPolygon(G.QPolygonF([C.QPointF(48, 32), C.QPointF(39, 26), C.QPointF(39, 38)]))
        elif kind == "image":
            _image(p)
        elif kind == "draw_strip":
            p.setBrush(G.QColor(255, 127, 14, 120)); p.setPen(_pen(ORANGE, 3)); p.drawRect(18, 10, 28, 44)
        elif kind == "remove_strip":
            p.setBrush(G.QColor(255, 127, 14, 60)); p.setPen(_pen(ORANGE, 2.5, C.Qt.DashLine)); p.drawRect(14, 10, 36, 44)
            p.setPen(_pen(RED, 6)); p.drawLine(22, 20, 42, 44); p.drawLine(42, 20, 22, 44)
        elif kind == "label_peak":
            p.setPen(_pen(BLUE, 3.5)); p.drawPath(_curve(lambda t: _spec(t) * 0.8, base=54, amp=30)); p.setPen(_pen(RED, 3)); p.drawLine(C.QPointF(22, 8), C.QPointF(22, 24)); p.drawLine(C.QPointF(22, 24), C.QPointF(17, 18)); p.drawLine(C.QPointF(22, 24), C.QPointF(27, 18))
    return d

ICONS.update({"open": _wrap(_open), "save": _wrap(_save), "image": _wrap(_image), "undo": _wrap(_arrow(True)), "redo": _wrap(_arrow(False)),
              "fit": _wrap(_fit), "peaks": _wrap(_peaks), "integral": _wrap(_integral), "cosmic": _wrap(_cosmic)})
for _k in ("baseline_pts", "eraser", "xline", "dxline", "pointer", "zoom", "shift", "multiply", "xy", "cursor", "text", "image", "draw_strip", "remove_strip", "label_peak"):
    ICONS["tool_" + _k] = _wrap(_tool(_k))

ICONS["cosmic"] = ICONS["tool_eraser"]


def _multi(p):
    for i, col in enumerate((BLUE, RED, GREEN)):
        p.setPen(_pen(col, 3.5)); p.drawPath(_curve(lambda t, i=i: 0.15 + 0.5 * _spec(t) * (0.6 + 0.2 * i), base=58 - 14 * i, amp=26))

def _single(p):
    _axes(p); p.setPen(_pen(BLUE, 4)); p.drawPath(_curve(lambda t: _spec(t) * 0.85, base=52, amp=38))

ICONS.update({"multi": _wrap(_multi), "single": _wrap(_single)})


def _stack(p):
    for i, col in enumerate((BLUE, RED, GREEN)):
        p.setPen(_pen(col, 3.5)); p.drawPath(_curve(lambda t: 0.55 * _spec(t), base=58 - 19 * i, amp=26))

ICONS["stack"] = _wrap(_stack)


def _quant(p):
    _axes(p); p.setPen(_pen(RED, 3.5)); p.drawLine(10, 50, 56, 14)
    p.setPen(_pen("#0b2540", 1.5)); p.setBrush(G.QColor(BLUE))
    for x, y in ((14, 46), (24, 41), (34, 31), (44, 26), (54, 14)): p.drawEllipse(C.QPointF(x, y + (3 if x in (24, 44) else -2)), 4, 4)

ICONS["quant"] = _wrap(_quant)


def _rsd(p):
    _axes(p)
    for i, (h, col) in enumerate(((30, BLUE), (36, BLUE), (27, BLUE), (33, BLUE))):
        x = 12 + i * 12; p.setPen(_pen("#333333", 1.5)); p.setBrush(G.QColor(col)); p.drawRect(x, 52 - h, 9, h)
    p.setPen(_pen(RED, 2.5, C.Qt.DashLine)); p.drawLine(8, 22, 58, 22)
    p.setPen(_pen("#333333", 2)); p.drawLine(34, 14, 34, 30); p.drawLine(30, 14, 38, 14); p.drawLine(30, 30, 38, 30)

ICONS["rsd"] = _wrap(_rsd)


def _ir(p):
    _axes(p); p.setPen(_pen(BLUE, 3.5))
    g = lambda t, c, w, a: a * math.exp(-0.5 * ((t - c) / w) ** 2)
    p.drawPath(_curve(lambda t: 0.9 - g(t, 0.25, 0.05, 0.55) - g(t, 0.5, 0.12, 0.35) - g(t, 0.75, 0.03, 0.7), base=52, amp=40))
    p.setPen(_pen(RED, 2.5))
    for t in (0.25, 0.75):
        x = 6 + 52 * t; y = 52 - 40 * (0.9 - (0.55 if t < 0.5 else 0.7)); p.drawLine(C.QPointF(x, y + 5), C.QPointF(x, y + 12))

ICONS["ir"] = _wrap(_ir)


def _bl_copy(p):
    p.setPen(_pen("#555555", 2.5)); p.setBrush(G.QColor("#ffffff")); p.drawRoundedRect(22, 8, 30, 38, 4, 4)
    p.setBrush(G.QColor("#dbeafe")); p.setPen(_pen(BLUE, 2.5)); p.drawRoundedRect(10, 18, 30, 38, 4, 4)
    p.setPen(_pen(BLUE, 2.5)); [p.drawLine(16, y, 34, y) for y in (30, 38, 46)]

def _bl_paste(p):
    p.setPen(_pen("#8a6d1d", 2.5)); p.setBrush(G.QColor("#f2c14e")); p.drawRoundedRect(10, 10, 44, 48, 5, 5)
    p.setBrush(G.QColor("#ffffff")); p.setPen(_pen("#555555", 2.5)); p.drawRoundedRect(17, 22, 30, 32, 3, 3)
    p.setBrush(G.QColor("#9aa0a6")); p.drawRoundedRect(24, 5, 16, 11, 3, 3)

def _bl_trash(p):
    p.setPen(_pen("#555555", 2.8)); p.setBrush(G.QColor("#e8eaed")); p.drawRoundedRect(16, 22, 32, 34, 4, 4)
    p.drawLine(12, 18, 52, 18); p.drawLine(26, 18, 26, 12); p.drawLine(26, 12, 38, 12); p.drawLine(38, 12, 38, 18)
    p.setPen(_pen("#777777", 2.5)); [p.drawLine(x, 28, x, 50) for x in (25, 32, 39)]

def _pick_b(p):
    p.setPen(_pen(ACCENT_ICON := "#1d7cd4", 3)); p.setBrush(G.QColor("#1d7cd4")); p.drawRoundedRect(8, 8, 48, 48, 8, 8)
    p.setPen(_pen("#ffffff", 5)); p.drawLine(18, 32, 44, 32); p.drawLine(34, 22, 44, 32); p.drawLine(34, 42, 44, 32)

def _clear_b(p):
    p.setPen(_pen("#d62728", 7)); p.drawLine(14, 14, 50, 50); p.drawLine(50, 14, 14, 50)

ICONS.update({"bl_copy": _wrap(_bl_copy), "bl_paste": _wrap(_bl_paste), "bl_trash": _wrap(_bl_trash), "pick_b": _wrap(_pick_b), "clear_b": _wrap(_clear_b)})


def _normalised(f):
    def g():
        ic = f(); sz = ic.availableSizes()[0] if ic.availableSizes() else C.QSize(N, N)
        return G.QIcon(centered(centered(ic.pixmap(sz))))
    return g


for _k in list(ICONS):                      # every icon, however it was drawn, ends up optically centred
    ICONS[_k] = _normalised(ICONS[_k])
