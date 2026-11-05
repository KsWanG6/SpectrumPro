"""Spectrum matching (library search) and SVM classification. Standard definitions."""
import numpy as np
from scipy.spatial import distance as _d
from .core import Spectrum

DISTANCES = {
    "euclidean": _d.euclidean, "chebyshev": _d.chebyshev, "manhattan": _d.cityblock,
    "canberra": _d.canberra, "correlation": _d.correlation, "cosine": _d.cosine,
    "sqeuclidean": _d.sqeuclidean,
}


def _on_grid(q: Spectrum, ref: Spectrum):
    lo, hi = max(q.x[0], ref.x[0]), min(q.x[-1], ref.x[-1])
    x = q.x[(q.x >= lo) & (q.x <= hi)]
    return np.interp(x, q.x, q.y), np.interp(x, ref.x, ref.y)


def rank_matches(query: Spectrum, library: list, metric: str = "correlation"):
    """Sorted [(distance, spectrum)], smaller = more similar."""
    f = DISTANCES[metric]
    res = []
    for r in library:
        a, b = _on_grid(query, r)
        res.append((float(f(a, b)), r))
    return sorted(res, key=lambda t: t[0])


def train_svm(spectra, labels, grid, **kw):
    from sklearn.svm import SVC
    X = np.array([np.interp(grid, s.x, s.y) for s in spectra])
    return SVC(**{"kernel": "rbf", "probability": True, **kw}).fit(X, labels), np.asarray(grid)


def predict_svm(model_grid, spectra):
    model, grid = model_grid
    X = np.array([np.interp(grid, s.x, s.y) for s in spectra])
    return model.predict(X), model.predict_proba(X)
