from math import sqrt

import numpy as np

from component_model.model import Model
from component_model.variable import Variable


class BouncingBall3D(Model):
    """Another BouncingBall model, made in Python and using Model and Variable to construct a FMU.

    Special features:

    * The ball has a 3-D vector as position and speed
    * As output variable the model estimates the next bouncing point
    * As input variables, the restitution coefficient `e` and the ground angle at the bouncing point can be changed.
    * Internal units are SI (m,s,rad)

    Args:
        pos (np.array)=(0,0,1): The 3-D position in of the ball at time [m]
        speed (np.array)=(1,0,0): The 3-D speed of the ball at time [m/s]
        g (float)=9.81: The gravitational acceleration [m/s^2]
        e (float)=0.9: The coefficient of restitution (dimensionless): |speed after| / |speed before| collision
        min_speed_z (float)=1e-6: The minimum speed in z-direction when bouncing stops [m/s]
    """

    def __init__(
        self,
        name: str = "BouncingBall3D",
        description="Another BouncingBall model, made in Python and using Model and Variable to construct a FMU",
        pos: tuple = (0, 0, 10),
        speed: tuple = (1, 0, 0),
        g: float = 9.81,
        e: float = 0.9,
        min_speed_z: float = 1e-6,
        **kwargs,
    ):
        super().__init__(name, description, author="DNV, SEACo project", **kwargs)
        self._pos = self._interface( 'pos', pos)
        self._speed = self._interface( 'speed', speed)
        self.a = np.array((0, 0, -g), float)
        self._g = self._interface( 'g', g)
        self._e = self._interface( 'e', e)
        self.min_speed_z = min_speed_z
        self.stopped = False
        self.time = 0.0
        self._p_bounce = self._interface( 'p_bounce', ('0m', '0m','0m')) # instantiates self.p_bounce. z always 0.
        self.t_bounce, self.p_bounce = self.next_bounce()

    def _interface(self, name:str, start:float|tuple):
        """Define a FMU2 interface variable, using the variable interface.

        Args:
            name (str): base name of the variable
            start (str|float|tuple): start value of the variable (optionally with units)
        
        Returns:
            the variable object. As a side effect the variable value is made available as self.<name>
        """
        if name == 'pos':
            return Variable(
                self,
                name="pos",
                description="The 3D position of the ball [m] (height in inch as displayUnit example.",
                causality="output",
                variability="continuous",
                initial="exact",
                start=start,
                rng=((0, "100 m"), None, (0, "10 m")),
            )
        elif name == 'speed':
            return Variable(
                self,
                name="speed",
                description="The 3D speed of the ball, i.e. d pos / dt [m/s]",
                causality="output",
                variability="continuous",
                initial="exact",
                start=start,
                rng=((0, "1 m/s"), None, ("-100 m/s", "100 m/s")),
            )
        elif name == 'g':
            return Variable(
                self,
                name="g",
                description="The gravitational acceleration (absolute value).",
                causality="parameter",
                variability="fixed",
                start=start,
                rng=(),
            )
        elif name == 'e':
            return Variable(
                self,
                name="e",
                description="The coefficient of restitution, i.e. |speed after| / |speed before| bounce.",
                causality="parameter",
                variability="fixed",
                start=start,
                rng=(),
            )
        elif name == 'p_bounce':
            return Variable(
                self,
                name="p_bounce",
                description="The expected position of the next bounce as 3D vector",
                causality="output",
                variability="continuous",
                start=start,
                rng=(),
            )

    def do_step(self, time, dt):
        """Perform a simulation step from `time` to `time + dt`."""
        if not super().do_step(time, dt):
            return False
        self.t_bounce, self.p_bounce = self.next_bounce()
        # print(f"Step@{time}. pos:{self.pos}, speed{self.speed}, t_bounce:{self.t_bounce}, p_bounce:{self.p_bounce}")
        while dt > self.t_bounce:  # if the time is this long
            dt -= self.t_bounce
            self.pos = self.p_bounce
            self.speed -= self.a * self.t_bounce  # speed before bouncing
            self.speed[2] = -self.speed[2]  # speed after bouncing if e==1.0
            self.speed *= self.e  # speed reduction due to coefficient of restitution
            if self.speed[2] < self.min_speed_z:
                self.stopped = True
                self.a[2] = 0.0
                self.speed[2] = 0.0
                self.pos[2] = 0.0
            self.t_bounce, self.p_bounce = self.next_bounce()
        self.pos += self.speed * dt + 0.5 * self.a * dt**2
        self.speed += self.a * dt
        if self.pos[2] < 0:
            self.pos[2] = 0
        print(f"@{time}. pos {self.pos}, speed {self.speed}, bounce {self.t_bounce}")
        return True

    def next_bounce(self):
        """Calculate time until next bounce and position where the ground will be hit,
        based on current time, pos and speed.
        """
        if self.stopped:  # stopped bouncing
            return (1e300, np.array((1e300, 1e300, 0), float))
            # return ( float('inf'), np.array( (float('inf'), float('inf'), 0), float))
        else:
            t_bounce = (self.speed[2] + sqrt(self.speed[2] ** 2 + 2 * self.g * self.pos[2])) / self.g
            p_bounce = self.pos + self.speed * t_bounce  # linear. not correct for z-direction!
            p_bounce[2] = 0
            return (t_bounce, p_bounce)

    def setup_experiment(self, start: float):
        """Set initial (non-interface) variables."""
        super().setup_experiment(start)
        self.stopped = False
        self.a = np.array((0, 0, -self.g), float)

