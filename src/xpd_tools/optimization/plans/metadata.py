"""Run metadata derivation for the X-ray/UV-Vis acquisition plan."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import fields
from typing import Any

from xpd_tools.optimization.helpers.beamline import XrayUvvisPlanContext


def _sample_name(rates: Sequence[float], labels: Sequence[str]) -> str:
    return "_".join(
        component
        for label, rate in zip(labels, rates, strict=True)
        for component in (label, f"{int(rate):03d}")
    )


def _device_name(device: Any) -> str:
    return str(device.name)


def _config_metadata(config: Any) -> dict[str, Any]:
    """Serialize one frozen configuration object, replacing a pump by its name."""
    metadata = {field.name: getattr(config, field.name) for field in fields(config)}
    if "pump" in metadata:
        metadata["pump"] = _device_name(metadata["pump"])
    return metadata


def _serialized_config(context: XrayUvvisPlanContext) -> dict[str, Any]:
    return {
        "devices": {
            "qepro": _device_name(context.qepro),
            "led": _device_name(context.led),
            "uv_shutter": _device_name(context.uv_shutter),
            "fast_shutter": _device_name(context.fast_shutter),
            "xray_detector": _device_name(context.xray_detector),
        },
        "sources": [_config_metadata(source) for source in context.sources],
        "dilutions": [_config_metadata(stage) for stage in context.dilutions],
        "wash_cycles": [_config_metadata(cycle) for cycle in context.wash_cycles],
        "mixer_lengths_cm": list(context.mixer_lengths_cm),
        "residence_time_ratio": context.residence_time_ratio,
        "quality": _config_metadata(context.quality),
        "xray": _config_metadata(context.xray),
        "fit_settings": _config_metadata(context.fit_settings),
    }


def _build_run_metadata(
    context: XrayUvvisPlanContext,
    rates: tuple[float, ...],
    supplied: Mapping[str, Any] | None,
    detector_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge caller metadata before authoritative derived metadata."""
    metadata = deepcopy(dict(supplied or {}))
    for obsolete in (
        "flow_config",
        "xray_config",
        "wash_config",
        "quality_config",
        "quality_thresholds",
    ):
        metadata.pop(obsolete, None)
    metadata.update(detector_metadata)
    sample_name = _sample_name(
        rates, tuple(source.sample_label for source in context.sources)
    )
    metadata.update(
        {
            "sample_type": sample_name,
            "sample_name": sample_name,
            "infuse_rates": list(rates),
            "dof_names": [source.dof for source in context.sources],
            "precursors": [source.precursor for source in context.sources],
            "pumps": [_device_name(source.pump) for source in context.sources],
            "detectors": [
                _device_name(context.qepro),
                _device_name(context.xray_detector),
            ],
            "xray_uvvis_config": _serialized_config(context),
            "use_good_bad": context.quality.enabled,
        }
    )
    return metadata
