# pyright: reportMissingImports=false, reportGeneralTypeIssues=false
from __future__ import annotations

import math
import os
import time
from functools import partial
from pathlib import Path
from typing import Any, Callable, TypeAlias

import matplotlib.pyplot as plt
import numpy as np

from .json5 import Json5Reader, json5_write
from .simulator_interface import SimulatorInterface, from_xml

# type definitions
PyVal: TypeAlias = str | float | int | bool  # simple python types / Json5 atom
Json5: TypeAlias = dict[str, "Json5Val"]  # Json5 object
Json5List: TypeAlias = list["Json5Val"]  # Json5 list
Json5Val: TypeAlias = PyVal | Json5 | Json5List  # Json5 values


"""
case_study module for definition and execution of simulation experiments
* read and compile the case definitions from configuration file
  Note that Json5 is here restriced to 'ordered keys' and 'unique keys within an object'
* set the start variables for a given case
* manipulate variables according to conditions during the simulation run
* save requested variables at given communication points during a simulation run
* check the validity of results when saving variables

With respect to MVx in general, this module serves the preparation of start conditions for smart testing.
Note: The classes Case and Cases should be kept together in this file to avoid circular references.
"""


class CaseInitError(Exception):
    """Special error indicating that something is wrong during initialization of cases."""

    pass


class CaseUseError(Exception):
    """Special error indicating that something is wrong during usage of cases."""

    pass


def _assert(condition: bool, msg: str, crit: int = 4, typ=CaseInitError):
    """Check condition and raise error is relevant with respect to condition and crit."""
    if crit == 1:
        print(f"DEBUG ({condition}): {msg}")
    elif crit == 2:
        print("INFO ({condition}): {msg}")
    else:
        if condition:
            return
        else:
            if crit == 3:
                print("WARNING:", msg)
            else:
                raise typ(msg) from None


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
        spec: dict | list | None = None,  # Json5 | Json5List | None = None,
        special: dict | None = None,
    ):
        self.cases = cases
        self.name = name
        self.description = description
        self.parent = parent
        if self.parent is not None:
            self.parent.append(self)
        self.subs: list = []  # own subcases
        assert isinstance(spec, (dict, list)), f"The spec for case {self.name} was not found"
        self.spec = spec
        # dict of special variable : value, like stopTime. @start of run this is sent to the Simulator to deal with it
        # the self.act_get/set objects are sorted dicts { time : [list of set actions]},
        #   including 'final' actions at stopTime
        #   including step actions as get actions at given intervals
        #   including step actions as get actions at all communication points as time=None
        if self.name == "results":
            assert special is not None, "startTime and stopTime settings needed for 'results'"
            self.special = special
            self.act_get: dict = {}
        elif self.name == "base":  # take over the results info and activities
            assert special is not None, "startTime and stopTime settings needed for 'base'"
            self.special = special
            self.act_get = self.cases.results.act_get
            self.act_set: dict = {}  # no set actions during results collection
        else:
            assert isinstance(self.parent, Case), f"Parent case expected for case {self.name}"
            self.special = dict(self.parent.special)
            self.act_get = Case._actions_copy(self.parent.act_get)
            self.act_set = Case._actions_copy(self.parent.act_set)
        self.results: dict = {}  # Json5 dict of results, added by cases.run_case() when run
        if self.name == "results":
            assert isinstance(self.spec, list), f"A list is expected as spec. Found {self.spec}"
            for k in self.spec:  # only keys, no values
                assert isinstance(k, str), f"A key (str) is expected as list element in results. Found {k}"
                self.read_spec_item(k)
        else:
            assert isinstance(self.spec, dict), f"A dict is expected as spec. Found {self.spec}"
            for k, v in self.spec.items():
                #                if isinstance(v, (str, float, int, bool)):
                # isinstance(v, list) and all(isinstance(x, (str, float, int, bool)) for x in v)
                self.read_spec_item(k, v)  # type: ignore
                # else:
                #    raise AssertionError(f"Unhandled spec value {v}") from None

        if self.name == "base":
            self.special = self._ensure_specials(self.special)  # must specify for base case
        self.act_get = dict(sorted(self.act_get.items()))
        if self.name != "results":
            self.act_set = dict(sorted(self.act_set.items()))

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

    def add_action(self, typ: str, action: Callable, args: tuple, at_time: float):
        """Add an action to one of the properties act_set, act_get, act_final, act_step - used for results.
        We use functools.partial to return the functions with fully filled in arguments.
        Compared to lambda... this allows for still accessible (testable) argument lists.

        Args:
            typ (str): the action type 'get' or 'set'
            action (Callable): the relevant action (manipulator/observer) function to perform
            args (tuple): action arguments as tuple (instance:int, type:int, valueReferences:list[int][, values])
            at_time (float): optional time argument (not needed for all actions)
        """
        if typ == "get":
            dct = self.act_get
        elif typ == "set":
            dct = self.act_set
        else:
            raise AssertionError(f"Unknown typ {typ} in add_action")
        assert isinstance(at_time, (float, int)), f"Actions require a defined time as float. Found {at_time}"
        if at_time in dct:
            for i, act in enumerate(dct[at_time]):
                if act.func.__name__ == action.__name__ and all(act.args[k] == args[k] for k in range(2)):
                    # the type of action, the model id and the variable type match
                    if all(r in act.args[2] for r in args[2]):  # refs are a subset or equal
                        if typ == "get":
                            return  # leave alone. Already included
                        else:  # set action. Need to (partially) replace value(s)
                            values = list(act.args[3])  # copy of existing values
                            for k, r in enumerate(act.args[2]):  # go through refs
                                for _k, _r in enumerate(args[2]):
                                    if r == _r:
                                        values[k] = args[3][_k]  # replace
                            dct[at_time][i] = partial(
                                action, args[0], args[1], act.args[2], tuple(values)
                            )  # replace action
                            return
            dct[at_time].append(partial(action, *args))

        else:  # no action for this time yet
            dct.update({at_time: [partial(action, *args)]})

    @staticmethod
    def _num_elements(obj) -> int:
        if obj is None:
            return 0
        elif isinstance(obj, (tuple, list, np.ndarray)):
            return len(obj)
        elif isinstance(obj, str):
            return int(len(obj) > 0)
        else:
            return 1

    def _disect_at_time(self, txt: str, value: PyVal | list[PyVal] | None = None) -> tuple[str, str, float]:
        """Disect the @txt argument into 'at_time_type' and 'at_time_arg'.

        Args:
            txt (str): The key text after '@' and before ':'
            value (PyVal, list(PyVal)): the value argument. Needed to distinguish the action type

        Returns
        -------
            tuple of pre, type, arg, where
            pre is the text before '@',
            type is the type of action (get, set, step),
            arg is the time argument, or -1
        """
        pre, _, at = txt.partition("@")
        assert len(pre), f"'{txt}' is not allowed as basis for _disect_at_time"
        if not len(at):  # no @time spec
            if self.name == "results" or (isinstance(value, str) and value.lower() == "novalue"):
                return (pre, "get", self.special["stopTime"])
            else:
                msg = f"Value required for 'set' in _disect_at_time('{txt}','{self.name}','{value}')"
                assert Case._num_elements(value), msg
                return (pre, "set", 0)  # set at startTime
        else:  # time spec provided
            try:
                arg_float = float(at)
            except Exception:
                arg_float = float("nan")
            if math.isnan(arg_float):
                if at.startswith("step"):
                    try:
                        return (pre, "step", float(at[4:]))
                    except Exception:
                        return (pre, "step", -1)  # this means 'all macro steps'
                else:
                    raise AssertionError(f"Unknown @time instruction {txt}. Case:{self.name}, value:'{value}'")
            else:
                return (pre, "set" if Case._num_elements(value) else "get", arg_float)

    def _disect_range(self, key: str) -> tuple[str, dict, list | range]:
        """Extract the variable name, definition and explicit variable range, if relevant
        (multi-valued variables, where only some all elements are addressed).
        Note: since values are not specified for get actions, the validity of values cannot be checked here.
        ToDo: handle multi-dimensional arrays (tables, ...).

        Args:
            key (str): The key as provided in case spec(, with [range] if provided).

        Returns
        -------
            1. The variable name as defined in the 'variables' section of the spec
            2. The variable definition, which the name refers to
            3. An iterator over indices of the variable, i.e. the range
        """
        pre, _, r = key.partition("[")
        try:
            cvar_info = self.cases.variables[pre]
        except KeyError as err:
            raise CaseInitError(f"Variable {pre} was not found in list of defined case variables") from err
        cvar_len = len(cvar_info["variables"])  # len of the tuple of refs
        if len(r):  # range among several variables
            r = r.rstrip("]").strip()  # string version of a non-trivial range
            parts_comma = r.split(",")
            rng: range | list[int] = []
            for i, p in enumerate(parts_comma):
                parts_ellipses = p.split("..")
                if len(parts_ellipses) == 1:  # no ellipses. Should be an index
                    try:
                        idx = int(p)
                        assert 0 <= idx < cvar_len, f"Index {idx} of variable {pre} out of range"
                    except ValueError as err:
                        raise CaseInitError(f"Unhandled index {p}[{i}] for variable {pre}") from err
                    assert isinstance(rng, list), "A list was expected as range here. Found {rng}"
                    rng.append(idx)
                else:
                    _assert(len(parts_ellipses) == 2, f"RangeError: Exactly two indices expected in {p} of {pre}")
                    parts_ellipses[1] = parts_ellipses[1].lstrip(".")  # facilitates the option to use '...' or '..'
                    try:
                        if len(parts_ellipses[0]) == 0:
                            idx0 = 0
                        else:
                            idx0 = int(parts_ellipses[0])
                        assert 0 <= idx0 <= cvar_len, f"Index {idx0} of variable {pre} out of range"
                        if len(parts_ellipses[1]) == 0:
                            idx1 = cvar_len
                        else:
                            idx1 = int(parts_ellipses[1])
                        assert idx0 <= idx1 <= cvar_len, f"Index {idx1} of variable {pre} out of range"
                    except ValueError as err:
                        raise CaseInitError(f"Unhandled ellipses '{parts_comma}' for variable {pre}") from err
                    rng = range(idx0, idx1)
        else:  # no expicit range
            if cvar_len == 1:  # scalar variable
                rng = [0]
            else:  # all elements
                rng = range(cvar_len)
        return (pre, cvar_info, rng)

    def read_spec_item(self, key: str, value: PyVal | list[PyVal] | None = None):
        """Use the alias variable information (key) and the value to construct an action function,
        which is run when this variable is set/read.

        In the simplest case, the key is a cases variable name. Optionally two elements can be added:

        #. a range, denoted by `[range-spec]` : choosing elements of a multi-valued variable.
          Note: when disecting the key, the actual length of the case variable is unknown, such that checks are limited.
          Rules:

           * no '[]': addresses always the whole variable - scalar or multi-valued. rng = ''
           * '[int]': addresses a single element of a multi-valued variable. rng = 'int'
           * '[int,int, ...]': addresses several elements of a multi-valued variable. rng = 'int,int,...'
           * '[int...int]': addresses a range of elements of a multi-valued variable. rng = 'int:int', i.e. a slice

        #. a time specification, denoted by `@time-spec` : action performed at specified time.
          Rules:

           * no '@': set actions are performed initially. get actions are performed at end of simulation (record final value)
           * @float: set/get action perfomred at specified time
           * @step optional-time-spec: Not allowed for set actions.
             Get actions performed at every communication point (no time-spec),
             or at time-spec time intervals

        Note: 'Get' actions are normally specified within 'results' and are the same for all cases.
          The possibility to observe specific variables in given cases is added through the syntax var@time : 'NoValue',
          which says: keep the value but record the variable.

        Args:
            key (str): the key of the spec item
            value (list[PyVal])=None: the values with respect to the item. For 'results' this is not used
        """
        if key in ("startTime", "stopTime", "stepSize"):
            self.special.update({key: value})  # just keep these as a dictionary so far
        else:  # expect a  variable-alias : value(s) specificator
            key, at_time_type, at_time_arg = self._disect_at_time(key, value)
            key, cvar_info, rng = self._disect_range(key)
            key = key.strip()
            if value is not None:  # check also the number of supplied values
                if isinstance(value, (str, float, int, bool)):  # make sure that there are always lists
                    value = [value]
                _assert(
                    sum(1 for _ in rng) == Case._num_elements(value),
                    f"Variable {key}: # values {Case._num_elements( value)} != # vars {sum( 1 for _ in rng)}",
                )
            var_refs = []
            var_vals = []
            for i, r in enumerate(rng):
                var_refs.append(cvar_info["variables"][r])
                if value is not None:
                    var_vals.append(value[i])
            # print(f"READ_SPEC, {key}@{at_time_arg}({at_time_type}):{value}[{rng}], alias={cvar_info}")
            if at_time_type in ("get", "step"):  # get actions
                for inst in cvar_info["instances"]:  # ask simulator to provide function to set variables:
                    _inst = self.cases.simulator.component_id_from_name(inst)
                    if not self.cases.simulator.allowed_action("get", _inst, tuple(var_refs), 0):
                        raise AssertionError(self.cases.simulator.message) from None
                    elif at_time_type == "get" or at_time_arg == -1:
                        self.add_action(
                            "get",
                            self.cases.simulator.get_variable_value,
                            (_inst, cvar_info["type"], tuple(var_refs)),
                            at_time_arg if at_time_arg <= 0 else at_time_arg * self.cases.timefac,
                        )
                    else:  # step actions
                        for time in np.arange(start=at_time_arg, stop=self.special["stopTime"], step=at_time_arg):
                            self.add_action(
                                time,
                                self.cases.simulator.get_variable_value,
                                (_inst, cvar_info["type"], tuple(var_refs)),
                                at_time_arg * self.cases.timefac,
                            )

            else:  # set actions
                assert value is not None, f"Variable {key}: Value needed for 'set' actions."
                assert at_time_type in ("set"), f"Unknown @time type {at_time_type} for case '{self.name}'"
                if SimulatorInterface.default_initial(cvar_info["causality"], cvar_info["variability"]) < 3:
                    assert at_time_arg <= self.special["startTime"], f"Initial settings at time {at_time_arg}?"
                    for inst in cvar_info["instances"]:  # ask simulator to provide function to set variables:
                        _inst = self.cases.simulator.component_id_from_name(inst)
                        if not self.cases.simulator.allowed_action("set", _inst, tuple(var_refs), 0):
                            raise AssertionError(self.cases.simulator.message) from None
                        self.add_action(
                            at_time_type,
                            self.cases.simulator.set_initial,
                            (_inst, cvar_info["type"], tuple(var_refs), tuple(var_vals)),
                            at_time_arg * self.cases.timefac,
                        )
                else:
                    for inst in cvar_info["instances"]:  # ask simulator to provide function to set variables:
                        _inst = self.cases.simulator.component_id_from_name(inst)
                        if not self.cases.simulator.allowed_action("set", _inst, tuple(var_refs), at_time_arg):
                            raise AssertionError(self.cases.simulator.message) from None
                        self.add_action(
                            at_time_type,
                            self.cases.simulator.set_variable_value,
                            (_inst, cvar_info["type"], tuple(var_refs), tuple(var_vals)),
                            at_time_arg * self.cases.timefac,
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

    def _ensure_specials(self, special: dict[str, Any]) -> dict[str, Any]:
        """Ensure that mandatory special variables are defined.
        The base case shall specify some special variables, needed by the simulator.
        These can be overridden by the hierarchy of a given case.
        The values of the base case ensure that critical values are always avalable.
        """

        def get_from_config(element: str, default: float | None = None):
            if isinstance(self.cases.simulator.sysconfig, Path):
                info = from_xml(self.cases.simulator.sysconfig, sub=None, xpath=".//{*}" + element)
                if not len(info):
                    return default
                txt = info[0].text
                if txt is None:
                    return default
                try:
                    return float(txt)
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
            jsfile = self.name + ".js5"
        elif not jsfile.endswith(".js5"):
            jsfile += ".js5"
        json5_write(results, Path(self.cases.file.parent, jsfile))

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

    @staticmethod
    def _actions_copy(actions: dict) -> dict:
        """Copy the dict of actions to a new dict,
        which can be changed without changing the original dict.
        Note: deepcopy cannot be used here since actions contain pointer objects.
        """
        res = {}
        for t, t_actions in actions.items():
            action_list = []
            for action in t_actions:
                action_list.append(partial(action.func, *action.args))
            res.update({t: action_list})
        return res

    @staticmethod
    def str_act(action: Callable):
        """Prepare a human readable view of the action."""
        txt = f"{action.func.__name__}(inst={action.args[0]}, type={action.args[1]}, ref={action.args[2]}"  # type: ignore
        if len(action.args) > 3:  # type: ignore
            txt += f", val={action.args[3]}"  # type: ignore
        return txt


class Cases:
    """Global book-keeping of all cases defined for a system model.

    * Ensure uniqueness of case names
    * Access to system model information: system model, component models and instantiated component models information
    * Definition of variable aliases (used throughout the cases)
    * Definition of cases and their relation (case hierarchy)

    Args:
        spec (Path): file name for cases specification
        simulator (SimulatorInterface)=None: Optional (pre-instantiated) SimulatorInterface object.
           If that is None, the spec shall contain a modelFile to be used to instantiate the simulator.
    """

    __slots__ = (
        "file",
        "spec",
        "simulator",
        "timefac",
        "variables",
        "base",
        "results",
        "_results_map",
        "results_print_type",
    )

    def __init__(
        self, spec: str | Path, simulator: SimulatorInterface | None = None, results_print_type: str = "names"
    ):
        self.file = Path(spec)  # everything relative to the folder of this file!
        assert self.file.exists(), f"Cases spec file {spec} not found"
        self.spec = Json5Reader(spec).js_py
        self.results_print_type = results_print_type
        if simulator is None:
            path = Path(self.file.parent, self.spec.get("modelFile", "OspSystemStructure.xml"))  # type: ignore
            assert path.exists(), f"OSP system structure file {path} not found"
            try:
                self.simulator = SimulatorInterface(
                    system=path, name=str(self.spec.get("name", "")), description=str(self.spec.get("description", ""))
                )
            except Exception as err:
                raise AssertionError(f"'modelFile' needed from spec: {err}") from err
        #            else:
        #                raise Exception("'modelFile' needed from spec.") from None
        #            assert path.exists(), f"'modelFile' {self.spec['modelFile']} not found."
        else:
            self.simulator = simulator  # SimulatorInterface( simulator = simulator)

        self.timefac = self._get_time_unit() * 1e9  # internally OSP uses pico-seconds as integer!
        # read the 'variables' section and generate dict { alias : { (instances), (variables)}}:
        self.variables = self.get_case_variables()
        self._results_map: dict = dict()  # cache of results indices translations used by results_map_get()
        self.read_cases()  # sets self.base and self.results

    def get_case_variables(self) -> dict[str, dict]:
        """Read the 'variables' main key, which defines self.variables (case variables) as a dictionary:
        { c_var_name : {'model':model ID, 'instances': tuple of instance names, 'variables': tuple of ValueReference,
        'type':CosimVariableType, 'causality':CosimVariableCausality, 'variability': CosimVariableVariability}.
        Optionally a description of the alias variable may be provided (and added to the dictionary).
        """
        _assert("variables" in self.spec, f"Mandatory key 'variables' not found in cases specification {self.file}")
        _assert(
            isinstance(self.spec["variables"], dict),
            "'variables' section of the spec should be a dict - name: [component(s), variable(s), [description]]",
        )
        if not isinstance(self.spec["variables"], dict):
            raise CaseInitError(
                "'variables' section of the spec should be a dict name: [component(s), variable(s), [description]]"
            ) from None

        variables = {}
        for k, v in self.spec["variables"].items():
            if not isinstance(v, list):
                raise CaseInitError(f"List of 'component(s)' and 'variable(s)' expected. Found {v}") from None
            _assert(len(v) in (2, 3), f"Variable spec should be: instance(s), variables[, description]. Found {v}.")
            _assert(
                isinstance(v[0], (str | tuple)),
                f"Component name(s) expected as first argument of variable spec. Found {v[0]}",
            )
            assert isinstance(v[0], str), f"String expected as model name. Found {v[0]}"
            model, comp = self.simulator.match_components(v[0])
            _assert(len(comp) > 0, f"No component model instances '{v[0]}' found for alias variable '{k}'")
            assert isinstance(v[1], str), f"Variable name(s) expected as second argument in variable spec. Found {v[1]}"
            _vars = self.simulator.match_variables(comp[0], v[1])  # tuple of matching var refs
            var: dict = {
                "model": model,
                "instances": comp,
                "variables": _vars,  # variables from same model!
            }
            _assert(len(var["variables"]) > 0, f"No matching variables found for alias {k}:{v}, component '{comp}'")
            if len(v) > 2:
                var.update({"description": v[2]})
            # We add also the more detailed variable info from the simulator (the FMU)
            # The type, causality and variability shall be equal for all variables.
            # The 'reference' element is the same as 'variables'.
            # next( iter( ...)) is used to get the first dict value
            var0 = next(iter(self.simulator.get_variables(model, _vars[0]).values()))  # prototype
            for i in range(1, len(var["variables"])):
                var_i = next(iter(self.simulator.get_variables(model, _vars[i]).values()))
                for test in ["type", "causality", "variability"]:
                    _assert(
                        var_i[test] == var0[test],
                        f"Variable with ref {var['variables'][i]} not same {test} as {var0} in model {model}",
                    )
            var.update({"type": var0["type"], "causality": var0["causality"], "variability": var0["variability"]})
            variables.update({k: var})
        return variables

    #     def get_alias_from_spec(self, modelname: str, instance: str, ref: Union[int, str]) -> str:
    #         """Get a variable alias from its detailed specification (modelname, instance, ref)."""
    #         for alias, var in self.variables.items():
    #             print("GET_ALIAS", alias, var)
    #             if var["model"].get("modelName") == modelname:
    #                 if instance in var["instances"]:
    #                     for v in var["variables"]:
    #                         if v.get("valueReference", "-1") == str(ref) or v.get("name", "") == ref:
    #                             return alias
    #
    def _get_time_unit(self) -> float:
        """Find system time unit from the spec and return as seconds.
        If the entry is not found, 1 second is assumed.
        """
        assert isinstance(self.spec, dict), f"Dict expected as spec. Found {type(self.spec)}"
        unit = str(self.spec["timeUnit"]) if "timeUnit" in self.spec else "second"
        if unit.lower().startswith("sec"):
            return 1.0
        if unit.lower().startswith("min"):
            return 60.0
        if unit.lower().startswith("h"):
            return 60 * 60.0
        if unit.lower().startswith("d"):
            return 24 * 60 * 60.0
        if unit.lower().startswith("y"):
            return 365 * 24 * 60 * 60.0
        if unit.lower() == "ms" or unit.lower().startswith("milli"):
            return 1.0 / 1000
        if unit.lower() == "us" or unit.lower().startswith("micro"):
            return 1.0 / 1000000
        return 1.0

    def read_cases(self):
        """Instantiate all cases defined in the spec.
        'results' and 'base' are defined firsts, since the others build on these
        Return the results and base case objects.
        The others are linked as sub-cases in their parent cases.
        """
        if (
            isinstance(self.spec, dict)
            and "base" in self.spec
            and isinstance(self.spec["base"], dict)
            and "spec" in self.spec["base"]
            and isinstance(self.spec["base"]["spec"], dict)
            and "results" in self.spec
            and isinstance(self.spec["results"], dict)
            and "spec" in self.spec["results"]
            and isinstance(self.spec["results"]["spec"], list)
        ):
            # we need to peek into the base case where startTime and stopTime should be defined
            special: dict[str, float] = {
                "startTime": self.spec["base"]["spec"].get("startTime", 0.0),  # type: ignore
                "stopTime": self.spec["base"]["spec"].get("stopTime", -1),  # type: ignore
            }  # type: ignore
            assert special["stopTime"] > 0, "No stopTime defined in base case"  # type: ignore        # all case definitions are top-level objects in self.spec. 'base' and 'results' are mandatory
            self.results = Case(
                self,
                "results",
                description=str(self.spec.get("description", "")),
                parent=None,
                spec=self.spec["results"].get("spec", None),
                special=special,
            )  # type: ignore
            self.base = Case(
                self,
                "base",
                description=str(self.spec.get("description", "")),
                parent=None,
                spec=self.spec["base"].get("spec", None),
                special=special,
            )  # type: ignore
            for k, v in self.spec.items():
                if k not in (
                    "name",
                    "description",
                    "modelFile",
                    "variables",
                    "timeUnit",  # ignore 'header'
                    "base",
                    "results",
                ):
                    assert isinstance(v, dict), f"dict expected as value {v} in read_case"
                    parent_name: str = v.get("parent", "base")  # type: ignore
                    parent_case = self.case_by_name(parent_name)
                    assert isinstance(parent_case, Case), f"Parent case needed for case {k}"
                    msg = f"Case spec expected. Found {v.get('spec')}"
                    assert "spec" in v and isinstance(v["spec"], dict), msg
                    _ = Case(self, k, description=str(v.get("description", "")), parent=parent_case, spec=v["spec"])
        else:
            raise CaseInitError(
                f"Mandatory main sections 'base' and 'results' needed. Found {list(self.spec.keys())}"
            ) from None

    def case_by_name(self, name: str) -> Case | None:
        """Find the case 'name' amoung all defined cases. Return None if not found.

        Args:
            name (str): the case name to find
        Returns:
            The case object or None
        """
        if self.base.name == name:
            return self.base
        elif self.results.name == name:
            return self.results
        else:
            found = self.base.case_by_name(name)
            if found is not None:
                return found
        return None

    def case_var_by_ref(self, comp: int | str, ref: int | tuple[int]) -> tuple[str, tuple]:
        """Get the case variable name related to the component model `comp` and the reference `ref`
        Returns a tuple of case variable name and an index (if composit variable).
        """
        component = self.simulator.component_name_from_id(comp) if isinstance(comp, int) else comp
        refs = (ref,) if isinstance(ref, int) else ref

        for var, info in self.variables.items():
            if component in info["instances"] and all(r in info["variables"] for r in refs):
                if len(refs) == len(info["variables"]):  # the whole variable is addressed
                    return (var, ())
                else:
                    return (var, tuple([info["variables"].index(r) for r in refs]))
        return ("", ())

    def info(self, case: Case | None = None, level: int = 0) -> str:
        """Show main infromation and the cases structure as string."""
        txt = ""
        if case is None:
            case = self.base
            txt += f"Cases {self.spec.get('name','noName')}. {self.spec.get('description','')}\n"
            if "modelFile" in self.spec:
                txt += f"System spec '{self.spec['modelFile']}'.\n"
            assert isinstance(case, Case), "At this point a Case object is expected as variable 'case'"
            txt += self.info(case=case, level=level)
        elif isinstance(case, Case):
            txt += "  " * level + case.name + "\n"
            for c in case.subs:
                txt += self.info(case=c, level=level + 1)
        else:
            raise ValueError(f"The argument 'case' shall be a Case object or None. Type {type(case)} found.")
        return txt

    def _make_results_header(self, case: Case):
        """Make a standard header for the results of 'case'.
        The data is added in run_case().
        """
        assert isinstance(self.spec, dict), f"Top level spec of cases: {type(self.spec)}"
        results = {
            "Header": {
                "case": case.name,
                "dateTime": time.time(),
                "cases": self.spec.get("name", "None"),
                "file": str(self.file),
                "casesDate": os.path.getmtime(self.file),
                "timeUnit": self.spec.get("timeUnit", "None"),
                "timeFactor": self.timefac,
            }
        }
        return results

    def _results_map_get(self, comp: int, refs: tuple[int]):
        """Get the translation of the component id `comp` + references `refs`
        to the variable names used in the cases file.
        To speed up the process the process the cache dict _results_map is used.
        """
        try:
            component, var = self._results_map[comp][refs]
        except Exception:
            component = self.simulator.component_name_from_id(comp)
            var, rng = self.case_var_by_ref(component, refs)
            if len(rng):  # elements of a composit variable
                var += f"{list(rng)}"
            if comp not in self._results_map:
                self._results_map.update({comp: {}})
            self._results_map[comp].update({refs: (component, var)})
        return component, var

    def _results_add(self, results: dict, time: float, comp: int, typ: int, refs: tuple[int], values: list):
        """Add the results of a get action to the results dict for the case.

        Args:
            results (dict): The results dict (js5-dict) collected so far and where a new item is added.
            time (float): the time of the results
            component (int): The index of the component
            typ (int): The data type of the variable as enumeration int
            ref (list): The variable references linked to this variable definition
            values (list): the values of the variable
            print_type (str)='plain': 'plain': use indices as supplied
        """
        if self.results_print_type == "plain":
            ref = refs[0] if len(refs) == 1 else str(refs)  # comply to js5 key rules
        elif self.results_print_type == "names":
            comp, ref = self._results_map_get(comp, refs)
        if time in results:
            if comp in results[time]:
                results[time][comp].update({ref: values})
            else:
                results[time].update({comp: {ref: values}})
        else:
            results.update({time: {comp: {ref: values}}})

    def run_case(self, name: str | Case, dump: bool | str = False):
        """Set up case 'name' and run it.

        Args:
            name (str,Case): case name as str or case object. The case to be run
            dump (str): Optionally save the results as json file.
              False:  only as string, True: json file with automatic file name, str: explicit filename.json
        """

        if isinstance(name, str):
            case = self.case_by_name(name)
            assert isinstance(case, Case), f"Could not find the case represented by {name}"
        elif isinstance(name, Case):
            case = name
        else:
            raise CaseUseError(f"Case {name} was not found") from None
        # Note: final actions are included as _get at end time
        # print("ACTIONS_SET", settings['actions_set')
        # print("ACTIONS_GET", settings['actions_get')
        # print("ACTIONS_STEP", settings['actions_step')
        act_step = case.act_get.get(-1, None)
        time = int(case.special["startTime"] * self.timefac)
        tstop = int(case.special["stopTime"] * self.timefac)
        tstep = int(case.special["stepSize"] * self.timefac)

        set_iter = case.act_set.items().__iter__()  # iterator over set actions => time, action_list
        try:
            t_set, a_set = next(set_iter)
        except StopIteration:
            t_set, a_set = (float("inf"), [])  # satisfy linter
        get_iter = case.act_get.items().__iter__()  # iterator over get actions => time, action_list
        try:
            t_get, a_get = next(get_iter)
        except StopIteration:
            t_get, a_get = (tstop + 1, [])
        results = self._make_results_header(case)
        print(f"BEFORE LOOP: {time}:{t_set}, act:{a_set}")
        while time < tstop:
            while time >= t_set:  # issue the set actions
                print(f"@{time}. Set actions {a_set}")
                for a in a_set:
                    a()
                try:
                    t_set, a_set = next(set_iter)
                except StopIteration:
                    t_set, a_set = 10 * tstop, []
            time += tstep
            print(f"(Re-)Start simulator at {time} with step {tstep}")
            self.simulator.simulator.simulate_until(time)

            while time >= t_get:  # issue the current get actions
                print("GET", time, t_get, a_get)
                for a in a_get:
                    # print("GET args", time, a.args)
                    self._results_add(results, time / self.timefac, a.args[0], a.args[1], a.args[2], a())
                try:
                    t_get, a_get = next(get_iter)
                except StopIteration:
                    t_get, a_get = 10 * tstop, []

            if act_step is not None:  # there are step-always actions
                for a in act_step:
                    # print("STEP args", a.args)
                    self._results_add(results, time / self.timefac, a.args[0], a.args[1], a.args[2], a())

        if dump:
            print(f"saving to file {dump}")
            case.save_results(results, dump)
        case.results = results
        return results
