"""Common beamline configuration utilities."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .qepro import QualityPolicy
from .sources import DilutionStage, FlowSource, WashCycle


@dataclass(frozen=True, kw_only=True)
class XraySettings:
    """X-ray detector acquisition settings."""

    exposure: float = 5.0
    frame_acq_time: float = 0.2
    no_dark: bool = True
    stream_name: str = "scattering"


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

@dataclass(frozen=True, kw_only=True)
class XrayPlanContext:
    """Static hardware and process configuration for one bound plan."""

    led: Any
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

@dataclass(frozen=True, kw_only=True)
class UvvisPlanContext:
    """Static hardware and process configuration for one bound plan."""

    qepro: Any
    led: Any
    uv_shutter: Any
    fast_shutter: Any
    sources: tuple[FlowSource, ...]
    dilutions: tuple[DilutionStage, ...]
    wash_cycles: tuple[WashCycle, ...]
    mixer_lengths_cm: tuple[float, ...] = (30.0,)
    residence_time_ratio: float = 1.0
    quality: QualityPolicy = QualityPolicy()
