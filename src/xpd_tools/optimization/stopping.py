"""Background success-threshold watcher for a running blop campaign.

Layered on top of the existing iterations= stopping mode, not a
replacement for it -- `BuildAgent.build()` + `QueueserverAgent.run(...)`
work exactly as before if you never call `set_success_criteria`/
`watch_and_stop`. When configured, a background thread polls completed
trial data and calls `agent.stop()` early once a success condition is met,
while `run()`'s own `iterations` ceiling still applies as the upper bound
either way.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from .agent import BuildAgent

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SuccessCriteria:
    """Optional early-stop thresholds for a running campaign.

    `min_correlation` and the `max_fwhm`/`min_plqy` pair are independent,
    mutually exclusive success paths -- either one being satisfied by some
    completed trial is enough to stop early, they are not combined with AND.
    """

    min_correlation: float | None = None
    max_fwhm: float | None = None
    min_plqy: float | None = None
    poll_interval: float = 5.0


def _correlation_metric_names(build_agent: "BuildAgent") -> tuple[str, ...]:
    """Names of the "wanted" (minimize=False) phase correlation metrics.

    Matches the same metric_prefix logic set_xray_objectives uses to build
    phase Objectives, so these are exactly the real outcome keys a
    completed trial will carry.
    """
    if not build_agent.phases:
        return ()
    prefix = "pdf_fit_corr_" if build_agent.pdf_mode == "fit" else "corr_"
    return tuple(
        f"{prefix}{phase.name}" for phase in build_agent.phases if not phase.minimize
    )


def watch_and_stop(
    agent: Any,
    future: "Future[Any]",
    build_agent: "BuildAgent",
) -> threading.Thread:
    """Start a background thread that stops `agent`'s campaign on success.

    Call after both `agent = build_agent.build()` and
    `future = agent.run(iterations=...)` -- polls
    `agent.ax_client.summarize(...)` every `poll_interval` seconds and
    calls `agent.stop()` as soon as any completed trial satisfies either
    configured criterion. Exits on its own, without stopping anything,
    once `future` resolves on its own (e.g. the `iterations` ceiling is
    reached first).

    Requires `build_agent.set_success_criteria(...)` to have been called.
    Returns the started thread; the caller decides whether to join it.
    """
    criteria = build_agent.success_criteria
    if criteria is None:
        raise ValueError(
            "build_agent.set_success_criteria(...) must be called before watch_and_stop()"
        )
    correlation_metrics = _correlation_metric_names(build_agent)

    def _watch() -> None:
        while not future.done():
            df = agent.ax_client.summarize(trial_statuses=["completed"])

            if criteria.min_correlation is not None:
                for metric in correlation_metrics:
                    if metric in df.columns and (df[metric] >= criteria.min_correlation).any():
                        logger.info(
                            "Success threshold reached: %s >= %s -- stopping campaign.",
                            metric,
                            criteria.min_correlation,
                        )
                        agent.stop()
                        return

            if criteria.max_fwhm is not None and criteria.min_plqy is not None:
                if {"log_FWHM", "log_PLQY"} <= set(df.columns):
                    fwhm = np.exp(df["log_FWHM"])
                    plqy = np.exp(df["log_PLQY"])
                    if ((fwhm <= criteria.max_fwhm) & (plqy >= criteria.min_plqy)).any():
                        logger.info(
                            "Success threshold reached: FWHM <= %s and PLQY >= %s -- "
                            "stopping campaign.",
                            criteria.max_fwhm,
                            criteria.min_plqy,
                        )
                        agent.stop()
                        return

            time.sleep(criteria.poll_interval)

    thread = threading.Thread(target=_watch, daemon=True, name="xpd-success-watcher")
    thread.start()
    return thread
