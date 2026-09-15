"""Blop optimizer and Queue Server integration."""

import tempfile
from pathlib import Path
from typing import Any, Literal

from bluesky.callbacks.zmq import RemoteDispatcher
from bluesky_queueserver_api.http import REManagerAPI
from tiled.client import from_profile, from_uri

from blop.ax import Objective, OutcomeConstraint, RangeDOF
from blop.ax.queueserver_agent import QueueserverAgent
from .cli import DEFAULT_SANDBOX_URI, DEFAULT_TILED_PROFILE, SANDBOX_CATALOG
from .plans import DilutionStage, FlowSource, WashCycle
from .helpers.dofs import Pump, _create_pump
from .helpers.phases import Phase, _create_phase, _write_pdf_references
from .helpers.qepro import PlqyReference, SpectraFitSettings
from . import plugins

_EVALUATORS = {
    "uvvis": plugins.UvvisEvaluation,
    "xray": plugins.XrayEvaluation,
    "xray-uvvis": plugins.XrayUvvisEvaluation,
}

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
        self.sources: list[FlowSource] | None = None
        self.dilutions: list[DilutionStage] | None = None
        self.wash_cycles: list[WashCycle] | None = None
        self.phases: list[Phase] | None = None
        self.plqy: PlqyReference | None = None
        self.fit_settings: SpectraFitSettings | None = None

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
        self.dofs = [_create_pump(pump) for pump in pumps]
        self._check_dof_source_alignment()

    def set_objectives(self,
        function: str,
        phases: list[Phase]) -> None:

        if self.use_pdf_fit:
            metric_prefix = "pdf_fit_corr_"
        else:
            metric_prefix = "corr_"

        # PDF Parameters
        assert function in [
            "cross_correlation",
            "nn_matrix",
            "pearson",
            "weighted_profile_r",
        ], "Correlation function must be a supported function."
        self.pdf_function = function

        _phase_objectives = [_create_phase(phase) for phase in phases]

        self.objectives = [
            *self.objectives,
            *_phase_objectives,
        ]

    def set_xray_objectives(self,
        # Measurement
        max_retries: int = 10,
        retry_delay: float = 2.0,
        # Configuration
        exposure: float = 600.0,
        frame_acq_time: float = 1.5,
        no_dark: bool = False,
        stream_name: str = "scattering",
        # Quality Checks
        use_good_bad: bool = True,
        good_target: int = 2,
        max_bad: int = 3,
        num_abs: int = 16,
        num_flu: int = 16,
        # Phase Fitting
        objective_function: str = "pearson",
        phases: list[Phase] = []
    ) -> None:

        self.xray_max_retries = max_retries
        self.xray_retry_delay = retry_delay
        self.exposure = exposure
        self.frame_acq_time = frame_acq_time
        self.no_dark = no_dark
        self.stream_name = stream_name
        self.use_good_bad = use_good_bad
        self.good_target = good_target
        self.max_bad = max_bad
        self.num_abs = num_abs
        self.num_flu = num_flu

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
        _phase_objectives = [_create_phase(phase) for phase in phases]

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

        with tempfile.TemporaryDirectory() as directory:
            evaluator_kwargs: dict[str, Any] = {}
            if needs_pdf:
                evaluator_kwargs["sandbox_client"] = self._sandbox_client()
                evaluator_kwargs["pdf_references"] = _write_pdf_references(
                    self.phases, Path(directory)
                )
                evaluator_kwargs["pdf_mode"] = "fit" if self.use_pdf_fit else "raw"
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
            acquisition_plan="xray_uvvis_acquire",
            outcome_constraints=(
                OutcomeConstraint(f"p >= {target - peak_tolerance:g}", p=peak),
                OutcomeConstraint(f"p <= {target + peak_tolerance:g}", p=peak),
            ),
            checkpoint_path=None if checkpoint_path is None else str(checkpoint_path),
        )
        return agent

    def export(self, ) -> None:
        # Export the agent state as a JSON string
        import json

        pass
