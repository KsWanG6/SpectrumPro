"""LabSpec-style look: blue theme, titled panels, collapsible sections."""
from PySide6 import QtWidgets as W, QtCore as C, QtGui as G
from .dialogs import make_widget, read_widget, write_widget

# Apple-style (macOS light) colour system, tinted with the project palette.
# Neutrals follow macOS: window #f5f5f7, separator #d2d2d7, label #1d1d1f / secondary #6e6e73, control fill #e8e8ed.
PALE, MID, ACCENT = "#ecf7fc", "#aad7e3", "#1d7cd4"            # project palette (sidebar tint / soft fill / accent)
INK, INK2, ACCENT_D = "#1d1d1f", "#6e6e73", "#14599e"           # label, secondary label, pressed accent
WINDOW, BAR, SEP, FILL, HOVER = "#f5f5f7", "#f6f6f8", "#d2d2d7", "#e8e8ed", "#e3e3e8"
SEL = "#d4e8f9"                                                  # accent at ~18 % : selected-toolbar / sidebar highlight
NAVY, BLUE, LIGHT = ACCENT_D, ACCENT, PALE
FONT = '"jf open 粉圓 2.0", "jf-openhuninn-2.0", "SF Pro Text", "-apple-system", "Helvetica Neue", "Segoe UI Variable", "Segoe UI", "Microsoft JhengHei UI", "PingFang TC", sans-serif'

def _arrows():
    """Write small chevron PNGs (up / down) once; used by spin boxes and combo boxes in the stylesheet."""
    import os, tempfile
    d = os.path.join(tempfile.gettempdir(), "ramanproc_ui"); os.makedirs(d, exist_ok=True)
    out = {}
    for name in ("up", "down"):
        path = os.path.join(d, f"chev_{name}.png")
        img = G.QImage(18, 18, G.QImage.Format_ARGB32); img.fill(0)
        q = G.QPainter(img); q.setRenderHint(G.QPainter.Antialiasing)
        pen = G.QPen(G.QColor(INK2), 2.2); pen.setCapStyle(C.Qt.RoundCap); pen.setJoinStyle(C.Qt.RoundJoin); q.setPen(pen)
        pts = [(4.5, 11.5), (9, 6.5), (13.5, 11.5)] if name == "up" else [(4.5, 6.5), (9, 11.5), (13.5, 6.5)]
        q.drawPolyline([C.QPointF(*pt) for pt in pts]); q.end(); img.save(path)
        out[name] = path.replace("\\", "/")
    return out


_AR = _arrows()

# Flat selection colours (no gradients): soft accent tint for selected controls, solid accent for primary buttons / list rows.
GLASS = SEL
GLASS_STRONG = ACCENT
RIM = ACCENT

STYLE = f"""
* {{ font-family: {FONT}; font-size: 10pt; }}
QMainWindow, QDialog, QWidget#qt_scrollarea_viewport {{ background: {WINDOW}; color: {INK}; }}
QLabel {{ color: {INK}; background: transparent; }}
/* menu bar / menus: light, like macOS */
QMenuBar {{ background: {BAR}; color: {INK}; border-bottom: 1px solid {SEP}; padding: 1px 4px; }}
QMenuBar::item {{ padding: 4px 10px; margin: 1px 1px; background: transparent; border-radius: 5px; }}
QMenuBar::item:selected {{ background: {ACCENT}; color: white; }}
QMenu {{ background: #fbfbfd; color: {INK}; border: 1px solid {SEP}; border-radius: 8px; padding: 5px; }}
QMenu::item {{ padding: 5px 22px 5px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {ACCENT}; color: white; }}
QMenu::separator {{ height: 1px; background: {SEP}; margin: 5px 8px; }}
QToolTip {{ background: #fbfbfd; color: {INK}; border: 1px solid {SEP}; border-radius: 6px; padding: 5px 7px; }}
/* unified toolbar */
QToolBar {{ background: {BAR}; border: 0; border-bottom: 1px solid {SEP}; spacing: 4px; padding: 4px 6px; }}
QToolBar QToolButton, QToolButton#BarBtn {{ color: {INK}; font-size: 9pt; background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 4px 4px; }}
QToolBar QToolButton:hover {{ background: {HOVER}; }}
QToolBar QToolButton:checked, QToolBar QToolButton:pressed {{ background: {GLASS}; color: {ACCENT_D}; border: 1px solid {RIM}; }}
QToolBar QToolButton:disabled {{ color: #a1a1a6; }}
QToolButton::menu-indicator {{ subcontrol-origin: padding; subcontrol-position: bottom right; right: 4px; bottom: 4px; width: 7px; height: 7px; }}
QToolButton::menu-button {{ border: 0; border-left: 1px solid {SEP}; width: 14px; border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}
QToolButton::menu-arrow {{ width: 8px; height: 8px; }}
QToolBar::separator {{ background: {SEP}; width: 1px; margin: 6px 5px; }}
/* left tool sidebar (macOS source-list tint) */
QToolBar#ToolStrip {{ background: {PALE}; border: 0; border-right: 1px solid {SEP}; padding: 4px 3px; }}
QToolBar#ToolStrip QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 0; }}
QToolBar#ToolStrip QToolButton:hover {{ background: #d9edf6; }}
QToolBar#ToolStrip QToolButton:checked {{ background: {GLASS}; border: 1px solid {RIM}; }}
QFrame#ToolSep {{ color: {SEP}; background: {SEP}; max-height: 1px; margin: 3px 4px; }}
QLabel#PanelTitle {{ background: {BAR}; color: {INK2}; font-weight: 600; font-size: 10pt; padding: 5px 10px; border-bottom: 1px solid {SEP}; qproperty-alignment: AlignCenter; }}
/* tabs: segmented-control look */
QTabWidget::pane {{ border: 1px solid {SEP}; background: {WINDOW}; top: -1px; border-radius: 6px; }}
QTabBar::tab {{ background: {FILL}; color: {INK}; padding: 5px 11px; border: 1px solid {SEP}; margin-right: -1px; font-weight: 500; }}
QTabBar::tab:first {{ border-top-left-radius: 7px; border-bottom-left-radius: 7px; }}
QTabBar::tab:last {{ border-top-right-radius: 7px; border-bottom-right-radius: 7px; margin-right: 0; }}
QTabBar::tab:hover {{ background: {HOVER}; }}
QTabBar::tab:selected {{ background: {GLASS}; color: {ACCENT_D}; font-weight: 600; border: 1px solid {RIM}; }}
QTabBar#WsBar::tab {{ background: transparent; color: {INK2}; border: 0; border-bottom: 2px solid transparent; padding: 5px 12px; border-radius: 0; margin: 0; }}
QTabBar#WsBar::tab:selected {{ background: transparent; color: {INK}; border: 0; border-bottom: 2px solid {ACCENT}; }}
QTabBar#WsBar::close-button {{ subcontrol-position: right; }}
QToolButton#HelpBtn {{ background: transparent; color: {INK2}; border: 0; border-bottom: 1px solid {SEP}; font-weight: 700; padding: 6px 9px; }}
QToolButton#HelpBtn:hover {{ color: {ACCENT_D}; }}
QSlider::groove:horizontal {{ height: 4px; background: {FILL}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {MID}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: white; border: 1px solid {ACCENT}; width: 14px; height: 14px; margin: -6px 0; border-radius: 8px; }}
QSlider::handle:horizontal:disabled {{ border: 1px solid {SEP}; }}
QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ color: #a1a1a6; background: {BAR}; }}
QLabel:disabled, QCheckBox:disabled {{ color: #a1a1a6; }}
/* controls */
QPushButton {{ background: white; color: {INK}; border: 1px solid {SEP}; border-radius: 6px; padding: 4px 12px; min-height: 18px; }}
QPushButton:hover {{ background: #f0f0f4; }}
QPushButton:pressed {{ background: {FILL}; }}
QPushButton#Apply {{ background: {GLASS_STRONG}; color: white; font-weight: 600; border: 1px solid {ACCENT_D}; }}
QPushButton#Apply:hover {{ background: {ACCENT_D}; }}
QToolButton#SectionHead {{ background: transparent; color: {INK2}; font-weight: 600; font-size: 9.5pt; text-align: left; border: 0; border-bottom: 1px solid {SEP}; border-radius: 0; padding: 6px 4px; }}
QToolButton#SectionHead:hover {{ color: {ACCENT_D}; }}
QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {{ background: white; color: {INK}; border: 1px solid {SEP}; border-radius: 5px; padding: 2px 6px; min-height: 20px; selection-background-color: {ACCENT}; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 18px; border: 0; background: transparent; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 18px; border: 0; background: transparent; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({_AR["up"]}); width: 9px; height: 9px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({_AR["down"]}); width: 9px; height: 9px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 20px; border: 0; }}
QComboBox::down-arrow {{ image: url({_AR["down"]}); width: 9px; height: 9px; }}
QComboBox QAbstractItemView {{ background: white; border: 1px solid {SEP}; selection-background-color: {ACCENT}; selection-color: white; outline: 0; }}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QCheckBox {{ color: {INK}; spacing: 6px; }}
QListWidget, QTableWidget {{ background: white; color: {INK}; alternate-background-color: #f7fafc; gridline-color: #e5e5ea; border: 1px solid {SEP}; border-radius: 6px; }}
QListWidget::item {{ padding: 3px 4px; border-radius: 4px; }}
QListWidget::item:selected, QTableWidget::item:selected {{ background: {ACCENT}; color: white; }}
QHeaderView::section {{ background: {BAR}; color: {INK2}; font-weight: 600; border: 0; border-bottom: 1px solid {SEP}; border-right: 1px solid #e5e5ea; padding: 4px 6px; }}
QStatusBar {{ background: {BAR}; color: {INK2}; border-top: 1px solid {SEP}; font-size: 9pt; }}
QStatusBar QLabel {{ color: {INK2}; }}
QScrollArea {{ border: 0; background: {WINDOW}; }}
QScrollArea > QWidget > QWidget {{ background: {WINDOW}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #c4c4ca; border-radius: 3px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: #a8a8ae; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #c4c4ca; border-radius: 3px; min-width: 28px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: {SEP}; }}
"""


class Section(W.QWidget):
    """Collapsible titled section (LabSpec right-panel style), with an optional "?" help button on the header."""

    def __init__(self, title, expanded=True, help=None):
        super().__init__()
        lay = W.QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 2); lay.setSpacing(0)
        self.head = W.QToolButton(); self.head.setObjectName("SectionHead")
        self.head.setCheckable(True); self.head.setChecked(expanded)
        self.head.setToolButtonStyle(C.Qt.ToolButtonTextBesideIcon)
        self.head.setSizePolicy(W.QSizePolicy.Expanding, W.QSizePolicy.Fixed)
        self.title = title
        top = W.QHBoxLayout(); top.setContentsMargins(0, 0, 0, 0); top.setSpacing(0); top.addWidget(self.head, 1)
        if help:
            hb = W.QToolButton(); hb.setObjectName("HelpBtn"); hb.setText("?"); hb.setToolTip("說明"); hb.setCursor(C.Qt.PointingHandCursor)
            hb.clicked.connect(lambda: W.QMessageBox.information(self, title, help)); top.addWidget(hb)
            self.help_btn = hb
        self.body = W.QWidget(); self.form = W.QVBoxLayout(self.body); self.form.setContentsMargins(8, 8, 8, 6)
        lay.addLayout(top); lay.addWidget(self.body)
        self.head.toggled.connect(self._toggle)
        self._toggle(expanded)

    def _toggle(self, on):
        self.head.setText(("▾  " if on else "▸  ") + self.title.replace("&", "&&"))
        self.body.setVisible(on)

    def add(self, w):
        l = w.layout()
        if l is not None and w.objectName() != "KeepMargins": l.setContentsMargins(0, 0, 0, 0)   # equal inset on both sides
        self.form.addWidget(w); return w

    def add_layout(self, l):
        self.form.addLayout(l)


class FormPanel:
    """Builds a form from OPS-style field specs; edits are pushed to callback(values).
    Field extras: "for": [methods] | "show": f(values)->bool (row visibility) | "enable": f(values)->bool (row greyed out) | "tip".
    `extras={key: [widgets]}` puts extra widgets (e.g. Fit / Sub buttons) to the right of that field."""

    def __init__(self, fields, on_change, extras=None, new_box=True):
        self.fields, self.on_change = fields, on_change
        self.widget = W.QWidget(); self.layout = W.QFormLayout(self.widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.widgets = {}; self.row_widgets = {}
        for f in fields:
            w = make_widget(f); self.widgets[f["key"]] = w
            row = w
            if extras and f["key"] in extras:
                row = W.QWidget(); h = W.QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6); h.addWidget(w, 1)
                for e in extras[f["key"]]: h.addWidget(e)
            self.row_widgets[f["key"]] = row
            self.layout.addRow(f["label"], row)
            sig = w.currentTextChanged if isinstance(w, W.QComboBox) else (w.toggled if isinstance(w, W.QCheckBox) else w.valueChanged)
            sig.connect(lambda *_: self._changed())
        self.new_box = W.QCheckBox("建立新光譜（不覆蓋原始）")
        if new_box:
            self.layout.addRow(self.new_box)
        self.new_box.toggled.connect(lambda *_: self._changed())
        if not new_box: self.new_box.setParent(self.widget); self.new_box.hide()
        self._lock = False
        self._update_rows()

    def _update_rows(self):
        vals = self.values(); m = vals.get("method")
        for f in self.fields:
            row = self.row_widgets[f["key"]]
            vis = True
            if f.get("for") is not None: vis = m in f["for"]
            if f.get("show") is not None: vis = bool(f["show"](vals))
            self.layout.setRowVisible(row, vis)
            if f.get("enable") is not None:
                on = bool(f["enable"](vals)); self.widgets[f["key"]].setEnabled(on)
                lab = self.layout.labelForField(row)
                if lab is not None: lab.setEnabled(on)

    def values(self):
        return {k: read_widget(w) for k, w in self.widgets.items()}

    def wants_new(self):
        return self.new_box.isChecked()

    def set_values(self, vals, new):
        self._lock = True
        for k, w in self.widgets.items():
            if k in vals: write_widget(w, vals[k])
        self.new_box.setChecked(bool(new))
        self._lock = False
        self._update_rows()

    def _changed(self):
        self._update_rows()
        if not self._lock: self.on_change(self.values(), self.wants_new())


class SpectrumBar(W.QScrollArea):
    """Vertical strip of colour swatches, one per spectrum: click = select, Ctrl/Shift = multi-select,
    double-click or right-click = show/hide."""
    clicked = C.Signal(int, object)     # index, keyboard modifiers
    toggled = C.Signal(int)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True); self.setFixedWidth(34)
        self.setHorizontalScrollBarPolicy(C.Qt.ScrollBarAlwaysOff)
        self._host = W.QWidget(); self._lay = W.QVBoxLayout(self._host)
        self._lay.setContentsMargins(4, 4, 4, 4); self._lay.setSpacing(4); self._lay.setAlignment(C.Qt.AlignTop)
        self.setWidget(self._host); self.buttons = []
        self.setStyleSheet(f"QScrollArea{{background:{PALE};border:0;border-left:1px solid {SEP}}}")

    def rebuild(self, items, selected):
        for b in self.buttons: b.setParent(None); b.deleteLater()
        self.buttons = []
        for i, it in enumerate(items):
            b = W.QToolButton(); b.setFixedSize(24, 24); b.setCursor(C.Qt.PointingHandCursor)
            b.setToolTip(f"{it.spec.name}\n點選＝選取（Ctrl/Shift 多選）；雙擊或右鍵＝顯示/隱藏")
            b.clicked.connect(lambda _=False, k=i: self.clicked.emit(k, W.QApplication.keyboardModifiers()))
            b.mouseDoubleClickEvent = lambda ev, k=i: self.toggled.emit(k)
            b.setContextMenuPolicy(C.Qt.CustomContextMenu); b.customContextMenuRequested.connect(lambda _p, k=i: self.toggled.emit(k))
            self._lay.addWidget(b); self.buttons.append(b)
        self.style_buttons(items, selected)

    def style_buttons(self, items, selected):
        for i, (b, it) in enumerate(zip(self.buttons, items)):
            sel = i in selected
            col = it.color if it.visible else "#e8e8ed"
            border = "2px solid #1d1d1f" if sel else ("1px solid #8e8e93" if it.visible else "1px dashed #8e8e93")
            b.setStyleSheet(f"QToolButton{{background:{col};border:{border};border-radius:6px}}QToolButton:hover{{border:2px solid #14599e}}")


def load_font(app):
    """Register the bundled jf open-huninn (粉圓) font (SIL OFL 1.1) and make it the application font. Falls back silently."""
    import os
    from PySide6 import QtGui as G2
    try:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "jf-openhuninn-2.0.ttf")
        fid = G2.QFontDatabase.addApplicationFont(path)
        fams = G2.QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if fams:
            f = app.font(); f.setFamily(fams[0]); app.setFont(f); return fams[0]
    except Exception:
        pass
    return None


def apply_light_palette(app):
    """Force a light palette so Windows dark mode cannot turn panels black / text unreadable."""
    try:
        app.styleHints().setColorScheme(C.Qt.ColorScheme.Light)
    except Exception:
        pass
    pal = G.QPalette()
    for role, col in [(G.QPalette.Window, WINDOW), (G.QPalette.WindowText, INK), (G.QPalette.Base, "#ffffff"),
                      (G.QPalette.AlternateBase, "#f7fafc"), (G.QPalette.Text, INK), (G.QPalette.Button, "#ffffff"),
                      (G.QPalette.ButtonText, INK), (G.QPalette.ToolTipBase, "#ffffff"), (G.QPalette.ToolTipText, INK),
                      (G.QPalette.Highlight, ACCENT), (G.QPalette.HighlightedText, "#ffffff"),
                      (G.QPalette.PlaceholderText, "#6a7f93")]:
        pal.setColor(role, G.QColor(col))
    for role in (G.QPalette.WindowText, G.QPalette.Text, G.QPalette.ButtonText):
        pal.setColor(G.QPalette.Disabled, role, G.QColor("#8a9bab"))
    app.setPalette(pal)
