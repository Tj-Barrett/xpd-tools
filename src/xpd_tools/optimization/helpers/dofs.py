
from dataclasses import dataclass

from blop.ax import RangeDOF


@dataclass(frozen=True, kw_only=True)
class Pump:
    """Pump infuser for experimental process."""

    name: str
    id: str
    bounds: tuple[float, float]
    parameter_type: str = "float"

    def __post_init__(self) -> None:
        # Normalize to a tuple regardless of what sequence type the caller
        # passed in -- keeps a hand-built Pump and a from_config()-rebuilt
        # one equal regardless of which the caller used.
        object.__setattr__(self, "bounds", tuple(self.bounds))


def _create_pump(pump: Pump) -> RangeDOF:
    return RangeDOF(
        name=f"infusion_rate_{pump.name}",
        bounds=pump.bounds,
        parameter_type=pump.parameter_type,
    )
