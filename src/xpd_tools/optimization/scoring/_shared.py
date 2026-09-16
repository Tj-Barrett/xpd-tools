"""Shared masking/interpolation/validation for the plain G(r) scorers."""

import numpy as np
from numpy.typing import ArrayLike


def _mask_and_interpolate(
    r_exp: ArrayLike,
    g_exp: ArrayLike,
    r_sim: ArrayLike,
    g_sim: ArrayLike,
    r_min: float,
    r_max: float,
    *,
    scorer: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Mask to [r_min, r_max] and interpolate the reference onto that grid.

    Every scorer that calls this divides or normalizes by something
    derived from spread (std, L2 norm, min/max range) of the *windowed*
    profiles -- a reference that's constant only within [r_min, r_max]
    (but not over its full range) passes analysis.pdf_profile's own
    constant-profile guard, since that guard checks the full, unmasked
    reference array. Checking here, against what's actually used, catches
    that case with a message naming the actual window.
    """
    r_exp = np.asarray(r_exp, dtype=float)
    g_exp = np.asarray(g_exp, dtype=float)
    r_sim = np.asarray(r_sim, dtype=float)
    g_sim = np.asarray(g_sim, dtype=float)

    mask = (r_exp >= r_min) & (r_exp <= r_max)
    r_slice = r_exp[mask]
    g_slice = g_exp[mask]
    g_sim_i = np.interp(r_slice, r_sim, g_sim)

    if np.ptp(g_slice) == 0 or np.ptp(g_sim_i) == 0:
        raise ValueError(
            f"{scorer}: measured or reference G(r) is constant within "
            f"r_min={r_min}, r_max={r_max} -- correlation is undefined"
        )
    return r_slice, g_slice, g_sim_i
