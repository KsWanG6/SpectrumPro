"""Mouse tools: custom ViewBox + toolbox widget."""
import pyqtgraph as pg
from PySide6 import QtWidgets as W, QtCore as C

# tool ids
POINTER, ZOOM, SHIFT, MULTIPLY, XY, CURSOR, TEXT, IMAGE = "pointer", "zoom", "shift", "multiply", "xy", "cursor", "text", "image"
DRAW_STRIP, REMOVE_STRIP, LABEL_PEAK = "draw_strip", "remove_strip", "label_peak"
XLINE = "xline"
DXLINE = "dxline"
ERASER = "eraser"
BASELINE = "baseline_pts"

DRAG_TOOLS = {SHIFT, MULTIPLY, DRAW_STRIP, ERASER, BASELINE, LABEL_PEAK, DXLINE}
CLICK_TOOLS = {BASELINE, ERASER, XLINE, DXLINE, XY, CURSOR, TEXT, IMAGE, REMOVE_STRIP, LABEL_PEAK}

TOOL_TIPS = {
    BASELINE: "手動基線：點一下加入基線錨點（靠近曲線會自動貼齊）；拖曳錨點調整；點已有的錨點則刪除。到 Processing → Baseline 按「套用手動基線」",
    ERASER: "橡皮擦（去宇宙射線）：點一下尖峰，或拖曳框住一段，把該範圍用中位數濾波抹掉尖峰（窗口取自 Processing 面板的去尖峰設定）",
    XLINE: "點一下在該處拉一條垂直標線並顯示 X 值（再點移動）；相鄰資料的 Y 值一併顯示",
    DXLINE: "雙 X 標線：按住拖曳＝一次拉出兩條線（起點與放開處）；或點兩下（第一下放第 1 條、第二下放第 2 條）；已有兩條時，點一下＝移動較近的那條。"
            "兩條線都可直接拖動；狀態列顯示 X₁、X₂、ΔX，以及每條光譜在兩線的 Y 與兩線之間的面積",
    POINTER: "拖曳平移；滾輪縮放；右鍵選單",
    ZOOM: "拖曳框選放大；右鍵拖曳縮放；使用「檢視 → 全範圍」還原",
    SHIFT: "在圖上按住拖曳：垂直平移選取（或最上層）光譜，放開後套用",
    MULTIPLY: "在圖上按住拖曳：以拖曳起點的 Y 值為基準，把它拉到放開位置，等比例縮放 Y",
    XY: "游標處顯示十字線與 X、Y 數值；點一下把座標顯示於狀態列",
    CURSOR: "點一下：吸附到最近的資料點並標示 X、Y",
    TEXT: "點一下放置文字（可拖曳移動）",
    IMAGE: "點一下選擇圖片檔並放置在圖上",
    DRAW_STRIP: "按住拖曳畫出區間（可多個）",
    REMOVE_STRIP: "點擊區間內部以移除該區間",
    LABEL_PEAK: "點擊峰附近：標示附近最高點的 X 位置；點已有的標示＝刪除；拖曳標示＝移動位置",
}


class ToolViewBox(pg.ViewBox):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.menu.addSeparator(); a = self.menu.addAction("移除頁面所有標記"); a.triggered.connect(lambda: self.win.clear_all_marks())

    def mouseDragEvent(self, ev, axis=None):
        if self.win.tool in DRAG_TOOLS and ev.button() == C.Qt.LeftButton:
            ev.accept()
            cur = self.mapToView(ev.pos())
            if ev.isStart():
                self.win.tool_press(self.mapToView(ev.buttonDownPos()))
            if ev.isFinish():
                self.win.tool_release(cur)
            else:
                self.win.tool_move(cur)
            return
        if self.win.tool in CLICK_TOOLS:
            ev.ignore()
            return
        super().mouseDragEvent(ev, axis)

    def mouseClickEvent(self, ev):
        if ev.button() == C.Qt.LeftButton and self.win.tool in CLICK_TOOLS:
            ev.accept()
            self.win.tool_click(self.mapToView(ev.pos()))
            return
        super().mouseClickEvent(ev)


class Toolbox(W.QWidget):
    """Vertical icon strip (LabSpec-style). One exclusive group of checkable tool buttons."""
    toolChanged = C.Signal(str)

    LAYOUT = [
        [("X 標線", XLINE), ("雙 X 標線（一次標兩條）", DXLINE), ("框選區間", DRAW_STRIP), ("十字線 XY", XY), ("放大", ZOOM),
         ("移動 Y 軸（Shift）", SHIFT), ("移動全圖（平移）", POINTER), ("標文字", TEXT), ("標峰值", LABEL_PEAK), ("橡皮擦（去宇宙射線）", ERASER), ("手動基線（加點）", BASELINE)],
        [("Multiply", MULTIPLY), ("資料點游標", CURSOR), ("插入圖片", IMAGE), ("移除區間", REMOVE_STRIP)],
    ]

    def __init__(self):
        super().__init__()
        from . import icons as IC
        lay = W.QVBoxLayout(self)
        lay.setContentsMargins(3, 4, 3, 4); lay.setSpacing(3)
        self.group = W.QButtonGroup(self); self.group.setExclusive(True)
        self.buttons = {}
        for gi, items in enumerate(self.LAYOUT):
            if gi:
                line = W.QFrame(); line.setFrameShape(W.QFrame.HLine); line.setObjectName("ToolSep"); lay.addWidget(line)
            for text, tid in items:
                b = W.QToolButton(); b.setCheckable(True); b.setAutoRaise(True)
                b.setIcon(IC.ICONS["tool_" + tid]()); b.setIconSize(C.QSize(26, 26)); b.setFixedSize(36, 36)
                b.setToolTip(f"<b>{text}</b><br>{TOOL_TIPS[tid]}")
                b.clicked.connect(lambda _=False, t=tid: self.select(t))
                self.group.addButton(b); lay.addWidget(b)
                self.buttons.setdefault(tid, []).append(b)
        lay.addStretch(1)
        self.select(POINTER)

    def select(self, tid):
        for t, bs in self.buttons.items():
            for b in bs: b.setChecked(t == tid)
        self.toolChanged.emit(tid)
