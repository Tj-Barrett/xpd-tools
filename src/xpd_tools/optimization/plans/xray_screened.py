"""Bound Queue Server acquisition plan for UV-Vis-screened X-ray runs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp

from ..helpers.beamline import XrayUvvisPlanContext
from .metadata import _build_run_metadata
from .preflight import _preflight
from .runtime import (
    _cleanup_devices,
    _configure_and_start,
    _measure_pl_with_quality_gate,
    _measure_scattering,
    _new_quality_signals,
    _prepare_xray_detector,
    _stop_running,
    _unique_devices,
    _wait_for_equilibrium,
    _with_safe_cleanup,
)
from .validation import _validate_context


def create_xray_screened_plan(context: XrayUvvisPlanContext) -> Callable[..., Any]:
    """Bind validated hardware once and return the Queue Server acquisition plan.

    Runs the UV-Vis fluorescence quality gate to decide whether the sample is
    worth committing X-ray beamtime to, but never measures absorbance and
    never records UV-Vis data as an optimization objective -- pair this plan
    with ``XrayEvaluation`` (PDF-only), not ``XrayUvvisEvaluation``.
    """
    _validate_context(context)
    quality_signals = _new_quality_signals()

    def xray_screened_acquire(
        suggestions: Sequence[Mapping[str, Any]],
        actuators: Sequence[Any],
        sensors: Sequence[Any] | None = None,
        md: Mapping[str, Any] | None = None,
    ):
        """Acquire one UV-Vis-screened X-ray optimization run."""
        del actuators, sensors
        rates = _preflight(context, suggestions)
        detector_metadata = yield from _prepare_xray_detector(context)
        run_metadata = _build_run_metadata(
            context,
            rates,
            md,
            detector_metadata,
        )
        started: list[Any] = []

        def cleanup():
            yield from _cleanup_devices(context, started)

        def acquisition():
            all_pumps = _unique_devices(
                [
                    *(source.pump for source in context.sources),
                    *(stage.pump for stage in context.dilutions),
                    *(cycle.pump for cycle in context.wash_cycles),
                ]
            )
            for pump in all_pumps:
                yield from pump.stop_pump2()

            yield from _configure_and_start(
                tuple(zip(context.sources, rates, strict=True)),
                started,
            )
            total_rate = sum(rates)
            dilution_settings = tuple(
                (stage, total_rate * stage.ratio) for stage in context.dilutions
            )
            before = tuple(
                item
                for item in dilution_settings
                if item[0].position == "before_equilibrium"
            )
            after = tuple(
                item
                for item in dilution_settings
                if item[0].position == "after_equilibrium"
            )
            yield from _configure_and_start(before, started)
            for stage, rate in before:
                if rate > 0 and stage.wait_sec:
                    yield from bps.sleep(stage.wait_sec)

            yield from _wait_for_equilibrium(
                tuple(source.pump for source in context.sources),
                context.mixer_lengths_cm,
                ratio=context.residence_time_ratio,
            )

            yield from _configure_and_start(after, started)
            for stage, rate in after:
                if rate > 0 and stage.wait_sec:
                    yield from bps.sleep(stage.wait_sec)

            yield from _measure_pl_with_quality_gate(context, quality_signals)
            yield from bps.mv(context.led, "Low", context.uv_shutter, "Low")

            yield from context.wrap_xray_run(
                _measure_scattering(context),
                context.xray.no_dark,
            )

            yield from _stop_running(tuple(started), started)
            for cycle in context.wash_cycles:
                yield from _configure_and_start(
                    ((cycle, cycle.rate_ul_min),),
                    started,
                )
                if cycle.rate_ul_min > 0 and cycle.duration_sec:
                    yield from bps.sleep(cycle.duration_sec)
                yield from _stop_running((cycle.pump,), started)

        plan = bpp.stage_wrapper(acquisition(), [context.qepro, context.xray_detector])
        plan = bpp.baseline_wrapper(
            plan, _unique_devices([source.pump for source in context.sources])
        )
        plan = _with_safe_cleanup(plan, cleanup)
        plan = bpp.run_wrapper(plan, md=run_metadata)
        plan = bpp.set_run_key_wrapper(plan, "xray_screened_acquire")
        return (yield from plan)

    return xray_screened_acquire
