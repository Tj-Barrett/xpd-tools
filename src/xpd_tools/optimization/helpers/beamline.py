"""Common beamline configuration utilities."""

from dataclasses import dataclass
from typing import Any, Callable

from .plans import DilutionStage, FlowSource, WashCycle

@dataclass(frozen=True, kw_only=True)
class XraySettings:
    """X-ray detector acquisition settings."""

    exposure: float = 5.0
    frame_acq_time: float = 0.2
    no_dark: bool = True


@dataclass(frozen=True, kw_only=True)
class XrayUvvisPlanContext:
    """Static hardware and process configuration for one bound plan."""

    qepro: Any
    led: Any
    uv_shutter: Any
    fast_shutter: Any
    xray_detector: Any
    wrap_xray_run: Callable[[Any, bool], Any]
    sources: tuple[FlowSource, ...]
    dilutions: tuple[DilutionStage, ...]
    wash_cycles: tuple[WashCycle, ...]
    mixer_lengths_cm: tuple[float, ...] = (30.0,)
    residence_time_ratio: float = 1.0
    quality: QualityPolicy = QualityPolicy()
    xray: XraySettings = XraySettings()
