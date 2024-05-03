# pyright: reportMissingImports=false, reportGeneralTypeIssues=false
from functools import partial
from pathlib import Path
from typing import TypeAlias

import matplotlib.pyplot as plt

from .cases import Cases
from .json5 import json5_write
from .simulator_interface import SimulatorInterface, from_xml

# type definitions
PyVal: TypeAlias = str | float | int | bool  # simple python types / Json5 atom
Json5: TypeAlias = dict[str, PyVal | "Json5" | "Json5List"]  # Json5 object
Json5List: TypeAlias = list[Json5 | PyVal]  # Json5 list


class CaseInitError(Exception):
    """Special error indicating that something is wrong during initialization of cases."""

    pass


class CaseUseError(Exception):
    """Special error indicating that something is wrong during usage of cases."""

    pass


class Case:
    """Instantiation of a Case object.
    Sub-cases are strored ins list 'self.subs'.
    Parent case is stored as 'self.parent' (None for 'base').
    The Cases object is registered as 'self.cases' and registers the unique case 'self.base'.

    Args:
        cases (Cases): Reference to the related Cases object
        name (str): Unique name of the case
        parent (Case): Parent case or None (base case)
        description (str)="": human readable description of the case. Strongly recommended to not leave empty.
        spec (dict): the dictionary of the case specification
    """

    def __init__(
        self,
        cases: "Cases",
        name: str,
        description: str = "",
        parent: "Case" | None = None,
        spec: Json5 | None = None,
    ):
        self.cases = cases
        self.name = name
        self.description = description
        self.parent = parent
        self.subs = []
        self.spec = {} if spec is None else spec
        self.special = (
            {}
        )  # dict of special variable : value, like stopTime. @start of run this is sent to the Simulator to deal with it
        self.act_set = {}  # dict of manipulator actions for specific times and this case. Updated by read_spec_item
        self.act_get = {}  # dict of observer actions for specific times and this case. Updated by read_spec_item
        self.act_final = []  # observer actions at end of simulation
        self.act_step = (
            {}
        )  # observer actions at intervals: {dt1:[actions...],...} where dt=None denotes all macro time steps
        self.results = {}  # Json5 dict added by cases.run_case() when run
        if self.name == "results":
            for k in self.spec:  # only keys, no values
                self.read_spec_item(k)
        else:
            assert isinstance(self.spec, dict), f"A dict is expected as spec. Found {self.spec}"
            for k, v in self.spec.items():
                if (isinstance(v, PyVal) or
                    (isinstance(v, list) and all(isinstance(x,PyVal) for x in v))):
                    self.read_spec_item(k, v) # type: ignore
                else:
                    raise AssertionError( f"Unhandled spec value {v}") from None

        if self.name == "base":
            self.special = self._ensure_specials(self.special)  # must specify for base case

    def iter(self):
        """Construct an iterator, allowing iteration from base case to this case through the hierarchy."""
        h = []
        nxt = self
        while True:  # need first to collect the path to the base case
            if nxt is None:
                break
            h.append(nxt)
            nxt = nxt.parent
        while len(h):
            yield h.pop()

    def case_by_name(self, name: str) -> "Case" | None:
        """Find the case 'name' within sub-hierarchy of this case. Return None if not found.

        Args:
            name (str): the case name to find
        Returns:
            The case object or None
        """
        for c in self.subs:
            if c.name == name:
                return c
            else:
                found = c.case_by_name(name)
                if found is not None:
                    return found
        return None

    def append(self, case: "Case"):
        """Append a case as sub-case to this case."""
        self.subs.append(case)

    def add_action(self, typ: str, action: callable, args: tuple[any, ...], at_time: float | None = None):
        """Add an action to one of the properties act_set, act_get, act_final, act_step - used for results.
        We use functools.partial to return the functions with fully filled in arguments.
        Compared to lambda... this allows for still accessible (testable) argument lists.

        Args:
            typ (str): the action type 'final', 'single' or 'step'
            action (Callable): the relevant action (manipulator/observer) function to perform
            args (tuple): action arguments as tuple (instance:str, type:int, valueReferences:list[int][, values])
            at_time (float): optional time argument
        """
        if typ == "final":
            assert at_time is None, f"Spurious argument {at_time} for final results action"
            self.act_final.append(partial(action, *args))
        elif typ in ("set", "get"):
            assert at_time is not None, "For single time results actions, the time argument is mandatory"
            if typ == "set":
                try:
                    self.act_set[at_time].append(partial(action, *args))
                except Exception:  # new time
                    self.act_set.update({at_time: [partial(action, *args)]})
            elif typ == "get":
                try:
                    self.act_get[at_time].append(partial(action, *args))
                except Exception:  # new time
                    self.act_get.update({at_time: [partial(action, *args)]})
        elif typ == "step":
            if at_time in self.act_step:
                self.act_step[at_time].append(partial(action, *args))
            else:  # new interval argument
                self.act_step.update({at_time: [partial(action, *args)]})

    @staticmethod
    def _num_elements(obj: any) -> int:
        if obj is None:
            return 0
        elif isinstance(obj, (tuple, list)):
            return len(obj)
        elif isinstance(obj, str):
            return int(len(obj) > 0)
        else:
            return 1

    @staticmethod
    def _disect_at_time(txt: str, case: str, value: PyVal | list[PyVal] | None = None) -> tuple[str, str, float | None]:
        """Disect the @txt argument into 'at_time_type' and 'at_time_arg'."""
        pre, _, at = txt.partition("@")
        assert len(pre), f"'{txt}' is not allowed as basis for _disect_at_time"
        if not len(at):  # no @time spec
            if case == "results":
                return (pre, "final", None)
            else:
                assert Case._num_elements(
                    value
                ), f"Value required for 'set' in _disect_at_time('{txt}','{case}','{value}')"
                return (pre, "set", 0)  # set at startTime
        else:  # time spec provided
            try:
                arg = float(at)
            except Exception:
                arg = at
            if isinstance(arg, str):
                if at.startswith("step"):
                    try:
                        return (pre, "step", float(arg[4:]))
                    except Exception:
                        return (pre, "step", None)  # this means 'all macro steps'
                else:
                    raise AssertionError(f"Unknown @time instruction {txt}. Case:{case}, value:'{value}'")
            else:
                return (pre, "set" if Case._num_elements(value) else "get", arg)

    @staticmethod
    def _disect_range(txt: str, case: str, value: PyVal | list[PyVal] | None) -> tuple[str, str]:
        """Extract the explicit variable range, if relevant
        (multi-valued variables where only some all elements are addressed).
        Note: it is not explicitly checked whether 'value' containsexacly the number of values required for the range.
        """
        pre, _, rng = txt.partition("[")
        if len(rng):  # range among several variables as python slice or comma-separated list
            rng = rng.rstrip("]").strip()
            assert (
                case == "results" or rng == "0" or isinstance(value, list)
            ), f"More than one value required to handle multi-valued setting [{rng}]"
        elif isinstance(value, list):  # all values (without explicit range)
            rng = ":"
        else:  # no range (single variable)
            rng = ""
        return (pre, rng)

    def read_spec_item(self, key: str, value: PyVal | list[PyVal] | None = None):
        """Use the alias variable information (key) and the value to construct an action function which is run when this variable is set/read.
        Optionally, for multi-valued variables (vectors) a range 'rng' may be provided, setting only part of the vector.

        rng (str): Possibility to set only part of a vector variable:
               '': set a single-valued variable, ':' set all variables of a vector, slice (without []) or comma-separated indexes to set part of vector
               The function tuple2_iter() is designed to iterate over the variable/values with respect to rng.

        Note: Observer actions are normally specified within 'results' and are the same for all cases.
          The possibility to observe specific variables in given cases is added through the syntax var@time : '',
          i.e. empty variable value specification, which says: keep the value but record the variable.

        Args:
            key (str): the key of the spec item
            value (PyVal,list[PyVal])=None: the value(s) with respect to the item. For 'results' this is not used
        """
        if key in ("startTime", "stopTime", "stepSize"):
            self.special.update({key: value})  # just keep these as a dictionary so far
        else:  # expect a  variable-alias : value(s) specificator
            key, at_time_type, at_time_arg = Case._disect_at_time(key, self.name, value)
            key, rng = Case._disect_range(key, self.name, value)
            key = key.strip()
            try:
                var_alias = self.cases.variables[key]
            except KeyError as err:
                raise CaseInitError(f"Variable {key} was not found in list of defined variable aliases") from err
            var_refs = []
            var_vals = []
            #            print(f"READ_SPEC, {key}@{at_time_arg}({at_time_type}):{value}[{rng}], alias={var_alias}")
            if self.name == "results":  # observer actions
                if rng == "":  # a single variable
                    var_refs.append(int(var_alias["variables"][0]))
                else:  # multiple variables
                    for [k, _] in tuple2_iter(var_alias["variables"], var_alias["variables"], rng):
                        var_refs.append(k)
                assert at_time_type in ("final", "get", "step"), f"Unknown @time type '{at_time_type}' for 'results'"
                for inst in var_alias["instances"]:  # ask simulator to provide function to set variables:
                    self.add_action(
                        at_time_type,
                        self.cases.simulator.get_variable_value,
                        (inst, var_alias["type"], tuple(var_refs)),
                        at_time_arg,
                    )

            else:  # manipulator actions
                assert value is not None, f"Value needed for manipulator actions. Found {value}"
                if rng == "":  # a single variable
                    var_refs.append(var_alias["variables"][0])
                    var_vals.append(
                        SimulatorInterface.pytype(var_alias["type"], value if isinstance(value, PyVal) else value[0])
                    )
                elif isinstance(value, list):  # multiple variables
                    for [k, v] in tuple2_iter(var_alias["variables"], tuple(value), rng):
                        var_refs.append(k)
                        var_vals.append(SimulatorInterface.pytype(var_alias["type"], v))

                assert at_time_type in ("set"), f"Unknown @time type {at_time_type} for case '{self.name}'"
                if at_time_arg == 0.0:  # initial settings use set_initial
                    for inst in var_alias["instances"]:  # ask simulator to provide function to set variables:
                        self.add_action(
                            at_time_type,
                            self.cases.simulator.set_initial,
                            (inst, var_alias["type"], tuple(var_refs), tuple(var_vals)),
                            at_time_arg,
                        )
                else:
                    for inst in var_alias["instances"]:  # ask simulator to provide function to set variables:
                        self.add_action(
                            at_time_type,
                            self.cases.simulator.set_variable_value,
                            (inst, var_alias["type"], tuple(var_refs), tuple(var_vals)),
                            at_time_arg,
                        )

    def list_cases(self, as_name=True, flat=False) -> list:
        """List this case and all sub-cases recursively, as name or case objects."""
        lst = [self.name if as_name else self]
        for s in self.subs:
            if flat:
                lst.extend(s.list_cases(as_name, flat))
            else:
                lst.append(s.list_cases(as_name, flat))
        return lst

    def _ensure_specials(self, special: dict[str, any]) -> dict[str, any]:
        """Ensure that mandatory special variables are defined.
        The base case shall specify some special variables, needed by the simulator.
        These can be overridden by the hierarchy of a given case.
        The values of the base case ensure that critical values are always avalable.
        """

        def get_from_config(element: str, default: float | None = None):
            if isinstance(self.cases.simulator.sysconfig, Path):
                info = from_xml(self.cases.simulator.sysconfig, sub=None, xpath=".//{*}" + element)[0].text
                if info is None:
                    return default
                try:
                    return float(info)
                except Exception:
                    return default

        if "startTime" not in special:
            special.update({"startTime": get_from_config("StartTime", 0.0)})
        assert "stopTime" in special, "'stopTime' should be specified as part of the 'base' specification."
        if "stepSize" not in special:
            step_size = get_from_config("BaseStepSize", None)
            if step_size is not None:
                special.update({"stepSize": step_size})
            else:
                raise CaseInitError("'stepSize' should be specified as part of the 'base' specification.") from None
        return special

    def save_results(self, results: dict, jsfile: bool | str):
        """Dump the results dict to a json5 file.

        Args:
            results (dict): results dict as produced by Cases.run_case()
            jsfile (bool,str): json file name to use for dump. If True: automatic file name generation.
        """
        if not jsfile:
            return
        if not isinstance(jsfile, str):
            jsfile = self.name + ".json"
        elif not jsfile.endswith(".json"):
            jsfile += ".json"
        json5_write(results, jsfile)

    def plot_time_series(self, aliases: list[str], title=""):
        """Use self.results to extract the provided alias variables and plot the data found in the same plot."""
        assert len(self.results), "The results dictionary is empty. Cannot plot results"
        timefac = self.cases.timefac
        for var in aliases:
            times = []
            values = []
            for key in self.results:
                if isinstance(key, int):  # time value
                    if var in self.results[key]:
                        times.append(key / timefac)
                        values.append(self.results[key][var][2][0])
            plt.plot(times, values, label=var, linewidth=3)

        if len(title):
            plt.title(title)
        plt.xlabel("Time")
        # plt.ylabel('Values')
        plt.legend()
        plt.show()


def tuple2_iter(tpl1: tuple, tpl2: tuple, rng: str):
    """Make an iterator over the tuples 'tpl1' and 'tpl2' with respect to range 'rng' provided as text.

    Args:
        tpl1 (tuple): the first tuple from which to return elements
        tpl2 (tuple): the second tuple from which to return elements
        rng (str): variable range description as string.
             Can be a single integer, a python slice without [], or a comma-separated list of integers
    """
    assert len(tpl1) == len(tpl2), f"The two tuples shall be of equal length. Found {tpl1} <-> {tpl2}"
    try:
        idx = int(rng)
        assert len(tpl2) > idx, f"Supplied tuples not long enough to return index {idx}"
        yield (tpl1[idx], tpl2[idx])
    except Exception:
        if ":" in rng:  # seems to be a slice
            pre, _, post = rng.partition(":")
            if not len(post):
                end = len(tpl1) - 1
            else:
                try:
                    end = int(post)
                    if end < -1:
                        end += len(tpl1)
                except ValueError as err:
                    raise CaseInitError(f"Unreadable range specification '{rng}'") from err
            idx = int(pre) if pre.isnumeric() else 0
            while idx <= end:
                yield (tpl1[idx], tpl2[idx])
                idx += 1
        elif "," in rng:  # seems to be a comma-separated list
            for e in rng.split(","):
                try:
                    idx = int(e)
                except ValueError as err:
                    raise CaseInitError(f"A comma-separated range must consist of integers. Found {rng}") from err
                yield (tpl1[idx], tpl2[idx])
        else:
            assert True, f"Only single integer, slice of comma-separated list allowed as range. Found {rng}"
