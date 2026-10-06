
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from blop.ax import Objective


@dataclass(frozen=True, kw_only=True)
class Phase:
    """Phase structure to score against using PDF."""

    name: str
    gr: str
    cif: str
    minimize: bool = False
    # cnn only: desired fraction (0-1) of this phase. The objective becomes
    # frac_dist_{name} (squared distance to it, minimized), with frac_{name}
    # constrained to target +/- fraction_tolerance.
    target_fraction: float | None = None
    fraction_tolerance: float = 0.05

    def __post_init__(self) -> None:
        if self.fraction_tolerance <= 0:
            raise ValueError(f"phase {self.name!r}: fraction_tolerance must be > 0")
        if self.target_fraction is None:
            return
        if not 0 <= self.target_fraction <= 1:
            raise ValueError(f"phase {self.name!r}: target_fraction must be in [0, 1]")
        if self.minimize:
            raise ValueError(
                f"phase {self.name!r}: target_fraction sets its own direction; "
                "drop minimize=True"
            )


def _create_phase(phase: Phase, *, metric_prefix: str) -> Objective:
    """Build the Ax objective for one phase's PDF metric.

    `metric_prefix` must match the evaluator's actual output key
    (`"corr_"` for raw mode, `"pdf_fit_corr_"` for fit mode, `"frac_"` for
    cnn) -- the objective name has to match a real evaluation outcome exactly.
    A cnn phase with a target minimizes `frac_dist_{name}` instead.
    """
    if metric_prefix == "frac_" and phase.target_fraction is not None:
        return Objective(name=f"frac_dist_{phase.name}", minimize=True)
    return Objective(
        name=f"{metric_prefix}{phase.name}",
        minimize=phase.minimize,
    )


def _phases_to_pdf_schema(
    phases: list[Phase], *, scoring_function: str | None = None
) -> dict[str, Any]:
    """Build a PDF reference schema dict from configured phases.

    Matches the JSON schema `helpers.pdf._load_pdf_references` parses.

    `gr`/`cif` are resolved to absolute paths.
    `scoring_function` is applied uniformly to every phase.
    """
    return {
        "schema_version": 1,
        "phases": [
            {
                "name": phase.name,
                "gr_path": str(Path(phase.gr).expanduser().resolve()),
                "cif_path": str(Path(phase.cif).expanduser().resolve()),
                "minimize": phase.minimize,
                **(
                    {}
                    if scoring_function is None
                    else {"scoring_function": scoring_function}
                ),
                **(
                    {}
                    if phase.target_fraction is None
                    else {"target_fraction": phase.target_fraction}
                ),
            }
            for phase in phases
        ],
    }


def _write_pdf_references(
    phases: list[Phase], directory: Path, *, scoring_function: str | None = None
) -> Path:
    """Write `_phases_to_pdf_schema(phases)` as a JSON file inside `directory`."""
    path = directory / "pdf_references.json"
    path.write_text(
        json.dumps(_phases_to_pdf_schema(phases, scoring_function=scoring_function))
    )
    return path
