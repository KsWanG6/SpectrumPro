"""SpectrumPro GUI - desktop front-end for the ramanproc library."""
import os, sys, copy
import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets as W, QtCore as C, QtGui as G

import ramanproc as rp
from ramanproc import Spectrum
from .dialogs import ParamDialog
from ramanproc import baselines as BL, filters as FL
from .math_panel import MathPanel
from .spectree import SpecTree, IDX as TREE_IDX
from .peak_section import PeakSection
from .figstyle import StyledAxis, FigureStyleSection, ASPECTS, EXPORT_BASE_W
from . import tools as T
from . import icons as IC
from . import theme as TH

APP_NAME = "SpectrumPro"
APP_VERSION = "2.3"
APP_AUTHOR = "Kuan-Syun Wang"


def icon_path(name="spectrumpro.png"):
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", name)

PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22"]


class Item:
    def __init__(self, spec: Spectrum, color):
        self.spec, self.color, self.visible = spec, color, True
        self.group = ""           # user group label
        self.raw = spec           # spectrum as loaded (for before/after comparison)
        self.stage = {}           # {"smooth": Spectrum, "base": (x, y), "pre_base": Spectrum}


class MainWindow(W.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}")
        self.resize(1400, 850)
        self.items: list[Item] = []
        self.params = {}           # last-used parameters per operation (for one-click use)
        self.undo, self.redo = [], []
        self.view_mode = "multi"
        self.ws_states = [self._new_ws_state("工作區 1")]; self.ws_cur = 0
        self.bl_pts = []; self.bl_fit = None; self.bl_clip = None
        self.dxlines = []; self.dx_region = None   # double X-line cursor
        self.curves, self.labels = {}, []
        self.marks = []           # fit curves etc. drawn by the Peaks section
        self.strips = []
        self.annots = []          # [(kind, item)] text / image annotations
        self.tool = T.POINTER
        self._drag = None
        self.dcursor = []         # data-cursor marker items
        self._color_i = 0
        self._dirty = False; self._autosave_err = None
        self._build_ui()
        self._build_menus()
        self._build_toolbar()
        self.autosave_timer = C.QTimer(self); self.autosave_timer.setInterval(30000)
        self.autosave_timer.timeout.connect(self.autosave); self.autosave_timer.start()
        self.statusBar().showMessage("就緒")

    def closeEvent(self, ev):
        """Closing the window ends the whole program (no background python process left behind), even if cleanup fails."""
        self._closing = True
        try: self.autosave_timer.stop()
        except Exception: pass
        try: self.clear_recovery()
        except Exception: pass
        for w_ in W.QApplication.topLevelWidgets():
            if w_ is not self:
                try: w_.close()
                except Exception: pass
        ev.accept()
        app = W.QApplication.instance()
        if app is not None: app.quit()
        if getattr(self, "_hard_exit", False):           # real run only: watchdog in case something keeps the process alive
            import threading
            t = threading.Timer(2.0, lambda: os._exit(0)); t.daemon = True; t.start()

    # ---------------- UI ----------------
    def _build_ui(self):
        pg.setConfigOptions(antialias=True, background="w", foreground="k")
        app = W.QApplication.instance()
        if app is not None and not app.property("ramanproc_styled"):        # once per process: re-styling re-polishes every live window
            app.setStyle("Fusion"); TH.load_font(app); TH.apply_light_palette(app); app.setProperty("ramanproc_styled", True)
        self.setStyleSheet(TH.STYLE)
        self.vb = T.ToolViewBox(self)
        self.plot = pg.PlotWidget(viewBox=self.vb, axisItems={o: StyledAxis(o) for o in ('bottom', 'left', 'top', 'right')})
        self.pi = self.plot.getPlotItem()
        self.pi.setLabel("bottom", "Raman Shift (cm⁻¹)")
        self.pi.setLabel("left", "Intensity")
        for _a in ("left", "bottom"): self.pi.getAxis(_a).enableAutoSIPrefix(False)      # never show "(x0.001)" for absorbance etc.
        self.pi.showGrid(x=True, y=True, alpha=0.25)
        self.legend = self.pi.addLegend(offset=(-10, 10))
        dash = pg.mkPen("#888", style=C.Qt.DashLine)
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=dash)
        self.hline = pg.InfiniteLine(angle=0, movable=False, pen=dash)
        self.pi.addItem(self.vline, ignoreBounds=True); self.pi.addItem(self.hline, ignoreBounds=True)
        self.hline.setVisible(False)
        self.plot.scene().sigMouseMoved.connect(self._mouse_moved)
        self.plot.viewport().installEventFilter(self); self.installEventFilter(self)     # hide the cursor read-out when the pointer leaves the plot

        # ---- centre: tabs (Spectra / Data), titled frame ----
        self.center = W.QTabWidget()
        frame = W.QWidget(); fl = W.QVBoxLayout(frame); fl.setContentsMargins(0, 0, 0, 0); fl.setSpacing(0)
        self.plot_title = W.QLabel("Spectra"); self.plot_title.setObjectName("PanelTitle")
        self.wsbar = W.QTabBar(); self.wsbar.setTabsClosable(True); self.wsbar.setExpanding(False); self.wsbar.setDrawBase(False)
        self.wsbar.addTab("工作區 1"); self.wsbar.setObjectName("WsBar")
        self.wsbar.currentChanged.connect(self.switch_workspace)
        self.wsbar.tabCloseRequested.connect(self.close_workspace)
        self.wsbar.tabBarDoubleClicked.connect(self.rename_workspace)
        self.wsbar.setToolTip("工作區：每個工作區有自己的光譜、復原記錄與標註；雙擊分頁可重新命名")
        wsadd = W.QToolButton(); wsadd.setText("＋ 新工作區"); wsadd.clicked.connect(lambda: self.add_workspace())
        wsrow = W.QHBoxLayout(); wsrow.setContentsMargins(4, 4, 4, 0); wsrow.addWidget(self.wsbar); wsrow.addWidget(wsadd); wsrow.addStretch(1)
        fl.addLayout(wsrow)
        fl.addWidget(self.plot_title)
        row = W.QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(0)
        self.specbar = TH.SpectrumBar()
        self.specbar.clicked.connect(self._bar_clicked); self.specbar.toggled.connect(self._bar_toggled)
        row.addWidget(self.plot, 1); row.addWidget(self.specbar)
        fl.addLayout(row, 1)
        self.center.addTab(frame, "Spectra")
        self.data_table = W.QTableWidget(0, 2); self.data_table.setHorizontalHeaderLabels(["X", "Y"])
        self.data_table.setAlternatingRowColors(True)
        self.center.addTab(self.data_table, "Data")
        from .quant_panel import QuantPanel
        self.quant = QuantPanel(self)
        self.center.addTab(self.quant, "Quantification 定量")
        from .peak_panel import PeakPanel
        self.peaks = PeakPanel(self)
        self.center.insertTab(2, self.peaks, "Peak Analysis 峰分析")
        from .rsd_panel import RsdPanel
        self.rsd = RsdPanel(self)
        self.center.insertTab(3, self.rsd, "RSD 重現性")
        self.peak_table = self.peaks.table; self.pk_rel = self.peaks.rel; self.pk_dist = self.peaks.dist
        self.center.currentChanged.connect(lambda _: self._fill_data_table())
        self.center.currentChanged.connect(self._center_changed)
        self.setCentralWidget(self.center)

        # ---- left icon strip ----
        self.toolbox = T.Toolbox()
        self.toolbox.setContextMenuPolicy(C.Qt.CustomContextMenu)
        def _tool_menu(pos):
            m = W.QMenu(self.toolbox); m.addAction("移除頁面所有標記").triggered.connect(self.clear_all_marks); m.exec(self.toolbox.mapToGlobal(pos))
        self.toolbox.customContextMenuRequested.connect(_tool_menu)
        self.toolbox.toolChanged.connect(self.set_tool)
        strip = W.QToolBar("工具"); strip.setObjectName("ToolStrip"); strip.setOrientation(C.Qt.Vertical)
        strip.setMovable(False); strip.addWidget(self.toolbox)
        self.addToolBar(C.Qt.LeftToolBarArea, strip)

        # ---- right panel: Browser / Info / Processing / Analysis / Display ----
        self.panel = W.QTabWidget(); self.panel.setMinimumWidth(420); self.panel.setMaximumWidth(560)
        self.listw = SpecTree()
        self.listw.itemChanged.connect(self._list_changed)
        self.listw.itemDoubleClicked.connect(lambda it, col=0: self.rename_selected() if not self.listw.is_header(it) else None)
        self.listw.itemSelectionChanged.connect(self._selection_changed)
        browser = W.QWidget(); bl = W.QVBoxLayout(browser); bl.setContentsMargins(4, 4, 4, 4)
        hint = W.QLabel("群組為上層、光譜為分支；勾選群組＝勾選／取消整組；點 ▸ 摺疊；選取群組＝選取整組；雙擊光譜＝重新命名"); hint.setWordWrap(True)
        self.filter_edit = W.QLineEdit(); self.filter_edit.setPlaceholderText("篩選名稱或群組…"); self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(lambda _: self.apply_filter())
        bl.addWidget(hint); bl.addWidget(self.filter_edit); bl.addWidget(self.listw, 1)
        self.listw.setContextMenuPolicy(C.Qt.CustomContextMenu); self.listw.customContextMenuRequested.connect(self._list_menu)
        row2 = W.QHBoxLayout()
        for text, fn in [("改色…", self.recolor_selected), ("群組…", self.group_selected), ("品質檢查", self.qc_report)]:
            b = W.QPushButton(text); b.clicked.connect(lambda _=False, f=fn: f()); row2.addWidget(b)
        self.sort_btn = W.QPushButton("排序 ▾"); sm = W.QMenu(self.sort_btn)
        for text, key in (("依名稱", "name"), ("依群組", "group"), ("依 X 起點", "xstart"), ("依最大強度（大→小）", "ymax")):
            sm.addAction(text).triggered.connect(lambda _=False, k=key: self.sort_items(k))
        self.sort_btn.setMenu(sm); row2.addWidget(self.sort_btn)
        bl.addLayout(row2)
        row_v = W.QHBoxLayout()
        for text, vis, tip in (("✔ 勾選選取", True, "把反白（框選）的光譜全部打勾顯示"), ("☐ 取消勾選選取", False, "一鍵取消反白（框選）光譜的勾選（隱藏，不刪除）")):
            b = W.QPushButton(text); b.setToolTip(tip); b.clicked.connect(lambda _=False, v=vis: self.set_visible_sel(v)); row_v.addWidget(b)
        bl.addLayout(row_v)
        row = W.QHBoxLayout()
        for text, fn in [("開啟…", self.open_files), ("刪除", self.remove_selected), ("全選", lambda: self.listw.selectAll())]:
            b = W.QPushButton(text); b.clicked.connect(lambda _=False, f=fn: f()); row.addWidget(b)
        self.send_btn = W.QPushButton("傳送到工作區 ▾"); self.send_menu = W.QMenu(self.send_btn)
        self.send_menu.aboutToShow.connect(self._fill_send_menu); self.send_btn.setMenu(self.send_menu); row.addWidget(self.send_btn)
        bl.addLayout(row)
        self.panel.addTab(browser, "Browser")

        self.info_label = W.QLabel(); self.info_label.setWordWrap(True); self.info_label.setAlignment(C.Qt.AlignTop | C.Qt.AlignLeft)
        self.info_label.setTextInteractionFlags(C.Qt.TextSelectableByMouse)
        info = W.QScrollArea(); info.setWidgetResizable(True); info.setWidget(self.info_label)
        self.panel.addTab(info, "Info")

        self._build_processing_tab()
        self._build_analysis_tab()
        self._build_display_tab()
        right = W.QDockWidget("", self); right.setTitleBarWidget(W.QWidget()); right.setWidget(self.panel)
        right.setFeatures(W.QDockWidget.NoDockWidgetFeatures); self.right_dock = right
        self.addDockWidget(C.Qt.RightDockWidgetArea, right)

        class _PeakDock:   # compatibility shim: "peak dock" == Peak Analysis tab
            def __init__(d, win): d.win = win
            def setVisible(d, v):
                if v: d.win.center.setCurrentWidget(d.win.peaks)
            def isVisible(d): return d.win.center.currentWidget() is d.win.peaks
        self.peak_dock = _PeakDock(self)

        self.hist_label = W.QLabel("")
        self.statusBar().addPermanentWidget(self.hist_label)

    # ---- Processing tab ----
    SMOOTH_HELP = ("Methods：Polynomial（Savitzky–Golay）、Median、FFT（低通）、DeNoise（Wiener）、1st／2nd derivative、Despike、SVD。\n"
                   "Mode Automatic：視窗由程式決定——取「最強峰高度損失不超過 Factor %」的最大奇數視窗；FFT 以雜訊底決定截止頻率；SVD 以雜訊門檻決定保留成分數。\n"
                   "Mode Manual：Window (pnt)、Order 依你設定的值；FFT 的 Factor 表示保留最低頻的百分比；SVD 的 Order 為保留成分數（多條光譜時一起分解）。\n"
                   "灰色的欄位在目前方法／模式下不使用。按「Run」套用到選取的光譜。\n（各欄位的詳細定義為本軟體自行訂定，未與其他軟體比對。）")
    BASELINE_HELP = ("Type：Linear/Polynom（Manual＝用左側「手動基線」工具在圖上點錨點；Auto＝自動挑錨點）、Multi polynomial（分段三次樣條，Order＝段數）、"
                     "Lorentzian（1–3 個寬 Lorentzian，Order＝個數）、Rolling Ball（Width 為球半徑 cm⁻¹）、Rolling Ball Auto（半徑由峰寬自動估計）、"
                     "Whittaker 1（AsLS）、Whittaker 2（arPLS）。\n"
                     "Fit：算出基線並以所選顏色顯示（不改資料）；Sub：把基線從選取的光譜扣除（若已有 Fit／貼上的基線則用它）。\n"
                     "Max points：Auto 類型把光譜分成這麼多等份，每份取一個候選錨點；Noise points：挑錨點前的移動平均寬度（點）；"
                     "Correct noise：錨點用平滑後高度（勾）或原始高度（不勾）。\n"
                     "Attach to curve：手動加點時錨點自動吸附到曲線。複製／貼上／刪除：複製目前基線、貼到其他光譜上、清除。\n"
                     "（參數定義為本軟體自行訂定，未與其他軟體比對；舊的 IterativeClipping／PolynomialFitting 已與參考軟體比對。）")
    BL_COLORS = {"Red": "#d62728", "Green": "#2ca02c", "Blue": "#1d7cd4", "Orange": "#ff7f0e", "Purple": "#9467bd", "Black": "#222222"}

    def _build_processing_tab(self):
        self.op_forms = {}
        host = W.QWidget(); lay = W.QVBoxLayout(host); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
        # Smoothing & Filtering
        sec = TH.Section("Smoothing & Filtering 平滑與濾波", help=self.SMOOTH_HELP)
        run = W.QLabel('<a href="run" style="color:#1d7cd4;text-decoration:none"><b>Run ▶</b></a>'); run.setObjectName("RunLink")
        run.setToolTip("對選取的光譜執行"); run.setTextInteractionFlags(C.Qt.LinksAccessibleByMouse)
        run.linkActivated.connect(lambda _: self.run_op("smooth", quick=True))
        fp = TH.FormPanel(self.OPS["smooth"][1], lambda v, n, k="smooth": self._panel_changed(k, v, n), new_box=False)
        sec.add(fp.widget); row = W.QHBoxLayout(); row.addStretch(1); row.addWidget(run)
        rw = W.QWidget(); rw.setLayout(row); sec.add(rw); self.run_link = run
        self.op_forms["smooth"] = fp; lay.addWidget(sec)
        # Baseline correction
        sec = TH.Section("Baseline correction 去背景", help=self.BASELINE_HELP)
        self.bl_fit_btn = W.QPushButton("Fit"); self.bl_sub_btn = W.QPushButton("Sub")
        self.bl_fit_btn.setToolTip("算出基線並顯示（不改資料）"); self.bl_sub_btn.setToolTip("從選取的光譜扣除基線")
        self.bl_sub_btn.setObjectName("Apply")
        for b_ in (self.bl_fit_btn, self.bl_sub_btn): b_.setFixedWidth(56)
        self.bl_fit_btn.clicked.connect(lambda: self.baseline_fit()); self.bl_sub_btn.clicked.connect(lambda: self.baseline_sub())
        cb = []
        for nm, tip, fn in (("bl_copy", "複製目前基線", self.baseline_copy), ("bl_paste", "貼上基線（內插到第一條選取光譜）", self.baseline_paste),
                            ("bl_trash", "刪除基線與手動錨點", self.baseline_delete)):
            t_ = W.QToolButton(); t_.setIcon(IC.ICONS[nm]()); t_.setIconSize(C.QSize(18, 18)); t_.setToolTip(tip); t_.setFixedSize(28, 26)
            t_.clicked.connect(lambda _=False, f=fn: f()); cb.append(t_)
        self.bl_copy_btn, self.bl_paste_btn, self.bl_del_btn = cb
        fp = TH.FormPanel(self.OPS["baseline"][1], lambda v, n, k="baseline": self._panel_changed(k, v, n),
                          extras={"method": [self.bl_fit_btn, self.bl_sub_btn], "color": cb}, new_box=False)
        sec.add(fp.widget)
        note = self.OPS["baseline"][2]
        lb = W.QLabel(note); lb.setWordWrap(True); lb.setStyleSheet("color:#6e6e73;font-size:9pt"); sec.add(lb)
        self.op_forms["baseline"] = fp; lay.addWidget(sec)
        # Normalization
        sec = TH.Section("Normalization 均一化", expanded=False)
        fp = TH.FormPanel(self.OPS["normalize"][1], lambda v, n, k="normalize": self._panel_changed(k, v, n))
        sec.add(fp.widget)
        lb = W.QLabel(self.OPS["normalize"][2]); lb.setWordWrap(True); lb.setStyleSheet("color:#27506f;font-size:9pt"); sec.add(lb)
        btn = W.QPushButton("套用 Apply"); btn.setObjectName("Apply"); btn.clicked.connect(lambda _=False: self.run_op("normalize", quick=True))
        sec.add(btn); self.op_forms["normalize"] = fp; lay.addWidget(sec)
        # Spectral math
        self.math = MathPanel(self); lay.addWidget(self.math)
        self.peak_sec = PeakSection(self); lay.addWidget(self.peak_sec)
        sec = TH.Section("Data 資料", expanded=False)
        grid = W.QGridLayout()
        buttons = [("平均 Average", self.op_average), ("裁切 Crop…", self.op_crop), ("Uniform X…", self.op_uniformx), ("標準化", self.op_standardize),
                   ("標準差曲線", self.op_stdcurve), ("自動堆疊", self.op_stack), ("新增/刪除點…", self.op_points)]
        for i, (t, fn) in enumerate(buttons):
            b = W.QPushButton(t); b.clicked.connect(lambda _=False, f=fn: f()); grid.addWidget(b, i // 2, i % 2)
        w = W.QWidget(); w.setLayout(grid); sec.add(w)
        lay.addWidget(sec)
        lay.addStretch(1)
        sa = W.QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(host); self.proc_scroll = sa
        self.panel.addTab(sa, "Processing")
        self._sync_panels()

    def row_visible(self, key, field):
        fp = self.op_forms[key]; return fp.layout.isRowVisible(fp.row_widgets[field])

    def show_math(self):
        self.panel.setCurrentWidget(self.proc_scroll); self.proc_scroll.ensureWidgetVisible(self.math)

    def _panel_changed(self, key, vals, new):
        self.params[key] = {**vals, "_new": new}
        self._update_tips()

    def _sync_panels(self):
        for key, fp in getattr(self, "op_forms", {}).items():
            vals, new = self._op_values(key)
            fp.set_values(vals, new)

    # ---- Analysis tab ----
    BAND_COLORS = ["#d62728", "#2ca02c", "#1f77b4", "#ff7f0e", "#9467bd", "#17becf"]

    def _build_analysis_tab(self):
        self.bands = []     # dicts: lo, hi, region, widgets
        host = W.QWidget(); lay = W.QVBoxLayout(host); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
        sec2 = TH.Section("Bands 區間積分")
        self.band_box = W.QVBoxLayout(); bw = W.QWidget(); bw.setLayout(self.band_box); sec2.add(bw)
        row = W.QHBoxLayout()
        ba = W.QPushButton("＋ 新增區間"); ba.clicked.connect(lambda: self.add_band())
        bc = W.QPushButton("計算面積"); bc.setObjectName("Apply"); bc.clicked.connect(self.compute_bands)
        bx = W.QPushButton("複製結果"); bx.clicked.connect(self.copy_bands)
        for b in (ba, bc, bx): row.addWidget(b)
        rw = W.QWidget(); rw.setLayout(row); sec2.add(rw)
        self.band_table = W.QTableWidget(0, 0); self.band_table.setMinimumHeight(130)
        vh = self.band_table.verticalHeader(); vh.setFixedWidth(130); vh.setTextElideMode(C.Qt.ElideMiddle)      # long spectrum names must not hide the values
        self.band_table.setTextElideMode(C.Qt.ElideMiddle); self.band_table.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
        self.band_table.horizontalHeader().setSectionResizeMode(W.QHeaderView.Stretch); self.band_table.horizontalHeader().setMinimumSectionSize(80)
        sec2.add(self.band_table)
        sec2.add(W.QLabel("<b>積分數值</b>（光譜名稱完整顯示，可選取複製）"))
        self.band_text = W.QPlainTextEdit(); self.band_text.setReadOnly(True); self.band_text.setMinimumHeight(120)
        self.band_text.setLineWrapMode(W.QPlainTextEdit.WidgetWidth)
        self.band_text.setPlaceholderText("按「計算面積」後，各光譜在每個區間的積分值會顯示在這裡。")
        f_ = G.QFontDatabase.systemFont(G.QFontDatabase.FixedFont); f_.setPointSize(10); self.band_text.setFont(f_)
        sec2.add(self.band_text)
        lay.addWidget(sec2)

        sec4 = TH.Section("EF 增強因子", expanded=False)
        f4 = W.QFormLayout()
        self.ef_center = W.QDoubleSpinBox(); self.ef_center.setRange(-1e6, 1e6); self.ef_center.setDecimals(1); self.ef_center.setValue(1075.0)
        self.ef_hw = W.QDoubleSpinBox(); self.ef_hw.setRange(0.1, 1e4); self.ef_hw.setDecimals(1); self.ef_hw.setValue(10.0)
        self.ef_mode = W.QComboBox(); self.ef_mode.addItems(["峰高", "峰高（扣兩端直線基線）", "峰面積", "峰面積（扣兩端直線基線）"])
        self.ef_basis = W.QComboBox(); self.ef_basis.addItems(["濃度法（C_SERS、C_RS）", "分子數法（N_SERS、N_RS）"])
        self.ef_basis.currentIndexChanged.connect(lambda _: self._ef_labels())
        self.ef_xs = W.QLineEdit("1e-9"); self.ef_xr = W.QLineEdit("1e-1")
        self.ef_ps = W.QDoubleSpinBox(); self.ef_ts = W.QDoubleSpinBox(); self.ef_pr = W.QDoubleSpinBox(); self.ef_tr = W.QDoubleSpinBox()
        for w_ in (self.ef_ps, self.ef_ts, self.ef_pr, self.ef_tr):
            w_.setRange(1e-6, 1e6); w_.setDecimals(4); w_.setValue(1.0)
        self.ef_lbl_xs = W.QLabel(); self.ef_lbl_xr = W.QLabel()
        for lab, w_ in (("峰位置 (cm⁻¹)", self.ef_center), ("半窗寬 ±(cm⁻¹)", self.ef_hw), ("響應", self.ef_mode), ("計算基準", self.ef_basis)):
            f4.addRow(lab, w_)
        f4.addRow(self.ef_lbl_xs, self.ef_xs); f4.addRow(self.ef_lbl_xr, self.ef_xr)
        f4.addRow("SERS 雷射功率", self.ef_ps); f4.addRow("SERS 積分時間 (s)", self.ef_ts)
        f4.addRow("Raman 雷射功率", self.ef_pr); f4.addRow("Raman 積分時間 (s)", self.ef_tr)
        w4 = W.QWidget(); w4.setLayout(f4); sec4.add(w4); self._ef_labels()
        self.ef_groups = {"sers": [], "ref": []}
        self.ef_lbl_groups = W.QLabel(); self.ef_lbl_groups.setWordWrap(True); sec4.add(self.ef_lbl_groups)
        r4 = W.QHBoxLayout()
        b_s = W.QPushButton("選取 → SERS 組"); b_s.clicked.connect(lambda: self.ef_set_group("sers"))
        b_r = W.QPushButton("選取 → Raman 參考組"); b_r.clicked.connect(lambda: self.ef_set_group("ref"))
        r4.addWidget(b_s); r4.addWidget(b_r); rw4 = W.QWidget(); rw4.setLayout(r4); sec4.add(rw4)
        r5 = W.QHBoxLayout()
        b_c = W.QPushButton("計算 EF"); b_c.setObjectName("Apply"); b_c.clicked.connect(self.ef_compute)
        b_x = W.QPushButton("複製結果"); b_x.clicked.connect(self.ef_copy)
        r5.addWidget(b_c); r5.addWidget(b_x); rw5 = W.QWidget(); rw5.setLayout(r5); sec4.add(rw5)
        self.ef_result = W.QLabel(""); self.ef_result.setWordWrap(True); self.ef_result.setTextInteractionFlags(C.Qt.TextSelectableByMouse)
        sec4.add(self.ef_result); self._ef_update_groups()
        lay.addWidget(sec4)
        lay.addStretch(1)
        sa = W.QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(host)
        sa.setHorizontalScrollBarPolicy(C.Qt.ScrollBarAlwaysOff)
        self.analysis_tab = sa
        self.panel.addTab(sa, "Analysis")

    def add_band(self, lo=None, hi=None):
        n = len(self.bands)
        if lo is None:
            xs = [it.spec.x for it in self.items if it.visible]
            a, b = (min(x[0] for x in xs), max(x[-1] for x in xs)) if xs else (400.0, 1600.0)
            lo, hi = a + (b - a) * 0.3, a + (b - a) * 0.4
        color = self.BAND_COLORS[n % len(self.BAND_COLORS)]
        row = W.QWidget(); h = W.QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0)
        sw = W.QLabel(); sw.setFixedSize(18, 18); sw.setStyleSheet(f"background:{color};border:1px solid #333")
        sl = W.QDoubleSpinBox(); sh = W.QDoubleSpinBox()
        for s_, v in ((sl, lo), (sh, hi)):
            s_.setRange(-1e6, 1e6); s_.setDecimals(1); s_.setValue(v); s_.setPrefix("")
        h.addWidget(sw); h.addWidget(W.QLabel("From")); h.addWidget(sl); h.addWidget(W.QLabel("To")); h.addWidget(sh)
        rm = W.QToolButton(); rm.setText("✕"); h.addWidget(rm)
        qc = G.QColor(color); qc.setAlpha(60)
        reg = pg.LinearRegionItem((lo, hi), brush=pg.mkBrush(qc), pen=pg.mkPen(color), movable=True)
        reg.setZValue(-5); self.pi.addItem(reg)
        band = {"lo": sl, "hi": sh, "region": reg, "row": row, "color": color}
        self.bands.append(band); self.band_box.addWidget(row)
        reg.sigRegionChanged.connect(lambda r=reg, a=sl, b=sh: (a.blockSignals(True), b.blockSignals(True),
                                     a.setValue(r.getRegion()[0]), b.setValue(r.getRegion()[1]), a.blockSignals(False), b.blockSignals(False)))
        for s_ in (sl, sh):
            s_.valueChanged.connect(lambda _=0, r=reg, a=sl, b=sh: r.setRegion((min(a.value(), b.value()), max(a.value(), b.value()))))
        rm.clicked.connect(lambda _=False, bd=band: self.remove_band(bd))
        return band

    def remove_band(self, band):
        if band in self.bands:
            self.bands.remove(band); self.pi.removeItem(band["region"]); band["row"].setParent(None); band["row"].deleteLater()

    def compute_bands(self):
        idx = self.targets()
        if not idx: return
        ranges = [tuple(sorted((b["lo"].value(), b["hi"].value()))) for b in self.bands]
        if not ranges: ranges = [tuple(sorted(r.getRegion())) for r in self.strips]   # use drawn strips
        if not ranges:
            self.add_band(); ranges = [tuple(sorted((self.bands[0]["lo"].value(), self.bands[0]["hi"].value())))]
        self.band_table.setRowCount(len(idx)); self.band_table.setColumnCount(len(ranges))
        self.band_table.setHorizontalHeaderLabels([f"{lo:.0f}–{hi:.0f}" for lo, hi in ranges])
        self.band_table.setVerticalHeaderLabels([self.items[i].spec.name for i in idx])
        self.band_result = []; text = []
        for r, i in enumerate(idx):
            rowv = []; sp = self.items[i].spec; text.append(sp.name)
            vi = self.band_table.verticalHeaderItem(r)
            if vi is not None: vi.setToolTip(sp.name)
            for c, (lo, hi) in enumerate(ranges):
                try: v = float(rp.integral(sp, lo, hi))
                except Exception: v = float("nan")
                clipped = lo < sp.x[0] or hi > sp.x[-1]
                rowv.append(v); it_ = W.QTableWidgetItem(f"{v:.6g}"); it_.setTextAlignment(C.Qt.AlignRight | C.Qt.AlignVCenter)
                if clipped: it_.setToolTip(f"區間超出光譜範圍（{sp.x[0]:.1f}–{sp.x[-1]:.1f}），只計算範圍內的部分")
                self.band_table.setItem(r, c, it_)
                text.append(f"  {lo:g}–{hi:g}\t面積 = {v:.6g}" + (f"　⚠ 區間超出光譜範圍（{sp.x[0]:.1f}–{sp.x[-1]:.1f}），只計算範圍內" if clipped else ""))
            self.band_result.append(rowv); text.append("")
        self.band_text.setPlainText("\n".join(text).rstrip())
        self.statusBar().showMessage(f"已計算 {len(ranges)} 個區間 × {len(idx)} 條光譜")

    def copy_bands(self):
        t = self.band_table
        lines = ["\t" + "\t".join(t.horizontalHeaderItem(c).text() for c in range(t.columnCount()))]
        for r in range(t.rowCount()):
            lines.append(t.verticalHeaderItem(r).text() + "\t" + "\t".join(t.item(r, c).text() for c in range(t.columnCount())))
        G.QGuiApplication.clipboard().setText("\n".join(lines))
        self.statusBar().showMessage("已複製到剪貼簿")

    # ---- EF ----
    def _ef_labels(self):
        n = self.ef_basis.currentIndex() == 1
        self.ef_lbl_xs.setText("N_SERS（探測分子數）" if n else "C_SERS（SERS 樣品濃度）")
        self.ef_lbl_xr.setText("N_RS（探測分子數）" if n else "C_RS（Raman 樣品濃度，同單位）")

    def _ef_update_groups(self):
        def names(k):
            ns = [it.spec.name for it in self.items if id(it) in self.ef_groups[k]]
            return "、".join(ns) if ns else "（尚未指定）"
        self.ef_lbl_groups.setText(f"<b>SERS 組</b>：{names('sers')}<br><b>Raman 參考組</b>：{names('ref')}")

    def ef_set_group(self, key):
        idx = self.selected_idx()
        if not idx:
            W.QMessageBox.warning(self, "EF", "請先在 Browser 選取光譜。"); return
        other = "ref" if key == "sers" else "sers"
        ids = [id(self.items[i]) for i in idx]
        self.ef_groups[key] = ids; self.ef_groups[other] = [i for i in self.ef_groups[other] if i not in ids]
        self._ef_update_groups()

    def ef_compute(self):
        try:
            mode_i = self.ef_mode.currentIndex(); mode, bl = ("height" if mode_i < 2 else "area"), mode_i % 2 == 1
            resp = {}
            for k in ("sers", "ref"):
                its = [it for it in self.items if id(it) in self.ef_groups[k]]
                if not its: raise ValueError("請先指定 SERS 組與 Raman 參考組（選取光譜後按對應按鈕）")
                resp[k] = [rp.peak_response(it.spec, self.ef_center.value(), self.ef_hw.value(), mode, bl) for it in its]
            out = rp.enhancement_factor(resp["sers"], resp["ref"], float(self.ef_xs.text()), float(self.ef_xr.text()),
                                        self.ef_ps.value(), self.ef_ts.value(), self.ef_pr.value(), self.ef_tr.value())
        except Exception as ex:
            W.QMessageBox.warning(self, "EF", str(ex)); return
        self.ef_last = out; sym = "N" if self.ef_basis.currentIndex() == 1 else "C"
        self.ef_result.setText(
            f"I<sub>SERS</sub> = {out['i_sers']:.5g} ± {out['i_sers_sd']:.3g}（n={out['n_sers']}）<br>"
            f"I<sub>RS</sub> = {out['i_ref']:.5g} ± {out['i_ref_sd']:.3g}（n={out['n_ref']}）<br><br>"
            f"<b>EF = {out['ef']:.4g} ± {out['ef_sd']:.2g}</b>　（log₁₀EF = {out['log10_ef']:.3f}）<br><br>"
            f"EF = (I<sub>SERS</sub>/{sym}<sub>SERS</sub>/P/t) ÷ (I<sub>RS</sub>/{sym}<sub>RS</sub>/P/t)")
        self.statusBar().showMessage(f"EF = {out['ef']:.3e}")

    def ef_copy(self):
        import re
        G.QGuiApplication.clipboard().setText(re.sub(r"<br\s*/?>", "\n", re.sub(r"</?(b|sub|span)[^>]*>", "", self.ef_result.text())))
        self.statusBar().showMessage("已複製到剪貼簿")

    # ---- Display tab ----
    def _build_display_tab(self):
        host = W.QWidget(); lay = W.QVBoxLayout(host); lay.setContentsMargins(0, 0, 0, 0)
        sec = TH.Section("Plot 繪圖")
        form = W.QFormLayout()
        self.cb_grid = W.QCheckBox("顯示格線"); self.cb_grid.setChecked(True)
        self.cb_legend = W.QCheckBox("顯示圖例"); self.cb_legend.setChecked(True)
        self.sp_width = W.QDoubleSpinBox(); self.sp_width.setRange(0.5, 8); self.sp_width.setSingleStep(0.5); self.sp_width.setValue(1.5)
        self.cb_bg = W.QComboBox(); self.cb_bg.addItems(["白色", "深色"])
        form.addRow(self.cb_grid); form.addRow(self.cb_legend); form.addRow("線寬", self.sp_width); form.addRow("背景", self.cb_bg)
        w = W.QWidget(); w.setLayout(form); sec.add(w)
        self.cb_grid.toggled.connect(lambda c: (self.pi.showGrid(x=c, y=c, alpha=0.25), self.act_grid.setChecked(c)))
        self.cb_legend.toggled.connect(lambda c: (self.legend.setVisible(c), self.act_legend.setChecked(c)))
        self.sp_width.valueChanged.connect(lambda _: self.redraw())
        self.cb_bg.currentIndexChanged.connect(self._bg_changed)
        lay.addWidget(sec)

        self.figstyle = FigureStyleSection(self); lay.addWidget(self.figstyle)

        sc = TH.Section("Compare 處理前後對照")
        fc = W.QVBoxLayout()
        self.cb_raw = W.QCheckBox("原始光譜（灰色虛線）"); self.cb_smooth = W.QCheckBox("平滑後（橘色點線）")
        self.cb_base = W.QCheckBox("基線估計（綠色）與去基線前光譜（紫色點線）"); self.cb_final = W.QCheckBox("最終結果（目前資料）"); self.cb_final.setChecked(True)
        for c_ in (self.cb_raw, self.cb_smooth, self.cb_base, self.cb_final):
            c_.toggled.connect(lambda _=False: self.redraw()); fc.addWidget(c_)
        nt = W.QLabel("對照對象為選取（或目前）的光譜；平滑 / 基線階段記錄自 Processing 的操作。若之後做過均一化等縮放，原始曲線仍是載入時的強度。")
        nt.setWordWrap(True); nt.setStyleSheet("color:#27506f;font-size:9pt"); fc.addWidget(nt)
        w = W.QWidget(); w.setLayout(fc); sc.add(w); lay.addWidget(sc)

        so = TH.Section("Overlay 平均 / 讀值 / 異常")
        fo = W.QVBoxLayout()
        self.cb_band = W.QCheckBox("平均 ± SD 誤差帶（顯示中的光譜，共同 X 範圍）")
        self.cb_only_mean = W.QCheckBox("只顯示平均與誤差帶（隱藏個別曲線）")
        self.cb_readout = W.QCheckBox("游標處顯示所有光譜的 Y 值"); self.cb_readout.setChecked(True)
        self.cb_qc = W.QCheckBox("標示異常點（◆尖峰、■飽和、×缺值）"); self.cb_qc.setChecked(True)
        for c_ in (self.cb_band, self.cb_only_mean, self.cb_qc):
            c_.toggled.connect(lambda _=False: self.redraw())
        for c_ in (self.cb_band, self.cb_only_mean, self.cb_readout, self.cb_qc): fo.addWidget(c_)
        w = W.QWidget(); w.setLayout(fo); so.add(w); lay.addWidget(so)

        sa = TH.Section("Axes 座標軸")
        fa = W.QFormLayout()
        self.cb_axis = W.QComboBox(); self.cb_axis.addItems(["拉曼位移 (cm⁻¹)", "波長 (nm)"])
        self.sp_laser = W.QDoubleSpinBox(); self.sp_laser.setRange(200, 2000); self.sp_laser.setDecimals(2); self.sp_laser.setValue(532.0); self.sp_laser.setSuffix(" nm")
        self.cb_invx = W.QCheckBox("X 軸反向")
        self.cb_yunit = W.QComboBox(); self.cb_yunit.setEditable(True)
        self.cb_yunit.addItems(["Intensity", "Intensity (a.u.)", "Intensity (counts)", "Intensity (counts/s)", "Normalized intensity", "Absorbance"])
        self.rng = [W.QDoubleSpinBox() for _ in range(4)]
        for r_ in self.rng: r_.setRange(-1e9, 1e9); r_.setDecimals(3)
        fa.addRow("X 單位", self.cb_axis); fa.addRow("雷射波長（轉換用）", self.sp_laser); fa.addRow(self.cb_invx); fa.addRow("Y 軸單位", self.cb_yunit)
        for lab, r_ in zip(("X 最小", "X 最大", "Y 最小", "Y 最大"), self.rng): fa.addRow(lab, r_)
        w = W.QWidget(); w.setLayout(fa); sa.add(w)
        rb = W.QHBoxLayout()
        b1 = W.QPushButton("套用範圍"); b1.setObjectName("Apply"); b1.clicked.connect(self.apply_range)
        b2 = W.QPushButton("自動範圍"); b2.clicked.connect(self.full_scale)
        rb.addWidget(b1); rb.addWidget(b2); rw = W.QWidget(); rw.setLayout(rb); sa.add(rw)
        nt = W.QLabel("波長檢視僅改變顯示；區間、標線等工具的數值會是波長座標，分析請在拉曼位移檢視下進行。")
        nt.setWordWrap(True); nt.setStyleSheet("color:#27506f;font-size:9pt"); sa.add(nt)
        lay.addWidget(sa); lay.addStretch(1)
        self.cb_axis.currentIndexChanged.connect(self.set_axis_mode); self.sp_laser.valueChanged.connect(lambda _: self.set_axis_mode())
        self.cb_invx.toggled.connect(lambda c: self.pi.invertX(c))
        self.cb_yunit.currentTextChanged.connect(lambda t: self.pi.setLabel("left", t or "Intensity"))
        for r_ in self.rng: r_.editingFinished.connect(self.apply_range)
        self.pi.vb.sigRangeChanged.connect(self._sync_range)
        sa_ = W.QScrollArea(); sa_.setWidgetResizable(True); sa_.setWidget(host); sa_.setHorizontalScrollBarPolicy(C.Qt.ScrollBarAlwaysOff)
        self.display_tab = sa_                      # many expandable sections: scroll instead of growing past the window
        self.panel.addTab(sa_, "Display")

    def _sync_range(self, *_):
        if not hasattr(self, "rng"): return
        (x0, x1), (y0, y1) = self.pi.viewRange()
        for r_, v in zip(self.rng, (x0, x1, y0, y1)):
            if not r_.hasFocus():
                r_.blockSignals(True); r_.setValue(v); r_.blockSignals(False)

    def apply_range(self):
        x0, x1, y0, y1 = (r_.value() for r_ in self.rng)
        if x1 > x0: self.pi.setXRange(x0, x1, padding=0)
        if y1 > y0: self.pi.setYRange(y0, y1, padding=0)

    def default_xlabel(self):
        if getattr(self, "axis_mode", "shift") == "nm": return "Wavelength (nm)"
        nm = [it for it in self.items if "xunit=nm" in it.spec.history]
        return "Wavelength (nm)" if nm and len(nm) == len(self.items) else "Raman Shift (cm⁻¹)"

    def set_axis_mode(self, *_):
        mode = "nm" if self.cb_axis.currentIndex() == 1 else "shift"
        self.axis_mode = mode
        self.pi.setLabel("bottom", getattr(self, "x_label_override", None) or self.default_xlabel())
        self.redraw(); self.full_scale()
        self.statusBar().showMessage("X 軸：波長（僅顯示用）" if mode == "nm" else "X 軸：拉曼位移")

    def _bg_changed(self, i):
        dark = i == 1
        self.plot.setBackground("#101820" if dark else "w")
        fg = "#dddddd" if dark else "k"
        for ax in ("left", "bottom"):
            self.pi.getAxis(ax).setPen(fg); self.pi.getAxis(ax).setTextPen(fg)
        if hasattr(self, "figstyle"): self.figstyle.apply()          # re-colour the frame (Auto = same as the axis lines)

    def _center_changed(self, i):
        if hasattr(self, "right_dock"):
            self.right_dock.setVisible(self.center.widget(i) not in (self.quant, self.peaks, self.rsd))   # quantification gets the full width

    def _active_idx(self):
        sel = self.selected_idx()
        if sel: return sel[0]
        for i, it in enumerate(self.items):
            if it.visible: return i
        return -1

    def _sync_view_btn(self):
        a = self.view_actions[self.view_mode]
        a.setChecked(True); self.view_btn.setIcon(a.icon()); self.view_btn.setText(a.text())

    def set_view_mode(self, mode):
        self.view_mode = mode
        self._sync_view_btn(); self.redraw(); self.full_scale()
        self.statusBar().showMessage({"single": "單曲線顯示：只顯示選取的光譜", "multi": "多重曲線顯示",
                                      "stack": "自動疊曲線：只影響顯示，資料未改動"}[mode])

    def _selection_changed(self):
        if self.view_mode == "single": self.redraw()
        self._update_info()
        self.specbar.style_buttons(self.items, set(self.selected_idx()))
        self._highlight_selected()

    def _bar_clicked(self, i, mods):
        it = self.listw.item(i)
        if it is None: return
        if mods & (C.Qt.ControlModifier | C.Qt.ShiftModifier):
            it.setSelected(not it.isSelected())
        else:
            self.listw.clearSelection(); it.setSelected(True)

    def _bar_toggled(self, i):
        it = self.listw.item(i)
        if it is not None:
            it.setCheckState(0, C.Qt.Unchecked if it.checkState(0) == C.Qt.Checked else C.Qt.Checked)

    def _highlight_selected(self):
        sel = set(self.selected_idx()); w = self.sp_width.value() if hasattr(self, "sp_width") else 1.5
        for i, it in enumerate(self.items):
            c = self.curves.get(id(it))
            if c is not None: c.setPen(pg.mkPen(it.color, width=w + (1.5 if i in sel and len(sel) < len(self.items) else 0)))

    def _update_info(self):
        idx = self.selected_idx()
        if not idx:
            self.info_label.setText("（未選取光譜）"); self.plot_title.setText("Spectra"); return
        it = self.items[idx[0]]; s = it.spec
        import html
        hist = "<br>".join("• " + html.escape(str(h)) for h in (s.history or [])) or "（無）"
        self.info_label.setText(
            f"<b>{html.escape(s.name)}</b><br>點數：{len(s.x)}<br>X 範圍：{s.x[0]:.2f} – {s.x[-1]:.2f}<br>"
            f"Y 範圍：{float(np.min(s.y)):.5g} – {float(np.max(s.y)):.5g}<br>"
            f"平均間距：{(s.x[-1] - s.x[0]) / max(len(s.x) - 1, 1):.3f}<br><br><b>處理歷程</b><br>{hist}"
            + (f"<br><br>（共選取 {len(idx)} 條，僅顯示第一條）" if len(idx) > 1 else ""))
        self.plot_title.setText(f"Spectra : {s.name}")

    def _fill_data_table(self):
        if self.center.currentIndex() != 1: return
        idx = self.selected_idx() or ([0] if self.items else [])
        if not idx: self.data_table.setRowCount(0); return
        s = self.items[idx[0]].spec
        self.data_table.setRowCount(len(s.x))
        for r, (x, y) in enumerate(zip(s.x, s.y)):
            self.data_table.setItem(r, 0, W.QTableWidgetItem(f"{x:.4f}")); self.data_table.setItem(r, 1, W.QTableWidgetItem(f"{y:.6g}"))

    def _act(self, menu, text, slot, shortcut=None, checkable=False):
        a = G.QAction(text, self)
        a.triggered.connect(slot)
        if shortcut: a.setShortcut(shortcut)
        a.setCheckable(checkable)
        menu.addAction(a)
        return a

    def _build_menus(self):
        mb = self.menuBar()
        f = mb.addMenu("檔案(&F)")
        self._act(f, "開啟光譜…", self.open_files, "Ctrl+O")
        self._act(f, "儲存選取光譜（文字檔）…", self.save_selected, "Ctrl+S")
        self._act(f, "匯出全部（XYY 單一檔）…", self.export_xyy)
        self._act(f, "匯出圖片（PNG / SVG / PDF）…", self.export_image)
        f.addSeparator()
        self._act(f, "儲存工作階段…（所有工作區）", self.save_session_dialog)
        self._act(f, "開啟工作階段…", self.open_session_dialog)
        f.addSeparator(); self._act(f, "結束", self.close, "Ctrl+Q")
        e = mb.addMenu("編輯(&E)")
        self.act_undo = self._act(e, "復原", self.do_undo, "Ctrl+Z")
        self.act_redo = self._act(e, "重做", self.do_redo, "Ctrl+Y")
        e.addSeparator()
        self._act(e, "重新命名…", self.rename_selected, "F2")
        self._act(e, "刪除選取", self.remove_selected, "Del")
        self._act(e, "移除全部文字", lambda: self.remove_annots("text"))
        self._act(e, "移除全部圖片", lambda: self.remove_annots("image"))
        self._act(e, "清除資料游標", self.clear_cursor)
        self._act(e, "清除 X 標線", self.clear_xline)
        self._act(e, "清除雙 X 標線", self.clear_dxline)
        self._act(e, "全選", self.listw.selectAll, "Ctrl+A")
        o = mb.addMenu("處理(&O)")
        for text, fn in [("平均 Average", self.op_average), ("裁切 Crop", self.op_crop),
                         ("平滑 Smooth", self.op_smooth),
                         ("去除基線 Remove Baseline", self.op_baseline), ("正規化 Normalize", self.op_normalize),
                         ("光譜數學 Spectral Math…", self.show_math), ("Uniform X", self.op_uniformx),
                         ("標準差曲線 Standard Deviation Curve", self.op_stdcurve),
                         ("新增 / 刪除點 Add/Remove Point", self.op_points)]:
            self._act(o, text, fn)
        o.addSeparator()
        for text, fn in [("標準化 Standardize", self.op_standardize), ("積分 Integral…", self.op_integral),
                         ("自動堆疊 Auto Stacking", self.op_stack)]:
            self._act(o, text, fn)
        p = mb.addMenu("峰(&P)")
        self._act(p, "峰分析 Peak Analysis…", self.op_peaks)
        self._act(p, "RSD 重現性…", lambda: self.center.setCurrentWidget(self.rsd))
        self._act(p, "清除峰標示", self.clear_labels)
        self._act(p, "移除頁面所有標記", self.clear_all_marks)
        s = mb.addMenu("區間(&S)")
        self._act(s, "加入區間（Strip）", self.toggle_strip)
        self._act(s, "移除全部區間", self.clear_strips)
        v = mb.addMenu("檢視(&V)")
        self._act(v, "全範圍 (X+Y)", self.full_scale, "Ctrl+0")
        self.act_grid = self._act(v, "格線", lambda c: self.pi.showGrid(x=c, y=c, alpha=0.25), checkable=True)
        self.act_grid.setChecked(True)
        self.act_legend = self._act(v, "圖例", lambda c: self.legend.setVisible(c), checkable=True)
        self.act_legend.setChecked(True)
        self._act(v, "峰分析分頁", lambda: self.peak_dock.setVisible(True))
        h = mb.addMenu("說明(&H)")
        self._act(h, "關於 SpectrumPro", self.show_about)
        self._refresh_actions()

    def show_about(self):
        dlg = W.QDialog(self); dlg.setWindowTitle(f"關於 {APP_NAME}")
        lay = W.QHBoxLayout(dlg); lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(20)
        pic = W.QLabel(); pm = G.QPixmap(icon_path())
        if not pm.isNull(): pic.setPixmap(pm.scaled(128, 128, C.Qt.KeepAspectRatio, C.Qt.SmoothTransformation))
        pic.setAlignment(C.Qt.AlignTop); lay.addWidget(pic)
        txt = W.QLabel(f"<div style='font-size:22pt;font-weight:bold'>{APP_NAME}</div>"
                       f"<div style='color:#666'>版本 {APP_VERSION}</div><br>"
                       "<div>拉曼 / SERS 光譜後處理與定量分析軟體</div>"
                       "<div style='color:#666'>演算法經與參考軟體輸出逐項比對（見 README）。</div><br>"
                       f"<div><b>作者 Author：</b>{APP_AUTHOR}</div>"
                       f"<div style='color:#666'>© {APP_AUTHOR}. All rights reserved.</div>")
        txt.setTextFormat(C.Qt.RichText); txt.setTextInteractionFlags(C.Qt.TextSelectableByMouse); lay.addWidget(txt, 1)
        dlg.exec()

    # ---------------- toolbar ----------------
    def _build_toolbar(self):
        tb = self.addToolBar("常用"); tb.setMovable(False); tb.setIconSize(C.QSize(40, 40))
        tb.setToolButtonStyle(C.Qt.ToolButtonTextUnderIcon)
        def std(key, text, slot, tip):
            a = G.QAction(IC.ICONS[key](), text, self); a.setToolTip(tip); a.triggered.connect(lambda _=False: slot()); tb.addAction(a); return a
        std("open", "開啟", self.open_files, "開啟光譜檔（Ctrl+O）")
        std("save", "儲存", self.save_selected, "儲存選取的光譜（Ctrl+S）")
        std("image", "圖片", self.export_image, "匯出圖片（PNG / SVG）")
        self.tb_undo = std("undo", "復原", self.do_undo, "復原（Ctrl+Z）")
        self.tb_redo = std("redo", "重做", self.do_redo, "重做（Ctrl+Y）")
        tb.addSeparator()
        self.quick_actions = {}
        specs = [("average", "平均", lambda: self.op_average(), None),
                 ("crop", "裁切", lambda: self.op_crop(quick=True), lambda: self.op_crop(quick=False)),
                 ("smooth", "平滑", lambda: self.run_op("smooth", quick=True), lambda: self.run_op("smooth")),
                 ("baseline", "去背景", lambda: self.run_op("baseline", quick=True), lambda: self.run_op("baseline")),
                 ("normalize", "均一化", lambda: self.run_op("normalize", quick=True), lambda: self.run_op("normalize"))]
        for key, text, quick, dialog in specs:
            act = G.QAction(IC.ICONS[key](), text, self); act.triggered.connect(lambda _=False, f=quick: f())
            btn = W.QToolButton(); btn.setDefaultAction(act); btn.setIconSize(C.QSize(40, 40))
            btn.setToolButtonStyle(C.Qt.ToolButtonTextUnderIcon); btn.setMinimumWidth(72)
            if dialog:
                m = W.QMenu(btn); a2 = m.addAction("設定參數…"); a2.triggered.connect(lambda _=False, f=dialog: f())
                btn.setMenu(m); btn.setPopupMode(W.QToolButton.DelayedPopup); btn.setToolTip('點一下＝以目前參數執行；長按＝開啟「設定參數…」')
            tb.addWidget(btn); self.quick_actions[key] = act
        tb.addSeparator()
        grp = G.QActionGroup(self); grp.setExclusive(True)
        self.view_actions = {}
        defs = (("single", "單曲線", "單曲線顯示：只顯示目前選取的那一條（點色塊條或列表切換）"),
                ("multi", "多曲線", "多重曲線顯示：同時顯示所有勾選的光譜"),
                ("stack", "自動疊", "自動疊曲線：所有勾選的光譜依序往上錯開顯示（只影響顯示，不改資料）"))
        menu = W.QMenu(self); pop = W.QWidget(); hl = W.QHBoxLayout(pop); hl.setContentsMargins(6, 6, 6, 6); hl.setSpacing(6)
        for key, text, tip in defs:
            a_ = G.QAction(IC.ICONS[key](), text, self); a_.setCheckable(True); a_.setToolTip(tip)
            grp.addAction(a_); self.view_actions[key] = a_
            a_.triggered.connect(lambda _=False, m=key: (self.set_view_mode(m), menu.hide()))
            b_ = W.QToolButton(); b_.setDefaultAction(a_); b_.setIconSize(C.QSize(44, 44)); b_.setFixedSize(76, 76)
            b_.setToolButtonStyle(C.Qt.ToolButtonTextUnderIcon); hl.addWidget(b_)
        wa = W.QWidgetAction(menu); wa.setDefaultWidget(pop); menu.addAction(wa)
        self.act_single, self.act_multi, self.act_stack = (self.view_actions[k] for k in ("single", "multi", "stack"))
        self.act_multi.setChecked(True)
        self.view_btn = W.QToolButton(); self.view_btn.setMenu(menu); self.view_btn.setPopupMode(W.QToolButton.InstantPopup)
        self.view_btn.setToolButtonStyle(C.Qt.ToolButtonTextUnderIcon); self.view_btn.setIconSize(C.QSize(40, 40)); self.view_btn.setMinimumWidth(72)
        self.view_btn.setToolTip("顯示方式：單曲線 / 多重曲線 / 自動疊曲線")
        tb.addWidget(self.view_btn); self._sync_view_btn()
        tb.addSeparator()
        std("peaks", "峰分析", lambda: (self.center.setCurrentWidget(self.peaks), self.peaks.find() if self.items else None), "開啟 Peak Analysis：尋峰、峰位、峰高、峰面積、峰比值")
        std("rsd", "RSD", lambda: (self.center.setCurrentWidget(self.rsd), self.rsd.compute() if self.items else None), "開啟 RSD 重現性：標定特徵峰（峰高或區域面積），畫長條圖並計算平均、SD、RSD%")
        std("quant", "定量 / LOD", lambda: (self.center.setCurrentWidget(self.quant), self.quant.load() if self.quant.table.rowCount() != len(self.items) else None), "開啟定量與 LOD 模組")
        std("integral", "區間積分", lambda: (self.panel.setCurrentWidget(self.analysis_tab), self.compute_bands()), "計算 Analysis 面板中各區間的面積")
        std("fit", "全範圍", self.full_scale, "顯示全部範圍（Ctrl+0）")
        self._update_tips()
        self._equalize_toolbar(tb)

    def _equalize_toolbar(self, tb):
        """Give every toolbar button the same width / height so icons, labels and borders line up symmetrically."""
        btns = [b for b in tb.findChildren(W.QToolButton) if b.isVisibleTo(tb) or True]
        for b in btns:
            b.setIconSize(C.QSize(36, 36)); b.setToolButtonStyle(C.Qt.ToolButtonTextUnderIcon); b.setMinimumWidth(0)
            b.setSizePolicy(W.QSizePolicy.Fixed, W.QSizePolicy.Fixed)
        w = max([b.sizeHint().width() for b in btns] + [66]); h = max([b.sizeHint().height() for b in btns] + [64])
        for b in btns: b.setFixedSize(w, h)
        self.toolbar_size = (w, h)

    def layout_audit(self):
        """Symmetry checks: (a) every icon's content is centred in its canvas, (b) toolbar buttons share one size,
        (c) tool-strip buttons are square with equal margins around the icon. Returns a list of problems (empty = OK)."""
        problems = []
        for b in self.findChildren(W.QToolButton):
            if b.objectName() in ("SectionHead",) or (b.defaultAction() is None and not b.text() and not b.toolTip()): continue   # skip Qt's own "»" extension buttons
            ic = b.icon()
            if ic.isNull(): continue
            sz = ic.availableSizes()[0] if ic.availableSizes() else None
            if sz is None: continue
            bb = IC.content_bbox(ic.pixmap(sz))
            if bb:
                cx, cy = (bb[0] + bb[2]) / 2 - sz.width() / 2, (bb[1] + bb[3]) / 2 - sz.height() / 2
                if abs(cx) > 1.0 or abs(cy) > 1.0: problems.append(f"icon off-centre by ({cx:.1f},{cy:.1f}) in {(b.text() or b.toolTip())[:20]!r}")
        tb = self.findChildren(W.QToolBar)
        main = [t for t in tb if t.objectName() != "ToolStrip"]
        for t in main:
            sizes = {(b.width(), b.height()) for b in t.findChildren(W.QToolButton) if b.width() > 20 and b.height() > 20}
            if len(sizes) > 1: problems.append(f"toolbar buttons differ in size: {sorted(sizes)}")
        for b in self.toolbox.findChildren(W.QToolButton):
            if b.width() != b.height(): problems.append("tool-strip button not square")
            m = (b.width() - b.iconSize().width()) / 2
            if m != int(m): problems.append("tool-strip icon margin uneven")
        return problems

    def _update_tips(self):
        if not hasattr(self, "quick_actions"): return
        sv = self._op_values("smooth")[0]; bv = self._op_values("baseline")[0]; nv = self._op_values("normalize")[0]
        base_txt = bv["method"] + (f"，階數 {bv['order']}" if bv["method"] in ("Polynom(Manual)", "Polynom(Auto)", "Multi polynomial", "Lorentzian", "PolynomialFitting") else "")
        sm_txt = f"{sv['method']}，{sv['mode']}" + (f"，窗口 {sv['window']}" if sv["mode"] == "Manual" and sv["method"] != "FFT" else "")
        tips = {"average": "平均：把選取的 2 條以上光譜平均成新光譜",
                "crop": "裁切：若圖上有區間（Strip）就裁成區間範圍；否則開啟對話框。按箭頭可手動輸入範圍",
                "smooth": f"平滑：{sm_txt}（按箭頭可更改）",
                "baseline": f"去背景：{base_txt}（按箭頭可更改）",
                "normalize": f"均一化：{nv['m']}（按箭頭可更改）"}
        for k, a in self.quick_actions.items():
            a.setToolTip(tips[k]); a.setStatusTip(tips[k])

    # ---------------- helpers ----------------
    def _next_color(self):
        c = PALETTE[self._color_i % len(PALETTE)]; self._color_i += 1; return c

    def _snapshot(self):
        return [(it.spec, it.color, it.visible, it.group, it.raw, dict(it.stage)) for it in self.items]

    def _restore(self, snap):
        self.items = []
        for sp, col, vis, grp, raw, stg in snap:
            it = Item(sp, col); it.visible = vis; it.group = grp; it.raw = raw; it.stage = dict(stg); self.items.append(it)
        self.refresh()

    def push_undo(self):
        self.undo.append(self._snapshot()); self.redo.clear()
        if len(self.undo) > 100: self.undo.pop(0)
        self._refresh_actions()

    def do_undo(self):
        if self.undo:
            self.redo.append(self._snapshot()); self._restore(self.undo.pop()); self._refresh_actions()

    def do_redo(self):
        if self.redo:
            self.undo.append(self._snapshot()); self._restore(self.redo.pop()); self._refresh_actions()

    def _refresh_actions(self):
        self.act_undo.setEnabled(bool(self.undo)); self.act_redo.setEnabled(bool(self.redo))
        if hasattr(self, "tb_undo"):
            self.tb_undo.setEnabled(bool(self.undo)); self.tb_redo.setEnabled(bool(self.redo))

    def selected_idx(self):
        return sorted(self.listw.row(i) for i in self.listw.selectedItems())

    def targets(self, minimum=1):
        idx = self.selected_idx() or [i for i, it in enumerate(self.items) if it.visible]
        if len(idx) < minimum:
            W.QMessageBox.warning(self, APP_NAME, f"請先選取至少 {minimum} 條光譜。")
            return None
        return idx

    def refresh(self):
        self.listw.blockSignals(True)
        sel = set(self.selected_idx()); rows = []
        for i, it in enumerate(self.items):
            q = self.qc_of(it)
            rows.append((i, it.group, ("⚠ " if q["issues"] else "") + it.spec.name, it.color, it.visible, i in sel,
                         ("品質檢查：\n" + "\n".join(t for _, t in q["issues"])) if q["issues"] else ""))
        self.listw.rebuild(rows)
        self.listw.blockSignals(False)
        self._dirty = True
        lab = getattr(self, "x_label_override", None) or self.default_xlabel()
        if self.pi.getAxis("bottom").labelText != lab: self.pi.setLabel("bottom", lab)
        self.apply_filter()
        self.redraw()
        self.hist_label.setText(f"{len(self.items)} 條光譜")
        self._update_info(); self._fill_data_table()
        self.specbar.rebuild(self.items, set(self.selected_idx())); self._highlight_selected()

    # ---- display options (Display tab); defaults apply before the tab exists ----
    def _opt(self, name, default=False):
        w_ = getattr(self, name, None)
        return w_.isChecked() if w_ is not None else default

    def qc_of(self, it, run=False):
        """Quality-check result of a spectrum. Nothing is checked automatically (import, redraw): a spectrum has a result only after
        the user ran 品質檢查 on it; after any processing step (new spectrum object) it is unchecked again."""
        c = getattr(self, "_qc_cache", None)
        if c is None: c = self._qc_cache = {}
        hit = c.get(id(it.spec))
        if (hit is None or hit[0] is not it.spec) and not run:
            return {"issues": [], "nan_idx": [], "sat_idx": [], "spike_idx": []}
        if hit is None or hit[0] is not it.spec:
            from ramanproc import qc
            try: res = qc.check_spectrum(it.spec)
            except Exception as ex: res = {"issues": [("error", str(ex))], "nan_idx": [], "sat_idx": [], "spike_idx": []}
            if len(c) > 400: c.clear()
            hit = c[id(it.spec)] = (it.spec, res)
        return hit[1]

    def _xmap(self, x):
        """Display transform of the X axis: Raman shift (cm-1) -> shown X."""
        if getattr(self, "axis_mode", "shift") == "nm":
            return 1e7 / (1e7 / self.laser_nm() - np.asarray(x, float))
        return np.asarray(x, float)

    def _xunmap(self, xd):
        if getattr(self, "axis_mode", "shift") == "nm":
            return 1e7 / self.laser_nm() - 1e7 / xd
        return xd

    def laser_nm(self):
        w_ = getattr(self, "sp_laser", None)
        return float(w_.value()) if w_ is not None else 532.0

    def redraw(self):
        for c in list(self.curves.values()):
            self.pi.removeItem(c)
        for c in getattr(self, "extra_items", []):
            try: self.pi.removeItem(c)
            except Exception: pass
        self.extra_items = []
        self.curves = {}
        self.legend.clear()
        act = self._active_idx(); top = 0.0
        width = self.sp_width.value() if hasattr(self, "sp_width") else 1.5
        show_final = self._opt("cb_final", True); only_mean = self._opt("cb_only_mean")
        shown = []
        for i, it in enumerate(self.items):
            if not it.visible or (self.view_mode == "single" and i != act): continue
            shown.append(it)
            y = it.spec.y
            if self.view_mode == "stack":
                lo, hi = float(np.nanmin(y)), float(np.nanmax(y)); y = y + (top - lo); top = hi + (top - lo) + 0.1 * (hi - lo)
            if not show_final or (only_mean and self.view_mode != "stack"): continue
            c = self.pi.plot(self._xmap(it.spec.x), y, pen=pg.mkPen(it.color, width=width), name=it.spec.name)
            self.curves[id(it)] = c
        if self.view_mode != "stack":
            self._draw_compare(shown, act)
            self._draw_band(shown)
        self._draw_qc(shown)
        if hasattr(self, "specbar"): self._highlight_selected()

    def _add_extra(self, item, ignore_bounds=False):
        self.pi.addItem(item, ignoreBounds=ignore_bounds); self.extra_items.append(item)

    def _draw_compare(self, shown, act):
        """Before/after overlays (raw, smoothed, baseline) for the selected (or active) spectra."""
        want_raw, want_sm, want_bl = self._opt("cb_raw"), self._opt("cb_smooth"), self._opt("cb_base")
        if not (want_raw or want_sm or want_bl): return
        sel = set(self.selected_idx()) or ({act} if act >= 0 else set())
        for i in sel:
            if i >= len(self.items) or self.items[i] not in shown: continue
            it = self.items[i]; st = it.stage
            if want_raw and it.raw is not None:
                self._add_extra(pg.PlotDataItem(self._xmap(it.raw.x), it.raw.y, pen=pg.mkPen("#7f7f7f", width=1.2, style=C.Qt.DashLine)))
            if want_sm and "smooth" in st:
                self._add_extra(pg.PlotDataItem(self._xmap(st["smooth"].x), st["smooth"].y, pen=pg.mkPen("#ff7f0e", width=1.2, style=C.Qt.DotLine)))
            if want_bl and "base" in st:
                bx, by = st["base"]
                pre = st.get("pre_base")                  # show the baseline on top of the spectrum it was removed from
                self._add_extra(pg.PlotDataItem(self._xmap(bx), by, pen=pg.mkPen("#2ca02c", width=1.6, style=C.Qt.DashDotLine)))
                if pre is not None:
                    self._add_extra(pg.PlotDataItem(self._xmap(pre.x), pre.y, pen=pg.mkPen("#9467bd", width=1.0, style=C.Qt.DotLine)))

    def band_stats(self, specs):
        """Mean and sample SD of several spectra on the first one's grid (common X range only)."""
        base = specs[0]
        lo, hi = max(sp.x[0] for sp in specs), min(sp.x[-1] for sp in specs)
        m = (base.x >= lo) & (base.x <= hi); x = base.x[m]
        if len(x) < 2: raise ValueError("光譜沒有共同的 X 範圍")
        Y = np.vstack([np.interp(x, sp.x, sp.y) for sp in specs])
        return x, Y.mean(axis=0), (Y.std(axis=0, ddof=1) if len(specs) > 1 else np.zeros_like(x))

    def _draw_band(self, shown):
        if not self._opt("cb_band") or len(shown) < 2: return
        try: x, mu, sd = self.band_stats([it.spec for it in shown])
        except ValueError: return
        xd = self._xmap(x)
        up = pg.PlotDataItem(xd, mu + sd, pen=pg.mkPen(None)); dn = pg.PlotDataItem(xd, mu - sd, pen=pg.mkPen(None))
        fill = pg.FillBetweenItem(up, dn, brush=pg.mkBrush(29, 124, 212, 70))
        for it_ in (up, dn): self._add_extra(it_)
        self._add_extra(fill)
        mean = self.pi.plot(xd, mu, pen=pg.mkPen("#0b3d6b", width=2.2), name=f"平均 ± SD（n={len(shown)}）")
        self.extra_items.append(mean)

    def _draw_qc(self, shown):
        if not self._opt("cb_qc", True): return
        for it in shown:
            q = self.qc_of(it); sp = it.spec
            for key, sym, col in (("spike_idx", "d", "#ff7f0e"), ("sat_idx", "s", "#d62728")):
                idx = np.asarray(q[key], int)
                if len(idx):
                    self._add_extra(pg.ScatterPlotItem(self._xmap(sp.x[idx]), sp.y[idx], symbol=sym, size=9, brush=pg.mkBrush(col), pen=pg.mkPen("k")))
            nn = np.asarray(q["nan_idx"], int)
            if len(nn):
                yy = np.where(np.isfinite(sp.y), sp.y, np.nan); yv = float(np.nanmedian(yy)) if np.isfinite(yy).any() else 0.0
                self._add_extra(pg.ScatterPlotItem(self._xmap(sp.x[nn]), [yv] * len(nn), symbol="x", size=11, pen=pg.mkPen("#d62728", width=2)))

    def apply_filter(self):
        f = getattr(self, "filter_edit", None)
        txt = f.text().strip().lower() if f is not None else ""
        for r in range(self.listw.count()):
            it = self.items[r]
            self.listw.item(r).setHidden(bool(txt) and txt not in (it.spec.name + " " + it.group).lower())
        for h in self.listw.headers():
            h.setHidden(all(h.child(k).isHidden() for k in range(h.childCount())))

    def _list_changed(self, li, col=0):
        if self.listw._building: return
        if self.listw.is_header(li):                      # (un)check a whole group
            on = li.checkState(0) == C.Qt.Checked
            self.listw.blockSignals(True)
            for k in range(li.childCount()):
                ch = li.child(k); r = self.listw.row(ch)
                if 0 <= r < len(self.items): self.items[r].visible = on
                ch.setCheckState(0, C.Qt.Checked if on else C.Qt.Unchecked)
            self.listw.update_header(li); self.listw.blockSignals(False)
            self.redraw(); self.specbar.style_buttons(self.items, set(self.selected_idx())); self._highlight_selected(); return
        r = self.listw.row(li)
        if 0 <= r < len(self.items):
            self.items[r].visible = li.checkState(0) == C.Qt.Checked
            if li.parent() is not None:
                self.listw.blockSignals(True); self.listw.update_header(li.parent()); self.listw.blockSignals(False)
            self.redraw(); self.specbar.style_buttons(self.items, set(self.selected_idx())); self._highlight_selected()

    def readout_values(self, xd):
        """[(name, color, y or None)] of every visible spectrum at displayed X `xd`."""
        x = float(self._xunmap(xd)); out = []
        for it in self.items:
            if not it.visible: continue
            sp = it.spec
            out.append((sp.name, it.color, float(np.interp(x, sp.x, sp.y)) if sp.x[0] <= x <= sp.x[-1] else None))
        return out

    def eventFilter(self, obj, ev):
        t = ev.type()
        try:
            if (obj is self.plot.viewport() and t in (C.QEvent.Leave, C.QEvent.Hide)) or (obj is self and t == C.QEvent.WindowDeactivate):
                self._hide_cursor_marks()      # pointer left the Spectra plot / another tab / the window lost focus (e.g. screenshot tools)
        except RuntimeError:
            pass                               # widgets already deleted while the application shuts down
        return super().eventFilter(obj, ev)

    def _hide_cursor_marks(self):
        ro = getattr(self, "readout", None)
        if ro is not None: ro.setVisible(False)
        self.vline.setVisible(False); self.hline.setVisible(False)
        self.statusBar().clearMessage()

    def _mouse_moved(self, pos):
        ro = getattr(self, "readout", None)
        if self.pi.vb.sceneBoundingRect().contains(pos):
            p = self.pi.vb.mapSceneToView(pos)
            self.vline.setPos(p.x()); self.hline.setPos(p.y())
            self.vline.setVisible(True); self.hline.setVisible(getattr(self, "tool", None) == T.XY)
            vals = self.readout_values(p.x()) if self.items else []
            xl = f"λ = {p.x():.2f} nm" if getattr(self, "axis_mode", "shift") == "nm" else f"X = {p.x():.2f}"
            msg = f"{xl}   Y = {p.y():.4g}"
            if vals: msg += "   |   " + "   ".join(f"{n}: {('—' if y is None else format(y, '.5g'))}" for n, _, y in vals[:6]) + (" …" if len(vals) > 6 else "")
            self.statusBar().showMessage(msg)
            if ro is None:
                ro = self.readout = pg.TextItem(anchor=(0, 1), fill=pg.mkBrush(255, 255, 255, 215), border=pg.mkPen("#999"))
                ro.setZValue(50); self.pi.addItem(ro, ignoreBounds=True)
            if self._opt("cb_readout", True) and vals:
                import html
                rows = "".join(f"<span style='color:{c}'>■</span> {html.escape(n)}: <b>{'—' if y is None else format(y, '.5g')}</b><br>" for n, c, y in vals[:8])
                ro.setHtml(f"<div style='font-size:9pt'>{xl.replace('X = ', 'X=')}<br>{rows}</div>"); ro.setPos(p.x(), p.y()); ro.setVisible(True)
            else:
                ro.setVisible(False)
        elif ro is not None:
            ro.setVisible(False)

    def full_scale(self):
        self.pi.autoRange()

    def add_spectrum(self, spec, color=None, group=None):
        """`group` = group label for the new spectrum (derived results inherit their source's group)."""
        it = Item(spec, color or self._next_color()); self.items.append(it)
        if group: it.group = group
        return it

    def group_of(self, idx):
        """Group shared by all spectra `idx`; if they come from different groups, the first one's group."""
        gs = [self.items[i].group for i in idx if 0 <= i < len(self.items)]
        gs = [g for g in gs if g]
        return gs[0] if gs else ""

    # ---------------- file I/O ----------------
    def open_files(self):
        paths, _ = W.QFileDialog.getOpenFileNames(self, "開啟光譜", "", "光譜文字檔 (*.txt *.csv *.dat *.xy);;所有檔案 (*)")
        if paths: self.load_paths(paths)

    def load_paths(self, paths, quiet=False):
        """Tolerant import: headers / BOM / encodings handled, unsorted or duplicate X fixed — and reported, never silent."""
        from ramanproc import safeio
        report, loaded = [], 0
        self.push_undo()
        for p in paths:
            try:
                for sp, notes in safeio.load_spectra(p):
                    it_ = self.add_spectrum(sp); loaded += 1
                    mt = getattr(sp, "meta", None) or {}
                    if mt.get("hidden"): it_.visible = False
                    elif mt.get("ylabel") and mt.get("xunit") == "nm": self.cb_yunit.setCurrentText(mt["ylabel"])
                    if notes: report.append(f"{sp.name}：" + "；".join(notes))
            except Exception as ex:
                report.append(f"✗ {os.path.basename(p)}：無法讀取（{ex}）")
        if not loaded: self.undo.pop(); self._refresh_actions()
        self.refresh(); self.full_scale()
        self.import_report = report
        if report and not quiet:
            W.QMessageBox.information(self, "匯入報告", f"已載入 {loaded} 條光譜。\n\n" + "\n".join(report[:30]) + ("\n…" if len(report) > 30 else ""))
        return loaded

    @staticmethod
    def _is_xyxy(path):
        try:
            with open(path) as f:
                line = f.readline()
            return len(line.replace(",", " ").split()) >= 4
        except Exception:
            return False

    def save_selected(self):
        idx = self.targets()
        if not idx: return
        if len(idx) == 1:
            p, _ = W.QFileDialog.getSaveFileName(self, "儲存光譜", self.items[idx[0]].spec.name + ".txt", "文字檔 (*.txt)")
            if p: rp.write_xy(self.items[idx[0]].spec, p)
        else:
            d = W.QFileDialog.getExistingDirectory(self, "選擇儲存資料夾")
            if d:
                for i in idx: rp.write_xy(self.items[i].spec, os.path.join(d, self.items[i].spec.name + ".txt"))
        self.statusBar().showMessage("已儲存")

    def export_xyy(self):
        vis = [it.spec for it in self.items if it.visible]
        if not vis: return
        p, _ = W.QFileDialog.getSaveFileName(self, "匯出 XYY", "spectra_xyy.txt", "文字檔 (*.txt)")
        if p: rp.write_xyy(vis, p)

    def export_image(self):
        p, _ = W.QFileDialog.getSaveFileName(self, "匯出圖片", "figure.png", "PNG (*.png);;SVG 向量 (*.svg);;PDF 向量 (*.pdf)")
        if p: self.export_figure(p)

    def export_figure(self, p, width=None, aspect="ui"):
        """Save the plot as currently viewed (zoom, axes, overlays). PNG raster; SVG / PDF vector.
        aspect: "ui" = ratio chosen in Display > Export (default 6:5 like the reference figure), None = keep the window ratio, or a number (w/h)."""
        if aspect == "ui": aspect = self.figstyle.aspect.currentData() if hasattr(self, "figstyle") else None
        if width is None: width = self.figstyle.png_w.value() if hasattr(self, "figstyle") else 2000
        hidden = [w_ for w_ in (self.vline, self.hline, getattr(self, "readout", None)) if w_ is not None and w_.isVisible()]
        for w_ in hidden: w_.setVisible(False)
        old = (self.plot.minimumSize(), self.plot.maximumSize())
        qc_was = self.cb_qc.isChecked()
        if qc_was: self.cb_qc.setChecked(False)          # QC markers (spike / saturation) are for inspection, not for the figure
        try:
            if aspect:                                   # lay the figure out at the target ratio, independent of the window
                self.plot.setFixedSize(EXPORT_BASE_W, int(round(EXPORT_BASE_W / aspect))); W.QApplication.processEvents()
            low = p.lower()
            if low.endswith(".pdf"):
                w_ = G.QPdfWriter(p); w_.setResolution(96)
                w_.setPageSize(G.QPageSize(C.QSizeF(self.plot.width() * 72 / 96 + 20, self.plot.height() * 72 / 96 + 20), G.QPageSize.Point))
                w_.setPageMargins(C.QMarginsF(0, 0, 0, 0))
                pt = G.QPainter(w_); pt.translate(10 * 96 / 72, 10 * 96 / 72); self.plot.render(pt); pt.end()
            elif low.endswith(".svg"):       # QtSvg writes real vector output (pyqtgraph's SVGExporter is incompatible with recent Qt)
                from PySide6.QtSvg import QSvgGenerator
                g = QSvgGenerator(); g.setFileName(p); g.setSize(self.plot.size()); g.setViewBox(C.QRect(0, 0, self.plot.width(), self.plot.height()))
                g.setTitle(APP_NAME); pt = G.QPainter(g); self.plot.render(pt); pt.end()
            else:
                import pyqtgraph.exporters as ex
                exporter = ex.ImageExporter(self.pi); exporter.parameters()["width"] = int(width)
                if self.cb_bg.currentIndex() == 0: exporter.parameters()["background"] = "w"
                exporter.export(p)
        finally:
            self.plot.setMinimumSize(old[0]); self.plot.setMaximumSize(old[1])
            if qc_was: self.cb_qc.setChecked(True)
            for w_ in hidden: w_.setVisible(True)
            W.QApplication.processEvents()
        self.statusBar().showMessage(f"已匯出 {os.path.basename(p)}")

    # ---------------- list editing ----------------
    def rename_selected(self):
        idx = self.selected_idx()
        if len(idx) != 1: return
        name, ok = W.QInputDialog.getText(self, "重新命名", "新名稱：", text=self.items[idx[0]].spec.name)
        if ok and name:
            self.push_undo(); self.items[idx[0]].spec.name = name; self.refresh()

    def _list_menu(self, pos):
        m = W.QMenu(self)
        for text, fn in [("重新命名…", self.rename_selected), ("改色…", self.recolor_selected), ("設定群組…", self.group_selected), (None, None),
                         ("顯示選取", lambda: self.set_visible_sel(True)), ("隱藏選取", lambda: self.set_visible_sel(False)),
                         ("只顯示選取", self.show_only_selected), ("全部顯示", self.show_all), ("只顯示此群組", self.show_group_of_selected), (None, None),
                         ("展開全部群組", lambda: self.listw.set_all_folded(False)), ("摺疊全部群組", lambda: self.listw.set_all_folded(True)), (None, None),
                         ("品質檢查", self.qc_report), ("刪除", self.remove_selected)]:
            if text is None: m.addSeparator()
            else: m.addAction(text).triggered.connect(lambda _=False, f=fn: f())
        m.exec(self.listw.viewport().mapToGlobal(pos))

    def recolor_selected(self, color=None):
        idx = self.selected_idx()
        if not idx: return
        if color is None:
            qc_ = W.QColorDialog.getColor(G.QColor(self.items[idx[0]].color), self, "選擇顏色")
            if not qc_.isValid(): return
            color = qc_.name()
        self.push_undo()
        for i in idx: self.items[i].color = color
        self.refresh()

    def group_selected(self, name=None):
        idx = self.selected_idx()
        if not idx: return
        if name is None:
            name, ok = W.QInputDialog.getText(self, "群組", "群組名稱（留空＝取消群組）：", text=self.items[idx[0]].group)
            if not ok: return
        self.push_undo()
        for i in idx: self.items[i].group = name.strip()
        self.refresh()

    def set_visible_sel(self, v):
        idx = self.selected_idx()
        if not idx: return
        self.push_undo()
        for i in idx: self.items[i].visible = v
        self.refresh()

    def show_only_selected(self):
        idx = set(self.selected_idx())
        if not idx: return
        self.push_undo()
        for i, it in enumerate(self.items): it.visible = i in idx
        self.refresh()

    def show_all(self):
        self.push_undo()
        for it in self.items: it.visible = True
        self.refresh()

    def show_group_of_selected(self):
        idx = self.selected_idx()
        if not idx: return
        g = self.items[idx[0]].group; self.push_undo()
        for it in self.items: it.visible = (it.group == g)
        self.refresh()

    def sort_items(self, key):
        keys = {"name": lambda it: it.spec.name.lower(), "group": lambda it: (it.group.lower(), it.spec.name.lower()),
                "xstart": lambda it: float(it.spec.x[0]), "ymax": lambda it: -float(np.nanmax(it.spec.y))}
        sel = [self.items[i] for i in self.selected_idx()]
        self.push_undo(); self.items.sort(key=keys[key])
        self.listw.clearSelection(); self.refresh()
        self.listw.blockSignals(True)
        for it in sel: self.listw.item(self.items.index(it)).setSelected(True)
        self.listw.blockSignals(False); self._selection_changed()

    def qc_report(self):
        """Per-spectrum data-quality report: saturation, spikes, missing points, flat spectra."""
        lines = []
        for it in self.items:
            q = self.qc_of(it, run=True)
            lines.append(("⚠ " if q["issues"] else "✓ ") + it.spec.name + ("：" + "；".join(t for _, t in q["issues"]) if q["issues"] else "：正常"))
        txt = "\n".join(lines) or "（沒有光譜）"
        if self.items: self.refresh()                       # show the ⚠ marks / plot markers for the spectra just checked
        W.QMessageBox.information(self, "品質檢查", txt)
        return txt

    def remove_selected(self):
        idx = self.selected_idx()
        if not idx: return
        self.push_undo()
        for i in reversed(idx): del self.items[i]
        self.refresh()

    # ---------------- operations ----------------
    def _track_stage(self, it, key, old, new):
        if key == "smooth":
            it.stage["smooth"] = new
        elif key == "baseline":
            it.stage["pre_base"] = old
            it.stage["base"] = (np.asarray(new.x), np.interp(new.x, old.x, old.y) - np.asarray(new.y))

    def _apply(self, idx, fn, label, create_new, key=None):
        """fn(Spectrum)->Spectrum applied to items[idx]."""
        try:
            results = [(i, fn(self.items[i].spec)) for i in idx]
        except Exception as ex:
            W.QMessageBox.warning(self, label, str(ex)); return
        self.push_undo()
        for i, new in results:
            src = self.items[i]; old = src.spec
            if create_new:
                new.name = f"{label}_{src.spec.name}"
                tgt = self.add_spectrum(new); tgt.raw, tgt.group, tgt.stage = src.raw, src.group, dict(src.stage)
            else:
                new.name = src.spec.name
                src.spec = new; tgt = src
            self._track_stage(tgt, key, old, new)
        self.refresh()
        self.statusBar().showMessage(f"{label} 完成（{len(results)} 條）")

    def _dialog_op(self, title, fields, build, note=None, minimum=1):
        idx = self.targets(minimum)
        if not idx: return
        dlg = ParamDialog(title, fields, self, note=note)
        if dlg.exec() != W.QDialog.Accepted: return
        v = dlg.values()
        self._apply(idx, lambda s: build(s, v), title.split()[0], dlg.wants_new())

    # ---- operations with remembered parameters (one-click + dialog) ----
    OPS = {
        "smooth": ("平滑", [
            {"key": "method", "label": "Methods", "type": "combo", "options": FL.METHODS, "default": "Polynomial"},
            {"key": "mode", "label": "Mode", "type": "combo", "options": FL.MODES, "default": "Automatic"},
            {"key": "window", "label": "Window (pnt)", "type": "slider", "min": 3, "max": 301, "default": 11, "odd": True,
             "enable": lambda v: v["mode"] == "Manual" and v["method"] != "FFT"},
            {"key": "order", "label": "Order", "type": "slider", "min": 1, "max": 12, "default": 3,
             "enable": lambda v: v["method"] in ("Polynomial", "1st derivative", "2nd derivative") or (v["method"] == "SVD" and v["mode"] == "Manual")},
            {"key": "factor", "label": "Factor (%)", "type": "slider", "min": 1, "max": 100, "default": 10,
             "enable": lambda v: (v["mode"] == "Automatic" and v["method"] not in ("FFT", "SVD", "Despike")) or (v["mode"] == "Manual" and v["method"] == "FFT")}],
            None),
        "baseline": ("去背景", [
            {"key": "method", "label": "Type", "type": "combo", "default": "Polynom(Auto)", "options": BL.TYPES + list(BL.LEGACY)},
            {"key": "order", "label": "Order", "type": "slider", "default": 3, "min": 1, "max": 12,
             "show": lambda v: v["method"] in ("Polynom(Manual)", "Polynom(Auto)", "Multi polynomial", "Lorentzian", "PolynomialFitting")},
            {"key": "max_points", "label": "Max points", "type": "slider", "default": 123, "min": 4, "max": 500,
             "show": lambda v: v["method"] in BL.ANCHOR_AUTO},
            {"key": "noise_points", "label": "Noise points", "type": "slider", "default": 64, "min": 1, "max": 500,
             "show": lambda v: v["method"] in BL.ANCHOR_AUTO},
            {"key": "width", "label": "Width (cm⁻¹)", "type": "float", "default": 100.0, "min": 1, "decimals": 1,
             "show": lambda v: v["method"] in ("Rolling Ball", "IterativeClipping")},
            {"key": "loglam", "label": "Smoothness log₁₀λ", "type": "float", "default": 5.0, "min": 0, "max": 12, "decimals": 1, "step": 0.5,
             "show": lambda v: v["method"] in ("Whittaker 1", "Whittaker 2")},
            {"key": "asym", "label": "Asymmetry p", "type": "float", "default": 0.01, "min": 0.0001, "max": 0.5, "decimals": 4, "step": 0.005,
             "show": lambda v: v["method"] == "Whittaker 1"},
            {"key": "correct_noise", "label": "", "type": "check", "default": True, "text": "Correct noise",
             "show": lambda v: v["method"] in BL.ANCHOR_AUTO},
            {"key": "attach", "label": "", "type": "check", "default": True, "text": "Attach to curve",
             "show": lambda v: v["method"] in BL.MANUAL, "tip": "手動加錨點時自動吸附到曲線"},
            {"key": "color", "label": "Color", "type": "combo", "options": ["Red", "Green", "Blue", "Orange", "Purple", "Black"], "default": "Red"}],
            "Fit 只顯示基線；Sub 才扣除。除 IterativeClipping／PolynomialFitting 外，各類型的參數定義為本軟體自行訂定，未與參考軟體比對；保留原 X 間距，不截斷負值。"),
        "cosmic": ("去宇宙射線", [
            {"key": "w", "label": "中位數窗口（奇數）", "type": "int", "default": 7, "min": 3, "max": 101, "step": 2}], None),
        "normalize": ("均一化", [
            {"key": "m", "label": "方法", "type": "combo", "options": ["YValue (min-max)", "UnderlineArea", "Max (y/max)", "Vector (L2)", "Peak height 峰高", "Peak area 峰面積"],
             "default": "YValue (min-max)"},
            {"key": "center", "label": "峰位 (cm⁻¹)", "type": "float", "default": 1075.0, "decimals": 1, "min": -1e6, "max": 1e6, "show": lambda v: v["m"].startswith("Peak") and not v["use_strip"]},
            {"key": "hw", "label": "視窗半寬", "type": "float", "default": 10.0, "decimals": 1, "min": 0.1, "max": 1e5, "show": lambda v: v["m"].startswith("Peak") and not v["use_strip"]},
            {"key": "use_strip", "label": "", "type": "check", "text": "以圖上區間（Strip）決定範圍", "default": False, "show": lambda v: v["m"].startswith("Peak")},
            {"key": "bl", "label": "", "type": "check", "text": "先扣區間兩端的直線基線", "default": False, "show": lambda v: v["m"].startswith("Peak")}],
            "Max：y/最大值（不扣基線）；L2：y/√Σy²；Peak height / area：每條光譜除以自己在該峰位視窗（或 Strip）的峰高／面積，做內標峰歸一化。"
            "各方法的定義為通用定義，未與參考軟體比對。"),
    }

    def _baseline_kwargs(self, v):
        return dict(order=v["order"], max_points=v["max_points"], noise_points=v["noise_points"], correct_noise=v["correct_noise"],
                    points=self.bl_pts, width=v["width"], loglam=v["loglam"], asym=v["asym"])

    def _build_op(self, key, s, v):
        if key == "smooth":
            return FL.apply_filter([s], v["method"], v["mode"], v["window"], v["order"], v["factor"])[0]
        if key == "baseline":
            m = v["method"]
            if m == "IterativeClipping": return rp.remove_baseline(s, "iterative_clipping", peak_width=v["width"])
            if m == "PolynomialFitting": return rp.remove_baseline(s, "polynomial", order=v["order"])
            base, _ = BL.fit_baseline(s, m, **self._baseline_kwargs(v))
            return BL.subtract(s, base, m)
        if key == "cosmic":
            return rp.remove_cosmic_ray(s, v["w"] if v["w"] % 2 else v["w"] + 1)
        if key == "normalize":
            m = v["m"]
            if m.startswith("Peak"):
                c, hw = float(v["center"]), float(v["hw"])
                if v.get("use_strip"):
                    if self.strip is None: raise ValueError("圖上沒有區間（Strip）。請先畫一個區間，或取消勾選「以圖上區間決定範圍」。")
                    a, b = sorted(float(t) for t in np.atleast_1d(self._xunmap(np.asarray(self.strip.getRegion(), float))))
                    c, hw = 0.5 * (a + b), 0.5 * (b - a)
                return rp.normalize(s, "peak_height" if "height" in m else "peak_area", center=c, hw=hw, baseline=bool(v.get("bl")))
            method = {"Y": "minmax", "U": "area", "M": "max", "V": "l2"}[m[0]]
            return rp.normalize(s, method)

    def _op_values(self, key):
        title, fields, _ = self.OPS[key]
        stored = self.params.get(key, {})
        return {f["key"]: stored.get(f["key"], f.get("default")) for f in fields}, bool(stored.get("_new", False))

    def run_op(self, key, quick=False):
        title, fields, note = self.OPS[key]
        idx = self.targets()
        if not idx: return
        vals, new = self._op_values(key)
        if not quick:
            fl = [dict(f, default=vals[f["key"]]) for f in fields]
            dlg = ParamDialog(f"{title}", fl, self, note=note)
            dlg.create_new.setChecked(new)
            if dlg.exec() != W.QDialog.Accepted: return
            vals, new = dlg.values(), dlg.wants_new()
            self.params[key] = {**vals, "_new": new}
            self._update_tips(); self._sync_panels()
        if key == "smooth":
            try:
                outs = FL.apply_filter([self.items[i].spec for i in idx], vals["method"], vals["mode"], vals["window"], vals["order"], vals["factor"])
            except Exception as ex:
                W.QMessageBox.warning(self, title, str(ex)); return
            look = {id(self.items[i].spec): o for i, o in zip(idx, outs)}
            self._apply(idx, lambda s: look[id(s)], title, new, key=key); return
        self._apply(idx, lambda s: self._build_op(key, s, vals), title, new, key=key)

    def op_smooth(self): self.run_op("smooth")
    def op_baseline(self): self.run_op("baseline")
    def op_cosmic(self): self.run_op("cosmic")
    def op_normalize(self): self.run_op("normalize")

    def op_ayb(self):
        self._dialog_op("A*Y+B", [{"key": "a", "label": "A", "type": "float", "default": 1.0, "decimals": 6},
                                  {"key": "b", "label": "B", "type": "float", "default": 0.0, "decimals": 6}],
                        lambda s, v: rp.ayb(s, v["a"], v["b"]))

    def op_logy(self):
        self._dialog_op("LogY", [{"key": "base", "label": "底數", "type": "float", "default": 10.0, "min": 1.01}],
                        lambda s, v: rp.log_y(s, v["base"]), note="底數與定義尚未與參考軟體比對；需 Y 全為正。")

    def op_uniformx(self):
        self._dialog_op("UniformX", [{"key": "step", "label": "X 間距", "type": "float", "default": 0.5, "min": 0.001, "decimals": 3}],
                        lambda s, v: rp.uniform_x(s, v["step"]))

    def op_crop(self, quick=False):
        idx = self.targets()
        if not idx: return
        if quick is True and self.strip is not None:
            a, b = self.strip.getRegion()
            self._apply(idx, lambda s: rp.crop(s, min(a, b), max(a, b)), "裁切", False); return
        lo = min(self.items[i].spec.x[0] for i in idx); hi = max(self.items[i].spec.x[-1] for i in idx)
        if self.strip is not None:
            lo, hi = self.strip.getRegion()
        dlg = ParamDialog("Crop 裁切", [{"key": "lo", "label": "X 最小", "type": "float", "default": float(lo), "decimals": 2},
                                        {"key": "hi", "label": "X 最大", "type": "float", "default": float(hi), "decimals": 2}], self,
                          note="若圖上有區間（Strip），預設取其範圍。")
        if dlg.exec() != W.QDialog.Accepted: return
        v = dlg.values()
        self._apply(idx, lambda s: rp.crop(s, v["lo"], v["hi"]), "Crop", dlg.wants_new())

    def op_standardize(self):
        idx = self.targets()
        if idx: self._apply(idx, rp.standardize, "Standardize", False)

    def op_average(self):
        idx = self.targets(2)
        if not idx: return
        self.push_undo(); self.add_spectrum(rp.average([self.items[i].spec for i in idx], "Average"), group=self.group_of(idx)); self.refresh()

    def op_stdcurve(self):
        idx = self.targets(2)
        if not idx: return
        self.push_undo(); self.add_spectrum(rp.std_curve([self.items[i].spec for i in idx], "StdDev"), group=self.group_of(idx)); self.refresh()

    def op_ay1by2c(self):
        idx = self.selected_idx()
        if len(idx) != 2:
            W.QMessageBox.warning(self, "A*Y1 ± B*Y2 + C", "請剛好選取 2 條光譜（第一條為 Y1）。"); return
        dlg = ParamDialog("A*Y1 ? B*Y2 + C", [
            {"key": "op", "label": "運算", "type": "combo", "options": ["+", "-", "*", "/"], "default": "-"},
            {"key": "a", "label": "A", "type": "float", "default": 1.0, "decimals": 6},
            {"key": "b", "label": "B", "type": "float", "default": 1.0, "decimals": 6},
            {"key": "c", "label": "C", "type": "float", "default": 0.0, "decimals": 6}], self, allow_new=False)
        if dlg.exec() != W.QDialog.Accepted: return
        v = dlg.values()
        try:
            new = rp.ay1_by2_c(self.items[idx[0]].spec, self.items[idx[1]].spec, v["a"], v["b"], v["c"], v["op"])
        except Exception as ex:
            W.QMessageBox.warning(self, "錯誤", str(ex)); return
        new.name = f"{self.items[idx[0]].spec.name}{v['op']}{self.items[idx[1]].spec.name}"
        self.push_undo(); self.add_spectrum(new, group=self.group_of(idx)); self.refresh()

    def op_points(self):
        idx = self.selected_idx()
        if len(idx) != 1:
            W.QMessageBox.warning(self, "增刪點", "請只選取 1 條光譜。"); return
        dlg = ParamDialog("增刪點", [
            {"key": "mode", "label": "動作", "type": "combo", "options": ["新增點", "刪除最近的點"]},
            {"key": "x", "label": "X", "type": "float", "default": 0.0, "decimals": 3},
            {"key": "y", "label": "Y（新增時使用）", "type": "float", "default": 0.0, "decimals": 6}], self, allow_new=False)
        if dlg.exec() != W.QDialog.Accepted: return
        v = dlg.values(); s = self.items[idx[0]].spec
        try:
            new = rp.add_point(s, v["x"], v["y"]) if v["mode"] == "新增點" else rp.remove_point(s, v["x"])
        except Exception as ex:
            W.QMessageBox.warning(self, "錯誤", str(ex)); return
        new.name = s.name; self.push_undo(); self.items[idx[0]].spec = new; self.refresh()

    STACK_ORDERS = ["清單順序", "名稱（自然排序）", "群組", "X 起點", "最大強度（小→大）", "最大強度（大→小）"]

    def _stack_order(self, idx, kind):
        """Item indices in the order they are stacked (first = first in the chosen order). Stable for ties."""
        import re
        nat = lambda t: [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", t)]      # s2 < s10
        keys = {"清單順序": lambda i: i,
                "名稱（自然排序）": lambda i: nat(self.items[i].spec.name),
                "群組": lambda i: (nat(self.items[i].group or ""), nat(self.items[i].spec.name)),
                "X 起點": lambda i: float(self.items[i].spec.x[0]),
                "最大強度（小→大）": lambda i: float(np.nanmax(self.items[i].spec.y)),
                "最大強度（大→小）": lambda i: -float(np.nanmax(self.items[i].spec.y))}
        return sorted(idx, key=keys[kind])

    def apply_stack(self, idx, order="清單順序", first_at_bottom=True, gap_pct=10.0, reorder_list=False):
        ordered = self._stack_order(idx, order)
        seq = ordered if first_at_bottom else ordered[::-1]            # auto_stacking puts the first one at the bottom
        stacked = rp.auto_stacking([self.items[i].spec for i in seq], gap_pct / 100.0)
        self.push_undo()
        for i, s_ in zip(seq, stacked):
            s_.name = self.items[i].spec.name; self.items[i].spec = s_
        if reorder_list:                                                # same slots in the list, new order of the selected spectra
            old = list(self.items)
            for slot, i in zip(sorted(idx), ordered): self.items[slot] = old[i]
        self.refresh(); self.full_scale()

    def op_stack(self):
        idx = self.targets(2)
        if not idx: return
        dlg = ParamDialog("自動堆疊 Auto Stacking", [
            {"key": "order", "label": "光譜排序", "type": "combo", "options": self.STACK_ORDERS, "default": self.STACK_ORDERS[0]},
            {"key": "dir", "label": "堆疊方向", "type": "combo", "options": ["排序第一條在最下", "排序第一條在最上"], "default": "排序第一條在最下"},
            {"key": "gap", "label": "間距（% 強度範圍）", "type": "float", "default": 10.0, "min": 0.0, "max": 500.0, "decimals": 1, "step": 5.0},
            {"key": "reorder", "label": "", "type": "check", "text": "同時依此順序重排光譜清單", "default": False}],
            self, allow_new=False, note="堆疊會把各光譜的 Y 值加上偏移量（可用 Ctrl+Z 復原）；之後若要做定量，請先復原。")
        if dlg.exec() != W.QDialog.Accepted: return
        v = dlg.values()
        self.apply_stack(idx, v["order"], v["dir"].endswith("最下"), v["gap"], v["reorder"])

    # ---------------- strips ----------------
    @property
    def strip(self):
        return self.strips[-1] if self.strips else None

    def add_strip(self, a=None, b=None):
        if a is None or b is None or isinstance(a, bool):       # a QAction's triggered(checked) may hand us a bool
            (x0, x1), _ = self.pi.viewRange(); a, b = x0 + (x1 - x0) * 0.4, x0 + (x1 - x0) * 0.6
        r = pg.LinearRegionItem([a, b], brush=pg.mkBrush(255, 165, 0, 50))
        self.pi.addItem(r); self.strips.append(r)
        return r

    def toggle_strip(self):      # menu: add one strip
        self.add_strip()

    def clear_strips(self):
        for r in self.strips: self.pi.removeItem(r)
        self.strips = []

    def op_integral(self):
        idx = self.targets()
        if not idx: return
        dlg = W.QDialog(self); dlg.setWindowTitle("Integral 積分")
        lay = W.QVBoxLayout(dlg)
        rb_val = W.QRadioButton("以輸入值決定範圍"); rb_str = W.QRadioButton("以圖上區間（Strip）決定範圍"); rb_val.setChecked(True)
        lo = W.QDoubleSpinBox(); hi = W.QDoubleSpinBox()
        for w in (lo, hi): w.setRange(-1e9, 1e9); w.setDecimals(2)
        lo.setValue(float(min(self.items[i].spec.x[0] for i in idx))); hi.setValue(float(max(self.items[i].spec.x[-1] for i in idx)))
        row = W.QHBoxLayout(); row.addWidget(W.QLabel("∫ 從")); row.addWidget(lo); row.addWidget(W.QLabel("到")); row.addWidget(hi); row.addWidget(W.QLabel("Y(X) dX"))
        lay.addWidget(rb_val); lay.addWidget(rb_str); lay.addLayout(row)
        out = W.QPlainTextEdit(); out.setReadOnly(True); out.setMinimumHeight(120); lay.addWidget(out)
        def calc():
            if rb_str.isChecked():
                if not self.strips: out.setPlainText("圖上尚無區間，請先用「區間 → 加入」或工具箱的 Draw Strip。"); return
                ranges = [r.getRegion() for r in self.strips]
            else:
                ranges = [(lo.value(), hi.value())]
            lines = []
            for a, b in ranges:
                lines.append(f"範圍：{a:.2f} – {b:.2f}（超出資料範圍的部分會被裁掉）")
                for i in idx:
                    lines.append(f"  {self.items[i].spec.name}: {rp.integral(self.items[i].spec, a, b):.2f}")
            out.setPlainText("\n".join(lines))
        btn = W.QPushButton("計算"); btn.clicked.connect(calc); lay.addWidget(btn)
        close = W.QPushButton("關閉"); close.clicked.connect(dlg.accept); lay.addWidget(close)
        calc(); dlg.exec()

    def op_peaks(self):
        """Menu entry: open the Peak Analysis module and run the peak search."""
        if not self.targets(): return
        self.center.setCurrentWidget(self.peaks); self.peaks.find()

    def do_peaks(self, rel_pct, dist):
        self.center.setCurrentWidget(self.peaks)
        return self.peaks.find(rel_pct, dist)

    def clear_labels(self):
        for t in self.labels: self.pi.removeItem(t)
        self.labels = []
        for m in self.marks: self.pi.removeItem(m)
        self.marks = []

    def clear_all_marks(self):
        """Remove every mark on the Spectra page: peak labels, fit curves, text / image notes, strips, cursors, X line, manual-baseline points."""
        self.clear_labels(); self.remove_annots("text"); self.remove_annots("image"); self.clear_strips(); self.clear_cursor(); self.clear_xline(); self.clear_dxline()
        self.bl_pts = []; self.bl_fit = None
        self._bl_update()
        if getattr(self, "bl_anchor", None) is not None: self.bl_anchor.setData([], [])
        if getattr(self, "bl_curve", None) is not None: self.bl_curve.setData([], [])
        if hasattr(self, "peak_sec"): self.peak_sec.rows = []; self.peak_sec.fits = []; self.peak_sec.table.setRowCount(0)
        self.statusBar().showMessage("已移除頁面上所有標記")


    # ---------------- mouse tools ----------------
    def set_tool(self, tid):
        self.tool = tid
        vb = self.vb
        vb.setMouseMode(pg.ViewBox.RectMode if tid == T.ZOOM else pg.ViewBox.PanMode)
        self.hline.setVisible(tid == T.XY)
        cursors = {T.POINTER: C.Qt.ArrowCursor, T.ZOOM: C.Qt.CrossCursor, T.XY: C.Qt.CrossCursor, T.XLINE: C.Qt.SplitHCursor, T.DXLINE: C.Qt.SplitHCursor, T.ERASER: C.Qt.CrossCursor, T.BASELINE: C.Qt.CrossCursor, T.CURSOR: C.Qt.CrossCursor,
                   T.TEXT: C.Qt.IBeamCursor, T.IMAGE: C.Qt.CrossCursor, T.SHIFT: C.Qt.SizeVerCursor, T.MULTIPLY: C.Qt.SizeVerCursor,
                   T.DRAW_STRIP: C.Qt.SizeHorCursor, T.REMOVE_STRIP: C.Qt.PointingHandCursor, T.LABEL_PEAK: C.Qt.PointingHandCursor}
        self.plot.setCursor(cursors.get(tid, C.Qt.ArrowCursor))
        if tid == T.BASELINE and hasattr(self, "panel"):
            self.panel.setCurrentIndex(2)
        self.statusBar().showMessage(T.TOOL_TIPS.get(tid, ""))

    def _tool_targets(self):
        idx = self.selected_idx()
        if idx: return idx
        vis = [i for i, it in enumerate(self.items) if it.visible]
        return vis[-1:] if vis else []

    def _nearest_point(self, p):
        """(item_index, point_index) of the visible data point nearest to view-coord p (normalised distance)."""
        import numpy as np
        (x0, x1), (y0, y1) = self.pi.viewRange()
        sx, sy = max(x1 - x0, 1e-12), max(y1 - y0, 1e-12)
        best = None
        for i, it in enumerate(self.items):
            if not it.visible: continue
            x, y = it.spec.x, it.spec.y
            k = int(np.clip(np.searchsorted(x, p.x()), 1, len(x) - 1)) if len(x) > 1 else 0
            for j in (k - 1, k):
                d = ((x[j] - p.x()) / sx) ** 2 + ((y[j] - p.y()) / sy) ** 2
                if best is None or d < best[0]: best = (d, i, j)
        return None if best is None else (best[1], best[2])

    def _label_at(self, p):
        sp_ = self.vb.mapViewToScene(p)
        for t_ in reversed(self.labels):
            if t_.sceneBoundingRect().adjusted(-4, -4, 4, 4).contains(sp_): return t_
        return None

    def tool_press(self, p0):
        t = self.tool
        self._drag = {"p0": p0}
        if t == T.LABEL_PEAK:
            lab = self._label_at(p0); self._drag["label"] = lab
            if lab is not None: self._drag["lab0"] = (lab.pos().x(), lab.pos().y())
        if t in (T.SHIFT, T.MULTIPLY):
            idx = self._tool_targets()
            self._drag["idx"] = idx
            self._drag["orig"] = {i: self.items[i].spec.y.copy() for i in idx}
        elif t == T.DRAW_STRIP:
            self._drag["region"] = self.add_strip(p0.x(), p0.x())
        elif t == T.DXLINE:
            self.set_dxlines(p0.x(), p0.x())
        elif t == T.BASELINE:
            self._drag["bl"] = self._bl_near(p0)
        elif t == T.ERASER:
            r = pg.LinearRegionItem([p0.x(), p0.x()], brush=pg.mkBrush(214, 39, 40, 60), movable=False)
            self.pi.addItem(r); self._drag["region"] = r

    def tool_move(self, p):
        d = self._drag
        if not d: return
        t = self.tool
        if t in (T.SHIFT, T.MULTIPLY):
            for i in d["idx"]:
                it = self.items[i]
                if t == T.SHIFT:
                    y = d["orig"][i] + (p.y() - d["p0"].y())
                else:
                    f = (p.y() / d["p0"].y()) if d["p0"].y() != 0 else 1.0
                    y = d["orig"][i] * f
                c = self.curves.get(id(it))
                if c is not None: c.setData(it.spec.x, y)
            if t == T.SHIFT:
                self.statusBar().showMessage(f"Shift ΔY = {p.y() - d['p0'].y():.4g}")
            else:
                f = (p.y() / d["p0"].y()) if d["p0"].y() != 0 else 1.0
                self.statusBar().showMessage(f"Multiply ×{f:.4g}")
        elif t == T.BASELINE and d.get("bl") is not None:
            self.bl_pts[d["bl"]] = (p.x(), p.y()); self._bl_update()
        elif t == T.LABEL_PEAK and d.get("label") is not None:
            x0, y0 = d["lab0"]; d["label"].setPos(x0 + p.x() - d["p0"].x(), y0 + p.y() - d["p0"].y())
        elif t in (T.DRAW_STRIP, T.ERASER) and "region" in d:
            d["region"].setRegion((d["p0"].x(), p.x()))
        elif t == T.DXLINE:
            self.set_dxlines(d["p0"].x(), p.x())

    def tool_release(self, p):
        d, self._drag = self._drag, None
        if not d: return
        t = self.tool
        if t == T.DXLINE:
            self.set_dxlines(d["p0"].x(), p.x()); return
        if t in (T.SHIFT, T.MULTIPLY) and d.get("idx"):
            dy = p.y() - d["p0"].y()
            f = (p.y() / d["p0"].y()) if d["p0"].y() != 0 else 1.0
            if (t == T.SHIFT and dy == 0) or (t == T.MULTIPLY and f == 1.0):
                self.redraw(); return
            self.push_undo()
            for i in d["idx"]:
                it = self.items[i]
                y = d["orig"][i] + dy if t == T.SHIFT else d["orig"][i] * f
                it.spec = it.spec.with_y(y, f"shift({dy:.6g})" if t == T.SHIFT else f"multiply({f:.6g})")
            self.refresh()
        elif t == T.ERASER and "region" in d:
            a, b = sorted((d["p0"].x(), p.x())); self.pi.removeItem(d["region"])
            if b - a > 1e-9: self.erase_spikes(a, b)
        elif t == T.DRAW_STRIP and "region" in d:
            d["region"].setRegion((d["p0"].x(), p.x()))
            a, b = d["region"].getRegion()
            if abs(b - a) < 1e-9:
                self.pi.removeItem(d["region"]); self.strips.remove(d["region"])
            else:
                lo, hi = sorted((a, b)); msgs = []
                for i in (self.selected_idx() or [k for k, it in enumerate(self.items) if it.visible])[:4]:
                    try: msgs.append(f"{self.items[i].spec.name}: {float(rp.integral(self.items[i].spec, lo, hi)):.6g}")
                    except Exception: pass
                self.statusBar().showMessage(f"區間 {lo:.1f}–{hi:.1f}  積分面積  " + "   ".join(msgs))

    def tool_click(self, p):
        t = self.tool
        if t == T.BASELINE:
            k = self._bl_near(p)
            if k is not None:
                self.bl_pts.pop(k)
            else:
                idx = self._tool_targets(); y = p.y()
                if idx:
                    sp = self.items[idx[0]].spec
                    if sp.x[0] <= p.x() <= sp.x[-1]:
                        yv = float(np.interp(p.x(), sp.x, sp.y)); py = self.vb.viewPixelSize()[1]
                        if self._op_values('baseline')[0].get('attach', True) and abs(yv - y) <= 12 * py: y = yv
                self.bl_pts.append((p.x(), y))
            self._bl_update()
        elif t == T.ERASER:
            hit = self._nearest_point(p)
            if hit is None: return
            sp = self.items[hit[0]].spec; dx = 3 * float(np.median(np.diff(sp.x)))
            self.erase_spikes(sp.x[hit[1]] - dx, sp.x[hit[1]] + dx, idx=[hit[0]])
        elif t == T.XLINE:
            self.set_xline(p.x())
        elif t == T.DXLINE:
            n = len(self.dxlines)
            if n < 2: self.set_dxline(n, p.x())                                   # 1st click = line 1, 2nd click = line 2
            else: self.set_dxline(int(np.argmin([abs(l.value() - p.x()) for l in self.dxlines])), p.x())     # then: move the nearer line
        elif t == T.XY:
            self.statusBar().showMessage(f"X = {p.x():.3f}, Y = {p.y():.6g}")
        elif t == T.CURSOR:
            hit = self._nearest_point(p)
            if hit is None: return
            i, j = hit; sp = self.items[i].spec
            self.clear_cursor()
            m = pg.ScatterPlotItem([sp.x[j]], [sp.y[j]], size=10, brush=pg.mkBrush(self.items[i].color), pen=pg.mkPen("k"))
            lab = pg.TextItem(f"{sp.name}\nX={sp.x[j]:.3f}  Y={sp.y[j]:.5g}", color="k", anchor=(0, 1.1),
                              fill=pg.mkBrush(255, 255, 220, 220), border=pg.mkPen("#999"))
            lab.setPos(sp.x[j], sp.y[j])
            self.pi.addItem(m); self.pi.addItem(lab); self.dcursor = [m, lab]
            self.statusBar().showMessage(f"{sp.name}: X={sp.x[j]:.3f}, Y={sp.y[j]:.6g}")
        elif t == T.TEXT:
            text, ok = W.QInputDialog.getText(self, "Add Text", "文字：")
            if ok and text:
                ti = pg.TextItem(text, color="k", anchor=(0, 1))
                ti.setFlag(ti.GraphicsItemFlag.ItemIsMovable, True)
                ti.setPos(p.x(), p.y()); self.pi.addItem(ti); self.annots.append(("text", ti))
        elif t == T.IMAGE:
            path, _ = W.QFileDialog.getOpenFileName(self, "Add Image", "", "圖片 (*.png *.jpg *.jpeg *.bmp *.gif)")
            if path: self.add_image(path, p)
        elif t == T.REMOVE_STRIP:
            for r in list(self.strips):
                a, b = r.getRegion()
                if min(a, b) <= p.x() <= max(a, b):
                    self.pi.removeItem(r); self.strips.remove(r)
        elif t == T.LABEL_PEAK:
            old = self._label_at(p)
            if old is not None:                       # click an existing label -> delete it
                self.pi.removeItem(old); self.labels.remove(old); return
            hit = self._nearest_point(p)
            if hit is None: return
            i, _ = hit; sp = self.items[i].spec
            (x0, x1), _ = self.pi.viewRange(); win = 0.03 * (x1 - x0)
            m = (sp.x >= p.x() - win) & (sp.x <= p.x() + win)
            if not m.any(): return
            k = np.nonzero(m)[0][int(np.argmax(sp.y[m]))]
            t_ = pg.TextItem(f"{float(sp.x[k]):.1f}", color=self.items[i].color, anchor=(0.5, 1.2))
            t_.setPos(sp.x[k], sp.y[k]); self.pi.addItem(t_); self.labels.append(t_)

    # ---------------- sessions / crash recovery ----------------
    def session_workspaces(self):
        return [{"name": st["name"], "items": self.items if i == self.ws_cur else st["items"]} for i, st in enumerate(self.ws_states)]

    def autosave(self):
        """Periodic crash-recovery snapshot (only when something changed). Never raises."""
        if not self._dirty: return False
        from ramanproc import safeio
        try:
            if not any(ws["items"] for ws in self.session_workspaces()):
                self.clear_recovery(); self._dirty = False; return False
            safeio.save_session(safeio.recovery_path(), self.session_workspaces(), self.ws_cur); self._dirty = False; self._autosave_err = None
            return True
        except Exception as ex:
            if self._autosave_err != str(ex):
                self._autosave_err = str(ex); self.statusBar().showMessage(f"自動存檔失敗：{ex}")
            return False

    def clear_recovery(self):
        from ramanproc import safeio
        try:
            os.remove(safeio.recovery_path())
        except OSError:
            pass

    def restore_session(self, workspaces, current=0):
        from ramanproc import safeio
        if not workspaces: return
        self.ws_states[self.ws_cur].update(self._ws_detach())
        self.ws_states = []
        for w_ in workspaces:
            st = self._new_ws_state(w_["name"])
            for d in w_["items"]:
                it = Item(d["spec"], d["color"]); it.visible, it.group, it.raw = d["visible"], d["group"], d["raw"]; st["items"].append(it)
            self.ws_states.append(st)
        self.ws_cur = min(max(current, 0), len(self.ws_states) - 1)
        self.wsbar.blockSignals(True)
        while self.wsbar.count(): self.wsbar.removeTab(0)
        for st in self.ws_states: self.wsbar.addTab(st["name"])
        self.wsbar.setCurrentIndex(self.ws_cur); self.wsbar.blockSignals(False)
        self._ws_apply(self.ws_states[self.ws_cur]); self.full_scale()

    def save_session_dialog(self):
        from ramanproc import safeio
        p, _ = W.QFileDialog.getSaveFileName(self, "儲存工作階段", "session.ramansession", "SpectrumPro 工作階段 (*.ramansession)")
        if p:
            try: safeio.save_session(p, self.session_workspaces(), self.ws_cur); self.statusBar().showMessage(f"已儲存工作階段：{os.path.basename(p)}")
            except Exception as ex: W.QMessageBox.warning(self, "儲存失敗", str(ex))

    def open_session_dialog(self):
        p, _ = W.QFileDialog.getOpenFileName(self, "開啟工作階段", "", "SpectrumPro 工作階段 (*.ramansession)")
        if p: self.open_session(p)

    def open_session(self, p):
        from ramanproc import safeio
        try: ws, cur = safeio.load_session(p)
        except Exception as ex:
            W.QMessageBox.warning(self, "開啟失敗", f"無法讀取工作階段：{ex}"); return False
        self.restore_session(ws, cur); self.statusBar().showMessage(f"已開啟工作階段：{os.path.basename(p)}"); return True

    # ---------------- workspaces ----------------
    @staticmethod
    def _new_ws_state(name):
        return {"name": name, "items": [], "undo": [], "redo": [], "strips": [], "annots": [], "bl_pts": [], "view": None, "sel": []}

    def _ws_detach(self):
        """Remove this workspace's overlay objects from the plot and return its state."""
        st = {"items": self.items, "undo": self.undo, "redo": self.redo, "bl_pts": self.bl_pts,
              "strips": [tuple(r.getRegion()) for r in self.strips], "sel": self.selected_idx(),
              "view": [list(r) for r in self.pi.viewRange()]}
        self.clear_strips(); self.clear_labels(); self.clear_cursor(); self.clear_xline(); self.clear_dxline()
        for k, it in self.annots: self.pi.removeItem(it)
        st["annots"] = self.annots; self.annots = []
        self.bl_pts = []; self._bl_update()
        return st

    def _ws_apply(self, st):
        self.items, self.undo, self.redo, self.bl_pts = st["items"], st["undo"], st["redo"], st["bl_pts"]
        for a, b in st["strips"]: self.add_strip(a, b)
        for k, it in st["annots"]: self.pi.addItem(it)
        self.annots = st["annots"]
        self.refresh()
        self.listw.blockSignals(True)
        for i in st["sel"]:
            if i < self.listw.count(): self.listw.item(i).setSelected(True)
        self.listw.blockSignals(False); self._selection_changed()
        self._bl_update(); self._refresh_actions()
        if st["view"]:
            (x0, x1), (y0, y1) = st["view"]; self.pi.setRange(xRange=(x0, x1), yRange=(y0, y1), padding=0)
        else:
            self.full_scale()
        self.statusBar().showMessage(f"工作區：{self.ws_states[self.ws_cur]['name']}")

    def _ws_name(self):
        n = 1
        names = {s["name"] for s in self.ws_states}
        while f"工作區 {n}" in names: n += 1
        return f"工作區 {n}"

    def add_workspace(self, name=None, specs=None):
        """Create an empty workspace (or one pre-filled with copies of `specs`) and switch to it."""
        st = self._new_ws_state(name or self._ws_name())
        for sp, col in (specs or []): st["items"].append(Item(sp, col))
        self.ws_states[self.ws_cur].update(self._ws_detach())
        self.ws_states.append(st); self.ws_cur = len(self.ws_states) - 1
        self.wsbar.blockSignals(True); self.wsbar.addTab(st["name"]); self.wsbar.setCurrentIndex(self.ws_cur); self.wsbar.blockSignals(False)
        self._ws_apply(st)

    def switch_workspace(self, i):
        if i < 0 or i == self.ws_cur or i >= len(self.ws_states): return
        self.ws_states[self.ws_cur].update(self._ws_detach())
        self.ws_cur = i; self._ws_apply(self.ws_states[i])

    def close_workspace(self, i, confirm=True):
        if len(self.ws_states) <= 1:
            self.statusBar().showMessage("至少要保留一個工作區"); return
        st = self.ws_states[i]
        has_data = bool(self.items) if i == self.ws_cur else bool(st["items"])
        if confirm and has_data and W.QMessageBox.question(
                self, "關閉工作區", f"關閉「{st['name']}」？其中的光譜與復原記錄會被丟棄。") != W.QMessageBox.Yes:
            return
        if i == self.ws_cur:
            self._ws_detach()
            del self.ws_states[i]
            self.ws_cur = max(0, i - 1)
            self.wsbar.blockSignals(True); self.wsbar.removeTab(i); self.wsbar.setCurrentIndex(self.ws_cur); self.wsbar.blockSignals(False)
            self._ws_apply(self.ws_states[self.ws_cur])
        else:
            del self.ws_states[i]
            if i < self.ws_cur: self.ws_cur -= 1
            self.wsbar.blockSignals(True); self.wsbar.removeTab(i); self.wsbar.setCurrentIndex(self.ws_cur); self.wsbar.blockSignals(False)

    def rename_workspace(self, i):
        if i < 0: return
        name, ok = W.QInputDialog.getText(self, "工作區名稱", "新名稱：", text=self.ws_states[i]["name"])
        if ok and name.strip():
            self.ws_states[i]["name"] = name.strip(); self.wsbar.setTabText(i, name.strip())

    def _fill_send_menu(self):
        m = self.send_menu; m.clear()
        for i, st in enumerate(self.ws_states):
            if i != self.ws_cur:
                m.addAction(f"→ {st['name']}").triggered.connect(lambda _=False, k=i: self.send_selected_to(k))
        m.addAction("→ 新工作區").triggered.connect(lambda: self.send_selected_to(-1))

    def send_selected_to(self, k):
        """Copy the selected spectra to workspace k (or a new one when k == -1)."""
        idx = self.targets()
        if not idx: return
        pairs = [(copy.deepcopy(self.items[i].spec), self.items[i].color) for i in idx]
        if k == -1:
            self.add_workspace(specs=pairs); return
        for sp, col in pairs: self.ws_states[k]["items"].append(Item(sp, col))
        self.statusBar().showMessage(f"已複製 {len(pairs)} 條光譜到「{self.ws_states[k]['name']}」")

    # ---- manual baseline ----
    def _bl_near(self, p):
        px, py = self.vb.viewPixelSize()
        for k, (x, y) in enumerate(self.bl_pts):
            if abs(x - p.x()) <= 9 * px and abs(y - p.y()) <= 9 * py: return k
        return None

    def _bl_update(self):
        if getattr(self, "bl_scatter", None) is None:
            self.bl_scatter = pg.ScatterPlotItem(size=11, brush=pg.mkBrush("#d62728"), pen=pg.mkPen("#0b2540", width=1.5))
            self.bl_curve = pg.PlotDataItem(pen=pg.mkPen("#d62728", width=2, style=C.Qt.DashLine))
            self.bl_scatter.setZValue(20); self.bl_curve.setZValue(19)
            self.pi.addItem(self.bl_curve); self.pi.addItem(self.bl_scatter)
        pts = self.bl_pts
        self.bl_scatter.setData([q[0] for q in pts], [q[1] for q in pts])
        idx = self._tool_targets()
        if len(pts) >= 2 and idx:
            sp = self.items[idx[0]].spec
            self.bl_curve.setData(sp.x, rp.baseline_from_points(sp, pts))
        else:
            self.bl_curve.setData([], [])
        self.statusBar().showMessage(f"手動基線：{len(pts)} 個錨點" + ("" if len(pts) >= 2 else "（至少 2 點才會顯示基線）"))

    def clear_bl_points(self):
        self.bl_pts = []; self._bl_update()

    def _bl_show(self, x, y, anchors=None):
        """Draw the fitted / pasted baseline (and auto anchors) in the chosen colour."""
        self._bl_update()
        col = self.BL_COLORS.get(self._op_values("baseline")[0].get("color", "Red"), "#d62728")
        self.bl_curve.setPen(pg.mkPen(col, width=2.2)); self.bl_curve.setData(self._xmap(np.asarray(x)), np.asarray(y))
        if getattr(self, "bl_anchor", None) is None:
            self.bl_anchor = pg.ScatterPlotItem(size=7, brush=pg.mkBrush("#ffffff"), pen=pg.mkPen("#222222", width=1.2))
            self.bl_anchor.setZValue(21); self.pi.addItem(self.bl_anchor)
        if anchors is not None: self.bl_anchor.setData(self._xmap(np.asarray(anchors[0])), np.asarray(anchors[1]))
        else: self.bl_anchor.setData([], [])

    def baseline_fit(self):
        idx = self._tool_targets()
        if not idx:
            W.QMessageBox.information(self, "Fit", "請先選取一條光譜。"); return None
        sp = self.items[idx[0]].spec; v = self._op_values("baseline")[0]; m = v["method"]
        if m in BL.LEGACY:
            res, base = rp.remove_baseline(sp, "iterative_clipping" if m == "IterativeClipping" else "polynomial",
                                           **({"peak_width": v["width"]} if m == "IterativeClipping" else {"order": v["order"]}), return_baseline=True)
            x, y, info = res.x, base, {"anchors": None, "notes": []}
        else:
            try: y, info = BL.fit_baseline(sp, m, **self._baseline_kwargs(v))
            except Exception as ex:
                W.QMessageBox.warning(self, "Fit", str(ex)); return None
            x = sp.x
        self.bl_fit = (np.asarray(x, float).copy(), np.asarray(y, float).copy(), m)
        self._bl_show(x, y, info.get("anchors"))
        self.statusBar().showMessage(f"Fit：{m}" + ("；" + "；".join(info["notes"]) if info.get("notes") else "") + "（按 Sub 扣除）")
        return self.bl_fit

    def baseline_sub(self):
        idx = self.targets()
        if not idx: return
        fit = getattr(self, "bl_fit", None)
        if fit is None:
            self.run_op("baseline", quick=True)
        else:
            fx, fy, label = fit
            self._apply(idx, lambda s: BL.subtract(s, np.interp(s.x, fx, fy), label), "去背景", False, key="baseline")
        self.bl_fit = None; self.bl_pts = []; self._bl_update()
        if getattr(self, "bl_anchor", None) is not None: self.bl_anchor.setData([], [])

    def baseline_copy(self):
        fit = getattr(self, "bl_fit", None) or self.baseline_fit()
        if fit is None: return
        self.bl_clip = tuple(fit)
        self.statusBar().showMessage(f"已複製基線（{fit[2]}，{len(fit[0])} 點）")

    def baseline_paste(self):
        clip = getattr(self, "bl_clip", None)
        if clip is None:
            self.statusBar().showMessage("尚未複製基線"); return
        idx = self._tool_targets()
        if not idx: return
        sp = self.items[idx[0]].spec; fx, fy, label = clip
        self.bl_fit = (sp.x.copy(), np.interp(sp.x, fx, fy), label)
        self._bl_show(sp.x, self.bl_fit[1])
        self.statusBar().showMessage(f"已貼上基線（{label}）；按 Sub 扣除")

    def baseline_delete(self):
        self.bl_fit = None; self.bl_pts = []; self._bl_update()
        if getattr(self, "bl_anchor", None) is not None: self.bl_anchor.setData([], [])
        self.bl_curve.setData([], [])

    def bl_auto_points(self, n=None):
        """Seed the manual anchors from an automatic fit (kept for the manual tool / tests)."""
        n = n or 10
        idx = self._tool_targets()
        if not idx: return
        sp = self.items[idx[0]].spec
        base, _ = BL.fit_baseline(sp, "Polynom(Auto)", order=3)
        ks = np.linspace(0, len(sp.x) - 1, n).astype(int)
        self.bl_pts = [(float(sp.x[k]), float(base[k])) for k in ks]
        self._bl_update()

    def apply_manual_baseline(self):
        if len(self.bl_pts) < 2:
            W.QMessageBox.warning(self, "手動基線", "請先用左側「手動基線」工具在圖上加入至少 2 個錨點。"); return
        idx = self.targets()
        if not idx: return
        pts = list(self.bl_pts)
        self._apply(idx, lambda s: rp.remove_baseline_points(s, pts), "手動基線", False, key="baseline")
        self.clear_bl_points()

    def erase_spikes(self, lo, hi, idx=None):
        """Eraser: apply the running-median spike filter only inside [lo, hi]."""
        idx = idx if idx is not None else self._tool_targets()
        if not idx: return
        w = int(self._op_values("cosmic")[0]["w"]); w = w if w % 2 else w + 1
        self.push_undo(); n = 0
        for i in idx:
            it = self.items[i]; m = (it.spec.x >= lo) & (it.spec.x <= hi)
            if not m.any(): continue
            y = np.where(m, rp.remove_cosmic_ray(it.spec, w).y, it.spec.y)
            if not np.array_equal(y, it.spec.y):
                it.spec = it.spec.with_y(y, f"eraser({lo:.1f}-{hi:.1f},w={w})"); n += 1
        if not n: self.undo.pop(); self._refresh_actions()
        self.refresh(); self.statusBar().showMessage(f"橡皮擦：{lo:.1f}–{hi:.1f} cm⁻¹，已處理 {n} 條")

    def set_xline(self, x):
        """Place / move the vertical marker line and show its X (and each visible spectrum's Y)."""
        if getattr(self, "xline", None) is None:
            self.xline = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen("#d62728", width=1.5),
                                         label="{value:.2f}", labelOpts={"position": 0.95, "color": "#d62728", "fill": (255, 255, 255, 200)})
            self.pi.addItem(self.xline, ignoreBounds=True)
            self.xline.sigPositionChanged.connect(lambda l: self._xline_msg(l.value()))
        self.xline.setValue(x); self._xline_msg(x)

    def _xline_msg(self, x):
        ys = []
        for it in self.items:
            if it.visible and it.spec.x[0] <= x <= it.spec.x[-1]:
                ys.append(f"{it.spec.name}: {float(np.interp(x, it.spec.x, it.spec.y)):.5g}")
        self.statusBar().showMessage(f"X = {x:.3f}   " + "   ".join(ys))

    # ---- double X line (two markers at once) ----
    DX_COLORS = ("#d62728", "#1d7cd4")

    def _dx_new_line(self, x, k):
        c = self.DX_COLORS[k]
        ln = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen(c, width=1.5), hoverPen=pg.mkPen(c, width=3),
                             label="{value:.2f}", labelOpts={"position": 0.95 - 0.08 * k, "color": c, "fill": (255, 255, 255, 200)})
        ln.setZValue(30); ln.sigPositionChanged.connect(lambda *_: self._dx_update()); self.pi.addItem(ln, ignoreBounds=True)
        return ln

    def set_dxline(self, k, x):
        """Place / move marker k (0 or 1)."""
        if not hasattr(self, "dxlines"): self.dxlines = []
        while len(self.dxlines) <= k: self.dxlines.append(self._dx_new_line(x, len(self.dxlines)))
        self.dxlines[k].setValue(x); self._dx_update()

    def set_dxlines(self, x1, x2):
        """Place both markers at once (drag)."""
        self.set_dxline(0, x1); self.set_dxline(1, x2)

    def dx_values(self):
        """(x_low, x_high) in data (Raman shift) coordinates, or None unless both markers exist."""
        if len(getattr(self, "dxlines", [])) < 2: return None
        a, b = sorted(float(self._xunmap(l.value())) for l in self.dxlines)
        return a, b

    def _dx_update(self):
        if len(getattr(self, "dxlines", [])) < 2:
            if self.dxlines: self.statusBar().showMessage(f"X₁ = {self.dxlines[0].value():.3f}　（再點一下放第 2 條線，或直接拖曳拉出兩條）")
            return
        lo_v, hi_v = sorted(l.value() for l in self.dxlines)
        if getattr(self, "dx_region", None) is None:
            r = pg.LinearRegionItem([lo_v, hi_v], brush=pg.mkBrush(29, 124, 212, 35), movable=False)
            for ln in r.lines: ln.setPen(pg.mkPen(None)); ln.setHoverPen(pg.mkPen(None)); ln.setMovable(False)
            r.setZValue(-5); self.pi.addItem(r, ignoreBounds=True); self.dx_region = r
        else:
            self.dx_region.setRegion((lo_v, hi_v))
        a, b = self.dx_values(); x1, x2 = self.dxlines[0].value(), self.dxlines[1].value()
        parts = []
        for it in self.items:
            if not it.visible: continue
            sp = it.spec
            if sp.x[0] <= a and b <= sp.x[-1]:
                y1, y2 = float(np.interp(float(self._xunmap(x1)), sp.x, sp.y)), float(np.interp(float(self._xunmap(x2)), sp.x, sp.y))
                parts.append(f"{sp.name}: Y₁={y1:.5g} Y₂={y2:.5g} ΔY={y2 - y1:.5g} 面積={float(rp.integral(sp, a, b)):.6g}")
        self.statusBar().showMessage(f"X₁ = {x1:.3f}　X₂ = {x2:.3f}　ΔX = {abs(x2 - x1):.3f}" + ("　|　" + "　".join(parts[:4]) + (" …" if len(parts) > 4 else "") if parts else ""))

    def clear_dxline(self):
        for l in getattr(self, "dxlines", []): self.pi.removeItem(l)
        self.dxlines = []
        if getattr(self, "dx_region", None) is not None: self.pi.removeItem(self.dx_region); self.dx_region = None

    def clear_xline(self):
        if getattr(self, "xline", None) is not None:
            self.pi.removeItem(self.xline); self.xline = None

    def add_image(self, path, p):
        import numpy as np
        from PySide6 import QtGui as G2
        img = G2.QImage(path)
        if img.isNull():
            W.QMessageBox.warning(self, "Add Image", "無法讀取圖片。"); return
        img = img.convertToFormat(G2.QImage.Format_RGBA8888)
        w_, h_ = img.width(), img.height()
        ptr = img.constBits()
        arr = np.frombuffer(ptr, dtype=np.uint8, count=w_ * h_ * 4).reshape(h_, w_, 4).copy()
        arr = arr.transpose(1, 0, 2)[:, ::-1]          # pyqtgraph: (x, y) with y up
        (x0, x1), (y0, y1) = self.pi.viewRange()
        vw, vh = max(self.vb.width(), 1), max(self.vb.height(), 1)
        w_view = 0.2 * (x1 - x0)
        h_view = w_view * (h_ * 1.0 / w_) * ((y1 - y0) / vh) / ((x1 - x0) / vw)
        item = pg.ImageItem(arr)
        item.setRect(C.QRectF(p.x(), p.y() - h_view, w_view, h_view))
        item.setZValue(-5)
        self.pi.addItem(item); self.annots.append(("image", item))

    def remove_annots(self, kind):
        keep = []
        for k, it in self.annots:
            if k == kind: self.pi.removeItem(it)
            else: keep.append((k, it))
        self.annots = keep

    def clear_cursor(self):
        for it in self.dcursor: self.pi.removeItem(it)
        self.dcursor = []


def install_excepthook(win):
    """Log uncaught exceptions to a file and tell the user, instead of the program silently dying / printing to a hidden console."""
    import traceback, tempfile, faulthandler
    log = os.path.join(os.environ.get("TEMP") or tempfile.gettempdir(), "SpectrumPro_error.log")
    try: faulthandler.enable(open(log + ".fault", "w"))
    except Exception: pass
    state = {"shown": 0}

    def hook(et, ev, tb):
        text = "".join(traceback.format_exception(et, ev, tb))
        try:
            with open(log, "a", encoding="utf-8") as f: f.write(text + "\n")
        except Exception: pass
        if getattr(win, "_closing", False): return           # never block shutdown with a dialog
        win._dirty = True
        try: win.autosave()                    # keep the user's work before anything else can go wrong
        except Exception: pass
        if state["shown"] < 3:
            state["shown"] += 1
            try: W.QMessageBox.critical(win, APP_NAME, f"發生未預期的錯誤（已自動保存目前工作）：\n{ev}\n\n詳細記錄：{log}")
            except Exception: pass
    sys.excepthook = hook
    return hook


def main():
    from ramanproc import safeio
    app = W.QApplication(sys.argv)
    app.setStyle("Fusion"); TH.load_font(app)
    app.setApplicationName(APP_NAME); app.setApplicationDisplayName(APP_NAME)
    app.setWindowIcon(G.QIcon(icon_path()))
    if sys.platform == "win32":          # own taskbar identity + icon (instead of the generic Python one)
        try:
            import ctypes; ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("KuanSyunWang.SpectrumPro")
        except Exception:
            pass
    w = MainWindow(); w._hard_exit = True; install_excepthook(w)
    rec = safeio.recovery_path()
    if os.path.isfile(rec):
        try:
            ws, cur = safeio.load_session(rec); n = sum(len(x["items"]) for x in ws)
            if n and W.QMessageBox.question(w, "還原上次的工作", f"偵測到上次未正常關閉的工作（{n} 條光譜）。要還原嗎？") == W.QMessageBox.Yes:
                w.restore_session(ws, cur)
            else:
                w.clear_recovery()
        except Exception:
            w.clear_recovery()
    paths = [p for p in sys.argv[1:] if os.path.isfile(p)]
    if paths: w.load_paths(paths)
    w.refresh(); w.show()
    app.setQuitOnLastWindowClosed(True)
    code = app.exec()
    try:
        sys.stdout.flush(); sys.stderr.flush()
    except Exception:
        pass
    os._exit(code)        # make sure no thread / timer keeps the process alive


if __name__ == "__main__":
    main()
