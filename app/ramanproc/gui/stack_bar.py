"""自動疊曲線（stack view）的手動調整：排序與間距。

Like Origin's Vertical Translate on a stacked graph:
- order: ▲/▼ (Ctrl+↑/↓) moves the selected spectra one place up/down in the stack; 「排序…」 = drag-and-drop list.
- spacing: drag a curve up/down with the 「拖曳間距」 tool (the toolbox's Shift tool acts on the stack while in this view);
  「上方一起移動」 also moves every curve above it, so only that one gap changes. Step ▲▼ (Alt+↑/↓) and 「位移…」 for exact values.
- All of this is display only (each Item keeps `stack_rank`, `stack_dy`); 「寫入資料」 adds the offsets to the Y data.
"""
from __future__ import annotations
import re
import numpy as np
from PySide6 import QtWidgets as W, QtCore as C, QtGui as G


def rank(it, i):
    r = getattr(it, "stack_rank", None)
    return (0, r, i) if r is not None else (1, i, i)          # unranked (new) spectra go on top, in list order


def order(win, only_shown=True):
    """Item indices from the bottom of the stack to the top."""
    idx = [i for i, it in enumerate(win.items) if it.visible or not only_shown]
    return sorted(idx, key=lambda i: rank(win.items[i], i))


def layout(win, idx_bottom_to_top):
    """{item_index: offset}: automatic stacking (gap % of each curve's range) + the curve's own manual offset."""
    gap = getattr(win, "stack_gap", 10.0) / 100.0
    out, top = {}, 0.0
    for i in idx_bottom_to_top:
        y = win.items[i].spec.y
        lo, hi = float(np.nanmin(y)), float(np.nanmax(y))
        base = top - lo
        out[i] = base + float(getattr(win.items[i], "stack_dy", 0.0))
        top = hi + base + gap * (hi - lo)
    return out


def set_order(win, seq_shown):
    """New bottom->top order for the shown spectra; hidden ones keep their slots."""
    full = order(win, only_shown=False)
    shown = set(seq_shown); it_ = iter(seq_shown)
    full = [next(it_) if i in shown else i for i in full]
    for r, i in enumerate(full): win.items[i].stack_rank = r


class OrderDialog(W.QDialog):
    """Drag-and-drop stack order. Top row = top of the stack."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win; self.setWindowTitle("疊圖排序"); self.resize(420, 480)
        lay = W.QVBoxLayout(self)
        lay.addWidget(W.QLabel("拖曳調整順序：最上面一列＝疊圖最上方的曲線。"))
        self.lw = W.QListWidget(); self.lw.setDragDropMode(W.QAbstractItemView.InternalMove)
        self.lw.setSelectionMode(W.QAbstractItemView.ExtendedSelection)
        for i in reversed(order(win)):
            it = win.items[i]
            li = W.QListWidgetItem(it.spec.name); li.setData(C.Qt.UserRole, i)
            pm = G.QPixmap(14, 14); pm.fill(G.QColor(it.color)); li.setIcon(G.QIcon(pm))
            self.lw.addItem(li)
        lay.addWidget(self.lw, 1)
        row = W.QHBoxLayout()
        for text, fn in (("▲", lambda: self._move(-1)), ("▼", lambda: self._move(1)), ("反轉", self._reverse)):
            b = W.QPushButton(text); b.clicked.connect(fn); row.addWidget(b)
        self.cb_sort = W.QComboBox(); self.cb_sort.addItems(["依名稱（自然排序）", "依群組", "依最大強度（大在上）", "依最大強度（小在上）", "依清單順序（第一條在上）"])
        b = W.QPushButton("套用排序"); b.clicked.connect(self._sort)
        row.addStretch(1); row.addWidget(self.cb_sort); row.addWidget(b)
        lay.addLayout(row)
        bb = W.QDialogButtonBox(W.QDialogButtonBox.Ok | W.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); lay.addWidget(bb)

    def _ids(self):
        return [self.lw.item(r).data(C.Qt.UserRole) for r in range(self.lw.count())]

    def _fill(self, ids):
        sel = {li.data(C.Qt.UserRole) for li in self.lw.selectedItems()}
        items = {self.lw.item(r).data(C.Qt.UserRole): self.lw.item(r).clone() for r in range(self.lw.count())}
        self.lw.clear()
        for i in ids:
            self.lw.addItem(items[i]); items[i].setSelected(i in sel)

    def _move(self, d):
        ids = self._ids(); sel = {li.data(C.Qt.UserRole) for li in self.lw.selectedItems()}
        rng = range(len(ids)) if d < 0 else range(len(ids) - 1, -1, -1)
        for r in rng:
            j = r + d
            if ids[r] in sel and 0 <= j < len(ids) and ids[j] not in sel: ids[r], ids[j] = ids[j], ids[r]
        self._fill(ids)

    def _reverse(self):
        self._fill(self._ids()[::-1])

    def _sort(self):
        nat = lambda t: [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", t)]
        its = self.win.items; k = self.cb_sort.currentIndex()
        key = [lambda i: nat(its[i].spec.name), lambda i: (nat(its[i].group or ""), nat(its[i].spec.name)),
               lambda i: -float(np.nanmax(its[i].spec.y)), lambda i: float(np.nanmax(its[i].spec.y)), lambda i: i][k]
        self._fill(sorted(self._ids(), key=key))

    def result_order(self):
        """bottom -> top"""
        return self._ids()[::-1]


class StackBar(W.QFrame):
    """Shown above the plot while the view is 自動疊."""

    def __init__(self, win):
        super().__init__()
        self.win = win; self.setObjectName("StackBar")
        h = W.QHBoxLayout(self); h.setContentsMargins(6, 2, 6, 2); h.setSpacing(4)
        h.addWidget(W.QLabel("疊圖："))
        self.sp_gap = W.QDoubleSpinBox(); self.sp_gap.setRange(-100, 500); self.sp_gap.setDecimals(0); self.sp_gap.setSingleStep(5)
        self.sp_gap.setSuffix(" %"); self.sp_gap.setValue(10); self.sp_gap.setToolTip("自動間距：各曲線之間留白＝下方曲線強度範圍的百分比")
        self.sp_gap.valueChanged.connect(self._gap_changed)
        h.addWidget(W.QLabel("間距")); h.addWidget(self.sp_gap)
        self._sep(h)
        h.addWidget(W.QLabel("順序"))
        self._btn(h, "▲", "選取的光譜在疊圖中往上移一層（Ctrl+↑）", lambda: self.move(+1), "Ctrl+Up")
        self._btn(h, "▼", "選取的光譜在疊圖中往下移一層（Ctrl+↓）", lambda: self.move(-1), "Ctrl+Down")
        self._btn(h, "排序…", "拖曳排序清單／依名稱、群組、強度排序／反轉", self.order_dialog)
        self._sep(h)
        self.b_drag = self._btn(h, "拖曳間距", "在圖上按住曲線上下拖曳，手動調整它的位置（Vertical Translate）", self.drag_tool)
        self.b_drag.setCheckable(True)
        self.cb_above = W.QCheckBox("上方一起移動"); self.cb_above.setChecked(True)
        self.cb_above.setToolTip("勾選：拖曳/微調某條曲線時，它上方的曲線也一起移動（只改變這一個間距）；不勾：只移動這一條")
        h.addWidget(self.cb_above)
        self._sep(h)
        h.addWidget(W.QLabel("微調"))
        self.sp_step = W.QDoubleSpinBox(); self.sp_step.setRange(0.1, 200); self.sp_step.setDecimals(1); self.sp_step.setValue(5); self.sp_step.setSuffix(" %")
        self.sp_step.setToolTip("每按一次 ▲▼ 移動的距離＝該曲線強度範圍的百分比（Alt+↑/↓）")
        h.addWidget(self.sp_step)
        self._btn(h, "上", "選取的光譜往上微調（Alt+↑）", lambda: self.step(+1), "Alt+Up")
        self._btn(h, "下", "選取的光譜往下微調（Alt+↓）", lambda: self.step(-1), "Alt+Down")
        self._btn(h, "位移…", "輸入選取光譜的位移量（Y 單位）", self.shift_dialog)
        self._sep(h)
        self._btn(h, "重設", "清除手動位移與排序，回到自動疊圖", self.reset)
        self._btn(h, "寫入資料", "把目前疊圖的位移加到光譜 Y 資料（可 Ctrl+Z 復原），並切回多曲線顯示", self.apply_to_data)
        h.addStretch(1)
        self.setVisible(False)

    def _btn(self, h, text, tip, fn, key=None):
        b = W.QToolButton(); b.setText(text); b.setToolTip(tip); b.clicked.connect(lambda _=False: fn()); h.addWidget(b)
        if key:
            sc = G.QShortcut(G.QKeySequence(key), self); sc.setContext(C.Qt.WindowShortcut); sc.activated.connect(fn)
        return b

    def _sep(self, h):
        f = W.QFrame(); f.setFrameShape(W.QFrame.VLine); f.setFrameShadow(W.QFrame.Sunken); h.addWidget(f)

    # ------------------------------------------------------------------ actions
    def _targets(self):
        sel = [i for i in self.win.selected_idx() if self.win.items[i].visible]
        if not sel: self.win.statusBar().showMessage("請先在 Browser 或色塊條選取要移動的光譜")
        return sel

    def _gap_changed(self, v):
        self.win.stack_gap = float(v)
        if self.win.view_mode == "stack": self.win.redraw()

    def move(self, d):
        """d=+1 up, -1 down, for the selected spectra (block moves keep their relative order)."""
        sel = set(self._targets())
        if not sel: return
        seq = order(self.win)
        rng = range(len(seq) - 1, -1, -1) if d > 0 else range(len(seq))
        moved = False
        for r in rng:
            j = r + d
            if seq[r] in sel and 0 <= j < len(seq) and seq[j] not in sel: seq[r], seq[j] = seq[j], seq[r]; moved = True
        if not moved: return
        self.win.push_undo(); set_order(self.win, seq); self.win.redraw()

    def order_dialog(self):
        if not self.win.items: return
        dlg = OrderDialog(self.win)
        if dlg.exec() != W.QDialog.Accepted: return
        self.win.push_undo(); set_order(self.win, dlg.result_order()); self.win.redraw(); self.win.full_scale()

    def drag_tool(self):
        from . import tools as T
        on = self.b_drag.isChecked()
        self.win.toolbox.select(T.SHIFT if on else T.POINTER)

    def sync_tool(self, tid):
        from . import tools as T
        self.b_drag.blockSignals(True); self.b_drag.setChecked(tid == T.SHIFT); self.b_drag.blockSignals(False)

    def _span(self, i):
        y = self.win.items[i].spec.y
        return float(np.nanmax(y) - np.nanmin(y)) or 1.0

    def add_offset(self, idx, dy_of):
        """dy_of(i) -> offset to add to curve i; with 上方一起移動 the curves above the lowest moved one get it too."""
        seq = order(self.win); moved = {}
        for i in idx:
            d = dy_of(i)
            for j in (seq[seq.index(i):] if self.cb_above.isChecked() and i in seq else [i]):
                moved[j] = moved.get(j, 0.0) + d
        for j, d in moved.items():
            self.win.items[j].stack_dy = float(getattr(self.win.items[j], "stack_dy", 0.0)) + d

    def step(self, d):
        idx = self._targets()
        if not idx: return
        self.win.push_undo()
        self.add_offset(idx, lambda i: d * self.sp_step.value() / 100.0 * self._span(i))
        self.win.redraw()

    def shift_dialog(self):
        idx = self._targets()
        if not idx: return
        v, ok = W.QInputDialog.getDouble(self, "位移 Shift Curve", "Y 位移量（正值往上）：", 0.0, -1e12, 1e12, 4)
        if not ok or v == 0: return
        self.win.push_undo(); self.add_offset(idx, lambda i: v); self.win.redraw()

    def reset(self):
        self.win.push_undo()
        for it in self.win.items: it.stack_rank = None; it.stack_dy = 0.0
        self.win.redraw(); self.win.full_scale()

    def apply_to_data(self):
        w = self.win
        seq = order(w)
        if not seq: return
        off = layout(w, seq)
        w.push_undo()
        for i in seq:
            it = w.items[i]; o = off[i]
            s = it.spec.with_y(it.spec.y + o, f"stack(offset={o:.6g})"); s.name = it.spec.name; it.spec = s
            it.stack_dy = 0.0
        w.set_view_mode("multi"); w.refresh()
        w.statusBar().showMessage(f"已把疊圖位移寫入 {len(seq)} 條光譜的 Y 資料（Ctrl+Z 復原）")


class StackDrag:
    """Shift-tool drag while the view is stacked: grab the curve nearest the press point and move it (display only)."""

    def __init__(self, win, p0):
        self.win, self.p0 = win, p0
        seq = order(win); self.off = layout(win, seq)
        best = None
        (x0, x1), (y0, y1) = win.pi.viewRange(); sy = max(y1 - y0, 1e-12)
        for i in seq:
            s = win.items[i].spec
            if not (s.x[0] <= p0.x() <= s.x[-1]): continue
            d = abs(float(np.interp(p0.x(), s.x, s.y)) + self.off[i] - p0.y()) / sy
            if best is None or d < best[0]: best = (d, i)
        self.i = best[1] if best else None
        if self.i is None: return
        above = win.stackbar.cb_above.isChecked()
        self.moving = seq[seq.index(self.i):] if above else [self.i]
        lw = win.listw; li = lw.item(self.i)                  # select the grabbed curve (so ▲▼ act on it next)
        if li is not None:
            lw.blockSignals(True); lw.clearSelection(); li.setSelected(True); lw.blockSignals(False); win._selection_changed()

    def move(self, p):
        if self.i is None: return
        dy = p.y() - self.p0.y()
        for j in self.moving:
            c = self.win.curves.get(id(self.win.items[j]))
            if c is not None: c.setData(self.win._xmap(self.win.items[j].spec.x), self.win.items[j].spec.y + self.off[j] + dy)
        self.win.statusBar().showMessage(f"{self.win.items[self.i].spec.name}：ΔY = {dy:.4g}" + ("（含上方曲線）" if len(self.moving) > 1 else ""))

    def release(self, p):
        if self.i is None: return
        dy = p.y() - self.p0.y()
        if dy:
            self.win.push_undo()
            for j in self.moving:
                it = self.win.items[j]; it.stack_dy = float(getattr(it, "stack_dy", 0.0)) + dy
        self.win.redraw()
