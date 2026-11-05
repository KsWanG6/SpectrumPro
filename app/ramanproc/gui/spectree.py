"""Browser list as a tree: group name on top, spectra as branches (check / select / fold per group)."""
from PySide6 import QtWidgets as W, QtCore as C, QtGui as G

IDX = C.Qt.UserRole          # leaf  -> spectrum index
GRP = C.Qt.UserRole + 1      # header-> group name ("" = ungrouped)


class SpecTree(W.QTreeWidget):
    """QTreeWidget that still answers the small QListWidget API the main window uses
    (item(i) / row(li) / count() / selectedItems() / selectAll()), where i = spectrum index."""

    def __init__(self):
        super().__init__()
        self.setHeaderHidden(True); self.setRootIsDecorated(True); self.setIndentation(18)
        self.setSelectionMode(W.QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True); self.setUniformRowHeights(True); self.setExpandsOnDoubleClick(True)
        self._leaves = {}
        self.collapsed = set()                     # group names the user folded
        self._building = False
        self.itemExpanded.connect(lambda it: self._fold(it, False))
        self.itemCollapsed.connect(lambda it: self._fold(it, True))

    def _fold(self, it, folded):
        if self._building or it.parent() is not None or it.data(0, IDX) is not None: return
        g = it.data(0, GRP)
        (self.collapsed.add if folded else self.collapsed.discard)(g)

    # ---- API used by MainWindow ----
    def count(self): return len(self._leaves)
    def item(self, i): return self._leaves.get(i)
    def row(self, li):
        v = li.data(0, IDX) if li is not None else None
        return -1 if v is None else v
    def is_header(self, li): return li is not None and li.data(0, IDX) is None
    def selectedItems(self):
        out = []
        for it in super().selectedItems():
            if self.is_header(it):
                out += [it.child(k) for k in range(it.childCount())]
            else: out.append(it)
        seen = set(); res = []
        for it in out:
            if id(it) not in seen: seen.add(id(it)); res.append(it)
        return res
    def selectAll(self):
        self.clearSelection()
        for it in self._leaves.values(): it.setSelected(True)

    def rebuild(self, rows):
        """rows: [(index, group, text, color, visible, selected, tooltip)] in spectrum order."""
        self._building = True; self.setUpdatesEnabled(False)
        try:
            self.clear(); self._leaves = {}
            groups = []
            for r in rows:
                if r[1] not in groups: groups.append(r[1])
            flat = groups == [""]                     # nobody is grouped -> plain list
            heads = {}
            for g in groups:
                if flat: break
                h = W.QTreeWidgetItem(self); h.setText(0, g or "未分組"); h.setData(0, GRP, g)
                f = h.font(0); f.setBold(True); h.setFont(0, f)
                h.setFlags((h.flags() | C.Qt.ItemIsUserCheckable) & ~C.Qt.ItemIsDragEnabled)
                heads[g] = h
            for (i, g, text, color, vis, sel, tip) in rows:
                li = W.QTreeWidgetItem(self if flat else heads[g]); li.setText(0, text); li.setData(0, IDX, i)
                li.setFlags(li.flags() | C.Qt.ItemIsUserCheckable)
                li.setCheckState(0, C.Qt.Checked if vis else C.Qt.Unchecked); li.setForeground(0, G.QColor(color))
                if tip: li.setToolTip(0, tip)
                self._leaves[i] = li
                if sel: li.setSelected(True)
            for g, h in heads.items():
                self.update_header(h); h.setExpanded(g not in self.collapsed)
        finally:
            self._building = False; self.setUpdatesEnabled(True)

    def update_header(self, h):
        n = h.childCount(); on = sum(h.child(k).checkState(0) == C.Qt.Checked for k in range(n))
        h.setText(0, f"{h.data(0, GRP) or '未分組'}  ({on}/{n})")
        h.setCheckState(0, C.Qt.Unchecked if on == 0 else C.Qt.Checked if on == n else C.Qt.PartiallyChecked)

    def headers(self):
        return [self.topLevelItem(k) for k in range(self.topLevelItemCount()) if self.is_header(self.topLevelItem(k))]

    def set_all_folded(self, folded):
        for h in self.headers(): h.setExpanded(not folded)
