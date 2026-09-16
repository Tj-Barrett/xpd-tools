from __future__ import annotations

import warnings
from pathlib import Path

from pymatgen.io.cif import CifParser

from xpd_tools.optimization.pdffit.pdffit_hooks import _write_oxidation_free_cif

_FIXTURES = Path(__file__).parent / "fixtures"


def _parse(cif_path: Path):
    # Matches test_evaluation.py's test_external_target_pdf_fit_is_finite --
    # this minimal fixture has no explicit _symmetry_equiv_pos_as_xyz loop,
    # which pymatgen warns about (and this repo's pytest config treats
    # warnings as hard errors).
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return CifParser(str(cif_path)).parse_structures(primitive=True)[0]


def test_write_oxidation_free_cif_strips_oxidation_states(tmp_path: Path) -> None:
    """_write_oxidation_free_cif is pure pymatgen -- unlike the rest of
    fit_pdf_correlations, it has no diffpy.pdffit2 dependency, so it's
    testable directly without a working pdffit2 install (which is broken
    in this local venv; see test_external_target_pdf_fit_is_finite).
    """
    source = _FIXTURES / "oxidized_target.cif"

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        output = _write_oxidation_free_cif(source, tmp_path)

    assert output.is_file()
    assert output.name == "oxidized_target_pym.cif"

    before = _parse(source)
    after = _parse(output)
    assert {str(site.specie) for site in before} == {"Cs+", "Pb2+", "Br-"}
    assert {str(site.specie) for site in after} == {"Cs", "Pb", "Br"}
