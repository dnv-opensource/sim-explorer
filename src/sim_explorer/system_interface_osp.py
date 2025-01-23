from functools import partial
from pathlib import Path
from typing import TypeAlias

from libcosimpy.CosimExecution import CosimExecution
from libcosimpy.CosimLogging import CosimLogLevel, log_output_level  # type: ignore
from libcosimpy.CosimManipulator import CosimManipulator  # type: ignore
from libcosimpy.CosimObserver import CosimObserver  # type: ignore

from sim_explorer.system_interface import SystemInterface

PyVal: TypeAlias = str | float | int | bool  # simple python types / Json5 atom


class SystemInterfaceOSP(SystemInterface):
    """Implements the SystemInterface as a OSP.

    Args:
       structure_file (Path): Path to system model definition file
       name (str)="System": Possibility to provide an explicit system name (if not provided by system file)
       description (str)="": Optional possibility to provide a system description
       log_level (str) = 'fatal': Per default the level is set to 'fatal',
          but it can be set to 'trace', 'debug', 'info', 'warning', 'error' or 'fatal' (e.g. for debugging purposes)
        **kwargs: Optional possibility to supply additional keyword arguments:

            * full_simulator_available=True to overwrite the oposite when called from a superclass
    """

    def __init__(
        self,
        structure_file: Path | str = "",
        name: str | None = None,
        description: str = "",
        log_level: str = "fatal",
        **kwargs,
    ):
        super().__init__(structure_file, name, description, log_level)
        self.full_simulator_available = True  # system and components specification + simulation capabilities
        # Note: The initialization of the OSP simulator itself is performed in init_simulator()
        #      Since this needs to be repeated before every simulation

    def init_simulator(self):
        """Instantiate and initialize the simulator, so that simulations can be run.
        Perforemd separately from __init__ so that it can be repeated before simulation runs.
        """
        log_output_level(CosimLogLevel[self.log_level.upper()])
        # ck, msg = self._check_system_structure(self.sysconfig)
        # assert ck, msg
        assert self.structure_file.exists(), "Simulator initialization requires the structure file."
        self.simulator = CosimExecution.from_osp_config_file(str(self.structure_file))
        assert isinstance(self.simulator, CosimExecution)
        # Instantiate a suitable manipulator for changing variables.
        self.manipulator = CosimManipulator.create_override()
        assert isinstance(self.manipulator, CosimManipulator)
        assert self.simulator.add_manipulator(manipulator=self.manipulator), "Could not add manipulator object"

        # Instantiate a suitable observer for collecting results.
        self.observer = CosimObserver.create_last_value()
        assert isinstance(self.observer, CosimObserver)
        assert self.simulator.add_observer(observer=self.observer), "Could not add observer object"
        assert self.simulator.status().current_time == 0
        return not self.simulator.status().error_code

    def _action_func(self, act_type: int, var_type: type):
        """Determine the correct action function and return it."""
        if act_type == 0:  # initial settings
            return {
                float: self.simulator.real_initial_value,
                int: self.simulator.integer_initial_value,
                str: self.simulator.string_initial_value,
                bool: self.simulator.boolean_initial_value,
            }[var_type]
        if act_type == 1:  # other set actions
            return {
                float: self.manipulator.slave_real_values,
                int: self.manipulator.slave_integer_values,
                bool: self.manipulator.slave_boolean_values,
                str: self.manipulator.slave_string_values,
            }[var_type]
        # get actions
        return {
            float: self.observer.last_real_values,
            int: self.observer.last_integer_values,
            bool: self.observer.last_boolean_values,
            str: self.observer.last_string_values,
        }[var_type]

    def do_action(self, time: int | float, act_info: tuple, typ: type):
        """Do the action described by the tuple using OSP functions."""
        if len(act_info) == 4:  # set action
            cvar, comp, refs, values = act_info
            _comp = self.component_id_from_name(comp)
            if time <= 0:  # initial setting
                func = self._action_func(0, typ)
                for r, v in zip(refs, values, strict=False):
                    if not func(_comp, r, v):
                        return False
                return True

            return self._action_func(1, typ)(_comp, refs, values)
        # get action
        cvar, comp, refs = act_info
        _comp = self.component_id_from_name(comp)
        assert time >= 0, "Get actions for all communication points shall be pre-compiled"
        return self._action_func(2, typ)(_comp, refs)

    def action_step(self, act_info: tuple, typ: type):
        """Pre-compile the step action and return the partial function
        so that it can be called at communication points.
        """
        assert len(act_info) == 3, f"Exactly 3 arguments exected. Found {act_info}"
        cvar, comp, refs = act_info
        _comp = self.component_id_from_name(comp)
        return partial(self._action_func(2, typ), _comp, refs)

    def run_until(self, time: int | float):
        """Instruct the simulator to simulate until the given time."""
        return self.simulator.simulate_until(time)
