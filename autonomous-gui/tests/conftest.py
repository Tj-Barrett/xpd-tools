"""
Shared setup for the autonomous GUI server tests.

Run with: python -m pytest autonomous-gui/tests
"""

import json
import sys
import time
import warnings
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

with warnings.catch_warnings():
    # Newer starlette warns that its httpx-based TestClient is deprecated.
    warnings.filterwarnings("ignore", message="Using `httpx`")
    from fastapi.testclient import TestClient

from xpd_tools.optimization.agent import BuildAgent
from xpd_tools.optimization.helpers.dofs import Pump
from xpd_tools.optimization.helpers.phases import Phase
from xpd_tools.optimization.plans import FlowSource

# Importable without installing: autonomous-gui/ holds the xpd_autonomous_gui package.
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def make_config(tmp_path: Path) -> Callable[..., Path]:
    """
    Factory writing a local xray config whose fake measurement echoes the reference.

    Returns:
        - Callable - make_config(iterations, name="halide", run=None, **top) -> Path
          of the JSON; `run` adds run-section keys, `top` sets top-level keys
          (e.g. agent_data_path).
    """
    radial = np.linspace(1.0, 25.0, 200)
    gr = tmp_path / "Wanted.gr"
    np.savetxt(gr, np.column_stack((radial, np.sin(radial))))
    cif = tmp_path / "Wanted.cif"
    cif.write_text(
        "data_test\n_symmetry_space_group_name_H-M 'P 1'\n"
        "_cell_length_a 6\n_cell_length_b 6\n_cell_length_c 6\n"
        "_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n"
    )

    def factory(
        iterations: int, name: str = "halide", run: dict | None = None, **top
    ) -> Path:
        agent = BuildAgent(evaluation_method="xray", queue_server=False)
        agent.set_dofs([Pump(name="CsPb", id="dds2_p1", bounds=(10, 200))])
        agent.experiment(
            sources=[
                FlowSource(
                    dof="infusion_rate_CsPb",
                    pump="dds2_p1",
                    precursor="CsPbOA",
                    sample_label="CsPb",
                )
            ]
        )
        agent.set_xray_objectives(
            screening="unscreened",
            exposure=0.1,
            frame_acq_time=0.1,
            phases=[Phase(name="Wanted", gr=str(gr), cif=str(cif), minimize=False)],
        )
        config = agent.to_config()
        config["run"] = {"iterations": iterations, **(run or {})}
        config.update(top)
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(config))
        return path

    return factory


@pytest.fixture
def client_for(tmp_path: Path) -> Callable[..., TestClient]:
    """
    Factory for a TestClient around a Session on `tmp_path`.

    Returns:
        - Callable - client_for(path=None) -> TestClient, loading `path` if given.
    """
    from xpd_autonomous_gui.server import Session, create_app

    def factory(path: Path | None = None) -> TestClient:
        return TestClient(create_app(Session(tmp_path, path)))

    return factory


@pytest.fixture
def wait_for() -> Callable[..., dict]:
    """
    Poller for /api/state.

    Returns:
        - Callable - wait_for(client, statuses, timeout=120) -> the state once its
          status is in `statuses`; fails the test on timeout.
    """

    def poll(client: TestClient, statuses: set[str], timeout: float = 120) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = client.get("/api/state").json()
            if state["status"] in statuses:
                return state
            time.sleep(0.2)
        pytest.fail(f"timed out waiting for {statuses}; last {state['status']}")

    return poll
