from collections.abc import Callable
from typing import Any
from component_model.model import Model
from component_model.variable import Variable
from functools import partial
from math import sin, pi
import numpy as np

# Note: PythonFMU (which component-model is built on) works on files and thus only one Model class allowed per file


def func(time: float, ampl: float = 1.0, omega: float = 0.1):
    return np.array((0, 0, ampl * sin(omega * time)), float)


class DrivingForce(Model):
    """A driving force in 3 dimensions which produces an ouput per time and can be connected to the oscillator.

    Args:
        func (callable)=func: The driving force function f(t).
            Note: The func can currently not really be handled as parameter and must be hard-coded here (see above).
            Soon to come: Model.build() function which honors parameters, such that function can be supplied from
            outside and the FMU can be re-build without changing the class.
    """

    def __init__(
        self, func: Callable[..., Any] = func, ampl: float = 1.0, freq: float = 1.0, **kwargs: Any,
    ):
        super().__init__(
            "DrivingForce",
            "A simple driving force for an oscillator",
            "Siegfried Eisinger",
            **kwargs,
        )
        self.ampl = ampl
        self.freq = freq
        self.func = partial(func, ampl=ampl, omega=freq / (2 * pi))
        self._interface(ampl, freq)

    def do_step(self, time: float, dt: float):
        self.f = self.func(time)
        return True  # very important!

    def exit_initialization_mode(self):
        """Internal state settings after initial variables are set."""
        self.func = partial(func, ampl=self.ampl, omega=self.freq / (2 * pi))
        print(f"Initial settings: ampl={self.ampl}, freq={self.freq}")

    def _interface(self, ampl: float, freq: float):
        """Define the FMU interface variables (parameters, inputs, outputs).

        Note: The variable object registrations like self._f provide access to the Variable meta-data
        like range and units, but are not really needed here.
        """
        self._ampl = self._interpolate = Variable(
            self,
            name="ampl",
            description="The amplitude of the force in N",
            causality="parameter",
            variability="fixed",
            typ=float,  # can be automatically determined
            start=ampl,
        )
        self._freq = self._interpolate = Variable(
            self,
            name="freq",
            description="The frequency of the force in 1/s",
            causality="parameter",
            variability="fixed",
            typ=float,  # can be automatically determined
            start=freq,
        )
        self._f = Variable(
            self,
            name="f",
            description="Output connector for the driving force f(t) in N",
            causality="output",
            variability="continuous",
            start=np.array((0, 0, 0), float),
        )
