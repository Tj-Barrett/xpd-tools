"""Non-negative matrix factorization dissimilarity."""

import warnings

import numpy as np
from numpy.typing import ArrayLike
from sklearn.decomposition import NMF
from sklearn.exceptions import ConvergenceWarning


def nn_matrix(
    r_exp: ArrayLike,
    g_exp: ArrayLike,
    r_sim: ArrayLike,
    g_sim: ArrayLike,
    r_min: float = 2.0,
    r_max: float = 20.0,
) -> float:
    """NN matrix dissimilarity between measured and reference G(r) profiles.

    Args
    -------
        - r_exp: Measured G(r) radial grid.
        - g_exp: Measured G(r) values.
        - r_sim: Reference G(r) radial grid.
        - g_sim: Reference G(r) values.
        - r_min: Minimum r value to consider.
        - r_max: Maximum r value to consider.

    Returns
    -------
        - Non-negative matrix factorization dissimilarity score.
    """
    r_exp = np.asarray(r_exp, dtype=float)
    g_exp = np.asarray(g_exp, dtype=float)
    r_sim = np.asarray(r_sim, dtype=float)
    g_sim = np.asarray(g_sim, dtype=float)

    # Mask to select r values between r_min and r_max
    mask = (r_exp >= r_min) & (r_exp <= r_max)
    r_slice_exp = r_exp[mask]
    g_slice_exp = g_exp[mask]

    # Interpolate the simulated G(r) values to match the experimental r values
    g_sim_i = np.interp(r_slice_exp, r_sim, g_sim)

    # Normalize each curve to unit L2 norm, independently, BEFORE comparing
    g_slice_exp = g_slice_exp / np.linalg.norm(g_slice_exp)
    g_sim_i = g_sim_i / np.linalg.norm(g_sim_i)

    # NMF needs non-negative input
    floor = min(g_slice_exp.min(), g_sim_i.min())
    eps = 1e-10
    p = g_slice_exp - floor + eps
    q = g_sim_i - floor + eps

    x = np.vstack([p, q])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ConvergenceWarning)
        model = NMF(n_components=1, init="nndsvd", random_state=42, max_iter=500)
        model.fit_transform(x)

    return float(model.reconstruction_err_)
