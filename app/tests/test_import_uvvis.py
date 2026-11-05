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
