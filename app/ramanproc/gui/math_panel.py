"""Spectral Math panel (LabSpec-style): One object / Two objects / Combine data."""
from __future__ import annotations
import PySide6.QtWidgets as W
import PySide6.QtCore as C
from .. import mathexpr as M
from . import theme as TH
from . import icons as IC

HELP = ("One object：對每條選取的光譜套用運算式。Y 與 X 是該光譜的陣列，例如 Y/5、log10(Y)、sqrt(Y)。\n"
        "　X 欄可改 X 軸（例如 X*1.001+2）。\n"
        "Two objects：A 是目前選取的光譜、B 是用 ▶ 按鈕指定的第二條光譜（B 會內插到 A 的 X 軸，且 B 的 X 範圍須涵蓋 A）。例如 A-B、A/B、A-0.8*B。\n"
        "Combine data：把 X 範圍不同（可部分重疊）的光譜接成一條；勾選 Adjust 時，後段會依重疊區間縮放並平移到與前段相符，重疊處線性漸變。\n"
        "可用函數：sqrt log ln log10 log2 exp sin cos tan abs pow min max；運算符 + - * / ^ %。\n"
        "（運算式語法與 Combine 的調整方式是本軟體自行定義，未與其他軟體比對。）")


class MathPanel(W.QWidget):
    def __init__(self, win):
        super().__init__(); self.win = win; self.b_spec = None
        lay = W.QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
        sec = TH.Section("Spectral Math 光譜數學", help=HELP)
        # One object
        sec.add(self._cap("One object"))
        f = W.QFormLayout(); f.setContentsMargins(0, 0, 0, 0)
        self.x_eq = W.QLineEdit("X"); self.y_eq = W.QLineEdit("Y/5")
        self.x_eq.setToolTip("X 軸運算式（保持 X 即不改變）"); self.y_eq.setToolTip("Y 運算式，例如 Y/5、log10(Y)")
        f.addRow("X", self.x_eq)
        row = W.QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0); row.addWidget(self.y_eq, 1)
        self.one_btn = self._run_btn("Apply equation"); self.one_btn.clicked.connect(self.run_one); row.addWidget(self.one_btn)
        rw = W.QWidget(); rw.setLayout(row); f.addRow("Y", rw)
        w = W.QWidget(); w.setLayout(f); sec.add(w)
        sec.add(self._line())
        # Two objects
        sec.add(self._cap("Two objects"))
        f2 = W.QFormLayout(); f2.setContentsMargins(0, 0, 0, 0)
        self.ab_eq = W.QLineEdit("A-B"); self.ab_eq.setToolTip("A = 選取的光譜；B = 指定的第二條光譜")
        row = W.QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0); row.addWidget(self.ab_eq, 1)
        self.two_btn = self._run_btn("Apply equation"); self.two_btn.clicked.connect(self.run_two); row.addWidget(self.two_btn)
        rw = W.QWidget(); rw.setLayout(row); f2.addRow("A =", rw)
        self.b_name = W.QLineEdit(); self.b_name.setReadOnly(True); self.b_name.setPlaceholderText("（尚未指定 B）")
        row = W.QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0); row.addWidget(self.b_name, 1)
        self.pick_btn = self._icon_btn("pick_b", "把目前選取的光譜指定為 B"); self.pick_btn.clicked.connect(self.pick_b)
        self.clear_btn = self._icon_btn("clear_b", "清除 B"); self.clear_btn.clicked.connect(self.clear_b)
        row.addWidget(self.pick_btn); row.addWidget(self.clear_btn)
        rw = W.QWidget(); rw.setLayout(row); f2.addRow("B =", rw)
        w = W.QWidget(); w.setLayout(f2); sec.add(w)
        sec.add(self._line())
        # Combine
        sec.add(self._cap("Combine data"))
        row = W.QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0)
        self.adjust = W.QCheckBox("Adjust overlapping intensities"); self.adjust.setChecked(True)
        self.comb_btn = self._run_btn("Combine"); self.comb_btn.clicked.connect(self.run_combine)
        row.addWidget(self.adjust, 1); row.addWidget(self.comb_btn)
        rw = W.QWidget(); rw.setLayout(row); sec.add(rw)
        lay.addWidget(sec)

    # -- small builders
    def _cap(self, t):
        l = W.QLabel(f"<b>{t}</b>"); return l

    def _line(self):
        l = W.QFrame(); l.setFrameShape(W.QFrame.HLine); l.setStyleSheet("color:#d2d2d7"); return l

    def _run_btn(self, tip):
        b = W.QToolButton(); b.setText("▶"); b.setToolTip(tip); b.setFixedSize(28, 24); return b

    def _icon_btn(self, name, tip):
        b = W.QToolButton(); b.setIcon(IC.ICONS[name]()); b.setIconSize(C.QSize(18, 18)); b.setToolTip(tip); b.setFixedSize(28, 24); return b

    # -- actions
    def run_one(self):
        idx = self.win.targets()
        if not idx: return
        x, y = self.x_eq.text().strip() or "X", self.y_eq.text().strip() or "Y"
        eq = (f"X = {x}; " if x.replace(" ", "").upper() != "X" else "") + f"Y = {y}"
        self.win._apply(idx, lambda s: M.apply_one(s, eq), "Math", False)

    def pick_b(self):
        idx = self.win.selected_idx()
        if len(idx) != 1:
            W.QMessageBox.warning(self.win, "Two objects", "請只選取 1 條光譜作為 B。"); return
        self.b_spec = self.win.items[idx[0]].spec; self.b_name.setText(self.b_spec.name)

    def clear_b(self):
        self.b_spec = None; self.b_name.clear()

    def run_two(self):
        if self.b_spec is None:
            W.QMessageBox.warning(self.win, "Two objects", "請先選取一條光譜，按 ▶ 指定為 B。"); return
        idx = [i for i in self.win.targets() if self.win.items[i].spec is not self.b_spec]
        if not idx: return
        eq = self.ab_eq.text().strip(); b = self.b_spec
        try:
            res = [(i, M.apply_two(self.win.items[i].spec, b, eq)) for i in idx]
        except Exception as ex:
            W.QMessageBox.warning(self.win, "Two objects", str(ex)); return
        self.win.push_undo()
        for i, new in res:
            new.name = f"{self.win.items[i].spec.name}[{eq}]"; self.win.add_spectrum(new, group=self.win.items[i].group)
        self.win.refresh(); self.win.statusBar().showMessage(f"Two objects：{eq}，產生 {len(res)} 條新光譜")

    def run_combine(self):
        idx = self.win.targets(2)
        if not idx: return
        try:
            new = M.combine([self.win.items[i].spec for i in idx], self.adjust.isChecked())
        except Exception as ex:
            W.QMessageBox.warning(self.win, "Combine", str(ex)); return
        self.win.push_undo(); self.win.add_spectrum(new, group=self.win.group_of(idx)); self.win.refresh()
        self.win.statusBar().showMessage(f"Combine：已接合 {len(idx)} 條光譜")
