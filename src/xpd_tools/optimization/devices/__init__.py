"""Real regular-ophyd device classes for the 28-ID-2 C-hutch halide perovskite rig.

Device subpackage layout:
  pumps.py   -- syrng_DDS / syrng_DDS_ax (Harvard DDS) and syrng_ultra (Harvard Ultra)
  qepro.py   -- QEPro spectrometer
  lights.py  -- LED, UV_shutter, fast shutter (EpicsMotor)

The factory `build_halide_devices` returns a dict keyed by the same pump-id
strings used in the experiment config (`FlowSource.pump`, etc.) so it can be
passed directly to `BuildAgent.build_local` or `BuildAgent.register_acquisition_plans`.
"""

from __future__ import annotations

from typing import Any

from xpd_tools.optimization.devices.lights import LED, FastShutter, UVShutter
from xpd_tools.optimization.devices.pumps import syrng_DDS, syrng_DDS_ax, syrng_ultra
from xpd_tools.optimization.devices.qepro import QEPro

__all__ = [
    "FastShutter",
    "LED",
    "QEPro",
    "UVShutter",
    "build_halide_devices",
    "check_halide_connections",
    "syrng_DDS",
    "syrng_DDS_ax",
    "syrng_ultra",
]

# PV prefixes for the C-hutch flow rig (XF:28IDC-ES:1)
_DDS1_PREFIX = "XF:28IDC-ES:1{Pump:Syrng-DDS:1"
_DDS2_PREFIX = "XF:28IDC-ES:1{Pump:Syrng-DDS:2"
_DDS3_PREFIX = "XF:28IDC-ES:1{Pump:Syrng-DDS:3"
_ULTRA1_PREFIX = "XF:28IDC-ES:1{Pump:Syrng-Ultra:1}:"
_ULTRA2_PREFIX = "XF:28IDC-ES:1{Pump:Syrng-Ultra:2}:"
_QEPRO_PREFIX = "XF:28ID2-ES{QEPro:Spec-1}:"
_LED_PV = "XF:28IDC-ES:1{Light:Flu-LED:1}Cmd"
_UV_SHUTTER_PV = "XF:28IDC-ES:1{Light:Abs-Sht:1}Cmd"
_FAST_SHUTTER_PV = "XF:28IDC-ES:1{Sh2:Exp-Ax:5}Mtr"


def build_halide_devices(*, mock: bool = False) -> dict[str, Any]:
    """Instantiate every device needed for a halide UV-Vis (or xray-uvvis) campaign.

    Returns a dict keyed by the pump-id strings used in experiment config
    (`FlowSource.pump`, `DilutionStage.pump`, `WashCycle.pump`) plus the
    named optical/detector devices:

        dds1_p1, dds2_p1, dds2_p2, dds3_p1, dds3_p2  -- DDS pump axes
        ultra1, ultra2                                  -- Ultra pump axes
        qepro                                           -- QEPro spectrometer
        led                                             -- fluorescence LED
        uv_shutter                                      -- absorbance shutter
        fast_shutter                                    -- beam fast-shutter motor

    Parameters
    ----------
    mock:
        When True return simulated devices (`legacy.devices.build_xpd_objects()`)
        instead of real EPICS-connected ones.  Useful for offline testing.
    """
    if mock:
        from xpd_tools.optimization.legacy.devices import build_xpd_objects
        return build_xpd_objects()

    dds1 = syrng_DDS(_DDS1_PREFIX, name="DDS1")
    dds2 = syrng_DDS(_DDS2_PREFIX, name="DDS2")
    dds3 = syrng_DDS(_DDS3_PREFIX, name="DDS3")

    return {
        # DDS pump axes  (note: PV strings contain literal braces from IOC naming)
        "dds1_p1": syrng_DDS_ax(
            _DDS1_PREFIX + "-Ax:A}",
            name="DDS1_p1",
            parent=dds1,
        ),
        "dds1_p2": syrng_DDS_ax(
            _DDS1_PREFIX + "-Ax:B}",
            name="DDS1_p2",
            parent=dds1,
        ),
        "dds2_p1": syrng_DDS_ax(
            _DDS2_PREFIX + "-Ax:A}",
            name="DDS2_p1",
            parent=dds2,
        ),
        "dds2_p2": syrng_DDS_ax(
            _DDS2_PREFIX + "-Ax:B}",
            name="DDS2_p2",
            parent=dds2,
        ),
        "dds3_p1": syrng_DDS_ax(
            _DDS3_PREFIX + "-Ax:A}",
            name="DDS3_p1",
            parent=dds3,
        ),
        "dds3_p2": syrng_DDS_ax(
            _DDS3_PREFIX + "-Ax:B}",
            name="DDS3_p2",
            parent=dds3,
        ),
        # Ultra pump axes
        "ultra1": syrng_ultra(_ULTRA1_PREFIX, name="Pump_Ultra1"),
        "ultra2": syrng_ultra(_ULTRA2_PREFIX, name="Pump_Ultra2"),
        # Spectrometer
        "qepro": QEPro(_QEPRO_PREFIX, name="QEPro"),
        # Lights and shutters
        "led": LED(_LED_PV, name="LED_M365LP1"),
        "uv_shutter": UVShutter(_UV_SHUTTER_PV, name="UV_shutter"),
        "fast_shutter": FastShutter(_FAST_SHUTTER_PV, name="shctl1"),
    }


class ConnectionReport:
    """Result of a single-device connection check."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.connected: bool = False
        self.readable_signals: list[str] = []
        self.failed_signals: list[str] = []
        self.error: str | None = None

    def __repr__(self) -> str:
        status = "OK" if self.connected else "FAIL"
        detail = ""
        if self.failed_signals:
            detail = f", failed PVs: {self.failed_signals}"
        if self.error:
            detail += f", error: {self.error}"
        return f"<ConnectionReport {self.name}: {status}{detail}>"


def check_halide_connections(
    devices: dict[str, Any],
    *,
    timeout: float = 10.0,
) -> dict[str, ConnectionReport]:
    """Validate EPICS connectivity for every device in *devices*.

    Performs **read-only** probes only — no set, no trigger, no plan execution.
    Calls ``wait_for_connection`` on each device then does a ``.get()`` on the
    signals the acquisition plans actually depend on.

    Parameters
    ----------
    devices:
        Dict as returned by ``build_halide_devices()``.
    timeout:
        Per-device connection timeout in seconds.

    Returns
    -------
    dict mapping device key → ConnectionReport.  A non-empty ``.failed_signals``
    or a False ``.connected`` indicates a problem.
    """
    import logging

    logger = logging.getLogger(__name__)

    # Signals each device role must expose for the plans to work
    _required_signals: dict[str, list[str]] = {
        # pump keys (DDS and Ultra share the same interface)
        "dds1_p1": ["status", "read_infuse_rate", "read_infuse_rate_unit"],
        "dds1_p2": ["status", "read_infuse_rate", "read_infuse_rate_unit"],
        "dds2_p1": ["status", "read_infuse_rate", "read_infuse_rate_unit"],
        "dds2_p2": ["status", "read_infuse_rate", "read_infuse_rate_unit"],
        "dds3_p1": ["status", "read_infuse_rate", "read_infuse_rate_unit"],
        "dds3_p2": ["status", "read_infuse_rate", "read_infuse_rate_unit"],
        "ultra1": ["status", "read_infuse_rate", "read_infuse_rate_unit"],
        "ultra2": ["status", "read_infuse_rate", "read_infuse_rate_unit"],
        # spectrometer
        "qepro": ["x_axis", "output", "spectrum_type", "correction"],
        # lights / shutters -- EpicsSignal; just get() them
        "led": [],
        "uv_shutter": [],
        "fast_shutter": [],
    }

    reports: dict[str, ConnectionReport] = {}

    for key, device in devices.items():
        report = ConnectionReport(key)
        reports[key] = report

        # 1. Connection handshake
        try:
            device.wait_for_connection(timeout=timeout)
            report.connected = True
        except Exception as exc:
            report.connected = False
            report.error = str(exc)
            logger.warning("Device %s failed to connect: %s", key, exc)
            continue

        # 2. Read-only probe of plan-critical signals
        required = _required_signals.get(key, [])
        for sig_name in required:
            try:
                sig = getattr(device, sig_name)
                sig.get()
                report.readable_signals.append(sig_name)
            except Exception as exc:
                report.failed_signals.append(sig_name)
                logger.warning(
                    "Device %s signal %s unreadable: %s", key, sig_name, exc
                )

        # For plain EpicsSignal devices (led, uv_shutter) try a bare .get()
        if not required:
            try:
                device.get()
                report.readable_signals.append("(value)")
            except Exception as exc:
                report.failed_signals.append("(value)")
                logger.warning("Device %s unreadable: %s", key, exc)

    return reports


def print_connection_report(reports: dict[str, ConnectionReport]) -> bool:
    """Print a human-readable connection report and return True if all OK."""
    all_ok = True
    for key, r in reports.items():
        if r.connected and not r.failed_signals:
            print(f"  ✓  {key}")
        else:
            all_ok = False
            status = "not connected" if not r.connected else "partial"
            print(f"  ✗  {key} [{status}]")
            if r.error:
                print(f"       error: {r.error}")
            for sig in r.failed_signals:
                print(f"       failed signal: {sig}")
    return all_ok
