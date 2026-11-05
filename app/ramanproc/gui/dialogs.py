from PySide6 import QtWidgets as W, QtCore as C


class SliderSpin(W.QWidget):
    """Number box + slider (as in the LabSpec panels). `odd=True` forces odd values."""
    valueChanged = C.Signal(int)

    def __init__(self, lo, hi, value, step=1, odd=False):
        super().__init__()
        self.odd = odd
        self.spin = W.QSpinBox(); self.spin.setRange(lo, hi); self.spin.setSingleStep(step); self.spin.setFixedWidth(64)
        self.slider = W.QSlider(C.Qt.Horizontal); self.slider.setRange(lo, hi); self.slider.setSingleStep(step); self.slider.setPageStep(max(step, (hi - lo) // 10))
        lay = W.QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(6); lay.addWidget(self.spin); lay.addWidget(self.slider, 1)
        self.spin.valueChanged.connect(self._from_spin); self.slider.valueChanged.connect(self._from_slider)
        self.setValue(value)

    def _fix(self, v):
        if self.odd and v % 2 == 0: v = v + 1 if v < self.spin.maximum() else v - 1
        return v

    def _from_spin(self, v):
        v = self._fix(v)
        if v != self.spin.value(): self.spin.blockSignals(True); self.spin.setValue(v); self.spin.blockSignals(False)
        self.slider.blockSignals(True); self.slider.setValue(v); self.slider.blockSignals(False); self.valueChanged.emit(v)

    def _from_slider(self, v):
        v = self._fix(v); self.spin.blockSignals(True); self.spin.setValue(v); self.spin.blockSignals(False)
        if v != self.slider.value(): self.slider.blockSignals(True); self.slider.setValue(v); self.slider.blockSignals(False)
        self.valueChanged.emit(v)

    def value(self): return self.spin.value()

    def setValue(self, v):
        v = self._fix(int(v)); self.spin.blockSignals(True); self.slider.blockSignals(True)
        self.spin.setValue(v); self.slider.setValue(v); self.spin.blockSignals(False); self.slider.blockSignals(False)
        self.valueChanged.emit(self.spin.value())

    def setEnabled(self, on):
        super().setEnabled(on)


def make_widget(f):
    t = f["type"]
    if t == "combo":
        w = W.QComboBox(); w.addItems([str(o) for o in f["options"]])
        if "default" in f: w.setCurrentText(str(f["default"]))
    elif t == "slider":
        w = SliderSpin(f.get("min", 0), f.get("max", 100), f.get("default", 0), f.get("step", 1), f.get("odd", False))
    elif t == "int":
        w = W.QSpinBox(); w.setRange(f.get("min", -10**9), f.get("max", 10**9)); w.setValue(f.get("default", 0))
        if "step" in f: w.setSingleStep(f["step"])
    elif t == "float":
        w = W.QDoubleSpinBox(); w.setDecimals(f.get("decimals", 4)); w.setRange(f.get("min", -1e12), f.get("max", 1e12))
        w.setValue(f.get("default", 0.0)); w.setSingleStep(f.get("step", 1.0))
    else:
        w = W.QCheckBox(); w.setChecked(bool(f.get("default", False)))
        if f.get("text"): w.setText(f["text"])
    if f.get("tip"): w.setToolTip(f["tip"])
    return w


def read_widget(w):
    if isinstance(w, W.QComboBox): return w.currentText()
    if isinstance(w, W.QCheckBox): return w.isChecked()
    return w.value()


def write_widget(w, v):
    if isinstance(w, W.QComboBox): w.setCurrentText(str(v))
    elif isinstance(w, W.QCheckBox): w.setChecked(bool(v))
    else: w.setValue(v)


class ParamDialog(W.QDialog):
    """Generic parameter dialog. fields: list of dicts
       {key, label, type: 'combo'|'int'|'float'|'check', options(for combo), default, min, max, step}"""

    def __init__(self, title, fields, parent=None, allow_new=True, note=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.widgets = {}
        form = W.QFormLayout(self)
        if note:
            lab = W.QLabel(note); lab.setWordWrap(True); form.addRow(lab)
        for f in fields:
            w = make_widget(f)
            self.widgets[f["key"]] = w
            form.addRow(f["label"], w)
        self.create_new = W.QCheckBox("建立新光譜（保留原光譜）") if allow_new else None
        if self.create_new:
            form.addRow(self.create_new)
        bb = W.QDialogButtonBox(W.QDialogButtonBox.Ok | W.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self):
        out = {}
        for k, w in self.widgets.items():
            if isinstance(w, W.QComboBox): out[k] = w.currentText()
            elif isinstance(w, W.QCheckBox): out[k] = w.isChecked()
            else: out[k] = w.value()
        return out

    def wants_new(self):
        return bool(self.create_new and self.create_new.isChecked())
