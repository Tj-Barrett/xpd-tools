"""PDF scoring functions."""

from .cross_correlation_pdf import cross_correlation
from .ensemble_pdf import EnsembleGoodnessOfFitScorer
from .nn_matrix_pdf import nn_matrix
from .pearson_pdf import pearson
from .weighted_profile_r_pdf import weighted_profile_r

_SCORING_FUNCTIONS = {
    "pearson": pearson,
    "cross_correlation": cross_correlation,
    "nn_matrix": nn_matrix,
    "weighted_profile_r": weighted_profile_r,
}
# "ensemble" is scored separately (see _resolve_scorer) -- it's stateful
# (running mean/std per phase across calls), unlike the plain functions
# above, so it can't live in _SCORING_FUNCTIONS's simple lookup table.
_ALL_SCORING_NAMES = frozenset({*_SCORING_FUNCTIONS, "ensemble"})

EnsembleScorers = dict[str, EnsembleGoodnessOfFitScorer]


def _resolve_scorer(scoring_function: str, phase_name: str, ensemble_scorers: EnsembleScorers):
    """Return the callable to score one phase's G(r) profile.

    `ensemble_scorers` is a per-evaluator, per-mode (raw vs. fit) registry
    that must persist across calls -- EnsembleGoodnessOfFitScorer tracks a
    running mean/std per metric to normalize each new score against the
    phase's own history, so a fresh instance every call would make it
    meaningless. One instance is created per phase name, lazily, the first
    time that phase is scored.
    """
    if scoring_function == "ensemble":
        return ensemble_scorers.setdefault(
            phase_name, EnsembleGoodnessOfFitScorer()
        ).score
    return _SCORING_FUNCTIONS[scoring_function]


__all__ = [
    "EnsembleGoodnessOfFitScorer",
    "EnsembleScorers",
    "cross_correlation",
    "nn_matrix",
    "pearson",
    "weighted_profile_r",
]
