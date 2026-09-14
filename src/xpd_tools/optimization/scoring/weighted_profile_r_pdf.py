"""Weighted-profile R-factor (Rw) between measured and reference G(r) profiles."""

import numpy as np
import pandas as pd


def weighted_profile_r(
    experiment_data_df: pd.DataFrame,
    simulated_data_df: pd.DataFrame,
    r_min: float = 2.0,
    r_max: float = 20.0,
) -> float:
    """Weighted-profile R-factor (Rw).

    Rw = sqrt( sum(w_i * (g_obs,i - g_calc,i)**2) / sum(w_i * g_obs,i**2) )

    In theory: Weights the points by their experimental G(r) values, so points with
    larger G(r) contribute more to the Rw calculation.
    In practice: the weights are normalized to sum to 1, so the denominator
    in the Rw formula is always 1 and can be omitted.

    Args
    -------
    experiment_data_df : pd.DataFrame
        The experimental G(r) data.
    simulated_data_df : pd.DataFrame
        The simulated G(r) data.
    r_min : float, optional
        The minimum r value to include in the calculation.
    r_max : float, optional
        The maximum r value to include in the calculation.

    Returns
    -------
    float
        The weighted-profile R-factor (Rw).
    """
    r_exp, g_exp = experiment_data_df["r"], experiment_data_df["g(r)"]
    r_sim, g_sim = simulated_data_df["r"], simulated_data_df["g(r)"]

    # Mask to select r values between r_min and r_max
    mask = (r_exp >= r_min) & (r_exp <= r_max)
    r_slice_exp = r_exp[mask]
    g_slice_exp = g_exp[mask]

    # Interpolate the simulated G(r) values to match the experimental r values
    g_sim_i = np.interp(r_slice_exp, r_sim, g_sim)

    # Normalize each curve to unit L2 norm, independently, BEFORE comparing
    g_slice_exp = g_slice_exp / np.linalg.norm(g_slice_exp)
    g_sim_i = g_sim_i / np.linalg.norm(g_sim_i)

    residual = g_slice_exp - g_sim_i
    rw = np.sqrt(np.sum(residual ** 2) / np.sum(g_slice_exp ** 2))

    return float(rw)
