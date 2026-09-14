"""Per-experiment evaluation plugins.

XrayUvvisEvaluation -- PDF/G(r) + PL/absorbance.
XrayEvaluation      -- PDF/G(r) only.
UvvisEvaluation     -- PL/absorbance only.
"""

from __future__ import annotations

from .uvvisOnly import UvvisEvaluation
from .xrayonly import XrayEvaluation
from .xrayuvvis import XrayUvvisEvaluation

__all__ = ["UvvisEvaluation", "XrayEvaluation", "XrayUvvisEvaluation"]
