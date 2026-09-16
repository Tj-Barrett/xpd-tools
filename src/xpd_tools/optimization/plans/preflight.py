"""Per-suggestion checks run before any device message is emitted."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from ..helpers.beamline import XrayUvvisPlanContext


def _preflight(
    context: XrayUvvisPlanContext,
    suggestions: Sequence[Mapping[str, Any]],
    *,
    plan_name: str,
) -> tuple[float, ...]:
    """Validate one complete suggestion before emitting any device message."""
    if len(suggestions) != 1 or not suggestions[0]:
        raise ValueError(f"{plan_name} requires exactly one nonempty suggestion")

    suggestion = suggestions[0]
    configured_dofs = tuple(source.dof for source in context.sources)
    configured_set = set(configured_dofs)
    supplied_dofs = {name for name in suggestion if name.startswith("infusion_rate_")}
    if supplied_dofs != configured_set:
        raise ValueError(
            "suggestion infusion DOFs must match sources: "
            f"expected {sorted(configured_set)}, got {sorted(supplied_dofs)}"
        )

    unknown_fields = sorted(set(suggestion) - configured_set - {"_id"})
    if unknown_fields:
        raise ValueError(f"suggestion has unknown fields: {', '.join(unknown_fields)}")

    rates = tuple(float(suggestion[dof]) for dof in configured_dofs)
    if any(not np.isfinite(rate) or rate < 0 for rate in rates):
        raise ValueError("infusion rates must be finite and non-negative")
    if not any(rate > 0 for rate in rates):
        raise ValueError("at least one infusion rate must be greater than zero")
    return rates
