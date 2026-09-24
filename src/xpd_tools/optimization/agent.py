"""Blop optimizer and Queue Server integration."""

import json
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from bluesky.callbacks.zmq import RemoteDispatcher
from bluesky_queueserver_api.http import REManagerAPI
from tiled.client import from_profile, from_uri

from ax.api.protocols import IMetric
from blop.ax import Objective, OutcomeConstraint, RangeDOF
from blop.ax.agent import Agent
from blop.ax.queueserver_agent import QueueserverAgent
from xpd_tools.optimization.cli import DEFAULT_SANDBOX_URI, DEFAULT_TILED_PROFILE, SANDBOX_CATALOG
from xpd_tools.optimization.plans import (
    DilutionStage,
    FlowSource,
    WashCycle,
    create_uvvis_plan,
    create_xray_plan,
    create_xray_screened_plan,
    create_xray_uvvis_plan,
)
from xpd_tools.optimization.helpers.beamline import (
    UvvisPlanContext,
    XrayPlanContext,
    XraySettings,
    XrayUvvisPlanContext,
)
from xpd_tools.optimization.helpers.dofs import Pump, _create_pump
from xpd_tools.optimization.helpers.phases import Phase, _create_phase, _write_pdf_references
from xpd_tools.optimization.helpers.qepro import PlqyReference, QualityPolicy, SpectraFitSettings
from xpd_tools.optimization.scoring import _ALL_SCORING_NAMES
from xpd_tools.optimization.stopping import SuccessCriteria
from xpd_tools.optimization import plugins

_EVALUATORS = {
    "uvvis": plugins.UvvisEvaluation,
    "xray": plugins.XrayEvaluation,
    "xray-uvvis": plugins.XrayUvvisEvaluation,
}

# build_local()'s counterpart to build()'s _acquisition_plan_name(): the
# same plan-name dispatch, but resolved to the real local callable instead
# of a Queue Server plan-name string.
_LOCAL_PLAN_FACTORIES = {
    "uvvis_acquire": create_uvvis_plan,
    "xray_acquire": create_xray_plan,
    "xray_screened_acquire": create_xray_screened_plan,
    "xray_uvvis_acquire": create_xray_uvvis_plan,
}


def _load_historical_data(
    path: str | Path,
    dof_names: Sequence[str],
    objective_names: Sequence[str],
    *,
    optional_names: Sequence[str] = (),
) -> list[dict[str, float]]:
    """Load historical observations from a CSV for seeding the optimizer.

    Expects columns named exactly like the configured DOFs (e.g. an export
    from `ax_client.summarize()`).

    Only `dof_names` are required as they anchor each point in parameter space
    for `AxOptimizer.ingest`'s `attach_trial`.
    """
    frame = pd.read_csv(path)
    missing_dofs = [name for name in dof_names if name not in frame.columns]
    if missing_dofs:
        raise ValueError(
            f"{path}: historical data is missing columns: {', '.join(missing_dofs)}"
        )

    present_objectives = [name for name in objective_names if name in frame.columns]
    if objective_names and not present_objectives:
        raise ValueError(
            f"{path}: historical data has none of the configured objectives "
            f"({', '.join(objective_names)}) -- likely the wrong file"
        )

    columns = [
        *dof_names,
        *present_objectives,
        *(name for name in optional_names if name in frame.columns),
    ]
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
                # PDF correlation mode:
                #   "raw"         -- raw measured-G(r) correlation is the
                #                    objective; pdffit2 refinement never runs.
                #   "fit"         -- pdffit2-refined correlation is the
                #                    objective; a refinement failure is fatal.
                #   "raw_tracked" -- raw correlation is the objective (like
                #                    "raw"), but pdffit2 refinement is also
                #                    attempted every evaluation purely for
                #                    comparison/tracking -- a refinement
                #                    failure is logged and evaluation
                #                    continues with the raw result only.
                pdf_mode: Literal["raw", "fit", "raw_tracked"] = "raw",
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
            "xray-uvvis",
            None
        ], "Evaluation method must be 'uvvis', 'xray', or 'xray-uvvis' (or None)."
        self.evaluation_method = evaluation_method

        # PDF correlation mode -- see the docstring above pdf_mode's parameter.
        self.pdf_mode = pdf_mode

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
        # Optional early-stop thresholds for build()'s campaign -- see
        # set_success_criteria/stopping.watch_and_stop. Doesn't change
        # build()/run() at all on its own; the existing iterations=
        # stopping mode is unaffected whether or not this is configured.
        self.success_criteria: SuccessCriteria | None = None

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
        pumps: Sequence[Pump]) -> None:
        # Normalized to a list regardless of what sequence type the caller
        # passed in (tuple, list, ...) -- from_config() always rebuilds
        # this as a list, so a hand-built and a config-rebuilt agent would
        # otherwise disagree on `self.pumps`'s type despite equal contents.
        self.pumps = list(pumps)
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
        phases: Sequence[Phase] = ()
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

        if objective_function not in _ALL_SCORING_NAMES:
            raise ValueError(f"Invalid objective function: {objective_function}")
        self.objective_function = objective_function

        # Handle phases -- normalized to a list regardless of what sequence
        # type the caller passed in (see set_dofs's comment).
        self.phases = list(phases)
        # Only strict "fit" mode makes the refined correlation the objective;
        # "raw" and "raw_tracked" both optimize against the raw correlation.
        metric_prefix = "pdf_fit_corr_" if self.pdf_mode == "fit" else "corr_"
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

    def set_success_criteria(
        self,
        *,
        min_correlation: float | None = None,
        max_fwhm: float | None = None,
        min_plqy: float | None = None,
        poll_interval: float = 5.0,
    ) -> None:
        """Configure optional early-stop thresholds for build()'s campaign.

        Runs in parallel as a worker thread watching the output of the main
        queueserver thread. This might be deprecated in favor of the implementation
        Tom and others are working on, since that seems more formal than this process.

        `min_correlation` and the `max_fwhm`/`min_plqy` are mutually exclusive.
        """
        if min_correlation is None and (max_fwhm is None or min_plqy is None):
            raise ValueError(
                "set_success_criteria needs at least one real target: "
                "min_correlation, or both max_fwhm and min_plqy together"
            )
        self.success_criteria = SuccessCriteria(
            min_correlation=min_correlation,
            max_fwhm=max_fwhm,
            min_plqy=min_plqy,
            poll_interval=poll_interval,
        )

    def experiment(
        self,
        sources: Sequence[FlowSource] | None = None,
        dilutions: Sequence[DilutionStage] | None = None,
        wash_cycles: Sequence[WashCycle] | None = None,
    ) -> None:
        # Normalized to lists regardless of what sequence type the caller
        # passed in -- see set_dofs's comment on why this matters for
        # to_config()/from_config() round-trips.
        self.sources = None if sources is None else list(sources)
        self.dilutions = None if dilutions is None else list(dilutions)
        self.wash_cycles = None if wash_cycles is None else list(wash_cycles)
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

        Only relevant for UV-Vis and xray-UVVis evaluation methods.
        """
        peak = IMetric(name="Peak")
        return (
            OutcomeConstraint(f"p >= {self.peak_target - self.peak_tolerance:g}", p=peak),
            OutcomeConstraint(f"p <= {self.peak_target + self.peak_tolerance:g}", p=peak),
        )

    def _acquisition_plan_name(self) -> str:
        """Select the registered acquisition-plan name for the current config.

        BuildAgent can only choose a plan, not build the
        actual plan callable: `create_xray_plan`/`create_uvvis_plan`/
        `create_xray_uvvis_plan` all need live ophyd device objects that
        exist only in the queue server's worker environment.
        """
        if self.evaluation_method == "uvvis":
            return "uvvis_acquire"
        if self.evaluation_method == "xray-uvvis":
            return "xray_uvvis_acquire"
        # evaluation_method == "xray": the plan depends on self.screening.
        if self.screening == "unscreened":
            return "xray_acquire"
        if self.screening == "screen_only":
            return "xray_screened_acquire"
        return "xray_uvvis_acquire"  # screening == "screen_and_record"

    def _validate_before_build(self) -> tuple[bool, bool]:
        """Shared build()/build_local() preconditions.

        Returns (needs_pdf, needs_plqy).
        """
        if self.dofs is None:
            raise ValueError(
                "set_dofs(...) must be called before build()/build_local()"
            )
        if self.sources is None:
            raise ValueError(
                "experiment(...) must be called before build()/build_local()"
            )
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
                "set_uvvis_objectives(...) to be called before build()/build_local()"
            )
        return needs_pdf, needs_plqy

    def _build_evaluator(
        self,
        needs_pdf: bool,
        *,
        tiled_client: Any | None = None,
        sandbox_client: Any | None = None,
    ) -> Any:
        """Build the evaluation function.

        `tiled_client`/`sandbox_client` override the real
        `_tiled_client()`/`_sandbox_client()` connections when given --
        `build_local()`'s way of substituting
        `legacy.build_fake_tiled_clients(...)` for genuinely offline runs;
        `build()` never passes these, so its behavior is unchanged.
        """
        with tempfile.TemporaryDirectory() as directory:
            evaluator_kwargs: dict[str, Any] = {}
            if needs_pdf:
                evaluator_kwargs["sandbox_client"] = (
                    sandbox_client
                    if sandbox_client is not None
                    else self._sandbox_client()
                )
                evaluator_kwargs["pdf_references"] = _write_pdf_references(
                    self.phases, Path(directory), scoring_function=self.objective_function
                )
                evaluator_kwargs["pdf_mode"] = self.pdf_mode
                evaluator_kwargs["r_min"] = self.min_radius
                evaluator_kwargs["r_max"] = self.max_radius
            if self.evaluation_method == "uvvis":
                evaluator_kwargs["tiled_client"] = (
                    tiled_client if tiled_client is not None else self._tiled_client()
                )
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
                evaluator_kwargs["tiled_client"] = (
                    tiled_client if tiled_client is not None else self._tiled_client()
                )
                evaluator_kwargs["plqy"] = self.plqy
                evaluator_kwargs["peak_target"] = self.peak_target
                evaluator_kwargs["uvvis_max_retries"] = self.uvvis_max_retries
                evaluator_kwargs["uvvis_retry_delay"] = self.uvvis_retry_delay
                evaluator_kwargs["xray_max_retries"] = self.xray_max_retries
                evaluator_kwargs["xray_retry_delay"] = self.xray_retry_delay
                evaluator_kwargs["fit_settings"] = self.fit_settings

            return _EVALUATORS[self.evaluation_method](**evaluator_kwargs)

    def _seed_historical_data(self, agent: Any, needs_plqy: bool) -> None:
        if self.agent_data_path is None:
            return
        historical = _load_historical_data(
            self.agent_data_path,
            [dof.name for dof in self.dofs],
            [objective.name for objective in self.objectives],
            optional_names=("Peak",) if needs_plqy else (),
        )
        if historical:
            agent.ingest(historical)

    def build(self, ) -> None:
        """Build the agent for use in a queueserver environment.

        This method should only be called when `queue_server=True`,
        and needs the local environment of the beamline to function
        properly.
        """
        if not self.queue_server:
            raise NotImplementedError(
                "queue_server=False -- call build_local(...) instead of build()"
            )
        needs_pdf, needs_plqy = self._validate_before_build()
        acquisition_plan = self._acquisition_plan_name()
        _evaluator = self._build_evaluator(needs_pdf)

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
        self._seed_historical_data(agent, needs_plqy)
        return agent

    def _build_plan_context(
        self,
        devices: Mapping[str, Any],
        wrap_xray_run: Callable[[Any, bool], Any],
        mixer_lengths_cm: tuple[float, ...],
        residence_time_ratio: float,
    ) -> XrayPlanContext | UvvisPlanContext | XrayUvvisPlanContext:
        """Bind sources/dilutions/wash_cycles' pump names to real devices.

        Builds the plan context matching `_acquisition_plan_name()`'s
        dispatch -- the same context shape the Queue Server's worker builds
        today (see `helpers.beamline`), just constructed here instead of in
        a separate worker process.
        """

        def _bind_pump(item: Any) -> Any:
            return replace(item, pump=devices[item.pump])

        common = {
            "sources": tuple(_bind_pump(source) for source in self.sources),
            "dilutions": tuple(_bind_pump(stage) for stage in self.dilutions or ()),
            "wash_cycles": tuple(_bind_pump(cycle) for cycle in self.wash_cycles or ()),
            "quality": self.quality_policy or QualityPolicy(enabled=False),
            "mixer_lengths_cm": mixer_lengths_cm,
            "residence_time_ratio": residence_time_ratio,
        }
        fit_settings = self.fit_settings or SpectraFitSettings()

        plan_name = self._acquisition_plan_name()
        if plan_name == "uvvis_acquire":
            return UvvisPlanContext(
                qepro=devices["qepro"],
                led=devices["led"],
                uv_shutter=devices["uv_shutter"],
                fast_shutter=devices["fast_shutter"],
                fit_settings=fit_settings,
                **common,
            )
        if plan_name == "xray_acquire":
            return XrayPlanContext(
                led=devices["led"],
                fast_shutter=devices["fast_shutter"],
                xray_detector=devices["xray_detector"],
                wrap_xray_run=wrap_xray_run,
                xray=self.xray_settings,
                **common,
            )
        # "xray_screened_acquire" or "xray_uvvis_acquire" -- both need the
        # full XrayUvvisPlanContext; they differ only in whether the plan
        # itself reports the UV-Vis measurement as evaluation data.
        return XrayUvvisPlanContext(
            qepro=devices["qepro"],
            led=devices["led"],
            uv_shutter=devices["uv_shutter"],
            fast_shutter=devices["fast_shutter"],
            xray_detector=devices["xray_detector"],
            wrap_xray_run=wrap_xray_run,
            xray=self.xray_settings,
            fit_settings=fit_settings,
            **common,
        )

    def build_local(
        self,
        devices: Mapping[str, Any],
        wrap_xray_run: Callable[[Any, bool], Any],
        *,
        # Same meaning/defaults as helpers.beamline's *PlanContext dataclass
        # fields -- on the queue-server path these are set directly on the
        # context by the worker's own startup script (never seen by
        # xpd_tools at all); build_local() has to build the context itself,
        # so it needs its own way to override them for real tubing, or (as
        # in tests) to make simulated runs fast.
        mixer_lengths_cm: tuple[float, ...] = (30.0,),
        residence_time_ratio: float = 1.0,
        # Real Tiled/sandbox connections by default -- same as build().
        # Override with legacy.build_fake_tiled_clients(...) to run fully
        # offline: there's no real pdfstream service to reduce a
        # simulated detector's data anyway, so a real sandbox_client can
        # never produce real results for a simulated campaign.
        tiled_client: Any | None = None,
        sandbox_client: Any | None = None,
    ) -> Agent:
        """No-queue-server build path.

        Drives a local Bluesky RunEngine directly against `devices` (real
        hardware or simulated), instead of dispatching acquisition plans by
        name through a Queue Server.

        Returns a `blop.ax.agent.Agent`.

        Can be used both as a fake atmosphere to test building of the agent
        and loading historical data, and as a local environment to run simulation
        driven bayesian optimization of the chemical space.
        """
        if self.queue_server:
            raise ValueError(
                "queue_server=True -- call build() instead of build_local()"
            )
        needs_pdf, needs_plqy = self._validate_before_build()
        _evaluator = self._build_evaluator(
            needs_pdf, tiled_client=tiled_client, sandbox_client=sandbox_client
        )

        context = self._build_plan_context(
            devices, wrap_xray_run, mixer_lengths_cm, residence_time_ratio
        )
        acquisition_plan = _LOCAL_PLAN_FACTORIES[self._acquisition_plan_name()](context)

        agent = Agent(
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
        self._seed_historical_data(agent, needs_plqy)
        return agent

    def to_config(self, filename: str | None = None) -> dict[str, Any] | None:
        """Compile the current configuration into a JSON-able dict.

        TODO: Expand to include local meta-data on the beamline. We should be
        able to reproduce the beamline state (devices, configuration) to
        recreate the agent if experimental data is weird.
        """
        _json  = {
            "connection": {
                "queue_server": self.queue_server,
                "http_server_uri": self.http_server_uri,
                "zmq_consumer_address": self.zmq_consumer_address,
                "tiled_profile": self.tiled_profile,
                "tiled_uri": self.tiled_uri,
                "sandbox_uri": self.sandbox_uri,
            },
            "evaluation_method": self.evaluation_method,
            "pdf_mode": self.pdf_mode,
            "agent_data_path": self.agent_data_path,
            "checkpoint_path": (
                None if self.checkpoint_path is None else str(self.checkpoint_path)
            ),
            "metadata": self.metadata,
            "success_criteria": (
                None if self.success_criteria is None else asdict(self.success_criteria)
            ),
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
        if filename is None:
            return _json

        else:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(_json, f, ensure_ascii=False, indent=4)

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
            pdf_mode=config["pdf_mode"],
            evaluation_method=config["evaluation_method"],
            agent_data_path=config["agent_data_path"],
            checkpoint_path=config["checkpoint_path"],
        )

        if config["metadata"] is not None:
            agent.set_metadata(config["metadata"])

        if config["success_criteria"] is not None:
            agent.set_success_criteria(**config["success_criteria"])

        if config["pumps"] is not None:
            agent.set_dofs(
                [
                    Pump(
                        name=pump["name"],
                        id=pump["id"],
                        bounds=pump["bounds"],
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
                    # JSON has no tuple type, so the range fields come back
                    # as lists -- SpectraFitSettings.__post_init__ restores
                    # them to tuples.
                    else SpectraFitSettings(**uvvis["fit_settings"])
                ),
                plqy=(
                    PlqyReference()
                    if uvvis["plqy"] is None
                    else PlqyReference(**uvvis["plqy"])
                ),
            )

        return agent
