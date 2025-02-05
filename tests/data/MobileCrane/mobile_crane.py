from crane_fmu.crane import Crane  # , Animation


class MobileCrane(Crane):
    """Simple mobile crane for FMU testing purposes.
    The crane has a short pedestal, one variable-length stiff boom and a rope.
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
        description: str = "Simple mobile crane (for FMU testing) with short pedestal, one variable-length elevation boom and a rope",
        author: str = "DNV, SEACo project",
        version: str = "0.2",
        pedestalMass: str = "10000.0 kg",
        pedestalHeight: str = "3.0 m",
        boomMass: str = "1000.0 kg",
        boomLength0: str = "8 m",
        boomLength1: str = "50 m",
        rope_mass_range: tuple = ("50kg", "2000 kg"),
        **kwargs,
    ):
        super().__init__(
            name=name, description=description, author=author, version=version, **kwargs
        )
        _ = self.add_boom(
            name="pedestal",
            description="The crane base, on one side fixed to the vessel and on the other side the first crane boom is fixed to it. The mass should include all additional items fixed to it, like the operator's cab",
            mass=pedestalMass,
            massCenter=(0.5, -1.0, 0.8),
            boom=(pedestalHeight, "0deg", "0deg"),
            boom_rng=(None, None, ("0deg", "360deg")),
        )
        _ = self.add_boom(
            name="boom",
            description="The boom. Can be lifted and length can change within the given range",
            mass=boomMass,
            massCenter=(0.5, 0, 0),
            boom=(boomLength0, "90deg", "0deg"),
            boom_rng=((boomLength0, boomLength1), (0, "90deg"), None),
        )
        _ = self.add_boom(
            name="rope",
            description="The rope fixed to the last boom. Flexible connection",
            mass="50.0 kg",  # so far basically the hook
            massCenter=0.95,
            mass_rng=rope_mass_range,
            boom=("1e-6 m", "180deg", "0 deg"),
            boom_rng=(
                ("1e-6 m", boomLength1),
                ("90deg", "270deg"),
                ("-180deg", "180deg"),
            ),
            damping=50.0,
            animationLW=2,
        )
        # make sure that _comSub is calculated for all booms:
        self.calc_statics_dynamics(None)

    def do_step(self, currentTime, stepSize):
        status = super().do_step(currentTime, stepSize)
        # print(f"Time {currentTime}, {self.rope_tip}")
        # print(f"MobileCrane.do_step. Status {status}")
        return status
