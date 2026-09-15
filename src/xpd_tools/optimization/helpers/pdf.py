"""PDF (G(r)) evaluation: schema, config loading, and pdffit2 scoring."""

from __future__ import annotations

import json
import re
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from ..pdffit import fit_pdf_correlations

import numpy as np
from tiled.queries import Eq

from ..analysis import pearson_profile
from ._common import _TiledAccessError, _retry_access

_PHASE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_ROOT_FIELDS = frozenset({"schema_version", "phases"})
_PHASE_FIELDS = frozenset(
    {"name", "gr_path", "cif_path", "minimize", "constraint_profile"}
)
_PHASE_REQUIRED_FIELDS = frozenset({"name", "gr_path", "minimize"})


@dataclass(frozen=True)
class _PdfPhaseReference:
    """Validated external PDF inputs for one phase."""

    name: str
    gr_path: Path
    minimize: bool
    cif_path: Path | None = None
    constraint_profile: Literal["none", "cs_pb_br3"] = "none"


def _require_exact_fields(
    value: dict[str, Any],
    allowed: frozenset[str],
    required: frozenset[str],
    field: str,
) -> None:
    unknown = sorted(value.keys() - allowed)
    if unknown:
        raise ValueError(f"{field} has unknown fields: {', '.join(unknown)}")
    missing = sorted(required - value.keys())
    if missing:
        raise ValueError(f"{field} is missing fields: {', '.join(missing)}")


def _reference_path(
    value: object,
    config_directory: Path,
    field: str,
    *,
    require_file: bool,
) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty path string")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = config_directory / candidate
    if require_file and not candidate.is_file():
        raise ValueError(f"{field} is not a file: {candidate}")
    return candidate


def _load_pdf_references(path: str | Path) -> tuple[_PdfPhaseReference, ...]:
    """Load and validate version-1 external PDF phase references."""
    config_path = Path(path).expanduser().resolve()
    try:
        document = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {config_path}: {exc.msg}") from exc

    if not isinstance(document, dict):
        raise ValueError(f"configuration root must be an object: {config_path}")
    _require_exact_fields(document, _ROOT_FIELDS, _ROOT_FIELDS, "configuration")
    if type(document["schema_version"]) is not int:
        raise ValueError("schema_version must be the integer 1")
    if document["schema_version"] != 1:
        raise ValueError(
            f"schema_version is unsupported: {document['schema_version']!r}"
        )

    raw_phases = document["phases"]
    if not isinstance(raw_phases, list) or not raw_phases:
        raise ValueError("phases must be a non-empty list")

    names: set[str] = set()
    phases: list[_PdfPhaseReference] = []
    for index, raw_phase in enumerate(raw_phases):
        field = f"phases[{index}]"
        if not isinstance(raw_phase, dict):
            raise ValueError(f"{field} must be an object")
        _require_exact_fields(
            raw_phase,
            _PHASE_FIELDS,
            _PHASE_REQUIRED_FIELDS,
            field,
        )

        name = raw_phase["name"]
        if not isinstance(name, str):
            raise ValueError(f"{field}.name must be a string")
        if not _PHASE_NAME.fullmatch(name):
            raise ValueError(
                f"{field}.name must match {_PHASE_NAME.pattern!r}: {name!r}"
            )
        if name in names:
            raise ValueError(f"{field}.name is duplicated: {name!r}")
        names.add(name)

        minimize = raw_phase["minimize"]
        if not isinstance(minimize, bool):
            raise ValueError(f"{field}.minimize must be a boolean")
        constraint_profile = raw_phase.get("constraint_profile", "none")
        if constraint_profile not in {"none", "cs_pb_br3"}:
            raise ValueError(
                f"{field}.constraint_profile is unsupported: {constraint_profile!r}"
            )

        gr_path = _reference_path(
            raw_phase["gr_path"],
            config_path.parent,
            f"{field}.gr_path",
            require_file=True,
        )
        cif_value = raw_phase.get("cif_path")
        cif_path = (
            None
            if cif_value is None
            else _reference_path(
                cif_value,
                config_path.parent,
                f"{field}.cif_path",
                require_file=False,
            )
        )
        phases.append(
            _PdfPhaseReference(
                name=name,
                gr_path=gr_path,
                minimize=minimize,
                cif_path=cif_path,
                constraint_profile=cast(
                    Literal["none", "cs_pb_br3"], constraint_profile
                ),
            )
        )
    return tuple(phases)

def _read_pdfstream_data(
    sandbox_client: Any,
    uid: Hashable,
    *,
    max_retries: int,
    retry_delay: float,
) -> dict[str, np.ndarray]:
    """Read the correlated pdfstream G(r) stream with bounded retries."""

    def read() -> dict[str, np.ndarray]:
        try:
            matches = sandbox_client.search(Eq("start.original_run_uid", uid))
            key = matches.keys().last()
            dataset = matches[key]["scattering"].read()
        except Exception as exc:
            raise _TiledAccessError(
                f"failed to read pdfstream data for uid={uid!r}"
            ) from exc
        missing = [field for field in ("gr_r", "gr_G") if field not in dataset]
        if missing:
            raise ValueError(
                "scattering stream is missing fields: " + ", ".join(missing)
            )
        return {
            field: np.asarray(dataset[field].values).squeeze()
            for field in ("gr_r", "gr_G")
        }

    return _retry_access(
        uid,
        "pdfstream scattering data",
        read,
        lambda: ("scattering stream",),
        max_retries=max_retries,
        retry_delay=retry_delay,
    )


def _raw_pdf_correlations(
    phases: Sequence[_PdfPhaseReference], pdf_data: Mapping[str, np.ndarray]
) -> dict[str, float]:
    results: dict[str, float] = {}
    for phase in phases:
        reference_r, reference_g = np.loadtxt(
            phase.gr_path,
            usecols=(0, 1),
            unpack=True,
        )
        results[f"corr_{phase.name}"] = pearson_profile(
            pdf_data["gr_r"],
            pdf_data["gr_G"],
            reference_r,
            reference_g,
        )
    return results


def _process_pdf(
    phases: Sequence[_PdfPhaseReference],
    pdf_data: Mapping[str, np.ndarray],
    pdf_mode: Literal["raw", "fit"],
    *,
    uid: Hashable,
) -> dict[str, float]:
    results = _raw_pdf_correlations(phases, pdf_data)
    if pdf_mode == "raw":
        return results
    try:
        results.update(fit_pdf_correlations(phases, pdf_data))
    except Exception as exc:
        raise RuntimeError(f"PDF fitting failed for uid={uid!r}") from exc
    return results
