"""Per-experiment evaluation plugins.

XrayUvvisEvaluation -- PDF/G(r) + PL/absorbance.
XrayEvaluation      -- PDF/G(r) only.
UvvisEvaluation     -- PL/absorbance only.
"""

from __future__ import annotations

from .UVvisOnly import UvvisEvaluation
from .XrayOnly import XrayEvaluation
from .XrayUVvis import XrayUvvisEvaluation

__all__ = ["UvvisEvaluation", "XrayEvaluation", "XrayUvvisEvaluation"]
