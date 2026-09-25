"""Relative file paths in a config resolve against the config file's folder."""

import json
from pathlib import Path


def _relative_phase_paths(path: Path, gr: str = "Wanted.gr") -> None:
    """
    Rewrite the config's phase gr/cif as paths relative to its folder.

    Args:
        - path: The config JSON (make_config writes absolute paths).
        - gr: The relative gr path to write.
    """
    config = json.loads(path.read_text())
    config["xray"]["phases"][0].update(gr=gr, cif="Wanted.cif")
    path.write_text(json.dumps(config))


def test_relative_phase_files_resolve_against_the_config_folder(
    tmp_path: Path, make_config, client_for, wait_for, monkeypatch
) -> None:
    """Started elsewhere, the server still finds gr/cif next to the config and runs."""
    path = make_config(iterations=1)
    _relative_phase_paths(path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    client = client_for(path)
    assert client.post("/api/build").json()["status"] == "built"
    client.post("/api/run")
    state = wait_for(client, {"finished", "failed"})
    assert state["status"] == "finished", state["error"]
    # The fake measurement echoes the reference, so it was really read.
    assert state["trials"][0]["corr_Wanted"] > 0.99
    # The config keeps the paths as written.
    assert state["config"]["xray"]["phases"][0]["gr"] == "Wanted.gr"


def test_missing_phase_file_is_reported_at_load(make_config, client_for) -> None:
    path = make_config(iterations=1)
    _relative_phase_paths(path, gr="refdata/missing.gr")
    response = client_for().post("/api/load", json={"path": path.name})
    assert response.status_code == 422
    assert "phase 'Wanted' gr not found" in response.json()["detail"]
