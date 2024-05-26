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
                if isinstance(v, (str, float, int, bool)) or (
                    isinstance(v, list) and all(isinstance(x, (str, float, int, bool)) for x in v)
                ):
                    self.read_spec_item(k, v)  # type: ignore
                else:
                    raise AssertionError(f"Unhandled spec value {v}") from None

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

    def add_action(self, typ: str, action: Callable, args: tuple, at_time: float | None = None):
        """Add an action to one of the properties act_set, act_get, act_final, act_step - used for results.
        We use functools.partial to return the functions with fully filled in arguments.
        Compared to lambda... this allows for still accessible (testable) argument lists.

        Args:
            typ (str): the action type 'final', 'single' or 'step'
            action (Callable): the relevant action (manipulator/observer) function to perform
            args (tuple): action arguments as tuple (instance:str, type:int, valueReferences:list[int][, values])
            at_time (float): optional time argument (not needed for all actions)
        """
        if typ == "get":
            dct = self.act_get
        elif typ == "set":
            dct = self.act_set
        else:
            raise AssertionError(f"Unknown typ {typ} in add_action")
        assert at_time is not None or typ == "get", "Set actions require a defined time"
        if at_time in dct:
            for i, act in enumerate(dct[at_time]):
                if all(act.args[i] == args[i] for i in range(3)):
                    dct[at_time][i] = partial(action, *args)
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
            value (PyVal, list(PyVal)): the value argument

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
            if self.name == "results" or value is None:
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

    def _disect_range(self, txt: str, value: PyVal | list[PyVal] | None) -> tuple[str, str]:
        """Extract the explicit variable range, if relevant
        (multi-valued variables where only some all elements are addressed).
        Note: it is not explicitly checked whether 'value' containsexacly the number of values required for the range.
        """
        pre, _, rng = txt.partition("[")
        if len(rng):  # range among several variables as python slice or comma-separated list
            rng = rng.rstrip("]").strip()
            msg = f"More than one value required to handle multi-valued setting [{rng}]"
            assert self.name == "results" or rng == "0" or isinstance(value, list), msg
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
            key, at_time_type, at_time_arg = self._disect_at_time(key, value)
            key, rng = self._disect_range(key, value)
            key = key.strip()
            try:
                var_alias = self.cases.variables[key]
            except KeyError as err:
                raise CaseInitError(f"Variable {key} was not found in list of defined variable aliases") from err
            var_refs = []
            var_vals = []
            # print(f"READ_SPEC, {key}@{at_time_arg}({at_time_type}):{value}[{rng}], alias={var_alias}")
            if at_time_type in ("get", "step"):  # get actions
                if rng == "":  # a single variable
                    var_refs.append(int(var_alias["variables"][0]))
                else:  # multiple variables
                    for [k, _] in tuple2_iter(var_alias["variables"], var_alias["variables"], rng):
                        var_refs.append(k)
                for inst in var_alias["instances"]:  # ask simulator to provide function to set variables:
                    _inst = self.cases.simulator.simulator.slave_index_from_instance_name(inst)
                    if not self.cases.simulator.allowed_action("get", _inst, tuple(var_refs), 0):
                        raise AssertionError(self.cases.simulator.message) from None
                    elif at_time_type == "get" or at_time_arg == -1:
                        self.add_action(
                            "get",
                            self.cases.simulator.get_variable_value,
                            (_inst, var_alias["type"], tuple(var_refs)),
                            at_time_arg if at_time_arg <= 0 else at_time_arg * self.cases.timefac,
                        )
                    else:  # step actions
                        for time in np.arange(start=at_time_arg, stop=self.special["stopTime"], step=at_time_arg):
                            self.add_action(
                                time,
                                self.cases.simulator.get_variable_value,
                                (_inst, var_alias["type"], tuple(var_refs)),
                                at_time_arg * self.cases.timefac,
                            )

            else:  # set actions
                assert value is not None, f"Value needed for manipulator actions. Found {value}"
                if rng == "":  # a single variable
                    var_refs.append(var_alias["variables"][0])
                    var_vals.append(
                        SimulatorInterface.pytype(
                            var_alias["type"], value if isinstance(value, (str, float, int, bool)) else value[0]
                        )
                    )
                elif isinstance(value, list):  # multiple variables
                    for [k, v] in tuple2_iter(var_alias["variables"], tuple(value), rng):
                        var_refs.append(k)
                        var_vals.append(SimulatorInterface.pytype(var_alias["type"], v))

                assert at_time_type in ("set"), f"Unknown @time type {at_time_type} for case '{self.name}'"
                if at_time_arg <= self.special["startTime"]:  # initial settings use set_initial
                    for inst in var_alias["instances"]:  # ask simulator to provide function to set variables:
                        _inst = self.cases.simulator.simulator.slave_index_from_instance_name(inst)
                        if not self.cases.simulator.allowed_action("set", _inst, tuple(var_refs), 0):
                            raise AssertionError(self.cases.simulator.message) from None
                        self.add_action(
                            at_time_type,
                            self.cases.simulator.set_initial,
                            (_inst, var_alias["type"], tuple(var_refs), tuple(var_vals)),
                            at_time_arg * self.cases.timefac,
                        )
                else:
                    for inst in var_alias["instances"]:  # ask simulator to provide function to set variables:
                        _inst = self.cases.simulator.simulator.slave_index_from_instance_name(inst)
                        if not self.cases.simulator.allowed_action("set", _inst, tuple(var_refs), at_time_arg):
                            raise AssertionError(self.cases.simulator.message) from None
                        self.add_action(
                            at_time_type,
                            self.cases.simulator.set_variable_value,
                            (_inst, var_alias["type"], tuple(var_refs), tuple(var_vals)),
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
        json5_write(results, Path( self.cases.file.parent, jsfile))

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

    __slots__ = ("file", "spec", "simulator", "timefac", "variables", "base", "results")

    def __init__(self, spec: str | Path, simulator: SimulatorInterface | None = None):
        self.file = Path(spec)  # everything relative to the folder of this file!
        assert self.file.exists(), f"Cases spec file {spec} not found"
        self.spec = Json5Reader(spec).js_py
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
        self.variables = self.get_alias_variables()
        self.read_cases()  # sets self.base and self.results

    def get_alias_variables(self) -> dict[str, dict]:
        """Read the 'variables' main key, which defines self.variables (aliases) as a dictionary:
        { alias : {'model':model ID, 'instances': tuple of instance names, 'variables': tuple of ValueReference,
        'type':CosimVariableType, 'causality':CosimVariableCausality, 'variability': CosimVariableVariability}.
        Optionally a description of the alias variable may be provided (and added to the dictionary).
        """
        msg = "Expecting the key 'variables' in the case study specification, defining the model variables in terms of component model instances and variable names"
        assert "variables" in self.spec, msg
        msg = "Expecting the 'variables' section of the spec to be a dictionary of variable alias : [component(s), variable(s), [description]]"
        assert isinstance(self.spec["variables"], dict), msg
        variables = {}
        for k, v in self.spec["variables"].items():
            assert isinstance(v, list), f"List of 'component(s)' and 'variable(s)' expected. Found {v}"
            msg = f"2 or 3 elements expected as variable spec: [instances, variables[, description]]. Found {len(v)}."
            assert len(v) in (2, 3), msg
            msg = f"Component name(s) expected as first argument of variable spec. Found {v[0]}"
            assert isinstance(v[0], (str | tuple)), msg
            model, comp = self.simulator.match_components(v[0])
            assert len(comp), f"No component model instances '{v[0]}' found for alias variable '{k}'"
            msg = f"Variable name(s) expected as second argument in variable spec. Found {v[1]}"
            assert isinstance(v[1], str), msg
            _vars = self.simulator.match_variables(comp[0], v[1])  # tuple of matching var refs
            var: dict = {
                "model": model,
                "instances": comp,
                "variables": _vars,  # variables from same model!
            }
            assert len(var["variables"]), f"No matching variables found for alias {k}:{v}, component '{comp}'"
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
                    msg = f"Variable with ref {var['variables'][i]} not same {test} as {var0} in model {model}"
                    assert var_i[test] == var0[test], msg
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
                "stopTime": self.spec["base"]["spec"].get("stopTime", -1),     # type: ignore
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
                "Both the sections 'base' and 'results' shall be defined as js5 objects in *.cases"
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
        else:
            found = self.base.case_by_name(name)
            if found is not None:
                return found
        return None

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

    def run_case(self, name: str | Case, dump: bool | str = False):
        """Set up case 'name' and run it.

        Args:
            name (str,Case): case name as str or case object. The case to be run
            dump (str): Optionally save the results as json file.
              False:  only as string, True: json file with automatic file name, str: explicit filename.json
        """

        def results_add(time, instance, alias, rng, values):

            try:
                [time].update({alias: [instance, rng, values]})
            except Exception:  # first set for this time
                results.update({time: {alias: [instance, rng, values]}})

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
                    t_set, a_set = float("inf"), []
            #            print(f"(Re-)Start simulator at {time} with step {tstep}")
            time += tstep
            self.simulator.simulator.simulate_until(time)

            while time >= t_get:  # issue the current get actions
                #                print("GET", time, t_get, a_get)
                for a in a_get:
                    #                    print("GET args", time, a.args)
                    results_add(time / self.timefac, a.args[0], a.args[1], a.args[2], a())
                try:
                    t_get, a_get = next(get_iter)
                except StopIteration:
                    t_get, a_get = float("inf"), []

            if act_step is not None:  # there are step-always actions
                for a in act_step:
                    #                    print("STEP args", a.args)
                    results_add(time / self.timefac, a.args[0], a.args[1], a.args[2], a())

        if dump:
            case.save_results(results, dump)
        case.results = results
        return results


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
