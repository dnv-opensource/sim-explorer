from pathlib import Path

from libcosimpy.CosimExecution import CosimExecution
from libcosimpy.CosimLogging import CosimLogLevel, log_output_level  # type: ignore
from libcosimpy.CosimManipulator import CosimManipulator  # type: ignore
from libcosimpy.CosimObserver import CosimObserver  # type: ignore

from sim_explorer.system_interface import SystemInterface


class SystemInterfaceOSP(SystemInterface):
    """Implements the SystemInterface as a OSP.

    Args:
       structure_file (Path): Path to system model definition file
       name (str)="System": Possibility to provide an explicit system name (if not provided by system file)
       description (str)="": Optional possibility to provide a system description
       log_level (str) = 'fatal': Per default the level is set to 'fatal',
          but it can be set to 'trace', 'debug', 'info', 'warning', 'error' or 'fatal' (e.g. for debugging purposes)
    """

    def __init__(
        self,
        structure_file: Path | str = "",
        name: str | None = None,
        description: str = "",
        log_level: str = "fatal",
    ):
        super().__init__(structure_file, name, description, log_level)
        log_output_level(CosimLogLevel[log_level.upper()])
        # ck, msg = self._check_system_structure(self.sysconfig)
        # assert ck, msg
        self.full_simulator_available = True  # system and components specification + simulation capabilities
        self.simulator = CosimExecution.from_osp_config_file(str(self.structure_file))
        assert isinstance(self.simulator, CosimExecution)
        # Instantiate a suitable manipulator for changing variables.
        self.manipulator = CosimManipulator.create_override()
        assert self.simulator.add_manipulator(manipulator=self.manipulator), "Could not add manipulator object"

        # Instantiate a suitable observer for collecting results.
        self.observer = CosimObserver.create_last_value()
        assert self.simulator.add_observer(observer=self.observer), "Could not add observer object"

    def reset(self):  # , cases:Cases):
        """Reset the simulator interface, so that a new simulation can be run."""
        assert isinstance(
            self.structure_file, Path
        ), "Simulator resetting does not work with explicitly supplied simulator."
        assert self.structure_file.exists(), "Simulator resetting does not work with explicitly supplied simulator."
        assert isinstance(self.manipulator, CosimManipulator)
        assert isinstance(self.observer, CosimObserver)
        # self.simulator = self._simulator_from_config(self.sysconfig)
        self.simulator = CosimExecution.from_osp_config_file(str(self.structure_file))
        assert self.simulator.add_manipulator(manipulator=self.manipulator), "Could not add manipulator object"
        assert self.simulator.add_observer(observer=self.observer), "Could not add observer object"

    def run_until(self, time: float):
        """Instruct the simulator to simulate until the given time."""
        return self.simulator.simulate_until(time)

    def set_initial(self, instance: int, typ: type, var_ref: int, var_val: str | float | int | bool):
        """Provide an _initial_value set function (OSP only allows simple variables).
        The signature is the same as the manipulator functions slave_real_values()...,
        only that variables are set individually and the type is added as argument.
        """
        if typ is float:
            return self.simulator.real_initial_value(instance, var_ref, typ(var_val))
        elif typ is int:
            return self.simulator.integer_initial_value(instance, var_ref, typ(var_val))
        elif typ is str:
            return self.simulator.string_initial_value(instance, var_ref, typ(var_val))
        elif typ is bool:
            return self.simulator.boolean_initial_value(instance, var_ref, typ(var_val))

    def set_variable_value(self, instance: int, typ: type, var_refs: tuple[int, ...], var_vals: tuple) -> bool:
        """Provide a manipulator function which sets the 'variable' (of the given 'instance' model) to 'value'.

        Args:
            instance (int): identifier of the instance model for which the variable is to be set
            var_refs (tuple): Tuple of variable references for which the values shall be set
            var_vals (tuple): Tuple of values (of the correct type), used to set model variables
        """
        _vals = [typ(x) for x in var_vals]  # ensure list and correct type
        if typ is float:
            return self.manipulator.slave_real_values(instance, list(var_refs), _vals)
        elif typ is int:
            return self.manipulator.slave_integer_values(instance, list(var_refs), _vals)
        elif typ is bool:
            return self.manipulator.slave_boolean_values(instance, list(var_refs), _vals)
        elif typ is str:
            return self.manipulator.slave_string_values(instance, list(var_refs), _vals)
        else:
            raise ValueError(f"Unknown type {typ}") from None

    def get_variable_value(self, instance: int, typ: type, var_refs: tuple[int, ...]):
        """Provide an observer function which gets the 'variable' value (of the given 'instance' model) at the time when called.

        Args:
            instance (int): identifier of the instance model for which the variable is to be set
            var_refs (tuple): Tuple of variable references for which the values shall be retrieved
        """
        if typ is float:
            return self.observer.last_real_values(instance, list(var_refs))
        elif typ is int:
            return self.observer.last_integer_values(instance, list(var_refs))
        elif typ is bool:
            return self.observer.last_boolean_values(instance, list(var_refs))
        elif typ is str:
            return self.observer.last_string_values(instance, list(var_refs))
        else:
            raise ValueError(f"Unknown type {typ}") from None
