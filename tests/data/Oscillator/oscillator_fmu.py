from typing import Any
import numpy as np
from component_model.model import Model
from component_model.variable import Variable


class HarmonicOscillator(Model):
    """Construct a simple model of a general harmonic oscillator, potentially driven by a force.

    The system obeys the equation F(t) - k*x - c*dx/dt = m*d^2x/dt^2

    where x shall be a 3D vector with an initial position. F(t)=0 as long as there is not external driving force.

    Args:
        k (float)=1.0: spring constant in N/m
        c (float)=0.0: Viscous damping coefficient in N.s/m
        m (float)=1.0: Mass of the spring load (spring mass negligible) in kg

    See also `Wikipedia <https://en.wikipedia.org/wiki/Harmonic_oscillator>`_
    """

    def __init__(self, k: float = 1.0, c: float = 0.0, m: float = 1.0, **kwargs: Any):
        super().__init__(
            "Oscillator", "A simple harmonic oscillator", "Siegfried Eisinger", **kwargs,
        )
        self.k = k
        self.c = c
        self.m = m
        self.x = np.array( (0,0,0), float)
        self.v = np.array( (0,0,0), float)
        self.f = np.array( (0,0,0), float)
        self._interface(k, c, m)

    def do_step(self, time: float, dt: float):
        """Do one simulation step of size dt.

        We implement a very simplistic algoritm based on difference calculus.
        """
        if not super().do_step(time, dt):  # needed for FMU mechanism
            return False
        a = (self.f - self.k * self.x - self.c * self.v) / self.m
        self.x += self.v * dt  # + a* dt*dt
        self.v += a * dt
        # print(f"@{time}: x={self.x}, v={self.v}, f={self.f}, a={a}")
        return True  # very important!

    def exit_initialization_mode(self):
        """Internal state settings after initial variables are set."""
        print(
            f"Initial settings: k={self.k}, c={self.c}, m={self.m}, x={self.x}, v={self.v}, f={self.f}"
        )

    # Note: The other FMU functions like .setup_experiment and  .exit_initialization_mode
    #       do not need special attention here and can be left out

    def _interface(self, k: float, c: float, m: float):
        """Define the FMU interface variables (parameters, inputs, outputs).

        Note: The variable object registrations like self._k provide access to the Variable meta-data
        like range and units, but are not really needed here.
        """
        self._k = self._interpolate = Variable(
            self,
            name="k",
            description="The spring constant in N/m",
            causality="parameter",
            variability="fixed",
            typ=float,  # can be automatically determined
            start=k,
        )
        self._c = self._interpolate = Variable(
            self,
            name="c",
            description="The damping constant N.s/m",
            causality="parameter",
            variability="fixed",
            typ=float,  # can be automatically determined
            start=c,
        )
        self._m = self._interpolate = Variable(
            self,
            name="m",
            description="The mass connected to the system in kg. The spring mass is assumed negligible.",
            causality="parameter",
            variability="fixed",
            typ=float,  # can be automatically determined
            start=m,
        )
        self._x = Variable(
            self,
            name="x",
            description="Output connector for the 3D position of the mass in m",
            causality="output",
            variability="continuous",
            initial="exact",
            start=np.array((0, 0, 1.0), float),
        )
        self._v = Variable(
            self,
            name="v",
            description="Output connector for the 3D speed of the mass in m/s",
            causality="output",
            variability="continuous",
            initial="exact",
            start=np.array((0, 0, 0), float),
        )
        self._f = Variable(
            self,
            name="f",
            description="Input connector for the 3D external force acting on the mass in N",
            causality="input",
            variability="continuous",
            start=np.array((0, 0, 0), float),
        )
