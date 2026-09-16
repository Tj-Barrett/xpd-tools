from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

from xpd_tools.optimization.agent import BuildAgent, _load_historical_data
from xpd_tools.optimization.helpers.dofs import Pump
from xpd_tools.optimization.helpers.phases import Phase
from xpd_tools.optimization.helpers.qepro import PlqyReference, SpectraFitSettings
from xpd_tools.optimization.plans import DilutionStage, FlowSource, WashCycle


@pytest.fixture
def phase_factory(tmp_path: Path) -> Callable[..., Phase]:
    """Write a real minimal .gr/.cif pair and return a matching Phase."""
    radial = np.linspace(1.0, 25.0, 200)

    def factory(name: str = "A", *, minimize: bool = False) -> Phase:
        gr_path = tmp_path / f"{name}.gr"
        np.savetxt(gr_path, np.column_stack((radial, np.sin(radial))))
        cif_path = tmp_path / f"{name}.cif"
        cif_path.write_text(
            "data_test\n_symmetry_space_group_name_H-M 'P 1'\n"
            "_cell_length_a 6\n_cell_length_b 6\n_cell_length_c 6\n"
            "_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n"
        )
        return Phase(name=name, gr=str(gr_path), cif=str(cif_path), minimize=minimize)

    return factory


@pytest.fixture
def mocked_queueserver() -> None:
    """Patch every network/queueserver call BuildAgent.build() can make."""
    targets = [
        "xpd_tools.optimization.agent.from_uri",
        "xpd_tools.optimization.agent.from_profile",
        "xpd_tools.optimization.agent.REManagerAPI",
        "xpd_tools.optimization.agent.RemoteDispatcher",
        "blop.ax.queueserver_agent.QueueserverClient",
        "blop.ax.queueserver_agent.QueueserverOptimizationRunner",
    ]
    patchers = [patch(target) for target in targets]
    for patcher in patchers:
        patcher.start()
    yield
    for patcher in patchers:
        patcher.stop()


def _pump(name: str = "CsPb", *, bounds: tuple[float, float] = (10, 200)) -> Pump:
    return Pump(name=name, id=f"dds-{name}", bounds=bounds)


def _source(name: str = "CsPb") -> FlowSource:
    return FlowSource(
        dof=f"infusion_rate_{name}",
        pump=f"dds-{name}",
        precursor=f"precursor-{name}",
        sample_label=name,
    )


def _uvvis_agent(**kwargs: Any) -> BuildAgent:
    agent = BuildAgent(
        evaluation_method="uvvis",
        http_server_uri="https://example.invalid",
        **kwargs,
    )
    agent.set_dofs([_pump()])
    agent.experiment(sources=[_source()])
    return agent


class TestDofSourceAlignment:
    def test_set_dofs_and_experiment_normalize_tuples_to_lists(self) -> None:
        """set_dofs/experiment/set_xray_objectives accept any sequence type
        (tuple, list, ...) and normalize to a list -- so a hand-built agent
        matches a from_config()-rebuilt one regardless of which the caller
        used (from_config always rebuilds lists).
        """
        agent = BuildAgent(evaluation_method="xray")
        agent.set_dofs((_pump(),))
        agent.experiment(
            sources=(_source(),), dilutions=(), wash_cycles=()
        )
        assert isinstance(agent.pumps, list)
        assert isinstance(agent.sources, list)
        assert isinstance(agent.dilutions, list)
        assert isinstance(agent.wash_cycles, list)

    def test_dofs_then_matching_sources_ok(self) -> None:
        agent = BuildAgent(evaluation_method="uvvis")
        agent.set_dofs([_pump()])
        agent.experiment(sources=[_source()])
        assert agent.dofs[0].name == "infusion_rate_CsPb"

    def test_sources_then_matching_dofs_ok(self) -> None:
        agent = BuildAgent(evaluation_method="uvvis")
        agent.experiment(sources=[_source()])
        agent.set_dofs([_pump()])
        assert agent.dofs[0].name == "infusion_rate_CsPb"

    def test_mismatch_raises_when_second_call_is_experiment(self) -> None:
        agent = BuildAgent(evaluation_method="uvvis")
        agent.set_dofs([_pump()])
        with pytest.raises(ValueError, match="must reference the same names"):
            agent.experiment(sources=[_source("Br")])

    def test_mismatch_raises_when_second_call_is_set_dofs(self) -> None:
        agent = BuildAgent(evaluation_method="uvvis")
        agent.experiment(sources=[_source("Br")])
        with pytest.raises(ValueError, match="must reference the same names"):
            agent.set_dofs([_pump()])

    def test_build_requires_set_dofs(self) -> None:
        agent = BuildAgent(evaluation_method="uvvis")
        agent.experiment(sources=[_source()])
        with pytest.raises(ValueError, match="set_dofs"):
            agent.build()

    def test_build_requires_experiment(self) -> None:
        agent = BuildAgent(evaluation_method="uvvis")
        agent.set_dofs([_pump()])
        with pytest.raises(ValueError, match="experiment"):
            agent.build()


class TestUvvisObjectives:
    def test_builds_plqy_reference(self) -> None:
        agent = _uvvis_agent()
        agent.set_uvvis_objectives(
            plqy=PlqyReference(
                excitation_wavelength_nm=400, solvent_refractive_index=1.5
            )
        )
        assert agent.plqy.reference_type == "quinine"
        assert agent.plqy.excitation_wavelength_nm == 400
        assert agent.plqy.solvent_refractive_index == 1.5

    def test_builds_spectra_fit_settings(self) -> None:
        agent = _uvvis_agent()
        agent.set_uvvis_objectives(
            plqy=PlqyReference(),
            fit_settings=SpectraFitSettings(pl_screen_key_height=50),
        )
        assert agent.fit_settings.pl_screen_key_height == 50
        assert agent.fit_settings.pl_wavelength_range == (400.0, 800.0)

    def test_build_requires_set_uvvis_objectives(self) -> None:
        agent = _uvvis_agent()
        with pytest.raises(ValueError, match="set_uvvis_objectives"):
            agent.build()


class TestXrayObjectives:
    def test_builds_xray_settings(self, phase_factory: Callable[..., Phase]) -> None:
        agent = BuildAgent(evaluation_method="xray")
        agent.set_xray_objectives(
            exposure=300.0,
            frame_acq_time=1.0,
            no_dark=True,
            stream_name="custom",
            phases=[phase_factory()],
        )
        assert agent.xray_settings.exposure == 300.0
        assert agent.xray_settings.frame_acq_time == 1.0
        assert agent.xray_settings.no_dark is True
        assert agent.xray_settings.stream_name == "custom"

    @pytest.mark.parametrize("objective_function", ["cnn", "ensemble", "unknown"])
    def test_objective_function_rejects_unimplemented_choices(
        self, objective_function: str, phase_factory: Callable[..., Phase]
    ) -> None:
        """'cnn' has no implementation anywhere; 'ensemble' exists as a
        stateful scorer but isn't wired into _SCORING_FUNCTIONS (see the
        objective_function/scoring findings from review) -- both must be
        rejected rather than silently accepted and ignored.
        """
        agent = BuildAgent(evaluation_method="xray")
        with pytest.raises(ValueError, match="Invalid objective function"):
            agent.set_xray_objectives(
                objective_function=objective_function, phases=[phase_factory()]
            )

    def test_phases_normalizes_tuples_to_lists(
        self, phase_factory: Callable[..., Phase]
    ) -> None:
        agent = BuildAgent(evaluation_method="xray")
        agent.set_xray_objectives(phases=(phase_factory(),))
        assert isinstance(agent.phases, list)

    def test_unscreened_has_no_quality_policy(
        self, phase_factory: Callable[..., Phase]
    ) -> None:
        agent = BuildAgent(evaluation_method="xray")
        agent.set_xray_objectives(screening="unscreened", phases=[phase_factory()])
        assert agent.quality_policy is None

    @pytest.mark.parametrize("screening", ["screen_only", "screen_and_record"])
    def test_screened_modes_build_quality_policy(
        self, screening: str, phase_factory: Callable[..., Phase]
    ) -> None:
        agent = BuildAgent(evaluation_method="xray")
        agent.set_xray_objectives(
            screening=screening,
            use_good_bad=False,
            good_target=5,
            max_bad=1,
            num_abs=8,
            num_flu=12,
            phases=[phase_factory()],
        )
        assert agent.quality_policy.enabled is False
        assert agent.quality_policy.good_batches == 5
        assert agent.quality_policy.max_bad_batches == 1
        assert agent.quality_policy.absorbance_shots == 8
        assert agent.quality_policy.fluorescence_shots == 12

    def test_stores_min_max_radius(self, phase_factory: Callable[..., Phase]) -> None:
        agent = BuildAgent(evaluation_method="xray")
        agent.set_xray_objectives(
            min_radius=3.0, max_radius=15.0, phases=[phase_factory()]
        )
        assert agent.min_radius == 3.0
        assert agent.max_radius == 15.0

    def test_stores_phases_and_applies_metric_prefix(
        self, phase_factory: Callable[..., Phase]
    ) -> None:
        phases = [phase_factory("Wanted"), phase_factory("Impurity", minimize=True)]

        raw_agent = BuildAgent(evaluation_method="xray", use_pdf_fit=False)
        raw_agent.set_xray_objectives(phases=phases)
        assert raw_agent.phases == phases
        assert {obj.name for obj in raw_agent.objectives} == {
            "corr_Wanted",
            "corr_Impurity",
        }

        fit_agent = BuildAgent(evaluation_method="xray", use_pdf_fit=True)
        fit_agent.set_xray_objectives(phases=phases)
        assert {obj.name for obj in fit_agent.objectives} == {
            "pdf_fit_corr_Wanted",
            "pdf_fit_corr_Impurity",
        }

    def test_build_requires_phases(self) -> None:
        agent = BuildAgent(evaluation_method="xray")
        agent.set_dofs([_pump()])
        agent.experiment(sources=[_source()])
        with pytest.raises(ValueError, match="requires phases"):
            agent.build()


class TestPeakOutcomeConstraints:
    def test_values_match_target_and_tolerance(self) -> None:
        agent = _uvvis_agent()
        agent.set_uvvis_objectives(
            peak_target=650, peak_tolerance=4, plqy=PlqyReference()
        )
        constraints = agent._peak_outcome_constraints()
        assert [str(c) for c in constraints] == ["Peak >= 646", "Peak <= 654"]


class TestAcquisitionPlanSelection:
    def test_uvvis(self) -> None:
        agent = _uvvis_agent()
        assert agent._acquisition_plan_name() == "uvvis_acquire"

    def test_xray_unscreened(self, phase_factory: Callable[..., Phase]) -> None:
        agent = BuildAgent(evaluation_method="xray")
        agent.set_xray_objectives(screening="unscreened", phases=[phase_factory()])
        assert agent._acquisition_plan_name() == "xray_acquire"

    def test_xray_screen_and_record(self, phase_factory: Callable[..., Phase]) -> None:
        agent = BuildAgent(evaluation_method="xray")
        agent.set_xray_objectives(
            screening="screen_and_record", phases=[phase_factory()]
        )
        assert agent._acquisition_plan_name() == "xray_uvvis_acquire"

    def test_xray_screen_only(self, phase_factory: Callable[..., Phase]) -> None:
        agent = BuildAgent(evaluation_method="xray")
        agent.set_xray_objectives(screening="screen_only", phases=[phase_factory()])
        assert agent._acquisition_plan_name() == "xray_screened_acquire"

    def test_xray_uvvis(self, phase_factory: Callable[..., Phase]) -> None:
        agent = BuildAgent(evaluation_method="xray-uvvis")
        agent.set_xray_objectives(phases=[phase_factory()])
        assert agent._acquisition_plan_name() == "xray_uvvis_acquire"


class TestLoadHistoricalData:
    def test_returns_matching_rows(self, tmp_path: Path) -> None:
        path = tmp_path / "history.csv"
        path.write_text("infusion_rate_CsPb,log_FWHM\n50.0,3.1\n75.0,3.0\n")
        rows = _load_historical_data(path, ["infusion_rate_CsPb"], ["log_FWHM"])
        assert rows == [
            {"infusion_rate_CsPb": 50.0, "log_FWHM": 3.1},
            {"infusion_rate_CsPb": 75.0, "log_FWHM": 3.0},
        ]

    def test_missing_required_column_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "history.csv"
        path.write_text("infusion_rate_CsPb\n50.0\n")
        with pytest.raises(ValueError, match="missing columns: infusion_rate_Br"):
            _load_historical_data(
                path, ["infusion_rate_CsPb", "infusion_rate_Br"], []
            )

    def test_optional_column_included_when_present(self, tmp_path: Path) -> None:
        path = tmp_path / "history.csv"
        path.write_text("infusion_rate_CsPb,Peak\n50.0,648.0\n")
        rows = _load_historical_data(
            path, ["infusion_rate_CsPb"], [], optional_names=("Peak",)
        )
        assert rows == [{"infusion_rate_CsPb": 50.0, "Peak": 648.0}]

    def test_optional_column_omitted_when_absent(self, tmp_path: Path) -> None:
        path = tmp_path / "history.csv"
        path.write_text("infusion_rate_CsPb\n50.0\n")
        rows = _load_historical_data(
            path, ["infusion_rate_CsPb"], [], optional_names=("Peak",)
        )
        assert rows == [{"infusion_rate_CsPb": 50.0}]


def test_pump_bounds_normalizes_to_tuple() -> None:
    """Pump.bounds is typed tuple[float, float] but nothing enforced it --
    from_config() always rebuilds it as a tuple, so a hand-built Pump using
    a list would silently mismatch. See Pump.__post_init__.
    """
    assert Pump(name="CsPb", id="dds2_p1", bounds=[10, 200]).bounds == (10, 200)
    assert isinstance(Pump(name="CsPb", id="dds2_p1", bounds=[10, 200]).bounds, tuple)


def test_spectra_fit_settings_ranges_normalize_to_tuple() -> None:
    """Same fragility as Pump.bounds, for SpectraFitSettings's four range
    fields -- see SpectraFitSettings.__post_init__.
    """
    settings = SpectraFitSettings(
        pl_percent_range=[40, 100],
        pl_wavelength_range=[400, 800],
        absorbance_percent_range=[10, 70],
        absorbance_wavelength_range=[210, 700],
    )
    assert settings.pl_percent_range == (40, 100)
    assert settings.pl_wavelength_range == (400, 800)
    assert settings.absorbance_percent_range == (10, 70)
    assert settings.absorbance_wavelength_range == (210, 700)
    assert all(
        isinstance(getattr(settings, field), tuple)
        for field in (
            "pl_percent_range",
            "pl_wavelength_range",
            "absorbance_percent_range",
            "absorbance_wavelength_range",
        )
    )


class TestConfigRoundTrip:
    def _full_agent(self, phase: Phase) -> BuildAgent:
        agent = BuildAgent(
            evaluation_method="xray-uvvis",
            http_server_uri="https://example.invalid",
            http_api_key="TOP-SECRET",
            zmq_consumer_address="ipc:///tmp/fake",
            tiled_profile="xpd",
            checkpoint_path="/tmp/ckpt.json",
        )
        agent.set_metadata({"beamline": "28id2", "comment": "test"})
        agent.set_dofs([_pump()])
        agent.experiment(
            sources=[_source()],
            dilutions=[
                DilutionStage(
                    pump="dds1_p1",
                    ratio=1.0,
                    position="before_equilibrium",
                    syringe_ml=20,
                    material="plastic_BD",
                    target_ml=20,
                )
            ],
            wash_cycles=[WashCycle(pump="ultra1")],
        )
        agent.set_xray_objectives(
            exposure=300.0,
            screening="screen_and_record",
            good_target=5,
            min_radius=3.0,
            max_radius=15.0,
            phases=[phase],
        )
        agent.set_uvvis_objectives(
            peak_target=650,
            peak_tolerance=4,
            plqy=PlqyReference(),
            fit_settings=SpectraFitSettings(),
        )
        return agent

    def test_to_config_excludes_api_key(self, phase_factory: Callable[..., Phase]) -> None:
        agent = self._full_agent(phase_factory())
        agent.http_api_key = "TOP-SECRET"
        text = json.dumps(agent.to_config())
        assert "TOP-SECRET" not in text

    def test_round_trip_through_json_is_identical(
        self, phase_factory: Callable[..., Phase]
    ) -> None:
        agent = self._full_agent(phase_factory())
        config = agent.to_config()
        reloaded = json.loads(json.dumps(config))

        rebuilt = BuildAgent.from_config(reloaded, http_api_key="TOP-SECRET")

        assert rebuilt.to_config() == config

    def test_rebuilt_agent_builds(
        self, phase_factory: Callable[..., Phase], mocked_queueserver: None
    ) -> None:
        agent = self._full_agent(phase_factory())
        rebuilt = BuildAgent.from_config(agent.to_config())
        built = rebuilt.build()
        assert built.acquisition_plan == "xray_uvvis_acquire"

    def test_live_object_state_matches_after_round_trip(
        self, phase_factory: Callable[..., Phase]
    ) -> None:
        """`from_config` must rebuild an agent whose live state (`__dict__`)
        matches the original -- a strictly stronger guarantee than the
        `to_config()`-output equality the other round-trip tests check.
        `to_config()` output can't distinguish a `list` from a `tuple`
        (both serialize to the same JSON array), so a to_config()-only
        check would miss a real regression class: e.g. `from_config`
        silently rebuilding `Pump.bounds` as a list when the original was
        a tuple (as happened in the example notebook -- see
        `test_dofs.py`/`helpers/dofs.py`'s `bounds: tuple[float, float]`).
        """
        agent = self._full_agent(phase_factory())
        config = json.loads(json.dumps(agent.to_config()))

        rebuilt = BuildAgent.from_config(config, http_api_key=agent.http_api_key)

        assert rebuilt.__dict__ == agent.__dict__

    def test_partial_config_round_trips_without_spurious_defaults(self) -> None:
        agent = BuildAgent(evaluation_method="uvvis")
        agent.set_uvvis_objectives(plqy=PlqyReference())

        config = agent.to_config()
        rebuilt = BuildAgent.from_config(config)

        assert rebuilt.to_config() == config
        assert rebuilt.dofs is None
        assert rebuilt.xray_settings is None


class TestBuildEndToEnd:
    def test_uvvis_succeeds(self, mocked_queueserver: None) -> None:
        agent = _uvvis_agent()
        agent.set_uvvis_objectives(plqy=PlqyReference())
        built = agent.build()
        assert built.acquisition_plan == "uvvis_acquire"

    def test_xray_succeeds(
        self, phase_factory: Callable[..., Phase], mocked_queueserver: None
    ) -> None:
        agent = BuildAgent(evaluation_method="xray", http_server_uri="https://example.invalid")
        agent.set_dofs([_pump()])
        agent.experiment(sources=[_source()])
        agent.set_xray_objectives(
            screening="screen_and_record", phases=[phase_factory()]
        )
        built = agent.build()
        assert built.acquisition_plan == "xray_uvvis_acquire"

    def test_objective_function_reaches_the_built_evaluator(
        self, phase_factory: Callable[..., Phase], mocked_queueserver: None
    ) -> None:
        """objective_function must actually control phase scoring, not just
        be stored -- see the objective_function dead-wiring bug found in
        review (fixed by threading it through _write_pdf_references).
        """
        agent = BuildAgent(evaluation_method="xray", http_server_uri="https://example.invalid")
        agent.set_dofs([_pump()])
        agent.experiment(sources=[_source()])
        agent.set_xray_objectives(
            objective_function="cross_correlation",
            screening="unscreened",
            phases=[phase_factory()],
        )
        built = agent.build()
        assert all(
            phase.scoring_function == "cross_correlation"
            for phase in built.evaluation_function.phases
        )

    def test_xray_screen_only_succeeds(
        self, phase_factory: Callable[..., Phase], mocked_queueserver: None
    ) -> None:
        agent = BuildAgent(evaluation_method="xray", http_server_uri="https://example.invalid")
        agent.set_dofs([_pump()])
        agent.experiment(sources=[_source()])
        agent.set_xray_objectives(screening="screen_only", phases=[phase_factory()])
        built = agent.build()
        assert built.acquisition_plan == "xray_screened_acquire"

    def test_xray_uvvis_succeeds(
        self, phase_factory: Callable[..., Phase], mocked_queueserver: None
    ) -> None:
        agent = BuildAgent(
            evaluation_method="xray-uvvis", http_server_uri="https://example.invalid"
        )
        agent.set_dofs([_pump()])
        agent.experiment(sources=[_source()])
        agent.set_xray_objectives(phases=[phase_factory()])
        agent.set_uvvis_objectives(plqy=PlqyReference())
        built = agent.build()
        assert built.acquisition_plan == "xray_uvvis_acquire"

    def test_queue_server_false_not_implemented(self) -> None:
        agent = _uvvis_agent(queue_server=False)
        with pytest.raises(NotImplementedError, match="queue_server=False"):
            agent.build()
