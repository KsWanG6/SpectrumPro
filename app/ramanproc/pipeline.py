import json
from . import smooth, remove_baseline, normalize, remove_cosmic_ray
from .ops import crop, uniform_x

_STEPS = {"smooth": smooth, "baseline": remove_baseline, "normalize": normalize,
          "cosmic": remove_cosmic_ray, "crop": crop, "uniform_x": uniform_x}


def run_pipeline(s, steps):
    """steps: [("smooth", {"method":"savgol","frame_length":9}), ("baseline", {...}), ...]. History is kept on the result."""
    for name, kw in steps:
        s = _STEPS[name](s, **kw)
    return s


def pipeline_to_json(steps) -> str:
    return json.dumps(steps, indent=2)
