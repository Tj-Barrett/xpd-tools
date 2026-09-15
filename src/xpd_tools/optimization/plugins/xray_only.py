"""X-ray-only optimization evaluation: PDF/G(r) data, no optical spectra."""

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


class XrayEvaluation:
    """Evaluate PDF/G(r) data for one acquisition run."""

    def __init__(
        self,
        sandbox_client: Any,
        pdf_references: str | Path,
        *,
        pdf_mode: Literal["raw", "fit"] = "fit",
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

        self.sandbox_client = sandbox_client
        self._pdf_mode: Literal["raw", "fit"] = pdf_mode
        self._phases = phases
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

    def __call__(
        self,
        uid: Hashable,
        suggestions: Sequence[Mapping[str, Any]],
    ) -> Sequence[Mapping[str, Any]]:
        """Evaluate a run's PDF data and return finite outcomes per suggestion."""
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

        return [
            {**pdf_metrics, "_id": suggestion["_id"]} for suggestion in suggestions
        ]
