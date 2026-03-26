from typing import Any

from py_crane.crane_fmu import CraneFMU


class MobileCrane(CraneFMU):
    """Simple mobile crane for FMU testing purposes.
    The crane has a short pedestal, one variable-length stiff boom and a wire.
    The size and weight of the various parts can be configured.

    Args:
        name (str) : name of the crane type
        description (str) : short description
        author (str)
        version (str)
        pedestalMass (str) : mass of the pedestal - quantity and unit as string
        pedestalHeight (str) : height (fixed) of the pedestal, with units
        boomMass (str) : mass of the single boom, with units
        boomLength0 (str) : minimum length of the boom, with units
        boomLength1 (str) : maximum length of the boom, with units
    """

    def __init__(
        self,
        name: str = "mobile_crane",
        description: str = "Simple mobile crane (for FMU testing) with short pedestal, one variable-length elevation boom and a wire",
        author: str = "DNV, SEACo project",
        version: str = "0.3",
        degrees: bool = True,
        pedestalMass: str = "10000.0 kg",
        pedestalCoM: tuple[float, float, float] = (0.5, -1.0, 0.8),
        pedestalHeight: str = "3.0 m",
        boomMass: str = "1000.0 kg",
        boomLength0: str = "8 m",
        boomLength1: str = "50 m",
        boomAngle: str = "90deg",
        wire_mass_range: tuple[str, str] = ("50kg", "2000 kg"),
        wire_mass: str | None = None,
        wire_length: float = 0.1,
        **kwargs: Any,
    ):
        super().__init__(name=name, description=description, author=author, version=version, degrees=degrees, **kwargs)
        _pedestal = self.add_boom(
            "pedestal",
            description="The crane base, on one side fixed to the vessel and on the other side the first crane boom is fixed to it. The mass should include all additional items fixed to it, like the operator's cab",
            mass=pedestalMass,
            mass_center=pedestalCoM,
            boom=(pedestalHeight, "0deg", "0deg"),
            boom_rng=(None, None, ()),
        )
        _boom = self.add_boom(
            "boom",
            description="The boom. Can be lifted and length can change within the given range",
            mass=boomMass,
            mass_center=(0.5, 0, 0),
            boom=(boomLength0, boomAngle, "0deg"),
            boom_rng=((boomLength0, boomLength1), (), None),
        )
        _ = self.add_boom(
            "wire",
            description="The wire fixed to the last boom. Flexible connection",
            mass=wire_mass_range[0] if wire_mass is None else wire_mass,
            mass_center=0.99,
            mass_rng=wire_mass_range,
            boom=(f"{wire_length}m", "90deg", "0 deg"),
            boom_rng=((f"{wire_length}m", boomLength1), (), ()),
            q_factor=50.0,
            additional_checks=True,
        )

        # make sure that _comSub is calculated for all booms:
        self.calc_statics_dynamics(None)

    def do_step(self, current_time: float, step_size: float):
        status = super().do_step(current_time, step_size)
        # print(f"Time {current_time}, {self.force}, {self.torque}, {self.booms('wire').end}")
        return status
