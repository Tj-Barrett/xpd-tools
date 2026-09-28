"""Sources for flow control in the optimization workflow.

Each pump entry may set `loaded_ml` (volume filled into the syringe) to have the
plans check, before every trial, that it can supply the trial; `reserve_ml` is kept
back for dead volume. Without `loaded_ml` the pump isn't checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, kw_only=True)
class FlowSource:
    """One precursor pump controlled by an optimization degree of freedom."""

    dof: str
    pump: Any
    precursor: str
    sample_label: str
    syringe_ml: float = 50.0
    material: str = "steel"
    target_ml: float = 30.0
    set_target: bool = True
    loaded_ml: float | None = None
    reserve_ml: float = 1.0


@dataclass(frozen=True, kw_only=True)
class DilutionStage:
    """A dilution pump started before or after mixer equilibration."""

    pump: Any
    ratio: float
    position: Literal["before_equilibrium", "after_equilibrium"]
    syringe_ml: float
    material: str
    target_ml: float
    set_target: bool = True
    wait_sec: float = 0.0
    loaded_ml: float | None = None
    reserve_ml: float = 1.0


@dataclass(frozen=True, kw_only=True)
class WashCycle:
    """One sequential wash-pump cycle."""

    pump: Any
    rate_ul_min: float = 500.0
    duration_sec: float = 60.0
    syringe_ml: float = 50.0
    material: str = "steel"
    target_ml: float = 30.0
    set_target: bool = False
    loaded_ml: float | None = None
    reserve_ml: float = 1.0
