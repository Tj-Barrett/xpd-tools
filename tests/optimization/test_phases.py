from __future__ import annotations

from pathlib import Path

from xpd_tools.optimization.helpers.phases import Phase, _phases_to_pdf_schema


def test_phases_to_pdf_schema_resolves_paths_and_matches_load_schema() -> None:
    phases = [
        Phase(name="Wanted", gr="refdata/Wanted.gr", cif="refdata/Wanted.cif"),
        Phase(name="Impurity", gr="refdata/Impurity.gr", cif="refdata/Impurity.cif", minimize=True),
    ]

    schema = _phases_to_pdf_schema(phases)

    assert schema["schema_version"] == 1
    assert [phase["name"] for phase in schema["phases"]] == ["Wanted", "Impurity"]
    assert schema["phases"][1]["minimize"] is True
    for phase, raw in zip(phases, schema["phases"], strict=True):
        assert raw["gr_path"] == str(Path(phase.gr).resolve())
        assert raw["cif_path"] == str(Path(phase.cif).resolve())
        assert Path(raw["gr_path"]).is_absolute()
        assert Path(raw["cif_path"]).is_absolute()
        assert "constraint_profile" not in raw
        assert "scoring_function" not in raw
