"""Regression tests: bugs found in the correctness review (each has a 'was broken' note) + reference checks of the main formulas.
Run from the app folder:  python -m pytest tests -q"""
import numpy as np
import pytest
from scipy import stats
from ramanproc import quant as Q, safeio, mathexpr as ME, peakanalysis as PA, baseline as B, ops, lod, ef, rsd
from ramanproc.core import Spectrum

LN2 = np.log(2)
gauss = lambda x, h, c, f: h * np.exp(-4 * LN2 * ((x - c) / f) ** 2)


# ---------------------------------------------------------------- fixed bugs
@pytest.mark.parametrize("model", ["linear", "linear_w1x", "linear_w1x2"])
@pytest.mark.parametrize("method", ["blank", "residual", "intercept"])
def test_lod_is_unit_equivariant(model, method):
    """Was broken: residual method with weighted models changed with the concentration unit (ratio 31.6 / 1.0 instead of 1000)."""
    rng = np.random.default_rng(1)
    c = np.array([1, 2, 5, 10, 20, 50.0]); y = 3 * c + 4 + rng.normal(0, 2, c.size); blank = [0.4, -0.3, 0.2, 0.1, -0.5]
    a = Q.lod_record(Q.fit_calibration(c, y, model), method, blank)
    b = Q.lod_record(Q.fit_calibration(c / 1000, y, model), method, blank)
    assert a["lod"] / b["lod"] == pytest.approx(1000, rel=1e-9)
    assert a["loq"] / b["loq"] == pytest.approx(1000, rel=1e-9)


def test_lod_residual_ols_unchanged():
    c = np.array([1, 2, 5, 10, 20.0]); y = 2 * c + 1 + np.array([.3, -.2, .1, -.4, .2])
    f = Q.fit_calibration(c, y, "linear")
    assert Q.lod_record(f, "residual")["lod"] == pytest.approx(3 * f["sy"] / f["slope"])
    assert f["sy_resp"] == pytest.approx(f["sy"])


def test_sigma_area_includes_baseline_noise():
    """Was broken: sigma_area ignored baseline-estimate noise (3-4x too small for linear / min baselines)."""
    rng = np.random.default_rng(0); x = np.arange(200, 1800, 1.0); sig = 5.0
    for bl, tol in (("none", 0.2), ("linear", 0.2), ("min", 0.3)):
        A = [PA.measure_peak(Spectrum(x, gauss(x, 1000, 1000, 14) + 50 + rng.normal(0, sig, x.size)), 1000, 30, bl, noise=sig)["area"] for _ in range(400)]
        rep = PA.measure_peak(Spectrum(x, gauss(x, 1000, 1000, 14) + 50), 1000, 30, bl, noise=sig)["sigma_area"]
        assert rep == pytest.approx(np.std(A, ddof=1), rel=tol), bl


def test_peak_ratio_area_sigma_matches_monte_carlo():
    rng = np.random.default_rng(5); x = np.arange(200, 1800, 1.0); R, S = [], []
    for _ in range(300):
        y = gauss(x, 1000, 1000.3, 14) + gauss(x, 500, 1300, 14) + 20 + rng.normal(0, 5, x.size)
        r = PA.peak_ratio(Spectrum(x, y), {"center": 1000, "hw": 30}, {"center": 1300, "hw": 30}, "area", noise=5.0)
        R.append(r["R"]); S.append(r["sigma_R"])
    assert np.mean(S) == pytest.approx(np.std(R, ddof=1), rel=0.3)


@pytest.mark.parametrize("eq,expect", [("max(Y,0)", [0, 0, 0, 0, 0, 1, 2]), ("min(Y,2)", [-4, -3, -2, -1, 0, 1, 2]),
                                       ("max(Y,0,1)", [1, 1, 1, 1, 1, 1, 2]), ("max(Y)", [2] * 7)])
def test_math_min_max(eq, expect):
    """Was broken: two-argument min/max raised 'inhomogeneous shape'."""
    s = Spectrum(np.arange(7.), np.arange(7.) - 4)
    assert ME.apply_one(s, eq).y == pytest.approx(expect)


def test_combine_nested_range_keeps_outer_data():
    """Was broken: a narrow spectrum inside a wide one overwrote the wide data beyond its end with its edge value."""
    big = Spectrum(np.arange(100., 3000), np.full(2900, 10.0)); small = Spectrum(np.arange(500., 1000), np.full(500, 20.0))
    out = ME.combine([big, small], adjust=False)
    assert out.y[np.searchsorted(out.x, 2000)] == 10.0
    assert out.y[np.searchsorted(out.x, 300)] == 10.0
    assert out.y[np.searchsorted(out.x, 999)] == pytest.approx(20.0, abs=0.1)
    assert np.all(np.diff(out.x) > 0)


def test_combine_partial_overlap_still_works():
    a = Spectrum(np.arange(100., 600), np.full(500, 10.0)); b = Spectrum(np.arange(500., 1000), np.full(500, 30.0))
    out = ME.combine([a, b], adjust=False)
    assert np.all(np.diff(out.x) > 0) and out.x[0] == 100 and out.x[-1] == 999
    assert out.y[np.searchsorted(out.x, 450)] == 10.0 and out.y[np.searchsorted(out.x, 800)] == 30.0


def test_clean_xy_duplicate_with_nan():
    """Was broken: NaN counted as 0 when averaging duplicate X (mean of 20 and NaN gave 10)."""
    x, y, notes = safeio.clean_xy([1., 2, 2, 3, 4, 5], [10., 20, np.nan, 30, 40, 50])
    assert y[1] == 20.0 and len(x) == 5
    x, y, _ = safeio.clean_xy([1., 2, 2, 3, 4, 5], [10., 20, 30, 30, 40, 50]); assert y[1] == 25.0
    x, y, _ = safeio.clean_xy([1., 2, 2, 3, 4, 5], [10., np.nan, np.nan, 30, 40, 50]); assert np.isnan(y[1])


# ---------------------------------------------------------------- reference checks of formulas that were verified correct
def test_ols_matches_linregress():
    rng = np.random.default_rng(1); c = np.array([1, 2, 5, 10, 20, 50.0]); y = 3 * c + 4 + rng.normal(0, 2, c.size)
    f = Q.fit_calibration(c, y); lr = stats.linregress(c, y)
    assert [f["slope"], f["intercept"], f["se_slope"], f["se_intercept"], f["r2"]] == pytest.approx(
        [lr.slope, lr.intercept, lr.stderr, lr.intercept_stderr, lr.rvalue ** 2])


@pytest.mark.parametrize("p,model", [(1, "linear_w1x"), (2, "linear_w1x2")])
def test_wls_matches_matrix_algebra(p, model):
    rng = np.random.default_rng(2); c = np.array([1, 2, 5, 10, 20, 50.0]); y = 3 * c + 4 + rng.normal(0, 2, c.size)
    w = c ** (-float(p)); X = np.column_stack([np.ones_like(c), c]); Wm = np.diag(w)
    beta = np.linalg.solve(X.T @ Wm @ X, X.T @ Wm @ y); r = y - X @ beta
    cov = (w * r ** 2).sum() / (len(c) - 2) * np.linalg.inv(X.T @ Wm @ X); f = Q.fit_calibration(c, y, model)
    assert [f["intercept"], f["slope"]] == pytest.approx(beta)
    assert [f["se_intercept"], f["se_slope"]] == pytest.approx(np.sqrt(np.diag(cov)))


def test_loglinear_round_trip():
    c = np.array([1, 10, 100, 1000, 1e4]); f = Q.fit_calibration(c, 50 * np.log10(c) + 20, "loglinear")
    assert Q.predict_conc(f, 50 * np.log10(300) + 20)["conc"] == pytest.approx(300)


def test_als_and_arpls_match_dense_reference():
    rng = np.random.default_rng(0); n = 120
    y = rng.normal(0, 1, n).cumsum() * 0.1 + np.linspace(0, 20, n) + gauss(np.arange(n * 1.0), 30, 60, 8)
    D = np.diff(np.eye(n), 2, axis=0); H = 1e4 * D.T @ D; w = np.ones(n)
    for _ in range(10):
        z = np.linalg.solve(np.diag(w) + H, w * y); w = 0.01 * (y > z) + 0.99 * (y < z)
    assert B._als(y, 1e4, 0.01, 10) == pytest.approx(z, abs=1e-6)


@pytest.mark.parametrize("model,eta", [("gaussian", 0.0), ("lorentzian", 1.0)])
def test_fit_peaks_recovers_parameters(model, eta):
    rng = np.random.default_rng(3); x = np.arange(200, 1800, 1.0)
    shape = PA._shape(x, 1000, 1000.3, 14, eta) + 50 + rng.normal(0, 1, x.size)
    p = PA.fit_peaks(Spectrum(x, shape), [1002], 40, model)["peaks"][0]
    assert p["position"] == pytest.approx(1000.3, abs=0.05) and p["fwhm"] == pytest.approx(14, abs=0.1)
    assert p["area"] == pytest.approx(PA.shape_area(1000, 14, eta), abs=4 * p["area_sd"])


def test_integral_and_derivatives():
    xs = np.linspace(0, np.pi, 50); assert ops.integral(Spectrum(xs, np.sin(xs))) == pytest.approx(2, abs=1e-4)
    from ramanproc import filters as FL
    x = np.arange(0, 20, 0.1); d = FL.apply_filter([Spectrum(x, np.sin(x))], "1st derivative", "Manual", window=11, order=3)[0].y
    assert np.abs(d - np.cos(x))[10:-10].max() < 5e-4


def test_ef_and_rsd():
    r = ef.enhancement_factor([1000, 1100, 900], [10, 11, 9], 1e-9, 1e-2)
    assert r["ef"] == pytest.approx(1e9)
    v = np.array([98., 103, 101, 95, 104, 99, 100]); s = rsd.rsd_stats(v)
    assert s["rsd"] == pytest.approx(100 * v.std(ddof=1) / v.mean())
    assert s["ci"] == pytest.approx(stats.t.interval(0.95, 6, v.mean(), stats.sem(v)))
