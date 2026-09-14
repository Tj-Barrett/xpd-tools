"""Blop optimizer and Queue Server integration."""

from typing import Literal

from blop.ax import Objective, OutcomeConstraint, RangeDOF
from blop.ax.queueserver_agent import QueueserverAgent
from .plans import DilutionStage, FlowSource, WashCycle
from .dofs import Pump, _create_pump
from .phases import Phase, _create_phase


class BuildAgent:
    def __init__(self,
                # Queue Server
                queue_server: bool = True,
                # HTTP Client
                http_server_uri: str | None = None,
                http_api_key: str | None = None,
                # ZMQ
                zmq_consumer_address: str | None = None,
                # Tiled
                tiled_profile: str | None = None,
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

        # Evaluation Function
        assert evaluation_method in [
            "uvvis",
            "xray",
            "xray-uvvis"
        ], "Evaluation method must be 'uvvis', 'xray', or 'xray-uvvis'."
        _eval_rename = {
            "uvvis": "UvvisEvaluation",
            "xray": "XrayEvaluation",
            "xray-uvvis": "XrayUvvisEvaluation",
        }
        self.evaluation_method = _eval_rename[evaluation_method]

        # Use PDFFIT?
        self.use_pdf_fit = use_pdf_fit
        # if self.use_pdf_fit:
        #     assert that pdffit2 can be imported and used so it doesnt fail at runtime

        # Objectives
        self.objectives = []
        if evaluation_method == "uvvis" or evaluation_method == "xray-uvvis":
            self.objectives = [
                Objective(name="log_FWHM", minimize=True),
                Objective(name="log_PLQY", minimize=False),
                Objective(name="peak_distance", minimize=True),
            ]

    def set_dofs(self,
        pumps: list[Pump]) -> None:
        self.dofs = [_create_pump(pump) for pump in pumps]

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

        self.max_retries = max_retries
        self.retry_delay = retry_delay
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
        # Objective Adjustment
        solvent: str = "toluene",
        solvent_abs: float = 1.506,
        # Screening
        screen_key_height: int = 200,
        screen_peak_height: int = 50,
        screen_peak_distance: int = 100,
        # Processing
        process_percent_range_pl: tuple[int, int] = (40, 100),
        process_percent_range_abs: tuple[int, int] = (10, 70),
        process_wavelength_range: tuple[int, int] = (210, 700),
        # Fitting
        fit_pl_wavelength_range: tuple[int, int] = (400, 800),
        fit_pl_maxfev: int = 100000,
        fit_abs_baseline_maxfev: int = 10000,
        fit_r2_window_sigma: int = 3,
        # Calibration Standard Reference
        reference: str = "quinine",
        ref_excitation_wavelength: int = 365,
        ref_absorbance: float = 0.361,
        ref_pl_integral: int = 952628,
        ref_refractive_index: float = 1.337,
        ref_plqy: float = 0.546,
    ) -> None:

        # Setting Objective Targets
        self.peak_target = peak_target
        self.peak_tolerance = peak_tolerance
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Solvent
        self.solvent = solvent
        self.solvent_abs = solvent_abs

        # Screening
        self.screen_key_height = screen_key_height
        self.screen_peak_height = screen_peak_height
        self.screen_peak_distance = screen_peak_distance

        # Processing
        self.process_percent_range_pl = process_percent_range_pl
        self.process_percent_range_abs = process_percent_range_abs
        self.process_wavelength_range = process_wavelength_range

        # Fitting
        self.fit_pl_wavelength_range = fit_pl_wavelength_range
        self.fit_pl_maxfev = fit_pl_maxfev
        self.fit_abs_baseline_maxfev = fit_abs_baseline_maxfev
        self.fit_r2_window_sigma = fit_r2_window_sigma

        # Setting Reference Data
        self.reference = reference
        self.ref_excitation_wavelength = ref_excitation_wavelength
        self.ref_absorbance = ref_absorbance
        self.ref_pl_integral = ref_pl_integral
        self.ref_refractive_index = ref_refractive_index
        self.ref_plqy = ref_plqy

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

    def build(self, ) -> None:
        agent = QueueserverAgent(
            re_manager_api,
            document_dispatcher,
            sensors=(),
            dofs=self.dofs,
            objectives=self.objectives,
            evaluation_function=evaluation,
            acquisition_plan="xray_uvvis_acquire",
            outcome_constraints=(
                OutcomeConstraint(f"p >= {target - peak_tolerance:g}", p=peak),
                OutcomeConstraint(f"p <= {target + peak_tolerance:g}", p=peak),
            ),
            checkpoint_path=None if checkpoint_path is None else str(checkpoint_path),
        return agent

    def export(self, ) -> None:
        # Export the agent state as a JSON string
        import json

        pass
