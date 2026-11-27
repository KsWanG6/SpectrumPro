"""GENESYS 30 (UV-Vis) CSV export: metadata lines + 'wavelength(nm) , ABS , %T' header + 3 columns."""
import os, numpy as np
from ramanproc import safeio

HERE = os.path.dirname(__file__)
F = os.path.join(HERE, "data", "genesys30_scan.csv")


def test_genesys_split_into_abs_and_percent_T():
    out = safeio.load_spectra(F)
    assert [s.name.split("_", 3)[-1] for s, _ in out] == ["ABS", "%T"]
    a, t = out[0][0], out[1][0]
    assert len(a.x) == 301 and a.x[0] == 400 and a.x[-1] == 700                # not sorted / merged / shortened
    assert a.y[0] == 0.549 and a.y[-1] == 0.155 and t.y[0] == 28.25 and t.y[-1] == 69.98
    assert np.allclose(a.y, -np.log10(t.y / 100), atol=6e-3)                    # ABS = -log10(T): proves columns are not mixed up
    assert a.meta["xunit"] == "nm" and a.meta["ylabel"] == "Absorbance" and not a.meta["hidden"] and t.meta["hidden"]
    assert "xunit=nm" in a.history


def test_three_columns_without_header_are_x_y1_y2(tmp_path):
    p = tmp_path / "xyy.txt"; x = np.arange(100., 110); np.savetxt(p, np.column_stack([x, 2 * x, 3 * x]))
    out = safeio.load_spectra(str(p))
    assert len(out) == 2 and np.allclose(out[0][0].x, x) and np.allclose(out[1][0].y, 3 * x)


def test_two_column_with_header_unchanged(tmp_path):
    p = tmp_path / "a.csv"; p.write_text("Raman shift,Intensity\n100,1\n101,2\n102,3\n103,4\n")
    out = safeio.load_spectra(str(p)); assert len(out) == 1 and list(out[0][0].y) == [1, 2, 3, 4]


def test_tab_utf16_titles_blank_column_and_mixed_axes(tmp_path):
    rows = ["Wavelength(nm)\tA(Abs)\tB(Abs)\t\tC(%T)"] + [f"{w}\t{w/1000}\t{w/500}\t\t{100-w/10}" for w in (300, 302, 304, 306, 308)]
    p = tmp_path / "u.csv"; p.write_bytes("\r\n".join(rows).encode("utf-16"))
    out = safeio.load_spectra(str(p))
    assert [s.name for s, _ in out] == ["u_A(Abs)", "u_B(Abs)", "u_C(%T)"]
    assert [s.meta["hidden"] for s, _ in out] == [False, False, True]        # same quantity visible, different Y quantity kept but hidden
    assert out[0][0].meta["xunit"] == "nm" and len(out[0][0].x) == 5


def test_edinburgh_pl_header_is_nm(tmp_path):
    p = tmp_path / "pl.csv"
    p.write_text("Labels,S\nType,Emission Scan\nStart,440\nStop,700\nXaxis,Wavelength\nYaxis,Counts\n,\n440,1.0E+03\n441,2.0E+03\n442,3.0E+03\n", encoding="utf-8")
    s = safeio.load_spectra(str(p))[0][0]
    assert s.meta["xunit"] == "nm" and len(s.x) == 3


# ------------------------------------------------------------------ IR
JASCO = ("TITLE\t\nDATA TYPE\tINFRARED SPECTRUM\nORIGIN\tJASCO\nDATE\t19/09/12\nTIME\t14:34:52\nXUNITS\t1/CM\nYUNITS\tTRANSMITTANCE\n"
         "FIRSTX\t  400.0\nLASTX\t 4000.0\nNPOINTS\t    ?\nXYDATA\n")


def _ir_file(tmp_path, ytxt=None):
    import numpy as np
    x = np.arange(400.0, 4001.0, 2.0)
    t = 96 - 20 * np.exp(-0.5 * ((x - 1700) / 12) ** 2) - 12 * np.exp(-0.5 * ((x - 2920) / 20) ** 2) - 6 * np.exp(-0.5 * ((x - 3340) / 90) ** 2)
    t = t - 4 * np.exp(-0.5 * ((x - 2349) / 10) ** 2)                   # fake CO2 dip
    p = tmp_path / "ir.txt"; p.write_text(JASCO + "\n".join(f"{a:.4f}\t{b:.4f}" for a, b in zip(x, t)) + "\n##END=\n", encoding="cp950")
    return p


def test_jasco_import_is_ir_transmittance(tmp_path):
    s = safeio.load_spectra(str(_ir_file(tmp_path)))[0][0]
    from ramanproc import ir
    assert ir.ir_mode(s) == "T" and s.meta["ylabel"] == "Transmittance (%)" and s.meta["xunit"] == "cm-1" and len(s.x) == 1801


def test_ir_roundtrip_co2_baseline_and_peaks(tmp_path):
    import numpy as np
    from ramanproc import ir
    s = safeio.load_spectra(str(_ir_file(tmp_path)))[0][0]
    a = ir.to_absorbance(s); assert ir.ir_mode(a) == "A" and np.allclose(ir.to_transmittance(a).y, s.y, atol=1e-6)
    assert ir.co2_band_height(s) > 0.01
    c = ir.co2_eliminate(s); assert ir.co2_band_height(c) < 0.001 and ir.ir_mode(c) == "T" and np.allclose(c.y[c.x < 2200], s.y[s.x < 2200])
    b = ir.base_correct(s, "rubberband"); assert ir.ir_mode(b) == "T" and b.y.max() <= 100.0 + 1e-6 and b.y.min() > 0
    for m, kw in (("poly", {}), ("anchors", {"anchors": [4000, 2000, 1000, 450]}), ("ends", {})): assert len(ir.base_correct(s, m, **kw).y) == len(s.y)
    pk = ir.predict_peaks(ir.co2_eliminate(s))
    xs = [round(p["x"]) for p in pk]
    assert any(abs(x - 1700) < 4 for x in xs) and any(abs(x - 2920) < 4 for x in xs)
    p1700 = [p for p in pk if abs(p["x"] - 1700) < 4][0]; assert p1700["cls"] == "s" and any("C=O" in g for g in p1700["guess"]) and p1700["t"] < 80
    assert any("C–H" in g for g in [p for p in pk if abs(p["x"] - 2920) < 4][0]["guess"])


# ------------------------------------------------------------------ figure: copy + axis dialog + Arial
def test_copy_figure_axis_dialog_and_font(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("RAMANPROC_HOME", str(tmp_path))
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QGuiApplication
    from ramanproc import Spectrum
    from ramanproc.gui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1300, 800); w.show()
    w.add_spectrum(Spectrum(np.linspace(1, 40, 40), np.linspace(0, 1, 40), "t")); w.refresh()
    w.copy_figure(); assert not QGuiApplication.clipboard().image().isNull()
    assert any("複製圖片" in a.text() for a in w.vb.menu.actions()) and any("座標軸設定" in a.text() for a in w.vb.menu.actions())
    w.open_axis_dialog(); d = w.axis_dialog
    d.type.setCurrentIndex(1); d.apply("Scale"); assert w.pi.ctrl.logXCheck.isChecked()
    d.type.setCurrentIndex(0); d.mj_type.setCurrentIndex(1); d.mj_val.setText("5"); d.apply("Scale"); d.tl_suf.setText(" nm"); d.apply("Tick Labels")
    d.ti_text.setText("Wavelength (nm)"); d.ti_font.setCurrentText("Arial"); d.apply("Title")
    assert w.pi.getAxis("bottom").labelText == "Wavelength (nm)" and w.pi.getAxis("bottom").labelStyle.get("font-family") == "Arial"
    assert w.pi.getAxis("bottom").tickStrings([5.0, 10.0], 1, 5) == ["5 nm", "10 nm"]
    d.reject(); assert not w.pi.ctrl.logXCheck.isChecked() and w.pi.getAxis("bottom").labelText != "Wavelength (nm)"
    w.figstyle.font_cb.setCurrentText("Arial"); assert w.figstyle.st["font"] == "Arial"


def test_axis_dialog_sides_and_default_ratio(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("RAMANPROC_HOME", str(tmp_path))
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QGuiApplication
    from ramanproc import Spectrum
    from ramanproc.gui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1300, 800); w.show()
    w.add_spectrum(Spectrum(np.linspace(1, 40, 40), np.linspace(0, 1, 40), "t")); w.refresh()
    assert abs(w.figstyle.aspect.currentData() - 1.25) < 1e-9                        # export / copy ratio = 5:4 like the reference figure
    w.copy_figure(); im = QGuiApplication.clipboard().image(); assert abs(im.width() / im.height() - 1.25) < 0.01
    w.open_axis_dialog(); d = w.axis_dialog
    d.tabs.setCurrentIndex(1); d.tl_side.setCurrentIndex(1); assert d._tl_cur == "top"           # Tick Labels: Top
    d.tl_show.setChecked(True); d.tl_suf.setText(" s"); d.apply()
    assert w.figstyle.st["box"] and w.pi.getAxis("top").isVisible() and w.pi.getAxis("top").style["showValues"]
    d.tabs.setCurrentIndex(4); d.lt_side.setCurrentIndex(3); assert d._lt_cur == "right"          # Line and Ticks: Right
    d.lt_line.setChecked(False); d.tk["major"]["style"].setCurrentText("In"); d.tk["major"]["length"].setCurrentText("12"); d.apply()
    ax = w.pi.getAxis("right"); assert ax.pen().color().alpha() == 0 and ax.cfg["major"]["style"] == "In" and ax.cfg["major"]["length"] == "12"
    assert w.pi.getAxis("left").pen().color().alpha() > 0                                          # other sides untouched
    d.lt_side.setCurrentIndex(0); d.lt_same.setChecked(True); d.ln_w.setCurrentText("4"); d.apply()
    assert w.figstyle.st["sides"]["top"]["line_width"] == "4"                                    # "same for Bottom and Top"
    assert w.figstyle.sec_text.head.isHidden() and w.figstyle.sec_frame.head.isHidden()           # fixed, not collapsible


def test_defaults_and_no_stale_overwrite(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("RAMANPROC_HOME", str(tmp_path))
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from ramanproc import Spectrum
    from ramanproc.gui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1300, 800); w.show(); fs = w.figstyle
    w.add_spectrum(Spectrum(np.linspace(1, 40, 40), np.linspace(0, 1, 40), "t")); w.refresh()
    st = fs.st
    assert (st["x_tick_size"], st["y_tick_size"], st["label_size"], st["axis_width"], st["frame_width"], st["frame_ticks"]) == (18, 18, 24, "3", "3", False)
    assert (fs.x_size.value(), fs.y_size.value(), fs.label_size.value(), fs.axis_w.currentText(), fs.frame_w.currentText(), fs.frame_ticks.isChecked()) == (18, 18, 24, "3", "3", False)
    assert w.pi.getAxis("bottom").pen().widthF() == 3.0
    w.open_axis_dialog(); d = w.axis_dialog
    fs.x_size.setValue(30); fs.label_bold.setChecked(True); fs.axis_w.setCurrentText("4")           # edited on the Figure tab...
    d.tabs.setCurrentIndex(1); d.apply()                                                           # ...then Apply on Tick Labels: must not revert
    assert fs.st["x_tick_size"] == 30 and fs.st["label_bold"] and w.pi.getAxis("bottom").pen().widthF() == 4.0
    assert "bold" in w.pi.getAxis("bottom").labelStyle["font-weight"]
    w.pi.getAxis("bottom").tick_col  # drawn from the side colour


def test_figure_defaults_match_reference_and_legend_size(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("RAMANPROC_HOME", str(tmp_path))
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from ramanproc import Spectrum
    from ramanproc.gui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1300, 800); w.show(); fs = w.figstyle
    w.add_spectrum(Spectrum(np.linspace(1, 40, 40), np.linspace(0, 1, 40), "sample A")); w.refresh()
    st = fs.st
    assert st["font"] == "Arial" and st["title_size"] == 14 and st["label_size"] == 24 and (st["x_tick_size"], st["y_tick_size"]) == (18, 18)
    assert st["label_bold"] and st["tick_bold"] and st["axis_width"] == "3" and st["box"] and st["frame_top"] and st["frame_right"] and st["frame_width"] == "3" and not st["frame_ticks"]
    assert fs.font_cb.currentText() == "Arial" and fs.label_bold.isChecked() and fs.box.isChecked() and not fs.frame_ticks.isChecked()
    assert st["legend_size"] == 20 and w.legend.items[0][1].opts["size"] == "20pt"
    fs.legend_size.setValue(28); assert w.legend.items[0][1].opts["size"] == "28pt"
    assert w.pi.getAxis("top").isVisible() and w.pi.getAxis("right").isVisible()


def test_legend_sample_length_width_link_and_drag(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("RAMANPROC_HOME", str(tmp_path))
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt, QPoint
    from ramanproc import Spectrum
    from ramanproc.gui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1300, 800); w.show()
    w.add_spectrum(Spectrum(np.linspace(1, 40, 40), np.linspace(0, 1, 40), "4-MBA_powder")); w.refresh()
    smp = w.legend.items[0][0]; assert smp.width() == 40.0                                  # twice the default 20 px
    w.sp_width.setValue(4); assert w.legend.items[0][0].item.opts["pen"].width() == 4        # sample pen = spectrum pen (follows line width)
    lg = w.legend; p0 = lg.pos(); vp = w.plot.viewport(); c = w.plot.mapFromScene(lg.mapToScene(lg.boundingRect().center()))
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, c)
    for k in range(1, 8): QTest.mouseMove(vp, QPoint(c.x() - 20 * k, c.y() + 20 * k)); app.processEvents()
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(c.x() - 140, c.y() + 140)); app.processEvents()
    p1 = lg.pos(); assert (p1.x(), p1.y()) != (p0.x(), p0.y())                              # dragged
    w.refresh(); assert (lg.pos().x(), lg.pos().y()) == (p1.x(), p1.y())                      # stays after a redraw
    w.reset_legend(); app.processEvents(); assert lg.pos().y() < p1.y()


def test_legend_font_controls_live_in_display_tab(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("RAMANPROC_HOME", str(tmp_path))
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from ramanproc import Spectrum
    from ramanproc.gui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1300, 900); w.show(); fs = w.figstyle
    w.add_spectrum(Spectrum(np.linspace(1, 40, 40), np.linspace(0, 1, 40), "sample A")); w.refresh()
    assert w.display_tab.isAncestorOf(fs.legend_font) and w.display_tab.isAncestorOf(fs.legend_size) and w.display_tab.isAncestorOf(fs.legend_bold)
    d = w.axis_dialog if getattr(w, "axis_dialog", None) else (w.open_axis_dialog() or w.axis_dialog)
    assert not d.isAncestorOf(fs.legend_size)                                  # no longer in the Axis dialog
    fs.legend_font.setCurrentText("Times New Roman"); fs.legend_size.setValue(30); fs.legend_bold.setChecked(True)
    lab = w.legend.items[0][1]
    assert fs.st["legend_font"] == "Times New Roman" and lab.opts["size"] == "30pt" and lab.opts.get("bold") is True and lab.item.font().family() == "Times New Roman" and lab.item.font().bold()
    fs.legend_font.setCurrentIndex(0); assert fs.st["legend_font"] == "" and w.legend.items[0][1].item.font().family() == "Arial"   # follows the figure font


def test_export_legend_scales_and_keeps_relative_position(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("RAMANPROC_HOME", str(tmp_path))
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QPointF
    from PySide6 import QtGui as G
    from ramanproc import Spectrum
    from ramanproc.gui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1400, 900); w.show()
    w.add_spectrum(Spectrum(np.linspace(400, 2000, 50), np.zeros(50), "4-MBA-powder")); w.refresh(); app.processEvents()
    lg = w.legend; lg.autoAnchor(QPointF(180, 120)); app.processEvents(); p0 = lg.pos()

    def legend_box(path):                                  # bounding box of the (black) legend text, top-middle part of the picture
        im = G.QImage(path); W_, H = im.width(), im.height(); xs, ys = [], []
        for y in range(int(H * 0.05), int(H * 0.45)):
            for x in range(int(W_ * 0.2), int(W_ * 0.95)):
                if im.pixelColor(x, y).red() < 40 and im.pixelColor(x, y).blue() < 40: xs.append(x); ys.append(y)
        return min(xs) / W_, min(ys) / H, (max(xs) - min(xs)) / W_

    a_, b_ = str(tmp_path / "a.png"), str(tmp_path / "b.png")
    w.export_figure(a_, width=1200); w.export_figure(b_, width=2400)
    la, lb = legend_box(a_), legend_box(b_)
    assert abs(la[2] - lb[2]) < 0.02 and abs(la[0] - lb[0]) < 0.02 and abs(la[1] - lb[1]) < 0.02      # same relative size and place at both resolutions
    assert (lg.pos().x(), lg.pos().y()) == (p0.x(), p0.y()) and w.legend.items[0][0].width() == 40     # on-screen legend untouched


def test_export_and_copy_have_transparent_background(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("RAMANPROC_HOME", str(tmp_path))
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QGuiApplication, QImage
    from ramanproc import Spectrum
    from ramanproc.gui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1300, 800); w.show(); fs = w.figstyle
    w.add_spectrum(Spectrum(np.linspace(1, 40, 40), np.linspace(0, 1, 40), "sample A")); w.refresh()
    assert fs.transparent.isChecked()
    a = str(tmp_path / "t.png"); w.export_figure(a, width=1200); im = QImage(a)
    px = [im.pixelColor(x, y).alpha() for x in range(0, im.width(), 5) for y in range(0, im.height(), 5)]
    assert im.hasAlphaChannel() and im.pixelColor(im.width() // 2, 4).alpha() == 0 and sum(a_ == 0 for a_ in px) > 0.5 * len(px)                        # background clear
    assert any(im.pixelColor(x, y).alpha() > 200 for x in range(0, im.width(), 7) for y in range(0, im.height(), 7))                                    # but the drawing is there
    w.copy_figure(); assert QGuiApplication.clipboard().image().pixelColor(5, 5).alpha() == 0
    fs.transparent.setChecked(False); b = str(tmp_path / "o.png"); w.export_figure(b, width=1200); im2 = QImage(b)
    assert im2.pixelColor(im2.width() // 2, 4).alpha() == 255                                                                                           # opt-out: white page again
    fs.transparent.setChecked(True)
    for ext in ("svg", "pdf"): w.export_figure(str(tmp_path / ("v." + ext))); assert os.path.getsize(tmp_path / ("v." + ext)) > 500
    assert w.plot.backgroundBrush().color().name() == "#ffffff"                                                                                         # screen background restored


def test_default_line_and_ticks_for_bottom_and_left(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("RAMANPROC_HOME", str(tmp_path))
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from ramanproc import Spectrum
    from ramanproc.gui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1300, 800); w.show(); fs = w.figstyle
    w.add_spectrum(Spectrum(np.linspace(1, 40, 40), np.linspace(0, 1, 40), "t")); w.refresh()
    for side in ("bottom", "left"):
        c = fs.eff_cfg(side, honor_show=False)
        assert c["major"] == {"style": "Out", "length": "8", "color": None, "width": "Auto"} and c["minor"] == {"style": "Out", "length": "5", "color": None, "width": "Auto"}
        sd = fs.st["sides"][side]; assert sd["lt_show"] and sd["line_show"] and sd["line_color"] is None and sd["line_width"] is None
        assert w.pi.getAxis(side).cfg["major"]["length"] == "8" and w.pi.getAxis(side).cfg["minor"]["style"] == "Out"
    for side in ("top", "right"):                                                      # frame sides: still no ticks
        assert fs.eff_cfg(side)["major"]["style"] == "None" and fs.eff_cfg(side)["minor"]["style"] == "None"
    w.open_axis_dialog(); d = w.axis_dialog; d.tabs.setCurrentIndex(4)
    assert (d.tk["major"]["style"].currentText(), d.tk["major"]["length"].currentText(), d.tk["minor"]["style"].currentText(), d.tk["minor"]["length"].currentText()) == ("Out", "8", "Out", "5")


def test_minor_count_with_auto_major_margins_and_end_labels(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("RAMANPROC_HOME", str(tmp_path))
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from ramanproc import Spectrum
    from ramanproc.gui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1400, 900); w.show()
    w.add_spectrum(Spectrum(np.linspace(400, 2000, 200), np.linspace(0, 1, 200), "t")); w.refresh()
    for _ in range(3): app.processEvents()
    vp = w.plot.viewport(); m = w.pi.layout.getContentsMargins()
    assert abs(m[0] - 0.05 * vp.width()) <= 1 and abs(m[1] - 0.05 * vp.height()) <= 1                      # spectra plot = 90 % of the widget
    ax = w.pi.getAxis("bottom")
    levels = lambda: [(round(sp, 3), len(v)) for sp, v in ax.tickValues(ax.range[0], ax.range[1], ax.width())]
    auto = levels(); assert len(auto) >= 2
    w.open_axis_dialog(); d = w.axis_dialog; d.tabs.setCurrentIndex(0)
    d.mn_type.setCurrentIndex(1); d.mn_cnt.setValue(5); d.apply()                                            # minor "By Counts" with major left on Auto
    lv = levels(); assert lv[0][0] == auto[0][0] and abs(lv[1][0] - auto[0][0] / 6) < 1e-3
    d.mj_type.setCurrentIndex(1); d.mj_val.setText("250"); d.apply(); lv = levels(); assert lv[0][0] == 250 and abs(lv[1][0] - 250 / 6) < 1e-3
    d.mj_type.setCurrentIndex(0); d.mn_type.setCurrentIndex(0); d.apply(); assert levels() == auto          # back to automatic
    assert ax.boundingRect().width() > super(type(ax), ax).boundingRect().width() + 20                         # room for a half-width end label
    w.export_figure(str(tmp_path / "e.png"), width=1000); assert ax.frozen_levels is None and not w._exporting   # export freezes ticks, then releases them


def test_default_y_unit_is_intensity_au(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("RAMANPROC_HOME", str(tmp_path))
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from ramanproc import Spectrum
    from ramanproc.gui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1300, 800); w.show()
    w.add_spectrum(Spectrum(np.linspace(1, 40, 40), np.linspace(0, 1, 40), "t")); w.refresh()
    assert w.cb_yunit.currentText() == "Intensity (a.u.)" and w.pi.getAxis("left").labelText == "Intensity (a.u.)"


def test_axis_titles_move_with_mouse_arrow_keys_and_dialog(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("RAMANPROC_HOME", str(tmp_path))
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt, QPoint
    from ramanproc import Spectrum
    from ramanproc.gui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1400, 900); w.show()
    w.add_spectrum(Spectrum(np.linspace(400, 2000, 100), np.linspace(0, 1, 100), "t")); w.refresh()
    for _ in range(4): app.processEvents()
    ax = w.pi.getAxis("bottom"); ay = w.pi.getAxis("left"); fs = w.figstyle
    def label_center(a):
        return w.plot.mapFromScene(a.mapToScene(a._label_rect().center()))
    # 1) mouse drag of the X title
    p0 = ax.label.pos(); c = label_center(ax); vp = w.plot.viewport()
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, c)
    for k in range(1, 7): QTest.mouseMove(vp, QPoint(c.x() + 10 * k, c.y() - 4 * k)); app.processEvents()
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(c.x() + 60, c.y() - 24)); app.processEvents()
    assert ax.label_dx > 30 and ax.label_dy < -10 and abs(fs.st["axes"]["x"]["label_dx"] - ax.label_dx) < 0.1       # moved and remembered
    assert ax.label.pos().x() > p0.x() + 30
    # 2) click selects, arrow keys nudge, Shift = 10 px, Esc deselects
    c = label_center(ay); QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, c); app.processEvents()
    assert w._sel_axis_label is ay
    QTest.keyClick(w.plot, Qt.Key_Left); QTest.keyClick(w.plot, Qt.Key_Down, Qt.ShiftModifier)
    assert ay.label_dx == -1 and ay.label_dy == 10 and fs.st["axes"]["y"]["label_dy"] == 10
    QTest.keyClick(w.plot, Qt.Key_Escape); assert w._sel_axis_label is None
    # 3) dialog offsets (and reset)
    w.open_axis_dialog(); d = w.axis_dialog; d.tabs.setCurrentIndex(2); d.ti_dx.setValue(25); d.ti_dy.setValue(-8); d.apply()
    assert ax.label_dx == 25 and ax.label_dy == -8
    d.ti_dx.setValue(0); d.ti_dy.setValue(0); d.apply(); assert ax.label_dx == 0 and ax.label_dy == 0
    # 4) the selection frame never ends up in an exported picture
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, label_center(ax)); w.export_figure(str(tmp_path / "x.png"), width=800); assert w._sel_axis_label is None


def test_xy_scale_bar_links_major_tick_drag_and_export(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("RAMANPROC_HOME", str(tmp_path))
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt, QPoint
    from ramanproc import Spectrum
    from ramanproc.gui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1400, 900); w.show()
    w.add_spectrum(Spectrum(np.linspace(400, 2000, 100), np.linspace(0, 1, 100), "t")); w.refresh()
    for _ in range(4): app.processEvents()
    sb = w.add_scalebar(); app.processEvents()
    assert sb.title("x") == f"{sb.major('x'):.6g}" and sb.length("x") == sb.major("x")
    w.figstyle.st["axes"]["x"]["major_step"] = "250"; w.figstyle.apply(); app.processEvents()
    assert sb.length("x") == 250 and sb.title("x") == "250"                      # linked to the major tick setting
    sb.st["y"]["length"] = "0.1"; sb.st["y"]["title"] = "$(Scale) a.u."; sb.refresh()
    assert sb.length("y") == 0.1 and sb.title("y") == "0.1 a.u."
    r = sb.boundingRect(); assert r.width() > 20 and r.height() > 20
    fx = sb.st["fx"]; sb.mouseDragEvent(type("E", (), {"button": lambda s: Qt.LeftButton, "accept": lambda s: None, "pos": lambda s: sb.mapFromParent(sb.pos() + QPoint(30, 0)), "lastPos": lambda s: sb.mapFromParent(sb.pos())})())
    assert sb.st["fx"] > fx
    w.open_scale_dialog(); d = w.scale_dialog; d.sec["x"]["length"].setText("100"); d.mode.setCurrentText("X Scale"); d.apply()
    assert sb.length("x") == 100 and sb.st["mode"] == "X Scale"; d.reject(); assert sb.st["mode"] == "XY Scales"
    out = str(tmp_path / "sb.png"); w.export_figure(out); assert os.path.getsize(out) > 1000
    w.remove_scalebar(); assert w.scalebar is None


def _fake_l6s(path, x, ys, xq=b"Spectr", xu=b"1/cm", yq=b"Intens", yu=b"Cnt", grid=None):
    """Minimal LabSpec 6 layout: typm/uni| strings, size record (uint32 at +12), tagged float32 array."""
    import struct
    from ramanproc import l6s
    def rec(q, u, sizes, a):
        b = l6s._TYP + q + b"\x00" * 4 + l6s._UNI + u + b"\x00" * 4
        for n in sizes: b += l6s._SZ + b"\x00" * 4 + struct.pack("<I", n) + b"\x00" * 4
        return b + l6s._TAM + b"\x00" * 8 + np.asarray(a, "<f4").tobytes()
    yall = np.concatenate(ys)
    data = b"LabSpec6" + b"\x00" * 24 + rec(xq, xu, [len(x)], x) + rec(yq, yu, [len(x), len(ys)], yall)
    for q, a in (grid or {}).items(): data += rec(q, b"\xb5m", [len(a)], a)       # map stage axes (µm)
    open(path, "wb").write(data)


def test_l6s_single_and_multi(tmp_path):
    x = np.linspace(400, 1800, 50); y1 = np.arange(50.) * 3; y2 = 1000 - np.arange(50.)
    p = str(tmp_path / "one.l6s"); _fake_l6s(p, x, [y1])
    out = safeio.load_spectra(p); s = out[0][0]
    assert len(out) == 1 and s.name == "one" and np.allclose(s.x, x.astype("f4")) and np.array_equal(s.y, y1)
    assert s.meta["xunit"] == "cm-1" and s.meta["ylabel"] == "Intensity (counts)"
    p2 = str(tmp_path / "two.dat"); _fake_l6s(p2, x, [y1, y2])       # detected by header, not extension
    out = safeio.load_spectra(p2)
    assert [o[0].name for o in out] == ["two_1", "two_2"] and np.array_equal(out[1][0].y, y2)


def test_l6s_real_file_matches_txt_export():
    import pytest
    d = r"H:/Lab/Manuscript/2026/@RH-Talanta/Revision/talanta-R2/AuNPs@CL"
    f, t = os.path.join(d, "-4R6G.l6s"), os.path.join(d, "-4R6G.txt")
    if not (os.path.exists(f) and os.path.exists(t)): pytest.skip("reference L6S/TXT pair not available")
    s = safeio.load_spectra(f)[0][0]; ref = safeio.load_spectra(t)[0][0]
    assert len(s.x) == len(ref.x) == 528
    assert np.array_equal(s.y, ref.y) and np.max(np.abs(s.x - ref.x)) < 0.01


def test_l6m_map_points_get_stage_coordinates(tmp_path):
    x = np.linspace(400, 1800, 30); gx = np.array([-4.0, -3.5, -3.0]); gy = np.array([1.0, 2.0])
    ys = [np.full(30, 10. * k) for k in range(6)]
    p = str(tmp_path / "m.l6m"); _fake_l6s(p, x, ys, grid={b"X": gx, b"Y": gy})
    out = safeio.load_spectra(p); sp = [o[0] for o in out]
    assert len(sp) == 6 and all(s.meta["group"] == "m" for s in sp)
    assert sp[1].meta["map_xy"] == (-3.5, 1.0) and sp[3].meta["map_xy"] == (-4.0, 2.0)     # row by row, X fastest
    assert sp[4].name == "m_5 (-3.50, 2.00 \u00b5m)" and sp[4].y[0] == 40 and "mapping 3×2" in out[0][1][0]


def test_l6m_real_map():
    import pytest
    f = r"D:/Downloads/AuNPs@CL_510-5_17_48_03_3_30 s_638nm_Edge_10% (4_0mW).l6m"
    if not os.path.exists(f): pytest.skip("reference L6M map not available")
    out = safeio.load_spectra(f); sp = [o[0] for o in out]
    assert len(sp) == 100 and all(len(s.x) == 613 for s in sp)
    assert abs(sp[0].meta["map_xy"][0] + 4.607) < 1e-3 and abs(sp[99].meta["map_xy"][1] - 0.09) < 1e-3
    assert sp[9].y.max() == max(s.y.max() for s in sp)                         # brightest corner = top right, as in LabSpec
    assert sp[0].meta["l6s"]["Title"].startswith("AuNPs@CL_510-5")
