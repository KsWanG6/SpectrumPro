"""SERS enhancement factor (analytical EF).

    EF = (I_SERS / (X_SERS * P_SERS * t_SERS)) / (I_RS / (X_RS * P_RS * t_RS))

I = peak response (height or area), X = concentration (same units for both) or number of probed molecules,
P = laser power, t = integration time (set to 1 when both measurements used identical settings).
Replicates give mean +- sample SD; EF uncertainty is propagated from the relative SDs of I_SERS and I_RS.
"""
import numpy as np


def enhancement_factor(i_sers, i_ref, x_sers, x_ref, p_sers=1.0, t_sers=1.0, p_ref=1.0, t_ref=1.0) -> dict:
    a = np.atleast_1d(np.asarray(i_sers, float)); b = np.atleast_1d(np.asarray(i_ref, float))
    for name, v in (("X_SERS", x_sers), ("X_RS", x_ref), ("P_SERS", p_sers), ("t_SERS", t_sers), ("P_RS", p_ref), ("t_RS", t_ref)):
        if not (v is not None and np.isfinite(v) and v > 0):
            raise ValueError(f"{name} must be a positive number")
    if len(a) == 0 or len(b) == 0:
        raise ValueError("need at least one SERS and one reference spectrum")
    ma, mb = float(a.mean()), float(b.mean())
    if mb <= 0 or ma <= 0:
        raise ValueError("mean peak responses must be positive (check peak window / baseline)")
    sa = float(a.std(ddof=1)) if len(a) > 1 else 0.0
    sb = float(b.std(ddof=1)) if len(b) > 1 else 0.0
    ef = (ma / (x_sers * p_sers * t_sers)) / (mb / (x_ref * p_ref * t_ref))
    sd = ef * float(np.hypot(sa / ma, sb / mb))
    return {"ef": ef, "ef_sd": sd, "log10_ef": float(np.log10(ef)), "i_sers": ma, "i_sers_sd": sa, "i_ref": mb, "i_ref_sd": sb,
            "n_sers": len(a), "n_ref": len(b)}
