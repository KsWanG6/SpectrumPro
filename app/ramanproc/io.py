import numpy as np
from .core import Spectrum


def read_xy(path: str, name: str | None = None) -> Spectrum:
    """Two-column text (space/tab/comma). With 3 columns the last two are used (leading index column)."""
    d = np.loadtxt(path, ndmin=2, delimiter=None if "," not in open(path).readline() else ",", comments=("#", "%"))
    if d.shape[1] < 2:
        raise ValueError("need at least two columns")
    return Spectrum(d[:, -2], d[:, -1], name or str(path))


def read_xyxy(path: str):
    """Multi-spectrum text: columns x1 y1 x2 y2 ... (NaN/blank padding allowed). Returns list of Spectrum."""
    d = np.genfromtxt(path, delimiter=None)
    d = np.atleast_2d(d)
    out = []
    for k in range(0, d.shape[1] - 1, 2):
        m = ~np.isnan(d[:, k]) & ~np.isnan(d[:, k + 1])
        out.append(Spectrum(d[m, k], d[m, k + 1], f"{path}#{k // 2 + 1}"))
    return out


def read_xyy(path: str):
    """Shared x then several y columns."""
    d = np.loadtxt(path, ndmin=2)
    return [Spectrum(d[:, 0], d[:, k], f"{path}#{k}") for k in range(1, d.shape[1])]


def write_xy(s: Spectrum, path: str):
    from .safeio import atomic_write
    atomic_write(path, lambda t: np.savetxt(t, np.column_stack([s.x, s.y]), delimiter="\t", fmt="%.15g"))


def write_xyy(spectra, path: str):
    ref = spectra[0]
    cols = [ref.x] + [np.interp(ref.x, t.x, t.y) for t in spectra]
    from .safeio import atomic_write
    atomic_write(path, lambda t: np.savetxt(t, np.column_stack(cols), delimiter="\t", fmt="%.15g"))
