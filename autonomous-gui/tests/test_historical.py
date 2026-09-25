"""Historical data (agent_data_path) in the GUI workflow."""

import json
from pathlib import Path

import pytest
from ax import Client

# Two good rows and one with inf, which the loader drops.
HISTORY = "infusion_rate_CsPb,corr_Wanted\n40.0,0.5\n150.0,0.7\n90.0,inf\n"


@pytest.fixture
def history(tmp_path: Path) -> Path:
    """
    Write a historical-data CSV next to the configs.

    Returns:
        - Path - The CSV.
    """
    path = tmp_path / "history.csv"
    path.write_text(HISTORY)
    return path


def test_relative_path_resolves_against_the_config_folder(
    tmp_path: Path, history, make_config, client_for, monkeypatch
) -> None:
    """Start the server elsewhere; the CSV is still found next to the config."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    client = client_for(make_config(iterations=2, agent_data_path="history.csv"))

    state = client.get("/api/state").json()
    assert state["historical"] == {"path": str(history.resolve()), "count": None}

    state = client.post("/api/build").json()
    assert state["historical"]["count"] == 2  # the inf row was dropped
    assert len(state["trials"]) == 2


def test_historical_trials_come_first_and_the_campaign_follows(
    history, make_config, client_for, wait_for
) -> None:
    """The count marks where history ends in the trials table (the plot divider)."""
    client = client_for(make_config(iterations=2, agent_data_path="history.csv"))
    client.post("/api/build")
    client.post("/api/run")
    state = wait_for(client, {"finished", "failed"})
    assert state["status"] == "finished", state["error"]
    assert state["historical"]["count"] == 2
    assert len(state["trials"]) == 4
    assert [t["infusion_rate_CsPb"] for t in state["trials"][:2]] == [40.0, 150.0]


def test_extra_initialization_trials_adds_to_the_history(
    history, make_config, client_for, monkeypatch
) -> None:
    """run.extra_initialization_trials: 3 with 2 historical trials -> budget 5."""
    seen = {}
    original = Client.configure_generation_strategy

    def spy(self, **kwargs):
        seen.update(kwargs)
        return original(self, **kwargs)

    monkeypatch.setattr(Client, "configure_generation_strategy", spy)
    path = make_config(
        iterations=2,
        agent_data_path="history.csv",
        run={
            "extra_initialization_trials": 3,
            "generation_strategy": {"initialize_with_center": False},
        },
    )
    client_for(path).post("/api/build")
    assert seen == {"initialize_with_center": False, "initialization_budget": 5}


def test_budget_set_twice_is_rejected(tmp_path: Path, make_config, client_for) -> None:
    path = make_config(
        iterations=2,
        run={
            "extra_initialization_trials": 3,
            "generation_strategy": {"initialization_budget": 10},
        },
    )
    client = client_for()
    response = client.post("/api/load", json={"path": path.name})
    assert response.status_code == 422
    assert "not both" in response.json()["detail"]


def test_missing_csv_is_reported_at_load(make_config, client_for) -> None:
    path = make_config(iterations=2, agent_data_path="nope.csv")
    response = client_for().post("/api/load", json={"path": path.name})
    assert response.status_code == 422
    assert "agent_data_path not found" in response.json()["detail"]


def test_csvs_lists_the_config_folder(history, make_config, client_for) -> None:
    client = client_for(make_config(iterations=2))
    assert client.get("/api/csvs").json() == ["history.csv"]
    # The saved JSON keeps the relative path as written.
    edited = client.get("/api/state").json()["config"]
    edited["agent_data_path"] = "history.csv"
    saved = client.put("/api/config", json=edited).json()["config_path"]
    assert json.loads(Path(saved).read_text())["agent_data_path"] == "history.csv"
