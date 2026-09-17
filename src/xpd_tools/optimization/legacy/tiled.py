"""Simulated Tiled catalogs for `BuildAgent.build_local()`.

`build_local()`'s evaluator still needs a `tiled_client` (raw UV-Vis data)
and/or `sandbox_client` (pdfstream-reduced PDF data) -- `_build_evaluator`
is shared with the Queue Server path and always builds real ones by
default. Real infrastructure has no way to produce pdfstream-reduced data
for a *simulated* acquisition anyway (there's no real pdfstream service
reducing a fake detector's data), so testing `build_local()` fully offline
means faking both catalogs instead.

`FakeTiledStream`/`FakeTiledRun`/`FakeTiledCatalog` match exactly the
`tiled_client[uid][stream_name].read()` / `sandbox_client.search(...)
.keys().last()` access patterns `helpers/pdf.py` and `helpers/qepro.py`
actually use -- see `helpers/common.py`'s `_read_stream_dataset` and
`helpers/pdf.py`'s `_read_pdfstream_data`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import numpy as np

from ..helpers.pdf import _load_reference_gr

if TYPE_CHECKING:
    from bluesky.run_engine import RunEngine

    from ..helpers.phases import Phase


class FakeTiledStream:
    """One data stream: `{field: array}`, read back as `.values` per field."""

    def __init__(self, data: Mapping[str, Any], *, failures: int = 0) -> None:
        self.data = {
            name: SimpleNamespace(values=np.asarray(value))
            for name, value in data.items()
        }
        self.failures = failures
        self.read_count = 0

    def read(self) -> dict[str, SimpleNamespace]:
        self.read_count += 1
        if self.read_count <= self.failures:
            raise OSError("stream is not ready")
        return self.data


class FakeTiledRun:
    """One run: a `run["stream_name"]` map plus `run.metadata["start"]`."""

    def __init__(
        self,
        streams: Mapping[str, FakeTiledStream],
        *,
        metadata: Mapping[str, Any] | None = None,
        use_good_bad: bool = False,
    ) -> None:
        self.streams = dict(streams)
        start = dict(metadata or {})
        start.setdefault("use_good_bad", use_good_bad)
        self.metadata = {"start": start}

    def __getitem__(self, name: str) -> FakeTiledStream:
        """`run["stream_name"]`."""
        return self.streams[name]


class FakeTiledCatalog:
    """A `client[uid]` catalog, plus the `.search(...).keys().last()` chain.

    `_read_pdfstream_data` uses that chain -- `search` ignores the actual
    query (it doesn't filter on `original_run_uid`) and just returns every
    run inserted so far; `last()` returns the most recently inserted one.
    Fine for the sequential, one-trial-at-a-time way `build_local()` runs
    a campaign; not a general Tiled query implementation.
    """

    def __init__(
        self,
        runs: Mapping[str, FakeTiledRun] | None = None,
        *,
        search_failures: int = 0,
    ) -> None:
        self.runs: dict[str, FakeTiledRun] = dict(runs or {})
        self.search_failures = search_failures
        self.search_count = 0

    def __getitem__(self, uid: Any) -> FakeTiledRun:
        """`client[uid]`."""
        return self.runs[str(uid)]

    def insert(self, uid: Any, run: FakeTiledRun) -> None:
        self.runs[str(uid)] = run

    def search(self, query: Any) -> FakeTiledCatalog:
        del query
        self.search_count += 1
        if self.search_count <= self.search_failures:
            raise OSError("catalog is not ready")
        return self

    def keys(self) -> FakeTiledCatalog:
        return self

    def last(self) -> str:
        return next(reversed(self.runs))


def run_from_documents(
    documents: Sequence[tuple[str, Mapping[str, Any]]], uid: str
) -> FakeTiledRun:
    """Reconstruct a `FakeTiledRun` for one run from a flat document list."""
    start = next(
        doc for name, doc in documents if name == "start" and doc["uid"] == uid
    )
    descriptors = {
        doc["uid"]: doc["name"]
        for name, doc in documents
        if name == "descriptor" and doc["run_start"] == uid
    }
    events: dict[str, list[Mapping[str, Any]]] = {
        stream_name: [] for stream_name in descriptors.values()
    }
    for name, doc in documents:
        if name == "event" and doc["descriptor"] in descriptors:
            events[descriptors[doc["descriptor"]]].append(doc["data"])
    streams = {
        stream_name: FakeTiledStream(
            {
                field: np.asarray([event[field] for event in stream_events])
                for field in stream_events[0]
            }
        )
        for stream_name, stream_events in events.items()
        if stream_events
    }
    return FakeTiledRun(streams, metadata=start)


def build_fake_tiled_clients(
    RE: RunEngine,
    *,
    phases: Sequence[Phase] = (),
) -> tuple[FakeTiledCatalog, FakeTiledCatalog]:
    """Build and subscribe a fake `(tiled_client, sandbox_client)` pair.

    Subscribes to `RE` so both catalogs fill in as a real campaign runs:
    every completed run is reconstructed from its own real documents into
    `tiled_client` (this needs no synthesis -- the simulated qepro/detector
    genuinely produce real absorbance/fluorescence/scattering events).

    There's no real pdfstream service to reduce a "scattering" stream into
    G(r) for a simulated run, so `sandbox_client` gets a synthesized
    result instead: the first "wanted" (`minimize=False`) phase's own real
    reference `.gr` data, echoed back as the "measurement" -- not
    physically meaningful, but a real, deterministic, correctly-shaped
    G(r) that exercises the full scoring pipeline (expect ~perfect
    correlation against that one phase). No-op (nothing inserted) for runs
    with no "scattering" stream, or if `phases` is empty.
    """
    tiled_client = FakeTiledCatalog()
    sandbox_client = FakeTiledCatalog()
    documents: list[tuple[str, Mapping[str, Any]]] = []

    wanted_phase = next((phase for phase in phases if not phase.minimize), None)

    def _on_document(name: str, doc: Mapping[str, Any]) -> None:
        documents.append((name, doc))
        if name != "stop":
            return
        uid = doc["run_start"]
        run = run_from_documents(documents, uid)
        tiled_client.insert(uid, run)
        if "scattering" in run.streams and wanted_phase is not None:
            gr_r, gr_g = _load_reference_gr(wanted_phase.gr)
            sandbox_client.insert(
                uid,
                FakeTiledRun(
                    {"scattering": FakeTiledStream({"gr_r": gr_r, "gr_G": gr_g})},
                    metadata={"original_run_uid": uid},
                ),
            )

    RE.subscribe(_on_document)
    return tiled_client, sandbox_client
