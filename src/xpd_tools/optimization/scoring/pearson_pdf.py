"""Pearson correlation coefficient between measured and reference G(r)."""

import numpy as np
import pandas as pd


def pearson(
    experiment_data_df: pd.DataFrame,
    simulated_data_df: pd.DataFrame,
    r_min: float = 2.0,
    r_max: float = 20.0,
) -> float:
    """Pearson correlation coefficient between the measured and reference G(r).

    Args
    -------
        experiment_data_df: DataFrame containing the measured G(r) profile.
        simulated_data_df: DataFrame containing the reference G(r) profile.
        r_min: Minimum r value to consider.
        r_max: Maximum r value to consider.

    Returns
    -------
        Pearson correlation coefficient between the measured and reference G(r).
    """
    r_exp, g_exp = experiment_data_df["r"], experiment_data_df["g(r)"]
    r_sim, g_sim = simulated_data_df["r"], simulated_data_df["g(r)"]

    # Mask to select r values between r_min and r_max
    mask = (r_exp >= r_min) & (r_exp <= r_max)
    r_slice = r_exp[mask]
    g_slice = g_exp[mask]

    # Interpolate the simulated G(r) values to match the experimental r values
    g_sim_i = np.interp(r_slice, r_sim, g_sim)
    pearson_results = np.corrcoef(g_slice, g_sim_i)[0, 1]

    return float(pearson_results)
