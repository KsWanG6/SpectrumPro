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
