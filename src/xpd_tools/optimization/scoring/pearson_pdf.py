"""Pearson correlation coefficient between measured and reference G(r)."""

import numpy as np
from numpy.typing import ArrayLike


def pearson(
    r_exp: ArrayLike,
    g_exp: ArrayLike,
    r_sim: ArrayLike,
    g_sim: ArrayLike,
    r_min: float = 2.0,
    r_max: float = 20.0,
) -> float:
    """Pearson correlation coefficient between the measured and reference G(r).

    Args
    -------
        r_exp: Measured G(r) radial grid.
        g_exp: Measured G(r) values.
        r_sim: Reference G(r) radial grid.
        g_sim: Reference G(r) values.
        r_min: Minimum r value to consider.
        r_max: Maximum r value to consider.

    Returns
    -------
        Pearson correlation coefficient between the measured and reference G(r).
    """
    r_exp = np.asarray(r_exp, dtype=float)
    g_exp = np.asarray(g_exp, dtype=float)
    r_sim = np.asarray(r_sim, dtype=float)
    g_sim = np.asarray(g_sim, dtype=float)

    # Mask to select r values between r_min and r_max
    mask = (r_exp >= r_min) & (r_exp <= r_max)
    r_slice = r_exp[mask]
    g_slice = g_exp[mask]

    # Interpolate the simulated G(r) values to match the experimental r values
    g_sim_i = np.interp(r_slice, r_sim, g_sim)
    pearson_result = np.corrcoef(g_slice, g_sim_i)[0, 1]

    return float(pearson_result)
