import numpy as np
import pytest
from ramanproc import normalize, Spectrum, lod

LN2 = np.log(2)
gauss = lambda x, h, c, f: h * np.exp(-4 * LN2 * ((x - c) / f) ** 2)
X = np.arange(400, 1800, 1.0)
S = Spectrum(X, gauss(X, 800, 1075, 12) + gauss(X, 400, 1580, 14) + 30 + 0.01 * (X - 400))


def test_max_keeps_baseline_and_maxes_to_one():
    o = normalize(S, "max"); assert o.y.max() == pytest.approx(1.0)
    assert o.y / S.y == pytest.approx(np.full(len(X), 1 / S.y.max()))


def test_l2_is_unit_vector():
    assert np.linalg.norm(normalize(S, "l2").y) == pytest.approx(1.0)


@pytest.mark.parametrize("bl", [False, True])
def test_peak_height_reference_peak_becomes_one(bl):
    o = normalize(S, "peak_height", center=1075, hw=15, baseline=bl)
    assert lod.peak_response(o, 1075, 15, "height", bl) == pytest.approx(1.0)
    assert o.y / S.y == pytest.approx(np.full(len(X), o.y[0] / S.y[0]))        # a pure scaling, no offset


@pytest.mark.parametrize("bl", [False, True])
def test_peak_area_reference_band_becomes_one(bl):
    o = normalize(S, "peak_area", center=1075, hw=40, baseline=bl)
    assert lod.peak_response(o, 1075, 40, "area", bl) == pytest.approx(1.0)


def test_internal_standard_ratio_is_invariant_to_gain():
    a = normalize(S, "peak_height", center=1075, hw=15, baseline=True)
    b = normalize(Spectrum(X, 7.3 * S.y), "peak_height", center=1075, hw=15, baseline=True)
    assert a.y == pytest.approx(b.y, rel=1e-9) or np.allclose(a.y - 0, b.y, atol=1e-9)


def test_existing_methods_unchanged():
    assert normalize(S, "minmax").y.min() == 0 and normalize(S, "minmax").y.max() == 1
    assert np.trapezoid(normalize(S, "area").y - normalize(S, "area").y.min(), X) == pytest.approx(1.0)


def test_errors_are_clear():
    with pytest.raises(ValueError, match="峰"): normalize(S, "peak_height", center=1075, hw=None)
    with pytest.raises(ValueError, match="≤ 0"): normalize(Spectrum(X, np.zeros_like(X) - 1), "peak_height", center=1075, hw=10)
    with pytest.raises(ValueError): normalize(Spectrum(X, -np.abs(S.y)), "max")
    with pytest.raises(ValueError, match="峰視窗"): normalize(S, "peak_area", center=5000, hw=10)
    with pytest.raises(ValueError): normalize(S, "nonsense")
