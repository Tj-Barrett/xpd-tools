# Autonomous GUI

Run an autonomous campaign from a browser instead of a notebook.

1. Develop and validate the workflow in a notebook, then save it:
   `build_agent.to_config("configs/halide.json")`.
2. Optionally add a `run` section to the JSON (below).
3. On the day, serve it and open the printed URL:

```bash
xpd-autonomous-server configs/halide.json          # http://127.0.0.1:8765
xpd-autonomous-server --config-dir configs         # start empty, pick in the GUI
```

Install the command once, in the same environment as xpd-tools:

```bash
pip install -e autonomous-gui        # from the xpd-tools checkout
```

Any `.json` in the config directory (default: the startup config's directory, else the
working directory) can be loaded from the Run page without restarting, as long as no
campaign is running. Loading drops the current agent.

### One driver at a time

The server takes an exclusive lock on `.xpd-autonomous.lock` in the working directory
(`--lock-file` to change it) and refuses to start if another server holds it, printing
who does (pid, host, user, start time, URL). The OS releases the lock when the server
exits, including crashes, so there is no stale lock to delete.

The lock only guards servers using the same lock file: start them from the same
directory, or pass the same `--lock-file`. It does not stop a notebook from driving
the instrument, and `flock` is unreliable on some network filesystems (NFS), so keep
the lock file on a local disk.

`connection.queue_server` in the JSON picks the mode: `true` drives the beamline
queue server via `build()`; `false` runs `build_local()` against simulated devices.
The queue-server API key is read from `QSERVER_HTTP_SERVER_API_KEY`.

## Pages

- **Run**: load a config; build, run, stop, clear; status, progress, success criteria,
  errors. Clear drops the built agent and its trials (the saved CSV stays) and is
  only allowed once no campaign is running: press Stop and let it end first.
- **Config**: every field of the JSON. Before a run anything can change; during a run
  only `success_criteria` can. Every applied edit is saved as a new
  `<name>__<timestamp>.json` next to the original.
- **Trials**: objectives and DOFs per trial, plus the table. When a campaign ends the
  table is saved as `<name>__<timestamp>_trials.csv`.

## `run` section

All keys are optional; these are the defaults.

```json
"run": {
    "iterations": 10,
    "n_points": 1,
    "generation_strategy": {},
    "extra_initialization_trials": null,
    "local": {"mixer_lengths_cm": [0.0], "residence_time_ratio": 0.0, "simulated": null}
}
```

- `generation_strategy`: kwargs for `ax_client.configure_generation_strategy(...)`.
- `extra_initialization_trials`: if set, Build sets `initialization_budget` to
  (historical trials ingested) + this, like the notebooks' `n_existing_trials + 5`.
  Don't also set `generation_strategy.initialization_budget`.
- `local`: `build_local()` only. `simulated: null` uses the fake Tiled clients; an object
  is passed to `build_simulated_tiled_clients(...)` (e.g. `dof_for_phase`, `pl_phases`,
  `noise_level`; `MP_API_KEY` from the environment).

Iterations are fixed once a run starts; to change them, stop, edit, build, and run again.
Stopping a local run interrupts the trial in progress, which Ax records as FAILED.

## Historical data

Set the config's top-level `agent_data_path` to an Ax-style CSV (e.g. a previous
campaign's `…_trials.csv`); the Config page offers the `.csv` files in the config folder.
A relative path is resolved against the config file's folder. At Build its rows are
ingested before any new trial: `peak_distance` is recomputed from `Peak` with the
config's `peak_target`, and rows with NaN/inf in the loaded columns are dropped. The Run
page shows the file and row count, and the Trials plots and table mark where history ends.

## Web app

The page is built once and served by `server.py`:

```bash
cd autonomous-gui/web
npm install
npm run build      # -> web/dist, served at /
npm run dev        # development: hot reload on :5173, proxies /api to :8765
```

Built with Vite, React 18, and [finch](https://github.com/bluesky/finch).

## Tests

```bash
python -m pytest autonomous-gui/tests
```
