
from dataclasses import dataclass

from blop.ax import RangeDOF


@dataclass(frozen=True, kw_only=True)
class Pump:
    """Pump infuser for experimental process."""

    name: str
    id: str
    bounds: tuple[float, float]
    parameter_type: str = "float"


def _create_pump(pump: Pump) -> RangeDOF:
    return RangeDOF(
        name=f"infusion_rate_{pump.name}",
        bounds=pump.bounds,
        parameter_type=pump.parameter_type,
    )
