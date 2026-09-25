"""
Serve a BuildAgent config JSON to the autonomous GUI.

Usage:
    xpd-autonomous-server [config.json] [--config-dir DIR] [--port 8765]

The JSON is `BuildAgent.to_config()` output plus an optional "run" section
(see RUN_DEFAULTS). `connection.queue_server` picks the mode: true drives the
beamline queue server via build(); false runs build_local() against simulated
devices on a local RunEngine. Any JSON in the config directory can also be
loaded from the GUI.

Only one server may run per lock file (default: .xpd-autonomous.lock in the
working directory), so two GUIs can't drive the instrument at once.
"""

import argparse
import copy
import fcntl
import getpass
import json
import logging
import os
import socket
import sys
import threading
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from typing import IO, Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from xpd_tools.optimization.agent import BuildAgent
from xpd_tools.optimization.stopping import watch_and_stop

logger = logging.getLogger("autonomous-gui")

RUN_DEFAULTS: dict[str, Any] = {
    "iterations": 10,
    "n_points": 1,
    # kwargs for run_agent.ax_client.configure_generation_strategy(...)
    "generation_strategy": {},
    # If set, initialization_budget = (historical trials ingested at Build) + this
    "extra_initialization_trials": None,
    # build_local() only
    "local": {
        "mixer_lengths_cm": [0.0],
        "residence_time_ratio": 0.0,
        # kwargs for build_simulated_tiled_clients(...); null uses the fake clients
        "simulated": None,
    },
}

# Top-level config keys that may change while a campaign is running.
RUNNING_EDITABLE = {"success_criteria"}


class Session:
    """
    The loaded config and the agent built from it.

    Args:
        - config_dir: Directory whose JSON files the GUI may load.
        - path: Config to load at startup, if any.
    """

    def __init__(self, config_dir: str | Path, path: str | Path | None = None) -> None:
        self.config_dir = Path(config_dir).resolve()
        self.path: Path | None = None
        self.config: dict[str, Any] | None = None
        self.build_agent: BuildAgent | None = None
        self.agent: Any = None
        self.stopper: Any = None
        self.future: Future | None = None
        self.status = "empty"
        self.error: str | None = None
        self.saved_path: Path | None = None
        self.trials_path: Path | None = None
        # Trials of the last campaign, kept visible after a config edit drops its agent.
        self.last_trials: list[dict[str, Any]] = []
        # How many of those trials were historical data ingested at Build.
        self.historical_count: int | None = None
        # Reentrant: a future that is already done runs _on_done inside run().
        self.lock = threading.RLock()
        if path is not None:
            self.load(path)

    @property
    def running(self) -> bool:
        """Whether a campaign is in progress."""
        return self.status in ("running", "stopping")

    def state(self) -> dict[str, Any]:
        """
        Snapshot for the GUI.

        Returns:
            - dict - status, error, config, editable keys, and the trials table.
        """
        mode = None
        if self.build_agent is not None:
            mode = "queue_server" if self.build_agent.queue_server else "local"
        path = self.saved_path or self.path
        return {
            "status": self.status,
            "error": self.error,
            "mode": mode,
            "config_dir": str(self.config_dir),
            "config_path": None if path is None else str(path),
            "config": self.config,
            "editable": sorted(RUNNING_EDITABLE) if self.running else "all",
            "trials": self._trials(),
            "trials_path": None if self.trials_path is None else str(self.trials_path),
            "historical": {
                "path": _historical_path(
                    self.config, self.path.parent if self.path else self.config_dir
                ),
                "count": self.historical_count,
            },
        }

    def _trials(self) -> list[dict[str, Any]]:
        """
        Trials table of the current agent, or of the last campaign if it was dropped.

        Returns:
            - list[dict] - One record per trial, as from ax_client.summarize().
        """
        if self.agent is None:
            return self.last_trials
        return json.loads(self.agent.ax_client.summarize().to_json(orient="records"))

    def files(self, suffix: str) -> list[str]:
        """
        Files in the config directory with `suffix`, newest first.

        Args:
            - suffix: e.g. ".json" (loadable configs) or ".csv" (historical data).

        Returns:
            - list[str] - Names relative to the config directory.
        """
        found = sorted(
            self.config_dir.glob(f"*{suffix}"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        return [f.name for f in found]

    def load(self, path: str | Path) -> None:
        """
        Load a config JSON from the config directory, dropping any built agent.

        Args:
            - path: File name within the config directory, or an absolute path in it.
        """
        with self.lock:
            if self.running:
                raise HTTPException(409, "Stop the campaign before loading a config")
            path = (self.config_dir / path).resolve()
            if path.parent != self.config_dir or path.suffix != ".json":
                raise HTTPException(403, f"{path} is not a JSON in {self.config_dir}")
            try:
                config = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise HTTPException(422, f"Can't read {path.name}: {exc}") from exc
            config["run"] = {**RUN_DEFAULTS, **config.get("run", {})}
            self.build_agent = _build_agent(config, path.parent)
            self.config = config
            self.path = path
            self.saved_path = None
            self.agent = None
            self.last_trials = []
            self.historical_count = None
            self.trials_path = None
            self.status = "loaded"
            self.error = None

    def _require_config(self) -> None:
        """Raise 409 until a config has been loaded."""
        if self.config is None:
            raise HTTPException(409, "Load a config first")

    def update_config(self, new: dict[str, Any]) -> None:
        """
        Apply an edited config and save it as a new timestamped JSON.

        Args:
            - new: The full edited config, including the "run" section.
        """
        with self.lock:
            self._require_config()
            if self.running:
                changed = {k for k in new.keys() | self.config.keys()
                           if new.get(k) != self.config.get(k)}
                locked = changed - RUNNING_EDITABLE
                if locked:
                    raise HTTPException(
                        409, f"Can't change {sorted(locked)} while running"
                    )
                if new["success_criteria"] is None:
                    raise HTTPException(
                        409, "Can't clear success_criteria while running"
                    )
                watching = self.build_agent.success_criteria is not None
                self.build_agent.set_success_criteria(**new["success_criteria"])
                if not watching:
                    watch_and_stop(self.stopper, self.future, self.build_agent)
            else:
                self.build_agent = _build_agent(new, self.path.parent)
                self.last_trials = self._trials()
                self.agent = None
                self.status = "loaded"
            self.config = copy.deepcopy(new)
            self.saved_path = self._save()

    def _save(self) -> Path:
        """
        Write the current config next to the original, timestamped.

        Returns:
            - Path - The new file.
        """
        out = self._stamped(".json")
        out.write_text(json.dumps(self.config, indent=4))
        return out

    def _stamped(self, suffix: str) -> Path:
        """
        Path next to the original config: `<stem>__<timestamp><suffix>`.

        Args:
            - suffix: File ending, e.g. ".json" or "_trials.csv".

        Returns:
            - Path - The timestamped path.
        """
        stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        return self.path.with_name(f"{self.path.stem.split('__')[0]}__{stamp}{suffix}")

    def build(self) -> None:
        """Build the agent: build() for the queue server, build_local() otherwise."""
        with self.lock:
            self._require_config()
            if self.running:
                raise HTTPException(409, "Already running")
            run = self.config["run"]
            try:
                if self.build_agent.queue_server:
                    self.agent = self.build_agent.build()
                    self.stopper = self.agent
                else:
                    self.agent, self.stopper = _build_local(
                        self.build_agent, run["local"]
                    )
                # Before any new trial, every trial is ingested historical data.
                historical = len(self.agent.ax_client.summarize())
                strategy = dict(run["generation_strategy"])
                if run["extra_initialization_trials"] is not None:
                    strategy["initialization_budget"] = (
                        historical + run["extra_initialization_trials"]
                    )
                if strategy:
                    self.agent.ax_client.configure_generation_strategy(**strategy)
            except Exception as exc:
                self.agent = None
                self.status = "loaded"
                self.error = repr(exc)
                raise HTTPException(500, f"Build failed: {exc!r}") from exc
            self.status = "built"
            self.error = None
            self.last_trials = []
            self.historical_count = historical
            self.trials_path = None

    def run(self) -> None:
        """Start the campaign in the background, plus the success watcher if set."""
        with self.lock:
            if self.agent is None:
                raise HTTPException(409, "Build the agent first")
            if self.running:
                raise HTTPException(409, "Already running")
            run = self.config["run"]
            if self.build_agent.queue_server:
                self.future = self.agent.run(
                    iterations=run["iterations"], n_points=run["n_points"]
                )
            else:
                self.future = self.stopper.start(run["iterations"], run["n_points"])
            self.status = "running"
            self.error = None
            self.future.add_done_callback(self._on_done)
            if self.build_agent.success_criteria is not None:
                watch_and_stop(self.stopper, self.future, self.build_agent)

    def stop(self) -> None:
        """Ask the running campaign to stop after cleanup."""
        with self.lock:
            if not self.running:
                raise HTTPException(409, "Not running")
            self.status = "stopping"
            stopper = self.stopper
        _request_stop(stopper)

    def clear(self) -> None:
        """Drop the built agent and its trials, keeping the config; refused mid-run."""
        with self.lock:
            self._require_config()
            if self.running:
                raise HTTPException(409, "Stop the campaign and let it end first")
            self.agent = self.stopper = self.future = None
            self.last_trials = []
            self.historical_count = None
            self.status = "loaded"
            self.error = None

    def _on_done(self, future: Future) -> None:
        with self.lock:
            try:
                self.trials_path = self._stamped("_trials.csv")
                self.agent.ax_client.summarize().to_csv(self.trials_path)
            except Exception:
                self.trials_path = None
                logger.exception("Couldn't save the trials table")
            exc = future.exception()
            if exc is None:
                self.status = "finished"
            elif (
                type(exc).__name__ == "RunEngineInterrupted"
                or self.status == "stopping"
            ):
                self.status = "stopped"
            else:
                self.status = "failed"
                self.error = repr(exc)
                logger.error("Campaign failed: %r", exc)


def _request_stop(stopper: Any) -> None:
    """
    Call `stopper.stop()` outside the session lock.

    The campaign may finish on its own first (a stop then finds the RunEngine idle),
    so a failed stop is logged rather than raised.

    Args:
        - stopper: QueueserverAgent or LocalRunner of the running campaign.
    """
    try:
        stopper.stop()
    except Exception as exc:
        logger.warning("Stop failed (campaign may already be ending): %r", exc)


def _historical_path(config: dict[str, Any] | None, base_dir: Path) -> str | None:
    """
    The config's agent_data_path, resolved against `base_dir` if relative.

    Args:
        - config: The loaded config, if any.
        - base_dir: The config file's folder.

    Returns:
        - str | None - Absolute path of the historical-data CSV, or None if unset.
    """
    if config is None or not config.get("agent_data_path"):
        return None
    return str((base_dir / config["agent_data_path"]).resolve())


def _resolve_phase(phase: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    """
    A phase with its gr/cif files resolved against `base_dir` and checked to exist.

    Args:
        - phase: One entry of the config's xray.phases.
        - base_dir: The config file's folder.

    Returns:
        - dict - A copy of the phase with absolute gr/cif paths.
    """
    resolved = dict(phase)
    for key in ("gr", "cif"):
        if phase.get(key):
            path = (base_dir / phase[key]).resolve()
            if not path.is_file():
                raise HTTPException(
                    422, f"phase {phase.get('name')!r} {key} not found: {path}"
                )
            resolved[key] = str(path)
    return resolved


def _build_agent(config: dict[str, Any], base_dir: Path) -> BuildAgent:
    """
    Rebuild a BuildAgent, turning config errors into HTTP 422.

    Args:
        - config: to_config()-shaped dict.
        - base_dir: Folder that relative file paths (agent_data_path, each phase's
          gr/cif) are resolved against: the config file's, so they don't depend on
          where server.py was started. The config itself keeps them as written.

    Returns:
        - BuildAgent - The rebuilt agent.
    """
    run = config.get("run", {})
    if (
        run.get("extra_initialization_trials") is not None
        and "initialization_budget" in run.get("generation_strategy", {})
    ):
        raise HTTPException(
            422,
            "Set run.extra_initialization_trials or "
            "run.generation_strategy.initialization_budget, not both",
        )
    historical = _historical_path(config, base_dir)
    if historical is not None and not Path(historical).is_file():
        raise HTTPException(422, f"agent_data_path not found: {historical}")
    resolved = {**config, "agent_data_path": historical}
    xray = config.get("xray") or {}
    if xray.get("phases"):
        resolved["xray"] = {
            **xray,
            "phases": [_resolve_phase(phase, base_dir) for phase in xray["phases"]],
        }
    try:
        return BuildAgent.from_config(
            resolved, http_api_key=os.environ.get("QSERVER_HTTP_SERVER_API_KEY")
        )
    except KeyError as exc:
        raise HTTPException(
            422, f"missing key {exc} (re-save it with BuildAgent.to_config())"
        ) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


class LocalRunner:
    """
    Run build_local()'s agent on a RunEngine in a worker thread.

    Exposes `ax_client` and `stop()` so watch_and_stop() treats it like a
    QueueserverAgent.

    Args:
        - agent: The agent returned by build_local().
        - RE: The RunEngine the agent's devices and Tiled clients are bound to.
    """

    def __init__(self, agent: Any, RE: Any) -> None:  # noqa: N803
        self.agent = agent
        self.RE = RE
        self.ax_client = agent.ax_client

    def start(self, iterations: int, n_points: int) -> Future:
        """
        Start `agent.optimize(...)` on a worker thread.

        Args:
            - iterations: Number of optimization iterations.
            - n_points: Points suggested per iteration.

        Returns:
            - Future - Resolves when the RunEngine returns or raises.
        """
        future: Future = Future()

        def _work() -> None:
            try:
                future.set_result(
                    self.RE(
                        self.agent.optimize(iterations=iterations, n_points=n_points)
                    )
                )
            except BaseException as exc:  # RunEngineInterrupted on stop()
                future.set_exception(exc)

        threading.Thread(target=_work, daemon=True, name="local-campaign").start()
        return future

    def stop(self) -> None:
        """Stop the RunEngine; it runs cleanup and marks the run 'success'."""
        self.RE.stop()


def _build_local(
    build_agent: BuildAgent, local: dict[str, Any]
) -> tuple[Any, LocalRunner]:
    """
    Build a local agent against simulated devices and Tiled clients.

    Args:
        - build_agent: A BuildAgent with queue_server=False.
        - local: The config's run.local section.

    Returns:
        - tuple - (agent, LocalRunner wrapping it).
    """
    from bluesky.run_engine import RunEngine

    from xpd_tools.optimization.legacy import (
        build_fake_tiled_clients,
        build_xpd_objects,
        identity_wrap_xray_run,
    )
    from xpd_tools.optimization.simulation import build_simulated_tiled_clients

    # No SIGINT handler: the RunEngine runs off the main thread.
    RE = RunEngine(context_managers=[])  # noqa: N806
    phases = build_agent.phases or ()
    if local["simulated"] is None:
        tiled_client, sandbox_client = build_fake_tiled_clients(RE, phases=phases)
    else:
        tiled_client, sandbox_client = build_simulated_tiled_clients(
            RE, phases=phases, **local["simulated"]
        )
    agent = build_agent.build_local(
        devices=build_xpd_objects(),
        wrap_xray_run=identity_wrap_xray_run,
        mixer_lengths_cm=tuple(local["mixer_lengths_cm"]),
        residence_time_ratio=local["residence_time_ratio"],
        tiled_client=tiled_client,
        sandbox_client=sandbox_client,
    )
    return agent, LocalRunner(agent, RE)


class SinglePageApp(StaticFiles):
    """Serve web/dist, falling back to index.html so client routes survive reloads."""

    async def get_response(self, path: str, scope: Any) -> Any:
        """Return the file at `path`, or index.html if there is none."""
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


def create_app(session: Session) -> FastAPI:
    """
    Build the FastAPI app around one session.

    Args:
        - session: The loaded config session.

    Returns:
        - FastAPI - The app, serving web/dist at / when it has been built.
    """
    app = FastAPI(title="xpd-tools autonomous GUI")

    @app.get("/api/state")
    def get_state() -> dict[str, Any]:
        return session.state()

    @app.get("/api/configs")
    def get_configs() -> list[str]:
        return session.files(".json")

    @app.get("/api/csvs")
    def get_csvs() -> list[str]:
        return session.files(".csv")

    @app.post("/api/load")
    def post_load(body: dict[str, str]) -> dict[str, Any]:
        session.load(body["path"])
        return session.state()

    @app.put("/api/config")
    def put_config(config: dict[str, Any]) -> dict[str, Any]:
        session.update_config(config)
        return session.state()

    @app.post("/api/build")
    def post_build() -> dict[str, Any]:
        session.build()
        return session.state()

    @app.post("/api/run")
    def post_run() -> dict[str, Any]:
        session.run()
        return session.state()

    @app.post("/api/stop")
    def post_stop() -> dict[str, Any]:
        session.stop()
        return session.state()

    @app.post("/api/clear")
    def post_clear() -> dict[str, Any]:
        session.clear()
        return session.state()

    # autonomous-gui/web/dist, next to this package (editable install / checkout)
    dist = Path(__file__).parent.parent / "web" / "dist"
    if dist.is_dir():
        app.mount("/", SinglePageApp(directory=dist, html=True), name="web")
    return app


def acquire_lock(path: Path, **info: Any) -> IO[str]:
    """
    Take an exclusive lock so only one GUI drives the instrument.

    The OS releases the lock when the process exits, so a crash leaves no stale
    lock. The file keeps the last holder's details for the error message.

    Args:
        - path: Lock file to create or reuse.
        - info: Extra details to record, e.g. the URL.

    Returns:
        - IO[str] - The open lock file; keep it open for the life of the process.
    """
    handle = path.open("a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.seek(0)
        holder = handle.read().strip() or "(no details)"
        handle.close()
        sys.exit(
            f"Another autonomous GUI already holds {path}:\n  {holder}\n"
            "Stop it first; only one may drive the instrument."
        )
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps({
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "user": getpass.getuser(),
        "started": datetime.now().isoformat(timespec="seconds"),
        **info,
    }))
    handle.flush()
    return handle


def main() -> None:
    """Take the lock, load the optional startup config, and serve the GUI."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument(
        "config", nargs="?", help="Config JSON to load at startup (optional)"
    )
    parser.add_argument(
        "--config-dir",
        help="Directory of loadable configs (default: the config's, else cwd)",
    )
    parser.add_argument("--lock-file", default=".xpd-autonomous.lock")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    url = f"http://{args.host}:{args.port}"
    lock = acquire_lock(Path(args.lock_file), url=url)  # noqa: F841 -- held until exit
    config_dir = args.config_dir or (Path(args.config).parent if args.config else ".")
    try:
        session = Session(
            config_dir, None if args.config is None else Path(args.config).resolve()
        )
    except HTTPException as exc:
        sys.exit(f"Invalid config {args.config}: {exc.detail}")
    print(f"Autonomous GUI: {url}  (configs from {session.config_dir})")
    uvicorn.run(create_app(session), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
