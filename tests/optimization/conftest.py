from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from bluesky.run_engine import RunEngine
from ophyd import Signal

from xpd_tools.optimization.legacy.devices import FakeAreaDetector, FakePump, FakeQEPro
from xpd_tools.optimization.legacy.tiled import (
    FakeTiledCatalog,
    FakeTiledRun,
    FakeTiledStream,
    run_from_documents,
)
from xpd_tools.optimization.plans import (
    DilutionStage,
    FlowSource,
    QualityPolicy,
    SpectraFitSettings,
    WashCycle,
    XraySettings,
    XrayUvvisPlanContext,
)


@pytest.fixture
def tiled_fakes() -> SimpleNamespace:
    return SimpleNamespace(
        Stream=FakeTiledStream,
        Run=FakeTiledRun,
        Catalog=FakeTiledCatalog,
        run_from_documents=run_from_documents,
    )


@pytest.fixture
def wavelength() -> np.ndarray:
    return np.arange(200.0, 951.0)


@pytest.fixture
def good_spectrum(wavelength: np.ndarray) -> np.ndarray:
    return 5000 * np.exp(-((wavelength - 660) ** 2) / (2 * 20**2))


@pytest.fixture
def bad_spectrum(wavelength: np.ndarray) -> np.ndarray:
    return 20 * np.exp(-((wavelength - 630) ** 2) / (2 * 20**2))


@pytest.fixture
def fake_qepro(
    wavelength: np.ndarray,
    good_spectrum: np.ndarray,
) -> FakeQEPro:
    device = FakeQEPro(name="QEPro", spectra=[good_spectrum] * 20)
    device.x_axis.put(wavelength)
    device.output.put(good_spectrum)
    return device


@pytest.fixture
def fake_pumps() -> dict[str, FakePump]:
    names = ("dds2_p1", "dds2_p2", "dds3_p1", "dds1_p1", "ultra2", "ultra1")
    return {name: FakePump(name=name) for name in names}


@pytest.fixture
def fake_area_detector() -> FakeAreaDetector:
    return FakeAreaDetector(name="xray_detector")


@pytest.fixture
def optical_signals() -> tuple[Signal, Signal, Signal]:
    return (
        Signal(name="led", value="Low"),
        Signal(name="uv_shutter", value="Low"),
        Signal(name="fast_shutter", value=20),
    )


@pytest.fixture
def documents(RE: RunEngine) -> list[tuple[str, dict[str, Any]]]:
    collected: list[tuple[str, dict[str, Any]]] = []
    RE.subscribe(lambda name, doc: collected.append((name, doc)))
    return collected


@pytest.fixture
def reference_config_factory(
    tmp_path: Path,
) -> Callable[..., Path]:

    def factory(
        phases: Sequence[tuple[str, bool]] = (("Target", False),),
        *,
        include_cif: bool = True,
    ) -> Path:
        radial = np.linspace(1.0, 25.0, 241)
        payload: list[dict[str, Any]] = []
        for index, (name, minimize) in enumerate(phases):
            gr_path = tmp_path / f"{name}.gr"
            np.savetxt(gr_path, np.column_stack((radial, np.sin(radial + index))))
            phase: dict[str, Any] = {
                "name": name,
                "gr_path": gr_path.name,
                "minimize": minimize,
            }
            if include_cif:
                cif_path = tmp_path / f"{name}.cif"
                cif_path.write_text(
                    "data_test\n"
                    "_symmetry_space_group_name_H-M 'P 1'\n"
                    "_cell_length_a 6\n_cell_length_b 6\n_cell_length_c 6\n"
                    "_cell_angle_alpha 90\n_cell_angle_beta 90\n"
                    "_cell_angle_gamma 90\n"
                    "loop_\n_atom_site_label\n_atom_site_type_symbol\n"
                    "_atom_site_fract_x\n_atom_site_fract_y\n"
                    "_atom_site_fract_z\nCs1 Cs 0 0 0\n"
                )
                phase["cif_path"] = cif_path.name
            payload.append(phase)
        config_path = tmp_path / "references.json"
        config_path.write_text(json.dumps({"schema_version": 1, "phases": payload}))
        return config_path

    return factory


@pytest.fixture
def plan_context_factory(
    fake_qepro: FakeQEPro,
    fake_pumps: Mapping[str, FakePump],
    optical_signals: tuple[Signal, Signal, Signal],
    fake_area_detector: FakeAreaDetector,
) -> Callable[..., XrayUvvisPlanContext]:
    led, uv_shutter, fast_shutter = optical_signals
    default_quality = QualityPolicy(
        enabled=False, absorbance_shots=1, fluorescence_shots=1
    )

    def identity_wrapper(plan: Any, no_dark: bool):
        return plan

    def factory(
        *,
        sources: tuple[FlowSource, ...] | None = None,
        dilutions: tuple[DilutionStage, ...] = (),
        wash_cycles: tuple[WashCycle, ...] = (),
        quality: QualityPolicy | None = None,
        xray: XraySettings | None = None,
        fit_settings: SpectraFitSettings | None = None,
        mixer_lengths_cm: tuple[float, ...] = (0.0,),
        residence_time_ratio: float = 0.0,
        wrap_xray_run: Any = None,
    ) -> XrayUvvisPlanContext:
        configured_sources = sources
        if configured_sources is None:
            configured_sources = tuple(
                FlowSource(
                    dof=f"infusion_rate_{label}",
                    pump=fake_pumps[pump],
                    precursor=precursor,
                    sample_label=label,
                )
                for label, pump, precursor in (
                    ("CsPb", "dds2_p1", "CsPbOA"),
                    ("Br", "dds2_p2", "TOABr"),
                    ("I2", "dds3_p1", "ZnI2"),
                )
            )
        return XrayUvvisPlanContext(
            qepro=fake_qepro,
            led=led,
            uv_shutter=uv_shutter,
            fast_shutter=fast_shutter,
            xray_detector=fake_area_detector,
            wrap_xray_run=wrap_xray_run or identity_wrapper,
            sources=configured_sources,
            dilutions=dilutions,
            wash_cycles=wash_cycles,
            mixer_lengths_cm=mixer_lengths_cm,
            residence_time_ratio=residence_time_ratio,
            quality=quality or default_quality,
            xray=xray or XraySettings(),
            fit_settings=fit_settings or SpectraFitSettings(),
        )

    return factory
