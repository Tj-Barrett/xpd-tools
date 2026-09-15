"""X-ray and UV-Vis optimization evaluation."""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import numpy as np

from ..helpers.pdf import (
    _PdfPhaseReference,
    _load_pdf_references,
    _process_pdf,
    _read_pdfstream_data,
)
from ..helpers.qepro import (
    PlqyReference,
    _compute_pl_outcomes,
    _filter_fl_to_good_batches,
    _read_tiled_data,
)


class XrayUvvisEvaluation:
    """Evaluate optical spectra and PDF data for one acquisition run."""

    def __init__(
        self,
        tiled_client: Any,
        sandbox_client: Any,
        pdf_references: str | Path,
        *,
        pdf_mode: Literal["raw", "fit"] = "fit",
        plqy: PlqyReference = PlqyReference(),  # ruff:ignore[function-call-in-default-argument]
        peak_target: float = 660,
        max_retries: int = 10,
        retry_delay: float = 2.0,
    ) -> None:
        if pdf_mode not in {"raw", "fit"}:
            raise ValueError("pdf_mode must be either 'raw' or 'fit'")
        if max_retries < 1:
            raise ValueError("max_retries must be at least one")
        if retry_delay < 0:
            raise ValueError("retry_delay cannot be negative")

        phases = _load_pdf_references(pdf_references)
        if pdf_mode == "fit":
            for phase in phases:
                if phase.cif_path is None:
                    raise ValueError(
                        f"phase {phase.name!r} requires cif_path for PDF mode 'fit'"
                    )
                if not phase.cif_path.is_file():
                    raise ValueError(
                        f"phase {phase.name!r} cif_path is not a file: {phase.cif_path}"
                    )

        self.tiled_client = tiled_client
        self.sandbox_client = sandbox_client
        self._pdf_mode: Literal["raw", "fit"] = pdf_mode
        self._phases = phases
        self._plqy = plqy
        self._peak_target = peak_target
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    @property
    def pdf_mode(self) -> Literal["raw", "fit"]:
        """PDF metrics used as optimization objectives."""
        return self._pdf_mode

    @property
    def phases(self) -> tuple[_PdfPhaseReference, ...]:
        """Validated PDF phase references in configured order."""
        return self._phases

    @property
    def peak_target(self) -> float:
        """Target fluorescence peak wavelength in nanometers."""
        return self._peak_target

    def __call__(
        self,
        uid: Hashable,
        suggestions: Sequence[Mapping[str, Any]],
    ) -> Sequence[Mapping[str, Any]]:
        """Evaluate a run and return finite outcomes for each suggestion."""
        # Single-suggestion restriction: outcomes are computed once per
        # acquisition, so >1 suggestion would silently receive identical
        # values. Revisit if batched suggestions per run are ever needed.
        if len(suggestions) > 1:
            raise RuntimeError(
                f"More than 1 suggestion is not supported, got: {len(suggestions)}"
            )
        fluorescence, absorbance, _metadata, batch_info = _read_tiled_data(
            self.tiled_client,
            uid,
            max_retries=self._max_retries,
            retry_delay=self._retry_delay,
        )
        if batch_info is not None:
            fluorescence = _filter_fl_to_good_batches(fluorescence, batch_info)

        outcomes = _compute_pl_outcomes(
            fluorescence, absorbance, self._plqy, self._peak_target, uid=uid
        )

        pdf_data = _read_pdfstream_data(
            self.sandbox_client,
            uid,
            max_retries=self._max_retries,
            retry_delay=self._retry_delay,
        )
        pdf_metrics = _process_pdf(self._phases, pdf_data, self._pdf_mode, uid=uid)
        for name, value in pdf_metrics.items():
            if not np.isfinite(value):
                raise ValueError(f"PDF correlation {name!r} is not finite")

        outcomes.update(pdf_metrics)
        return [{**outcomes, "_id": suggestion["_id"]} for suggestion in suggestions]
