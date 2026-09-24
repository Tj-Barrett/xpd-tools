"""Per-experiment evaluation plugins.

XrayUvvisEvaluation -- PDF/G(r) + PL/absorbance.
XrayEvaluation      -- PDF/G(r) only.
UvvisEvaluation     -- PL/absorbance only.
"""

from __future__ import annotations

from xpd_tools.optimization.plugins.uvvis_only import UvvisEvaluation
from xpd_tools.optimization.plugins.xray_only import XrayEvaluation
from xpd_tools.optimization.plugins.xray_uvvis import XrayUvvisEvaluation

__all__ = ["UvvisEvaluation", "XrayEvaluation", "XrayUvvisEvaluation"]
