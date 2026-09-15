
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
    simulated: bool = False
    minimize: bool = False


def _create_phase(phase: Phase, *, metric_prefix: str) -> Objective:
    """Build the Ax objective for one phase's PDF correlation metric.

    `metric_prefix` must match the evaluator's actual output key
    (`"corr_"` for raw mode, `"pdf_fit_corr_"` for fit mode) -- the
    objective name has to match a real evaluation outcome exactly.
    """
    return Objective(
        name=f"{metric_prefix}{phase.name}",
        minimize=phase.minimize,
    )


def _phases_to_pdf_schema(phases: list[Phase]) -> dict[str, Any]:
    """Build a version-1 PDF reference schema dict from configured phases.

    Matches the JSON schema `helpers.pdf._load_pdf_references` parses.
    `gr`/`cif` are resolved to absolute paths so the result stays valid
    regardless of where it ends up written (e.g. a temp file elsewhere on
    disk) -- `constraint_profile`/`scoring_function` are omitted so
    `_load_pdf_references` applies its own defaults.
    """
    return {
        "schema_version": 1,
        "phases": [
            {
                "name": phase.name,
                "gr_path": str(Path(phase.gr).expanduser().resolve()),
                "cif_path": str(Path(phase.cif).expanduser().resolve()),
                "minimize": phase.minimize,
            }
            for phase in phases
        ],
    }


def _write_pdf_references(phases: list[Phase], directory: Path) -> Path:
    """Write `_phases_to_pdf_schema(phases)` as a JSON file inside `directory`.

    The caller owns `directory`'s lifetime (e.g. a `TemporaryDirectory`
    context) -- the file only needs to exist for `_load_pdf_references` to
    parse it once, during evaluator construction.
    """
    path = directory / "pdf_references.json"
    path.write_text(json.dumps(_phases_to_pdf_schema(phases)))
    return path
