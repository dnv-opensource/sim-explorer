# pyright: reportMissingImports=false, reportGeneralTypeIssues=false
from __future__ import annotations

import os
import time
from functools import partial
from pathlib import Path
from typing import TypeAlias

import matplotlib.pyplot as plt

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
        spec: Json5 | Json5List | None = None,
    ):
        self.cases = cases
        self.name = name
        self.description = description
        self.parent = parent
        self.subs = []
        self.spec = {} if spec is None else spec
        self.special = {}  # dict of special variable : value, like stopTime. @start of run this is sent to the Simulator to deal with it
        self.act_set = {}  # dict of manipulator actions for specific times and this case. Updated by read_spec_item
        self.act_get = {}  # dict of observer actions for specific times and this case. Updated by read_spec_item
        self.act_final = []  # observer actions at end of simulation
        self.act_step = {}  # observer actions at intervals: {dt1:[actions...],...} where dt=None denotes all macro time steps
        self.results = {}  # Json5 dict added by cases.run_case() when run
        if self.name == "results":
            assert isinstance(self.spec, list), f"A list is expected as spec. Found {self.spec}"
            for k in self.spec:  # only keys, no values
                assert isinstance(k, str), f"A key (str) is expected as list element in results. Found {k}"
                self.read_spec_item(k)
        else:
            assert isinstance(self.spec, dict), f"A dict is expected as spec. Found {self.spec}"
            for k, v in self.spec.items():
                if isinstance(v, PyVal) or (isinstance(v, list) and all(isinstance(x, PyVal) for x in v)):
                    self.read_spec_item(k, v)  # type: ignore
                else:
                    raise AssertionError(f"Unhandled spec value {v}") from None

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
                info = from_xml(self.cases.simulator.sysconfig, sub=None, xpath=".//{*}" + element)
                if not len(info):
                    return default
                info = info[0].text
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
        self.file = spec
        self.spec = Json5Reader(spec).js_py
        if simulator is None:
            #            if isinstance( self.spec.get('modelFile', None), ( Path, str)):
            try:
                path = Path(str(self.spec["modelFile"])).resolve()
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
        for k, v in self.spec.items():  # all case definitions are top-level objects in self.spec
            if k in ("name", "description", "modelFile", "variables", "timeUnit"):  # ignore 'header'
                pass
            else:
                assert isinstance(v, dict), f"dict expected as value {v} in read_case"
                parent, case = self.read_case(k, v)  # type: ignore

                if k in ("base", "results"):  # should always be included. Define properties.
                    setattr(self, k, case)
                    if k == "base":
                        print(self.base)
                else:
                    assert isinstance(parent, Case), f"Parent case needed for case {case.name}"
                    parent.append(case)

    def get_alias_variables(self) -> dict[str, dict]:
        """Read the 'variables' main key, which defines self.variables (aliases) as a dictionary:
        { alias : {'model':model ID, 'instances': tuple of instance names, 'variables': tuple of ValueReference,
          'type':CosimVariableType, 'causality':CosimVariableCausality, 'variability': CosimVariableVariability}.
        Optionally a description of the alias variable may be provided (and added to the dictionary).
        """
        assert (
            "variables" in self.spec
        ), "Expecting the key 'variables' in the case study specification, defining the model variables in terms of component model instances and variable names"
        assert isinstance(
            self.spec["variables"], dict
        ), "Expecting the 'variables' section of the spec to be a dictionary of variable alias : [component(s), variable(s), [description]]"
        variables = {}
        for k, v in self.spec["variables"].items():
            assert isinstance(v, list), f"List of 'component(s)' and 'variable(s)' expected. Found {v}"
            assert len(v) in (
                2,
                3,
            ), f"2 or 3 elements expected as variable spec: [instances, variables[, description]]. Found {len(v)}."
            assert isinstance(
                v[0], (str | tuple)
            ), f"Component name(s) expected as first argument of variable spec. Found {v[0]}"
            model, comp = self.simulator.match_components(v[0])
            assert len(comp), f"No component model instances '{v[0]}' found for alias variable '{k}'"

            assert isinstance(v[1], str), f"Variable name(s) expected as second argument in variable spec. Found {v[1]}"
            _vars = self.simulator.match_variables(comp[0], v[1])
            var = {
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
            var0 = next(iter(self.simulator.get_variables(model, var["variables"][0]).values()))
            for i in range(1, len(var["variables"])):
                var_i = self.simulator.get_variables(model, var["variables"][i])
                for test in ["type", "causality", "variability"]:
                    assert (
                        var_i[test] == var0[test]
                    ), f"Variable with ref {var['variables'][i]} not same {test} as {var0} in model {model}"
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

    def read_case(self, name: str, spec: Json5) -> tuple[Case | None, Case]:
        """Define the case 'name'Based on the cases specification 'spec' as json5 python dict, register case 'name
        Generate case objects and store as 'self.base' or in list 'self.subs' of sub-cases.
        """
        if name in ("base", "results"):  # these two are top level objects, linking to Cases
            parent_name, parent_case = ("", None)
        else:
            parent_name = spec.get("parent", "base")
            parent_case = self.case_by_name(str(parent_name))
            assert parent_case is not None, f"For case {name} with parent {parent_name} the parent case was not found"
        assert "spec" in spec and isinstance(
            spec["spec"], (dict, list)
        ), f"Case spec expected. Found {spec.get('spec')}"
        case = Case(self, name, description=str(spec.get("description", "")), parent=parent_case, spec=spec["spec"])
        return (parent_case, case)

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

    def collect_settings(self, case: Case, tfac: float = 1.0) -> dict[str, dict]:
        """Iterate through the case hierarchy of this case, collecting 'special' settings and time-based actions.

        Args:
            case (Case): The case object for which to collect the settings
            tfac (float)=1.0: A time scaling factor. Time becomes an integer (in OSP)

        Returns
        -------
            A dict[str, dict|list] containing the named special variables and the named actions.
            special : startTime, stopTime, stepSize
            actions_set : dict of manipulator actions for specific times and this case.
            actions_get : dict of observer actions for specific times and this case.
              Includes also final actions at stopTime, step actions in periodic intervals
              and step actions without time argument (each step) as time=None.
        """

        def add_action(dct: dict, time: float, action_list: list):
            try:
                dct[time].extend(action_list)
            except Exception:
                dct.update({time: action_list})

        special = {}
        # 1. Get the 'special' settings, which also contain 'startTime', 'stepSize' and 'stopTime'
        for c in case.iter():
            special.update(c.special)  # update the special variables through the hierarchy, keeping the last value
        tstart = special["startTime"]
        tstop = special["stopTime"]
        settings = {"special": special}

        actions_set = {}  # dict of absolute times and list of manipulator actions issued at these times

        # 2. Do another iteration to collect actions_set
        for c in case.iter():
            for t, alist in c.act_set.items():
                add_action(actions_set, int(t * tfac) if t < tstart else int(tstart * tfac), alist)

        # 3. Collect actions_get
        actions_get = {}  # dict of absolute times and list of observer actions issued at these times
        for t, alist in self.results.act_get.items():
            add_action(actions_get, int(t * tfac) if t < tstart else int(tstart * tfac), alist)

        for dt, alist in self.results.act_step.items():  # step actions. Time value represents an interval time!
            if dt is None:  # do this at all macro steps (which may be unknown at this point, i.e. variable)
                print("ACTION NONE", dt, alist, actions_get)
                if None in actions_get:
                    actions_get[None].extend(alist)
                else:
                    actions_get.update({None: alist})
            else:  # a step interval explicitly provided. We add the (known) times to the actions dict.
                t = int(tstart * tfac)
                dt = int(dt * tfac)
                while t <= int(tstop * tfac):
                    add_action(actions_get, t, alist)
                    t += dt
        # 4. Final get actions
        if len(self.results.act_final):  # add these at stopTime
            for c in case.iter():
                add_action(actions_get, int(tstop * tfac), c.act_final)

        settings.update({"actions_set": actions_set, "actions_get": actions_get})

        return settings

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
              False: results only as string, True: json file with automatic file name, str: explicit filename.json
        """

        def action_iter(dct):
            for t, lst in dct.items():
                if t is not None:  # None means at each step!
                    yield t, lst

        def results_add(time, instance, alias, rng, values):
            try:
                results[time].update({alias: [instance, rng, values]})
            except Exception:  # first set for this time
                results.update({time: {alias: [instance, rng, values]}})

        if isinstance(name, Case):
            case = name
        else:
            case = self.case_by_name(name)
        assert isinstance(case, Case), f"Could not find the case represented by {name}"

        settings = self.collect_settings(case, self.timefac)
        # Note: final actions are included as _get at end time
        #        print("ACTIONS_SET", settings['actions_set')
        #        print("ACTIONS_GET", settings['actions_get')
        #        print("ACTIONS_STEP", settings['actions_step')
        time = int(settings["special"]["startTime"] * self.timefac)
        tstop = int(settings["special"]["stopTime"] * self.timefac)
        tstep = int(settings["special"]["stepSize"] * self.timefac)

        next_set = action_iter(settings["actions_set"])
        try:
            t_set, a_set = next(next_set)
        except StopIteration:
            t_set, a_set = (float("inf"), [])  # satisfy linter
        next_get = action_iter(settings["actions_get"])
        try:
            t_get, a_get = next(next_get)
        except StopIteration:
            t_get, a_get = (tstop + 1, [])
        results = self._make_results_header(case)
        while time < tstop:
            if time >= t_set:  # issue the set actions
                for a in a_set:
                    a()
                try:
                    t_set, a_set = next(next_set)
                except StopIteration:
                    pass

            self.simulator.simulator.simulate_until(tstep)

            if time >= t_get:  # issue the current get actions
                #                print("GET", time, t_get, a_get)
                for a in a_get:
                    print("GET args", time, a.args)
                    results_add(time, a.args[0], a.args[1], a.args[2], a())
                t_get, a_get = next(next_get)
            if None in settings["actions_get"]:  # there are step-always actions
                for a in settings["actions_get"][None]:  # observed at every step
                    #                print("STEP args", a.args)
                    results_add(time, a.args[0], a.args[1], a.args[2], a())

            time += tstep
        #            print("TIME ", time)

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
