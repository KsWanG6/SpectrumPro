"""ramanproc: Raman spectrum post-processing (independent implementation).

Behaviour was characterised against reference input/output pairs and
published methods (Savitzky-Golay, SNIP/iterative clipping, min-max).
"""
from .core import Spectrum
from .smooth import smooth
from .baseline import remove_baseline, baseline_from_points, remove_baseline_points
from .normalize import normalize
from .cosmic import remove_cosmic_ray
from .io import read_xy, read_xyxy, read_xyy, write_xy, write_xyy
from .ops import *
from .peaks import find_raman_peaks
from .classify import rank_matches, train_svm, predict_svm
from .pipeline import run_pipeline

from .lod import peak_response, calibration, lod_loq
from .ef import enhancement_factor
from . import quant
from . import peakanalysis
from . import qc

from . import safeio
