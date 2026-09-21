from __future__ import annotations

from typing import Any
from unittest.mock import patch

import numpy as np
import pytest
from bluesky.run_engine import RunEngine
from ophyd import Signal

from xpd_tools.optimization.helpers.beamline import XrayPlanContext, XraySettings
from xpd_tools.optimization.helpers.phases import Phase
from xpd_tools.optimization.helpers.qepro import PlqyReference
from xpd_tools.optimization.legacy.devices import FakeAreaDetector, FakePump
from xpd_tools.optimization.plans import (
    FlowSource,
    QualityPolicy,
    create_xray_plan,
    create_xray_uvvis_plan,
)
from xpd_tools.optimization.plugins import UvvisEvaluation
from xpd_tools.optimization.simulation.tiled import (
    _synthesize_absorbance_edge,
    _synthesize_pl_spectrum,
    build_simulated_tiled_clients,
    linear_dof_weights,
)


def test_linear_dof_weights_normalizes() -> None:
    start_doc = {
        "dof_names": ["infusion_rate_CsPb", "infusion_rate_Br"],
        "infuse_rates": [30.0, 90.0],
    }
    dof_for_phase = {"CsPbBr3": "infusion_rate_Br", "CsBr": "infusion_rate_CsPb"}
    weights = linear_dof_weights(start_doc, dof_for_phase)
    assert weights["CsPbBr3"] == pytest.approx(0.75)
    assert weights["CsBr"] == pytest.approx(0.25)


def test_linear_dof_weights_falls_back_to_uniform_when_all_zero() -> None:
    start_doc = {"dof_names": ["infusion_rate_CsPb"], "infuse_rates": [0.0]}
    dof_for_phase = {"CsPbBr3": "infusion_rate_CsPb", "CsBr": "infusion_rate_Br"}
    assert linear_dof_weights(start_doc, dof_for_phase) == {"CsPbBr3": 0.5, "CsBr": 0.5}


@patch("xpd_tools.optimization.simulation.tiled.MPAPIUser")
def test_build_simulated_tiled_clients_mixes_phase_pdfs(
    mock_mp_user_cls: Any,
    RE: RunEngine,
) -> None:
    """The point of build_simulated_tiled_clients(): different suggestions
    should score against different, DOF-weighted mixtures of real (here,
    faked-out) Materials-Project PDFs, instead of the same static G(r)
    every time.
    """
    r_ref = np.linspace(1.0, 25.0, 5)
    gr_wanted = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    gr_unwanted = np.array([5.0, 4.0, 3.0, 2.0, 1.0])
    mock_mp_user_cls.return_value.load.return_value = (
        r_ref,
        np.column_stack([gr_wanted, gr_unwanted]),
    )

    phases = [
        Phase(name="Wanted", gr="unused.gr", cif="unused.cif", minimize=False),
        Phase(name="Unwanted", gr="unused.gr", cif="unused.cif", minimize=True),
    ]
    dof_for_phase = {"Wanted": "infusion_rate_CsPb", "Unwanted": "infusion_rate_Br"}

    tiled_client, sandbox_client = build_simulated_tiled_clients(
        RE, phases=phases, dof_for_phase=dof_for_phase
    )
    mock_mp_user_cls.assert_called_once()
    call_kwargs = mock_mp_user_cls.call_args.kwargs
    assert call_kwargs["formulas"] == ["Wanted", "Unwanted"]
    # Defaults should be the cheaper ones, not MPAPIUser's own qstep=0.01/
    # rstep=0.01/r=(1.0, 30.0) -- see chat re: _debye_sum's O(n_atoms**2 *
    # n_q_points) cost.
    assert call_kwargs["qstep"] == 0.05
    assert call_kwargs["rstep"] == 0.05
    assert call_kwargs["r"] == (1.0, 22.0)

    pump = FakePump(name="dds2_p1")
    context = XrayPlanContext(
        led=Signal(name="led", value="Low"),
        fast_shutter=Signal(name="fast_shutter", value=20),
        xray_detector=FakeAreaDetector(name="xray_detector"),
        wrap_xray_run=lambda plan, no_dark: plan,
        sources=(
            FlowSource(
                dof="infusion_rate_CsPb",
                pump=pump,
                precursor="CsPbOA",
                sample_label="CsPb",
            ),
        ),
        dilutions=(),
        wash_cycles=(),
        mixer_lengths_cm=(0.0,),
        residence_time_ratio=0.0,
        xray=XraySettings(exposure=0.1, frame_acq_time=0.1),
    )
    plan = create_xray_plan(context)

    result = RE(plan([{"_id": 1, "infusion_rate_CsPb": 25.0}], []))
    run_uid = result.plan_result

    # Only infusion_rate_CsPb was suggested -- Br's weight is 0, so the
    # mixture should be exactly the "Wanted" phase's own PDF.
    stored = sandbox_client[run_uid]["scattering"].read()
    np.testing.assert_allclose(stored["gr_G"].values, gr_wanted)
    np.testing.assert_allclose(stored["gr_r"].values, r_ref)
    assert run_uid in tiled_client.runs


@patch("xpd_tools.optimization.simulation.tiled.MPAPIUser")
def test_build_simulated_tiled_clients_synthesizes_pl_peak_from_band_gap(
    mock_mp_user_cls: Any,
    RE: RunEngine,
    plan_context_factory: Any,
) -> None:
    """The band-gap extension: tiled_client's fluorescence spectrum should
    be a synthetic Gaussian at 1240/mixed_band_gap_eV, not whatever the
    (zero-valued) simulated qepro actually produced.
    """
    r_ref = np.linspace(1.0, 25.0, 5)
    mock_mp_user_cls.return_value.load.return_value = (
        r_ref,
        np.column_stack([np.ones(5), np.ones(5)]),
    )
    mock_mp_user_cls.return_value.band_gaps.return_value = {
        "Wanted": 2.0,
        "Unwanted": 4.0,
    }

    phases = [
        Phase(name="Wanted", gr="unused.gr", cif="unused.cif", minimize=False),
        Phase(name="Unwanted", gr="unused.gr", cif="unused.cif", minimize=True),
    ]
    dof_for_phase = {"Wanted": "infusion_rate_CsPb", "Unwanted": "infusion_rate_Br"}

    tiled_client, _sandbox_client = build_simulated_tiled_clients(
        RE, phases=phases, dof_for_phase=dof_for_phase
    )

    context = plan_context_factory(
        quality=QualityPolicy(enabled=False, absorbance_shots=1, fluorescence_shots=1)
    )
    plan = create_xray_uvvis_plan(context)
    result = RE(
        plan(
            [
                {
                    "_id": 1,
                    "infusion_rate_CsPb": 30.0,
                    "infusion_rate_Br": 0.0,
                    "infusion_rate_I2": 0.0,
                }
            ],
            [],
        )
    )
    run_uid = result.plan_result

    # Only infusion_rate_CsPb was suggested -- Br's weight is 0, so the
    # mixed band gap should be exactly "Wanted"'s (2.0 eV).
    fl = tiled_client[run_uid]["fluorescence"].read()
    x_axis = fl["QEPro_x_axis"].values
    expected = _synthesize_pl_spectrum(x_axis, 1240.0 / 2.0, 20.0, 5000.0)
    np.testing.assert_allclose(fl["QEPro_output"].values, expected)

    # Absorbance is also synthesized -- a sigmoid edge plateauing at
    # absorbance_value, not a flat line (see _synthesize_absorbance_edge).
    abs_ = tiled_client[run_uid]["absorbance"].read()
    expected_absorbance = _synthesize_absorbance_edge(
        abs_["QEPro_x_axis"].values, 0.3, 350.0, 30.0
    )
    np.testing.assert_allclose(abs_["QEPro_output"].values, expected_absorbance)


@patch("xpd_tools.optimization.simulation.tiled.MPAPIUser")
def test_build_simulated_tiled_clients_makes_plqy_finite_end_to_end(
    mock_mp_user_cls: Any,
    RE: RunEngine,
    plan_context_factory: Any,
) -> None:
    """Before absorbance synthesis, log_PLQY always hit helpers.qepro's
    1e-10 failure floor (ln(1e-10) ~= -23.0259) because the simulated
    qepro's real absorbance output was flat zero. With a real (if
    synthetic) absorbance spectrum, UvvisEvaluation's actual PLQY fit
    should now produce a real, sane (not just finite) value.

    A flat (constant) absorbance spectrum isn't enough on its own:
    helpers.analysis.correct_absorbance's linear baseline fit reproduces
    a flat line almost exactly, leaving a machine-epsilon residual whose
    *sign* is float noise -- calculate_plqy's division by that either
    blows up to a physically nonsensical PLQY (e.g. ~1e15, log~34) or
    goes negative and re-triggers the same 1e-10 floor. Bounding
    log_PLQY to a sane range here catches that regression; `!= 1e-10`
    alone would not have.
    """
    r_ref = np.linspace(1.0, 25.0, 5)
    mock_mp_user_cls.return_value.load.return_value = (
        r_ref,
        np.column_stack([np.ones(5), np.ones(5)]),
    )
    mock_mp_user_cls.return_value.band_gaps.return_value = {
        "Wanted": 2.0,
        "Unwanted": 4.0,
    }

    phases = [
        Phase(name="Wanted", gr="unused.gr", cif="unused.cif", minimize=False),
        Phase(name="Unwanted", gr="unused.gr", cif="unused.cif", minimize=True),
    ]
    dof_for_phase = {"Wanted": "infusion_rate_CsPb", "Unwanted": "infusion_rate_Br"}

    tiled_client, _sandbox_client = build_simulated_tiled_clients(
        RE, phases=phases, dof_for_phase=dof_for_phase
    )

    context = plan_context_factory(
        quality=QualityPolicy(enabled=False, absorbance_shots=1, fluorescence_shots=1)
    )
    plan = create_xray_uvvis_plan(context)
    result = RE(
        plan(
            [
                {
                    "_id": 1,
                    "infusion_rate_CsPb": 30.0,
                    "infusion_rate_Br": 0.0,
                    "infusion_rate_I2": 0.0,
                }
            ],
            [],
        )
    )
    run_uid = result.plan_result

    evaluation = UvvisEvaluation(
        tiled_client,
        plqy=PlqyReference(
            excitation_wavelength_nm=365,
            absorbance=0.361,
            pl_integral=952628,
            refractive_index=1.337,
            plqy=0.546,
            solvent_refractive_index=1.506,
        ),
        peak_target=1240.0 / 2.0,
    )
    outcomes = evaluation(run_uid, [{"_id": 1}])

    log_plqy = outcomes[0]["log_PLQY"]
    assert np.isfinite(log_plqy)
    # A real PLQY is in (0, 1], i.e. log_PLQY <= 0 -- generously bounded
    # below too, to catch a division-by-near-zero blowup either way.
    assert -20.0 < log_plqy <= 5.0


@patch("xpd_tools.optimization.simulation.tiled.MPAPIUser")
def test_build_simulated_tiled_clients_mixes_per_phase_fwhm_and_absorbance(
    mock_mp_user_cls: Any,
    RE: RunEngine,
    plan_context_factory: Any,
) -> None:
    """pl_fwhm_nm/absorbance_value as {phase_name: value} mappings should
    mix by the same weights as the band gap, not stay fixed constants.
    """
    r_ref = np.linspace(1.0, 25.0, 5)
    mock_mp_user_cls.return_value.load.return_value = (
        r_ref,
        np.column_stack([np.ones(5), np.ones(5)]),
    )
    mock_mp_user_cls.return_value.band_gaps.return_value = {
        "Wanted": 2.0,
        "Unwanted": 4.0,
    }

    phases = [
        Phase(name="Wanted", gr="unused.gr", cif="unused.cif", minimize=False),
        Phase(name="Unwanted", gr="unused.gr", cif="unused.cif", minimize=True),
    ]
    dof_for_phase = {"Wanted": "infusion_rate_CsPb", "Unwanted": "infusion_rate_Br"}

    tiled_client, _sandbox_client = build_simulated_tiled_clients(
        RE,
        phases=phases,
        dof_for_phase=dof_for_phase,
        pl_fwhm_nm={"Wanted": 10.0, "Unwanted": 30.0},
        absorbance_value={"Wanted": 0.2, "Unwanted": 0.6},
    )

    context = plan_context_factory(
        quality=QualityPolicy(enabled=False, absorbance_shots=1, fluorescence_shots=1)
    )
    plan = create_xray_uvvis_plan(context)
    result = RE(
        plan(
            [
                {
                    "_id": 1,
                    # Equal weight this time -- 0.5/0.5 mix.
                    "infusion_rate_CsPb": 10.0,
                    "infusion_rate_Br": 10.0,
                    "infusion_rate_I2": 0.0,
                }
            ],
            [],
        )
    )
    run_uid = result.plan_result

    fl = tiled_client[run_uid]["fluorescence"].read()
    expected_fwhm = 0.5 * 10.0 + 0.5 * 30.0  # == 20.0
    expected_peak_nm = 1240.0 / (0.5 * 2.0 + 0.5 * 4.0)
    expected_fl = _synthesize_pl_spectrum(
        fl["QEPro_x_axis"].values, expected_peak_nm, expected_fwhm, 5000.0
    )
    np.testing.assert_allclose(fl["QEPro_output"].values, expected_fl)

    abs_ = tiled_client[run_uid]["absorbance"].read()
    expected_absorbance = _synthesize_absorbance_edge(
        abs_["QEPro_x_axis"].values, 0.5 * 0.2 + 0.5 * 0.6, 350.0, 30.0
    )
    np.testing.assert_allclose(abs_["QEPro_output"].values, expected_absorbance)


@patch("xpd_tools.optimization.simulation.tiled.MPAPIUser")
def test_build_simulated_tiled_clients_clamps_extreme_band_gap_to_a_fittable_peak(
    mock_mp_user_cls: Any,
    RE: RunEngine,
    plan_context_factory: Any,
) -> None:
    """A large band gap (e.g. an ionic salt mixed in alongside a real
    semiconductor) can put 1240/mixed_eg well below 400nm, which
    helpers.qepro.classify_pl hardcodes as "not real PL" and discards --
    silently reproducing the same Peak=0.0 failure floor this whole
    feature was built to avoid. The clamp must keep it fittable.
    """
    r_ref = np.linspace(1.0, 25.0, 5)
    mock_mp_user_cls.return_value.load.return_value = (
        r_ref,
        np.column_stack([np.ones(5), np.ones(5)]),
    )
    # 10 eV -> 124nm unclamped -- far below classify_pl's 400nm floor.
    mock_mp_user_cls.return_value.band_gaps.return_value = {
        "Wanted": 10.0,
        "Unwanted": 10.0,
    }

    phases = [
        Phase(name="Wanted", gr="unused.gr", cif="unused.cif", minimize=False),
        Phase(name="Unwanted", gr="unused.gr", cif="unused.cif", minimize=True),
    ]
    dof_for_phase = {"Wanted": "infusion_rate_CsPb", "Unwanted": "infusion_rate_Br"}

    tiled_client, _sandbox_client = build_simulated_tiled_clients(
        RE, phases=phases, dof_for_phase=dof_for_phase
    )

    context = plan_context_factory(
        quality=QualityPolicy(enabled=False, absorbance_shots=1, fluorescence_shots=1)
    )
    plan = create_xray_uvvis_plan(context)
    result = RE(
        plan(
            [
                {
                    "_id": 1,
                    "infusion_rate_CsPb": 30.0,
                    "infusion_rate_Br": 0.0,
                    "infusion_rate_I2": 0.0,
                }
            ],
            [],
        )
    )
    run_uid = result.plan_result

    fl = tiled_client[run_uid]["fluorescence"].read()
    x_axis = fl["QEPro_x_axis"].values.reshape(-1)
    output = fl["QEPro_output"].values.reshape(-1)
    assert x_axis[int(np.argmax(output))] >= 400.0

    evaluation = UvvisEvaluation(
        tiled_client,
        plqy=PlqyReference(
            excitation_wavelength_nm=365,
            absorbance=0.361,
            pl_integral=952628,
            refractive_index=1.337,
            plqy=0.546,
            solvent_refractive_index=1.506,
        ),
        peak_target=450,
    )
    outcomes = evaluation(run_uid, [{"_id": 1}])
    assert outcomes[0]["Peak"] != 0.0


@patch("xpd_tools.optimization.simulation.tiled.MPAPIUser")
def test_build_simulated_tiled_clients_pl_phases_restricts_pl_mix(
    mock_mp_user_cls: Any,
    RE: RunEngine,
    plan_context_factory: Any,
) -> None:
    """pl_phases=("Wanted",) should make PL depend only on Wanted's band
    gap/FWHM, even though Wanted/Unwanted are 0.5/0.5 in the full mix
    (used for absorbance, unaffected by pl_phases).
    """
    r_ref = np.linspace(1.0, 25.0, 5)
    mock_mp_user_cls.return_value.load.return_value = (
        r_ref,
        np.column_stack([np.ones(5), np.ones(5)]),
    )
    mock_mp_user_cls.return_value.band_gaps.return_value = {
        "Wanted": 2.0,
        "Unwanted": 10.0,
    }

    phases = [
        Phase(name="Wanted", gr="unused.gr", cif="unused.cif", minimize=False),
        Phase(name="Unwanted", gr="unused.gr", cif="unused.cif", minimize=True),
    ]
    dof_for_phase = {"Wanted": "infusion_rate_CsPb", "Unwanted": "infusion_rate_Br"}

    tiled_client, _sandbox_client = build_simulated_tiled_clients(
        RE,
        phases=phases,
        dof_for_phase=dof_for_phase,
        pl_phases=("Wanted",),
        pl_fwhm_nm={"Wanted": 10.0, "Unwanted": 30.0},
        absorbance_value={"Wanted": 0.2, "Unwanted": 0.6},
    )

    context = plan_context_factory(
        quality=QualityPolicy(enabled=False, absorbance_shots=1, fluorescence_shots=1)
    )
    plan = create_xray_uvvis_plan(context)
    result = RE(
        plan(
            [
                {
                    "_id": 1,
                    # Equal weight -- would pull the peak far below classify_pl's
                    # 400nm floor without pl_phases restricting the PL mix.
                    "infusion_rate_CsPb": 10.0,
                    "infusion_rate_Br": 10.0,
                    "infusion_rate_I2": 0.0,
                }
            ],
            [],
        )
    )
    run_uid = result.plan_result

    fl = tiled_client[run_uid]["fluorescence"].read()
    expected_fl = _synthesize_pl_spectrum(
        fl["QEPro_x_axis"].values, 1240.0 / 2.0, 10.0, 5000.0
    )
    np.testing.assert_allclose(fl["QEPro_output"].values, expected_fl)

    # Absorbance still mixes over all phases -- unaffected by pl_phases.
    abs_ = tiled_client[run_uid]["absorbance"].read()
    expected_absorbance = _synthesize_absorbance_edge(
        abs_["QEPro_x_axis"].values, 0.5 * 0.2 + 0.5 * 0.6, 350.0, 30.0
    )
    np.testing.assert_allclose(abs_["QEPro_output"].values, expected_absorbance)
