"""Cross-correlation-function similarity S12 between measured and reference G(r)."""

import numpy as np
import pandas as pd


def cross_correlation(
    experiment_data_df: pd.DataFrame,
    simulated_data_df: pd.DataFrame,
    r_min: float = 2.0,
    r_max: float = 20.0,
    lag_halfwidth: float = 0.5,
) -> float:
    """Habermehl, Schlesinger & Prill, J. Appl. Cryst. 2021, 54, 612-623.

    DOI: 10.1107/S1600576721001722.

    Cross-correlation-function similarity S12 between measured and
    reference G(r) profiles

    CCF_ab(s) = sum_r a(r) * b(r + s)
    w(s)      = 1 - |s| / l   for |s| <= l, else 0   (l = lag_halfwidth)
    S12       = sum_s w(s) CCF_12(s) / sqrt(sum_s w(s) CCF_11(s) * sum_s w(s) CCF_22(s))

    Range is 0 to 1, 1 = identical -- higher means more similar.

    Args
    -------
        - experiment_data_df: DataFrame containing the experimental G(r) data.
        - simulated_data_df: DataFrame containing the simulated G(r) data.
        - r_min: Minimum r value to consider.
        - r_max: Maximum r value to consider.
        - lag_halfwidth: Halfwidth of the lag window.

    Returns
    -------
        - Cross-correlation similarity score
    """
    r_exp, g_exp = experiment_data_df["r"], experiment_data_df["g(r)"]
    r_sim, g_sim = simulated_data_df["r"], simulated_data_df["g(r)"]

    mask = (r_exp >= r_min) & (r_exp <= r_max)
    r_slice_exp = r_exp[mask].to_numpy()
    g_slice_exp = g_exp[mask].to_numpy()

    # Interpolate the simulated G(r) values to match the experimental r values
    g_sim_i = np.interp(r_slice_exp, r_sim, g_sim)

    def rescale(g: np.ndarray) -> np.ndarray:
        floor = g.min()
        baseline = g[-5:].mean()
        return (g - floor) / (baseline - floor)

    g1 = rescale(g_slice_exp)
    g2 = rescale(g_sim_i)

    # Mean-center so the lag-0 term alone reduces to Pearson's r exactly
    g1 = g1 - g1.mean()
    g2 = g2 - g2.mean()

    dr = r_slice_exp[1] - r_slice_exp[0]
    max_lag = round(lag_halfwidth / dr)
    lags = np.arange(-max_lag, max_lag + 1)
    weights = 1.0 - np.abs(lags) * dr / lag_halfwidth

    def weighted_ccf(a: np.ndarray, b: np.ndarray) -> float:
        n = len(a)
        total = 0.0
        for lag, w in zip(lags, weights, strict=True):
            if lag >= 0:
                total += w * np.dot(a[: n - lag], b[lag:])
            else:
                total += w * np.dot(a[-lag:], b[: n + lag])
        return total

    ccf_12 = weighted_ccf(g1, g2)
    ccf_11 = weighted_ccf(g1, g1)
    ccf_22 = weighted_ccf(g2, g2)

    return float(ccf_12 / np.sqrt(ccf_11 * ccf_22))
