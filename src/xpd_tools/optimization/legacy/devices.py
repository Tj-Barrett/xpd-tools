"""Simulated ophyd devices matching the shape `plans/runtime.py` needs.

Not faithful copies of the real `xpd-profile-collection` device classes
(real PV prefixes, full component trees) -- that repo is being deprecated,
and there is no real hardware to be faithful to. These expose only the
attributes/methods the acquisition plans actually touch: `set_infuse2`/
`infuse_pump2`/`stop_pump2`/`status` for pumps, `cam.acquire_time`/
`images_per_set`/trigger-and-read for the detector, trigger-and-read for
qepro.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from bluesky import plan_stubs as bps
from ophyd import Component as Cpt
from ophyd import Device, Signal
from ophyd.status import DeviceStatus


class FakeQEPro(Device):
    """Simulated QEPro spectrometer: triggers pop a pre-loaded spectrum."""

    x_axis = Cpt(Signal, value=np.linspace(200.0, 950.0, 751))
    output = Cpt(Signal, value=np.zeros(751))
    spectrum_type = Cpt(Signal, value="Corrected Sample")
    correction = Cpt(Signal, value="Dark")

    def __init__(
        self,
        *args: Any,
        spectra: Sequence[np.ndarray] | None = None,
        fail_on_trigger: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.spectra = list(spectra or [])
        self.fail_on_trigger = fail_on_trigger
        self.trigger_count = 0

    def trigger(self) -> DeviceStatus:
        self.trigger_count += 1
        status = DeviceStatus(self)
        if self.fail_on_trigger == self.trigger_count:
            status.set_exception(RuntimeError("QEPro trigger failed"))
            return status
        if self.spectra:
            spectrum = self.spectra.pop(0)
            self.output.put(np.asarray(spectrum, dtype=float))
        status.set_finished()
        return status


class FakePump(Device):
    """Simulated New Era syringe pump: set_infuse2/infuse_pump2/stop_pump2."""

    read_infuse_rate = Cpt(Signal, value=0.0)
    read_infuse_rate_unit = Cpt(Signal, value="ul/min")
    status = Cpt(Signal, value="Stopped")

    def __init__(
        self,
        *args: Any,
        fail_start: bool = False,
        fail_stop_call: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fail_start = fail_start
        self.fail_stop_call = fail_stop_call
        self.configurations: list[dict[str, Any]] = []
        self.start_count = 0
        self.stop_count = 0

    def set_infuse2(
        self,
        input_size: float,
        *,
        syringe_material: str,
        set_target: bool,
        target_vol: float,
        target_unit: str,
        infuse_rate: float,
        infuse_unit: str,
    ):
        self.configurations.append(
            {
                "input_size": input_size,
                "syringe_material": syringe_material,
                "set_target": set_target,
                "target_vol": target_vol,
                "target_unit": target_unit,
                "infuse_rate": infuse_rate,
                "infuse_unit": infuse_unit,
            }
        )
        yield from bps.mv(
            self.read_infuse_rate,
            infuse_rate,
            self.read_infuse_rate_unit,
            infuse_unit,
        )

    def infuse_pump2(self):
        self.start_count += 1
        if self.fail_start:
            raise RuntimeError(f"failed to start {self.name}")
        yield from bps.mv(self.status, "Infusing")

    def stop_pump2(self):
        self.stop_count += 1
        if self.fail_stop_call == self.stop_count:
            raise RuntimeError(f"failed to stop {self.name}")
        yield from bps.mv(self.status, "Stopped")


class FakeAreaDetector(Device):
    """Simulated X-ray area detector: just enough for trigger_and_read."""

    class Cam(Device):
        """Simulated cam plugin exposing acquire_time."""

        acquire_time = Cpt(Signal, value=0.1)

    cam = Cpt(Cam, "")
    images_per_set = Cpt(Signal, value=1)
    image = Cpt(Signal, value=1.0)

    def __init__(self, *args: Any, fail_trigger: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fail_trigger = fail_trigger

    def trigger(self) -> DeviceStatus:
        status = DeviceStatus(self)
        if self.fail_trigger:
            status.set_exception(RuntimeError("X-ray trigger failed"))
        else:
            status.set_finished()
        return status


# Pump ids matching this package's own examples (examples/halide_example_class.ipynb,
# tests/optimization/conftest.py's fake_pumps) -- not any particular real beamline's
# device names, since xpd-profile-collection (which owned those) is being deprecated.
_PUMP_IDS = ("dds1_p1", "dds2_p1", "dds2_p2", "dds3_p1", "dds3_p2", "ultra1", "ultra2")


def build_xpd_objects() -> dict[str, Any]:
    """Build a full set of simulated devices for `BuildAgent.build_local()`.

    For verifying an agent config actually builds and its acquisition plan
    actually runs locally (no Queue Server, ZMQ proxy, or real beamline
    hardware) -- not for driving real hardware. Returns a `devices` mapping
    shaped exactly as `build_local()` expects: "led", "uv_shutter",
    "fast_shutter", "qepro", "xray_detector", plus one simulated pump per
    id in `_PUMP_IDS`.
    """
    devices: dict[str, Any] = {
        "led": Signal(name="led", value="Low"),
        "uv_shutter": Signal(name="uv_shutter", value="Low"),
        "fast_shutter": Signal(name="fast_shutter", value=20),
        "qepro": FakeQEPro(name="QEPro"),
        "xray_detector": FakeAreaDetector(name="xray_detector"),
    }
    devices.update({pump_id: FakePump(name=pump_id) for pump_id in _PUMP_IDS})
    return devices


def identity_wrap_xray_run(plan: Any, no_dark: bool) -> Any:
    """Passthrough `wrap_xray_run`.

    No real X-ray safety wrapping needed against simulated devices.
    `build_local()` has no default for this (real usage needs
    caller-owned safety logic); this is the local/simulated-testing
    equivalent.
    """
    del no_dark
    return plan
