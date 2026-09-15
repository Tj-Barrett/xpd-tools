"""Blop optimizer and Queue Server integration."""

import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from bluesky.callbacks.zmq import RemoteDispatcher
from bluesky_queueserver_api.http import REManagerAPI
from tiled.client import from_profile, from_uri

from ax.api.protocols import IMetric
from blop.ax import Objective, OutcomeConstraint, RangeDOF
from blop.ax.queueserver_agent import QueueserverAgent
from .cli import DEFAULT_SANDBOX_URI, DEFAULT_TILED_PROFILE, SANDBOX_CATALOG
from .plans import DilutionStage, FlowSource, WashCycle
from .helpers.beamline import XraySettings
from .helpers.dofs import Pump, _create_pump
from .helpers.phases import Phase, _create_phase, _write_pdf_references
from .helpers.qepro import PlqyReference, QualityPolicy, SpectraFitSettings
from . import plugins

_EVALUATORS = {
    "uvvis": plugins.UvvisEvaluation,
    "xray": plugins.XrayEvaluation,
    "xray-uvvis": plugins.XrayUvvisEvaluation,
}


def _load_historical_data(
    path: str | Path,
    dof_names: Sequence[str],
    objective_names: Sequence[str],
    *,
    optional_names: Sequence[str] = (),
) -> list[dict[str, float]]:
    """Load historical observations from a CSV for seeding the optimizer.

    Expects columns named exactly like the configured DOFs/objectives (e.g.
    an export from `ax_client.summarize()`). `optional_names` (e.g. "Peak",
    an outcome-constraint metric rather than a formal objective) are
    included when present but don't cause a missing-column error on their
    own -- extra columns beyond all of these are ignored.
    """
    frame = pd.read_csv(path)
    required = [*dof_names, *objective_names]
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise ValueError(f"{path}: historical data is missing columns: {', '.join(missing)}")
    columns = required + [name for name in optional_names if name in frame.columns]
    return frame[columns].astype(float).to_dict(orient="records")


class BuildAgent:
    def __init__(self,
                # Queue Server
                queue_server: bool = True,
                # HTTP Client
                http_server_uri: str | None = None,
                http_api_key: str | None = None,
                # ZMQ
                zmq_consumer_address: str | None = None,
                # Tiled (tiled_uri takes precedence over tiled_profile when set)
                tiled_profile: str | None = None,
                tiled_uri: str | None = None,
                # Tiled sandbox catalog where pdfstream writes analysis results
                sandbox_uri: str = DEFAULT_SANDBOX_URI,
                # PDF Fit
                use_pdf_fit: bool = False,
                # Evaluation Method
                evaluation_method: str | None = None,
                # Agent Historical Data
                agent_data_path: str | None = None,
                # Optimizer checkpoint (distinct from agent_data_path: this is
                # blop's own state file, not historical observations to ingest)
                checkpoint_path: str | Path | None = None,
        ) -> None:
        # Queue Server
        self.queue_server = queue_server
        # HTTP Client
        self.http_server_uri = http_server_uri
        self.http_api_key = http_api_key
        # ZMQ
        self.zmq_consumer_address = zmq_consumer_address
        # Tiled
        self.tiled_profile = tiled_profile
        self.tiled_uri = tiled_uri
        self.sandbox_uri = sandbox_uri
        # Optimizer checkpoint
        self.checkpoint_path = checkpoint_path
        # Historical data CSV to seed the optimizer with (distinct from
        # checkpoint_path -- see above)
        self.agent_data_path = agent_data_path

        # Evaluation Function
        assert evaluation_method in [
            "uvvis",
            "xray",
            "xray-uvvis"
        ], "Evaluation method must be 'uvvis', 'xray', or 'xray-uvvis'."
        self.evaluation_method = evaluation_method

        # Use PDFFIT?
        self.use_pdf_fit = use_pdf_fit
        # if self.use_pdf_fit:
        #     assert that pdffit2 can be imported and used so it doesnt fail at runtime

        # DOFs and flow sources: either may be configured first; see
        # _check_dof_source_alignment for the cross-check applied once both exist.
        self.dofs: list[RangeDOF] | None = None
        # Retained alongside self.dofs -- RangeDOF drops Pump.id (the
        # hardware address), which a config round-trip needs back.
        self.pumps: list[Pump] | None = None
        self.sources: list[FlowSource] | None = None
        self.dilutions: list[DilutionStage] | None = None
        self.wash_cycles: list[WashCycle] | None = None
        self.phases: list[Phase] | None = None
        self.plqy: PlqyReference | None = None
        self.fit_settings: SpectraFitSettings | None = None
        self.xray_settings: XraySettings | None = None
        self.screening: Literal["unscreened", "screen_only", "screen_and_record"] | None = None
        self.quality_policy: QualityPolicy | None = None
        self.xray_max_retries: int | None = None
        self.xray_retry_delay: float | None = None
        self.min_radius: float | None = None
        self.max_radius: float | None = None
        self.objective_function: str | None = None
        self.peak_target: float | None = None
        self.peak_tolerance: float | None = None
        self.uvvis_max_retries: int | None = None
        self.uvvis_retry_delay: float | None = None
        self.metadata: dict[str, Any] | None = None
        self.metadata_string: str | None = None

        # Objectives
        self.objectives = []
        if evaluation_method == "uvvis" or evaluation_method == "xray-uvvis":
            self.objectives = [
                Objective(name="log_FWHM", minimize=True),
                Objective(name="log_PLQY", minimize=False),
                Objective(name="peak_distance", minimize=True),
            ]

    def _check_dof_source_alignment(self) -> None:
        """Cross-check configured DOFs against flow-source DOF names.

        No-op until both `set_dofs` and `experiment` have been called at
        least once; either may come first.
        """
        if self.dofs is None or self.sources is None:
            return
        dof_names = {dof.name for dof in self.dofs}
        source_names = {source.dof for source in self.sources}
        if dof_names != source_names:
            raise ValueError(
                "DOFs and flow sources must reference the same names: "
                f"sources missing a DOF: {sorted(source_names - dof_names)}; "
                f"DOFs missing a source: {sorted(dof_names - source_names)}"
            )

    def set_dofs(self,
        pumps: list[Pump]) -> None:
        self.pumps = pumps
        self.dofs = [_create_pump(pump) for pump in pumps]
        self._check_dof_source_alignment()

    def set_xray_objectives(self,
        # Measurement
        max_retries: int = 10,
        retry_delay: float = 2.0,
        # Configuration
        exposure: float = 600.0,
        frame_acq_time: float = 1.5,
        no_dark: bool = False,
        stream_name: str = "scattering",
        # Screening: whether/how a UV-Vis fluorescence quality gate runs
        # during X-ray acquisition.
        #   "unscreened"        -- no UV-Vis hardware touched at all.
        #   "screen_only"       -- gate runs (accept/reject before spending
        #                          X-ray beamtime), but the UV-Vis
        #                          measurement isn't reported as evaluation
        #                          data (PDF-only objectives).
        #   "screen_and_record" -- gate runs and its data is also used for
        #                          evaluation (the "xray-uvvis" case).
        screening: Literal["unscreened", "screen_only", "screen_and_record"] = "screen_only",
        use_good_bad: bool = True,
        good_target: int = 2,
        max_bad: int = 3,
        num_abs: int = 16,
        num_flu: int = 16,
        # Phase Fitting
        objective_function: str = "pearson",
        # PDF correlation masking window (radial distance, Angstroms) --
        # how much of each phase's G(r) contributes to its correlation
        # score. See analysis.pdf_profile's r_min/r_max.
        min_radius: float = 2.0,
        max_radius: float = 20.0,
        phases: list[Phase] = []
    ) -> None:

        self.xray_max_retries = max_retries
        self.xray_retry_delay = retry_delay
        self.min_radius = min_radius
        self.max_radius = max_radius

        # Detector acquisition settings
        self.xray_settings = XraySettings(
            exposure=exposure,
            frame_acq_time=frame_acq_time,
            no_dark=no_dark,
            stream_name=stream_name,
        )

        # Screening / fluorescence quality-gating and shot-count policy.
        # Only "unscreened" means no UV-Vis hardware is involved; the other
        # two both need a real QualityPolicy for the acquisition-side gate,
        # they just differ in whether the resulting data is later used for
        # evaluation (a plans.py/evaluation_method concern, not this one).
        self.screening = screening
        self.quality_policy = (
            None
            if screening == "unscreened"
            else QualityPolicy(
                enabled=use_good_bad,
                good_batches=good_target,
                max_bad_batches=max_bad,
                absorbance_shots=num_abs,
                fluorescence_shots=num_flu,
            )
        )

        if objective_function in [
            "pearson",
            "nn_matrix",
            "cnn",
            "ensemble",
            "weighted_profile_r",
            "cross_correlation"
        ]:
            self.objective_function = objective_function
        else:
            raise ValueError(f"Invalid objective function: {objective_function}")
            exit()

        # Handle phass
        self.phases = phases
        metric_prefix = "pdf_fit_corr_" if self.use_pdf_fit else "corr_"
        _phase_objectives = [
            _create_phase(phase, metric_prefix=metric_prefix) for phase in phases
        ]

        self.objectives = [
            *self.objectives,
            *_phase_objectives,
        ]

    def set_uvvis_objectives(self,
        # Objective Target
        peak_target: float = 450.0,
        peak_tolerance: float = 5.0,
        max_retries: int = 10,
        retry_delay: float = 2.0,
        # Screening, data selection, and fitting windows
        fit_settings: SpectraFitSettings = SpectraFitSettings(),  # ruff:ignore[function-call-in-default-argument]
        # Calibration Standard Reference
        plqy: PlqyReference = PlqyReference(),  # ruff:ignore[function-call-in-default-argument]
    ) -> None:

        # Setting Objective Targets
        self.peak_target = peak_target
        self.peak_tolerance = peak_tolerance
        self.uvvis_max_retries = max_retries
        self.uvvis_retry_delay = retry_delay

        # Screening, data selection, and fitting windows
        self.fit_settings = fit_settings

        # Calibration Standard Reference
        self.plqy = plqy

        # Objectives are handled upon starting to make sure they are in the same positin
        # as the hardcoded version of the software. We can readdress this in the future
        # but it will not be backwards compatible.

    def set_metadata(self, metadata: dict) -> None:
        self.metadata = metadata
        # Place holder for storing metadata as a string
        # We should probably grab UUIDs and version info, as well as run info
        self.metadata_string = ""
        for key, value in metadata.items():
            self.metadata_string += f"{key}: {value}\n"

    def experiment(
        self,
        sources: list[FlowSource] | None = None,
        dilutions: list[DilutionStage] | None = None,
        wash_cycles: list[WashCycle] | None = None,
    ) -> None:
        self.sources = sources
        self.dilutions = dilutions
        self.wash_cycles = wash_cycles
        self._check_dof_source_alignment()

    def _tiled_client(self) -> Any:
        """Resolve the raw-data Tiled client; `tiled_uri` wins when set."""
        if self.tiled_uri:
            return from_uri(self.tiled_uri)
        return from_profile(self.tiled_profile or DEFAULT_TILED_PROFILE)

    def _sandbox_client(self) -> Any:
        """Resolve the pdfstream sandbox catalog client."""
        return from_uri(self.sandbox_uri)[SANDBOX_CATALOG]

    def _peak_outcome_constraints(self) -> tuple[OutcomeConstraint, ...]:
        """Constrain the fitted PL peak to `peak_target` +/- `peak_tolerance`.

        Only meaningful for evaluation methods that produce a "Peak" metric
        (`"uvvis"`, `"xray-uvvis"`); the caller is responsible for only
        calling this when that's the case.
        """
        peak = IMetric(name="Peak")
        return (
            OutcomeConstraint(f"p >= {self.peak_target - self.peak_tolerance:g}", p=peak),
            OutcomeConstraint(f"p <= {self.peak_target + self.peak_tolerance:g}", p=peak),
        )

    def _acquisition_plan_name(self) -> str:
        """Select the registered acquisition-plan name for the current config.

        BuildAgent can only choose a *plan name string* here, not build the
        actual plan callable: `create_xray_plan`/`create_uvvis_plan`/
        `create_xray_uvvis_plan` all need live ophyd device objects that
        exist only in the queue server's worker environment, never in this
        client-side process. The queue server resolves the name to an
        already-registered plan at run time.
        """
        if self.evaluation_method == "uvvis":
            return "uvvis_acquire"
        if self.evaluation_method == "xray-uvvis":
            return "xray_uvvis_acquire"
        # evaluation_method == "xray": the plan depends on self.screening.
        if self.screening == "unscreened":
            return "xray_acquire"
        if self.screening == "screen_only":
            raise NotImplementedError(
                "screening='screen_only' has no matching acquisition plan yet -- "
                "only 'unscreened' (xray_acquire) and 'screen_and_record' "
                "(xray_uvvis_acquire) are registered today"
            )
        return "xray_uvvis_acquire"  # screening == "screen_and_record"

    def build(self, ) -> None:
        if not self.queue_server:
            raise NotImplementedError(
                "queue_server=False (direct blop.ax.agent.Agent, no queueserver) "
                "is not yet implemented"
            )
        if self.dofs is None:
            raise ValueError("set_dofs(...) must be called before build()")
        if self.sources is None:
            raise ValueError("experiment(...) must be called before build()")
        self._check_dof_source_alignment()

        needs_pdf = self.evaluation_method in ("xray", "xray-uvvis")
        if needs_pdf and not self.phases:
            raise ValueError(
                f"evaluation_method={self.evaluation_method!r} requires phases; "
                "call set_xray_objectives(phases=...) first"
            )
        needs_plqy = self.evaluation_method in ("uvvis", "xray-uvvis")
        if needs_plqy and self.plqy is None:
            raise ValueError(
                f"evaluation_method={self.evaluation_method!r} requires "
                "set_uvvis_objectives(...) to be called before build()"
            )
        acquisition_plan = self._acquisition_plan_name()

        with tempfile.TemporaryDirectory() as directory:
            evaluator_kwargs: dict[str, Any] = {}
            if needs_pdf:
                evaluator_kwargs["sandbox_client"] = self._sandbox_client()
                evaluator_kwargs["pdf_references"] = _write_pdf_references(
                    self.phases, Path(directory)
                )
                evaluator_kwargs["pdf_mode"] = "fit" if self.use_pdf_fit else "raw"
                evaluator_kwargs["r_min"] = self.min_radius
                evaluator_kwargs["r_max"] = self.max_radius
            if self.evaluation_method == "uvvis":
                evaluator_kwargs["tiled_client"] = self._tiled_client()
                evaluator_kwargs["plqy"] = self.plqy
                evaluator_kwargs["peak_target"] = self.peak_target
                evaluator_kwargs["max_retries"] = self.uvvis_max_retries
                evaluator_kwargs["retry_delay"] = self.uvvis_retry_delay
                evaluator_kwargs["fit_settings"] = self.fit_settings
            elif self.evaluation_method == "xray":
                evaluator_kwargs["max_retries"] = self.xray_max_retries
                evaluator_kwargs["retry_delay"] = self.xray_retry_delay
            elif self.evaluation_method == "xray-uvvis":
                # X-ray and UV-Vis are separate hardware with independent
                # retry policies -- kept as two distinct pairs rather than
                # sharing one, even though the reference implementation this
                # was ported from used a single shared cadence for both.
                evaluator_kwargs["tiled_client"] = self._tiled_client()
                evaluator_kwargs["plqy"] = self.plqy
                evaluator_kwargs["peak_target"] = self.peak_target
                evaluator_kwargs["uvvis_max_retries"] = self.uvvis_max_retries
                evaluator_kwargs["uvvis_retry_delay"] = self.uvvis_retry_delay
                evaluator_kwargs["xray_max_retries"] = self.xray_max_retries
                evaluator_kwargs["xray_retry_delay"] = self.xray_retry_delay
                evaluator_kwargs["fit_settings"] = self.fit_settings

            _evaluator = _EVALUATORS[self.evaluation_method](**evaluator_kwargs)

        re_manager_api = REManagerAPI(http_server_uri=self.http_server_uri)
        if self.http_api_key:
            re_manager_api.set_authorization_key(api_key=self.http_api_key)
        document_dispatcher = RemoteDispatcher(self.zmq_consumer_address)

        agent = QueueserverAgent(
            re_manager_api,
            document_dispatcher,
            sensors=(),
            dofs=self.dofs,
            objectives=self.objectives,
            evaluation_function=_evaluator,
            acquisition_plan=acquisition_plan,
            outcome_constraints=(
                self._peak_outcome_constraints() if needs_plqy else ()
            ),
            checkpoint_path=(
                None if self.checkpoint_path is None else str(self.checkpoint_path)
            ),
        )

        if self.agent_data_path is not None:
            historical = _load_historical_data(
                self.agent_data_path,
                [dof.name for dof in self.dofs],
                [objective.name for objective in self.objectives],
                optional_names=("Peak",) if needs_plqy else (),
            )
            if historical:
                agent.ingest(historical)

        return agent

    def to_config(self) -> dict[str, Any]:
        """Compile the current configuration into a JSON-able dict.

        Grouped by concern (connection, DOFs, experiment hardware, X-ray,
        UV-Vis) rather than mirroring internal attribute names one-to-one --
        a future config parser rebuilds each group's real objects (`Pump`,
        `FlowSource`, `XraySettings`, ...) from its own dict, however suits
        that group, rather than this method trying to reverse-engineer the
        setter methods' historical keyword-argument names.

        `http_api_key` is deliberately never included -- it's a credential,
        not configuration, and shouldn't round-trip through a saved file.
        """
        return {
            "connection": {
                "queue_server": self.queue_server,
                "http_server_uri": self.http_server_uri,
                "zmq_consumer_address": self.zmq_consumer_address,
                "tiled_profile": self.tiled_profile,
                "tiled_uri": self.tiled_uri,
                "sandbox_uri": self.sandbox_uri,
            },
            "evaluation_method": self.evaluation_method,
            "use_pdf_fit": self.use_pdf_fit,
            "agent_data_path": self.agent_data_path,
            "checkpoint_path": (
                None if self.checkpoint_path is None else str(self.checkpoint_path)
            ),
            "metadata": self.metadata,
            "pumps": (
                None if self.pumps is None else [asdict(pump) for pump in self.pumps]
            ),
            "experiment": {
                "sources": (
                    None
                    if self.sources is None
                    else [asdict(source) for source in self.sources]
                ),
                "dilutions": (
                    None
                    if self.dilutions is None
                    else [asdict(stage) for stage in self.dilutions]
                ),
                "wash_cycles": (
                    None
                    if self.wash_cycles is None
                    else [asdict(cycle) for cycle in self.wash_cycles]
                ),
            },
            "xray": {
                "max_retries": self.xray_max_retries,
                "retry_delay": self.xray_retry_delay,
                "settings": (
                    None if self.xray_settings is None else asdict(self.xray_settings)
                ),
                "screening": self.screening,
                "quality_policy": (
                    None
                    if self.quality_policy is None
                    else asdict(self.quality_policy)
                ),
                "objective_function": self.objective_function,
                "min_radius": self.min_radius,
                "max_radius": self.max_radius,
                "phases": (
                    None
                    if self.phases is None
                    else [asdict(phase) for phase in self.phases]
                ),
            },
            "uvvis": {
                "peak_target": self.peak_target,
                "peak_tolerance": self.peak_tolerance,
                "max_retries": self.uvvis_max_retries,
                "retry_delay": self.uvvis_retry_delay,
                "fit_settings": (
                    None if self.fit_settings is None else asdict(self.fit_settings)
                ),
                "plqy": None if self.plqy is None else asdict(self.plqy),
            },
        }

    @classmethod
    def from_config(
        cls, config: Mapping[str, Any], *, http_api_key: str | None = None
    ) -> "BuildAgent":
        """Rebuild a `BuildAgent` from a `to_config()`-shaped dict.

        Replays the same setter calls a notebook would make, reconstructing
        each group's real objects (`Pump`, `FlowSource`, `Phase`, ...) from
        its own dict -- a group is only replayed if the corresponding
        setter was actually called when the config was produced (detected
        by its always-set field being non-`None`), so an agent that never
        configured e.g. UV-Vis round-trips back to the same unconfigured
        state, not a spuriously-defaulted one.

        `http_api_key` is never read from `config` (see `to_config`) --
        pass it here directly (e.g. from an environment variable) if the
        rebuilt agent needs one.
        """
        connection = config["connection"]
        agent = cls(
            queue_server=connection["queue_server"],
            http_server_uri=connection["http_server_uri"],
            http_api_key=http_api_key,
            zmq_consumer_address=connection["zmq_consumer_address"],
            tiled_profile=connection["tiled_profile"],
            tiled_uri=connection["tiled_uri"],
            sandbox_uri=connection["sandbox_uri"],
            use_pdf_fit=config["use_pdf_fit"],
            evaluation_method=config["evaluation_method"],
            agent_data_path=config["agent_data_path"],
            checkpoint_path=config["checkpoint_path"],
        )

        if config["metadata"] is not None:
            agent.set_metadata(config["metadata"])

        if config["pumps"] is not None:
            agent.set_dofs(
                [
                    Pump(
                        name=pump["name"],
                        id=pump["id"],
                        bounds=tuple(pump["bounds"]),
                        parameter_type=pump["parameter_type"],
                    )
                    for pump in config["pumps"]
                ]
            )

        experiment = config["experiment"]
        agent.experiment(
            sources=(
                None
                if experiment["sources"] is None
                else [FlowSource(**source) for source in experiment["sources"]]
            ),
            dilutions=(
                None
                if experiment["dilutions"] is None
                else [DilutionStage(**stage) for stage in experiment["dilutions"]]
            ),
            wash_cycles=(
                None
                if experiment["wash_cycles"] is None
                else [WashCycle(**cycle) for cycle in experiment["wash_cycles"]]
            ),
        )

        xray = config["xray"]
        if xray["settings"] is not None:
            quality = xray["quality_policy"] or {}
            agent.set_xray_objectives(
                max_retries=xray["max_retries"],
                retry_delay=xray["retry_delay"],
                exposure=xray["settings"]["exposure"],
                frame_acq_time=xray["settings"]["frame_acq_time"],
                no_dark=xray["settings"]["no_dark"],
                stream_name=xray["settings"]["stream_name"],
                screening=xray["screening"],
                use_good_bad=quality.get("enabled", True),
                good_target=quality.get("good_batches", 2),
                max_bad=quality.get("max_bad_batches", 3),
                num_abs=quality.get("absorbance_shots", 16),
                num_flu=quality.get("fluorescence_shots", 16),
                objective_function=xray["objective_function"],
                min_radius=xray["min_radius"],
                max_radius=xray["max_radius"],
                phases=(
                    []
                    if xray["phases"] is None
                    else [Phase(**phase) for phase in xray["phases"]]
                ),
            )

        uvvis = config["uvvis"]
        if uvvis["fit_settings"] is not None or uvvis["plqy"] is not None:
            agent.set_uvvis_objectives(
                peak_target=uvvis["peak_target"],
                peak_tolerance=uvvis["peak_tolerance"],
                max_retries=uvvis["max_retries"],
                retry_delay=uvvis["retry_delay"],
                fit_settings=(
                    SpectraFitSettings()
                    if uvvis["fit_settings"] is None
                    else SpectraFitSettings(
                        **{
                            # JSON has no tuple type -- these four fields
                            # come back as lists and must be restored.
                            key: (
                                tuple(value)
                                if key
                                in (
                                    "pl_percent_range",
                                    "pl_wavelength_range",
                                    "absorbance_percent_range",
                                    "absorbance_wavelength_range",
                                )
                                else value
                            )
                            for key, value in uvvis["fit_settings"].items()
                        }
                    )
                ),
                plqy=(
                    PlqyReference()
                    if uvvis["plqy"] is None
                    else PlqyReference(**uvvis["plqy"])
                ),
            )

        return agent
