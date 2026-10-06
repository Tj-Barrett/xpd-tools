from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from xpd_tools.optimization.helpers.pdf import _load_pdf_references, _raw_pdf_correlations
from xpd_tools.optimization.helpers.phases import Phase, _write_pdf_references


class _FakeCnn:
    """Stands in for CnnScorer: a fixed 0.7 CsPbBr3 / 0.3 Cs4PbBr6 prediction."""

    def score(self, r, g, phase_names, r_min, r_max):
        pred = {"CsPbBr3": 0.7, "Cs4PbBr6": 0.3}
        return {name: pred[name] for name in phase_names}


def test_target_fraction_scores_closeness_to_target(tmp_path: Path) -> None:
    phases = [
        Phase(name="CsPbBr3", gr="a.gr", cif="a.cif", target_fraction=0.6),
        Phase(name="Cs4PbBr6", gr="b.gr", cif="b.cif", target_fraction=0.4),
    ]
    refs = _load_pdf_references(_write_pdf_references(phases, tmp_path, scoring_function="cnn"))
    assert [p.target_fraction for p in refs] == [0.6, 0.4]

    r = np.linspace(1, 30, 100)
    scores = _raw_pdf_correlations(
        refs, {"gr_r": r, "gr_G": np.sin(r)}, ensemble_scorers={}, cnn_scorer=_FakeCnn()
    )
    # miss of 0.1 out of a worst-case miss of 0.6
    assert scores["corr_CsPbBr3"] == pytest.approx(1 - 0.1 / 0.6)
    assert scores["corr_Cs4PbBr6"] == pytest.approx(1 - 0.1 / 0.6)


@pytest.mark.parametrize(
    ("phase", "match"),
    [
        ({"scoring_function": "pearson", "gr_path": "x.gr", "target_fraction": 0.5}, "requires scoring_function"),
        ({"scoring_function": "cnn", "target_fraction": 1.5}, r"in \[0, 1\]"),
        ({"scoring_function": "cnn", "target_fraction": 0.5, "minimize": True}, "maximized"),
    ],
)
def test_target_fraction_rejects_bad_config(tmp_path: Path, phase: dict, match: str) -> None:
    (tmp_path / "x.gr").write_text("1 0\n2 1\n")
    config = tmp_path / "c.json"
    config.write_text(json.dumps({"schema_version": 1, "phases": [{"name": "A", "minimize": False, **phase}]}))
    with pytest.raises(ValueError, match=match):
        _load_pdf_references(config)


def test_target_fractions_must_not_sum_above_one(tmp_path: Path) -> None:
    config = tmp_path / "c.json"
    config.write_text(json.dumps({"schema_version": 1, "phases": [
        {"name": n, "minimize": False, "scoring_function": "cnn", "target_fraction": 0.6} for n in "AB"
    ]}))
    with pytest.raises(ValueError, match="sum to 1.2"):
        _load_pdf_references(config)
