"""Low syringe volume: the campaign waits in 'refill' until POST /api/refilled."""

import json

from fastapi.testclient import TestClient

from xpd_autonomous_gui.server import Session, create_app


def test_refill_then_continue(make_config, tmp_path, wait_for) -> None:
    """A short syringe stops the campaign; Refilled clears its counter and finishes it."""
    path = make_config(iterations=3)
    config = json.loads(path.read_text())
    config["experiment"]["sources"][0]["loaded_ml"] = 3.0  # 2 mL usable (1 mL reserve)
    path.write_text(json.dumps(config))
    session = Session(tmp_path, path)
    client = TestClient(create_app(session))

    client.post("/api/build")
    pump = session.stopper.devices["dds2_p1"]
    pump.read_infused.put(2.0)  # already used: nothing left for a trial
    client.post("/api/run")

    state = wait_for(client, {"refill", "failed", "finished"})
    assert state["status"] == "refill", state["error"]
    assert state["refill"]["pumps"] == ["dds2_p1"]
    assert state["refill"]["message"].startswith("Refill needed: dds2_p1 (CsPb) has 0.00 mL")
    assert state["remaining"] == 3
    # Run would start over; the refill has to be acknowledged (or cleared) first.
    assert client.post("/api/run").status_code == 409

    assert client.post("/api/refilled").json()["status"] == "running"
    assert pump.read_infused.get() < 2.0  # counter cleared, then counting again
    state = wait_for(client, {"refill", "failed", "finished"})
    assert state["status"] == "finished", state["error"]
    completed = [t for t in state["trials"] if t["trial_status"] == "COMPLETED"]
    assert len(completed) == 3


def test_refilled_needs_a_pending_refill(make_config, client_for) -> None:
    """Refilled is refused unless a refill is pending."""
    client = client_for(make_config(iterations=1))
    assert client.post("/api/refilled").status_code == 409


def test_old_config_shows_loaded_ml(make_config, client_for) -> None:
    """A config written before loaded_ml existed gets it (blank) for the Config page."""
    path = make_config(iterations=1)
    config = json.loads(path.read_text())
    del config["experiment"]["sources"][0]["loaded_ml"]
    del config["experiment"]["sources"][0]["reserve_ml"]
    path.write_text(json.dumps(config))

    source = client_for(path).get("/api/state").json()["config"]["experiment"]["sources"][0]
    assert (source["loaded_ml"], source["reserve_ml"]) == (None, 1.0)


def test_state_lists_fixed_choices(make_config, client_for) -> None:
    """Objective functions and screening modes come from xpd-tools, for dropdowns."""
    choices = client_for(make_config(iterations=1)).get("/api/state").json()["choices"]
    assert "pearson" in choices["xray.objective_function"]
    assert choices["evaluation_method"] == ["uvvis", "xray", "xray-uvvis"]
    assert choices["pdf_mode"] == ["raw", "fit", "raw_tracked"]
    assert choices["xray.screening"] == ["unscreened", "screen_only", "screen_and_record"]


def test_simulation_presets_come_from_the_config(make_config, client_for) -> None:
    """run.local.simulated: fake or Materials Project, with a DOF dropdown per phase."""
    client = client_for(make_config(iterations=1))
    state = client.get("/api/state").json()
    fake, mp = state["presets"]["run.local.simulated"]
    assert fake["value"] is None
    assert mp["value"] == {"dof_for_phase": {"Wanted": None}}
    assert state["choices"]["run.local.simulated.dof_for_phase.Wanted"] == [
        None,
        "infusion_rate_CsPb",
    ]

    # Materials Project with no DOF picked can't simulate anything: Build says so.
    config = state["config"]
    config["run"]["local"]["simulated"] = mp["value"]
    assert client.put("/api/config", json=config).status_code == 200
    response = client.post("/api/build")
    assert response.status_code == 500
    assert "pick a DOF for at least one phase" in response.json()["detail"]


def test_success_criteria_options_apply(make_config, client_for) -> None:
    """The three success-criteria options; a picked one applies with only its fields."""
    client = client_for(make_config(iterations=1))
    state = client.get("/api/state").json()
    labels = [option["label"] for option in state["presets"]["success_criteria"]]
    assert labels == [
        "None (runs all iterations)",
        "Minimum correlation",
        "Maximum FWHM and minimum PLQY",
    ]

    config = {**state["config"], "success_criteria": {"min_correlation": 0.8, "poll_interval": 5}}
    applied = client.put("/api/config", json=config)
    assert applied.status_code == 200, applied.json()
    assert client.post("/api/build").status_code == 200

    # Picked but not filled in: Apply says what's missing.
    config["success_criteria"] = {"min_correlation": None, "poll_interval": 5}
    refused = client.put("/api/config", json=config)
    assert refused.status_code == 422
    assert "at least one real target" in refused.json()["detail"]
