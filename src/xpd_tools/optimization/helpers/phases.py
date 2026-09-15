
from dataclasses import dataclass

from blop.ax import Objective


@dataclass(frozen=True, kw_only=True)
class Phase:
    """Phase structure to score against using PDF."""

    name: str
    gr: str
    cif: str
    simulated: bool = False
    minimize: bool = False


def _create_phase(phase: Phase) -> Objective:
    return Objective(
        name=phase.name,
        minimize=phase.minimize
    )
