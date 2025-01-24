"""
Python module to manage cases
with respect to reading *.cases files, running cases and storing results.
"""

from __future__ import annotations

import copy
import os
from collections.abc import Callable, Generator, Iterable, Iterator, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from sim_explorer.assertion import Assertion
from sim_explorer.exceptions import CaseInitError
from sim_explorer.json5 import Json5
from sim_explorer.models import AssertionResult, Temporal
from sim_explorer.system_interface import SystemInterface
from sim_explorer.system_interface_osp import SystemInterfaceOSP
from sim_explorer.utils.misc import from_xml
from sim_explorer.utils.paths import get_path, relative_path
from sim_explorer.utils.types import TValue

"""
sim_explorer module for definition and execution of simulation experiments
* read and compile the case definitions from configuration file
  Note that Json5 is here restriced to 'ordered keys' and 'unique keys within an object'
* set the start variables for a given case
* manipulate variables according to conditions during the simulation run
* save requested variables at given communication points during a simulation run
* check the validity of results when saving variables

With respect to MVx in general, this module serves the preparation of start conditions for smart testing.
Note: The classes Case and Cases should be kept together in this file to avoid circular references.
"""


class Case:
    """Instantiation of a Case object.
    Sub-cases are strored ins list 'self.subs'.
    Parent case is stored as 'self.parent' (None for 'base').
    The Cases object is registered as 'self.cases' and registers the unique case 'self.base'.

    Args:
        cases (Cases): Reference to the related Cases object
        name (str): Unique name of the case
        spec (dict): the dictionary of the case specification
    """

    def __init__(
        self,
        cases: Cases,
        name: str,
        spec: dict[str, Any],
        special: dict[str, Any] | None = None,
    ) -> None:
        self.cases = cases
        self.name = name
        self.js = Json5(spec)
        self.description = self.js.jspath("$.description", str) or ""
        self.subs: list = []  # own subcases
        self.res: Results | None = None

        if name == "base":
            self.parent = None
        else:  # all other cases need a parent
            parent_name = self.js.jspath("$.parent", str) or "base"
            parent_case = self.cases.case_by_name(parent_name)
            assert isinstance(parent_case, Case), f"Parent case for {self.name} required. Found {parent_name}"
            self.parent = parent_case
            self.parent.append(self)

        if self.name == "results":
            raise ValueError("'results' should not be used as case name. Add general results to 'base'")

        self.special: dict[str, Any] = {}
        self.act_get: dict[float, list[tuple[float, list[tuple[Any, ...]]]]] = {}
        self.act_set: dict[float, list[tuple[float, list[tuple[Any, ...]]]]] = {}
        if self.name == "base":  # take over the results info and activities
            assert special is not None, "startTime and stopTime settings needed for 'base'"
            self.special = special
            self.act_get = {}
            self.act_set = {}  # no set actions during results collection
        else:
            assert isinstance(self.parent, Case), f"Parent case expected for case {self.name}"
            self.special = dict(self.parent.special)
            self.act_get = copy.deepcopy(self.parent.act_get)
            self.act_set = copy.deepcopy(self.parent.act_set)

        if self.cases.simulator.full_simulator_available:
            for k, v in self.js.jspath(path="$.spec", typ=dict, errorMsg=True).items():
                self.read_spec_item(k, v)
            _results = self.js.jspath("$.results", list)
            if _results is not None:
                for _res in _results:
                    self.read_spec_item(_res)
            self.asserts: list = []  # list of assert keys
            _assert = self.js.jspath("$.assert", dict)
            if _assert is not None:
                for k, v in _assert.items():
                    _ = self.read_assertion(k, v)
            if self.name == "base":
                self.special = self._ensure_specials(self.special)  # must specify for base case
            self.act_get = dict(sorted(self.act_get.items()))
            self.act_set = dict(sorted(self.act_set.items()))
        # self.res represents the Results object and is added when collecting results or when evaluating results

    def add_results_object(self, res: Results) -> None:
        self.res = res

    def iter(self) -> Generator[Case, None, None]:
        """Construct an iterator, allowing iteration from base case to this case through the hierarchy."""
        h = []
        nxt = self
        while True:  # need first to collect the path to the base case
            h.append(nxt)
            if nxt.parent is None:
                break
            nxt = nxt.parent
        while len(h):
            yield h.pop()

    def case_by_name(self, name: str) -> Case | None:
        """Find the case 'name' within sub-hierarchy of this case. Return None if not found.

        Args:
            name (str): the case name to find
        Returns:
            The case object or None
        """
        for c in self.subs:
            if c.name == name:
                return c
            found = c.case_by_name(name)
            if found is not None:
                return found
        return None

    def append(self, case: Case) -> None:
        """Append a case as sub-case to this case."""
        self.subs.append(case)

    def _add_actions(self, act_type: str, at_time: float, act_list: list[Callable]) -> None:
        """Add actions to one of the properties act_get, act_set.
        The act_list should be prepared by the system_interface in the way it is needed there.
        """
        dct = self.act_get if act_type == "get" else self.act_set

        if at_time not in dct:
            dct.update({at_time: []})
        dct[at_time].extend(act_list)

    @staticmethod
    def _num_elements(obj: object) -> int:
        if obj is None:
            return 0
        if isinstance(obj, tuple | list | np.ndarray):
            return len(obj)
        if isinstance(obj, str):
            return int(len(obj) > 0)
        return 1

    def _disect_at_time_tl(
        self,
        txt: str,
        value: Any | None = None,  # noqa: ANN401
    ) -> tuple[str, Temporal, tuple[str | float, ...]]:
        """Disect the @txt argument into 'at_time_type' and 'at_time_arg' for Temporal specification.

        Args:
            txt (str): The key text after '@' and before ':'
            value (Any): the value argument. Needed to distinguish the action type

        Returns
        -------
            tuple of pre, type, arg, where
            pre is the text before '@',
            type is the Temporal type,
            args is the tuple of temporal arguments (may be empty)
        """

        def time_spec(at: str) -> tuple[Temporal, tuple[str | float, ...]]:
            """Analyse the specification after '@' and disect into typ and arg."""
            try:
                arg_float = float(at)
                return (Temporal["T"], (arg_float,))
            except ValueError:
                for i in range(len(at) - 1, -1, -1):
                    try:
                        typ = Temporal[at[i]]
                    except KeyError:  # noqa: PERF203
                        pass
                    else:
                        if at[i + 1 :].strip() == "":
                            return (typ, ())
                        if typ == Temporal.T:
                            return (typ, (float(at[i + 1 :].strip()),))
                        return (typ, (at[i + 1 :].strip(),))
                raise ValueError(f"Unknown Temporal specification {at}") from None

        pre, _, at = txt.partition("@")
        assert len(pre), f"'{txt}' is not allowed as basis for _disect_at_time"
        assert isinstance(value, list), f"Assertion spec expected: [expression, description]. Found {value}"
        if not len(at):  # no @time spec. Assume 'A'lways
            return (pre, Temporal.ALWAYS, ())
        typ, arg = time_spec(at)
        return (pre, typ, arg)

    def _disect_at_time_spec(
        self,
        txt: str,
        value: Any | None = None,  # noqa: ANN401
    ) -> tuple[str, str, float]:
        """Disect the @txt argument into 'at_time_type' and 'at_time_arg'.

        Args:
            txt (str): The key text after '@' and before ':'
            value (Any): the value argument. Needed to distinguish the action type

        Returns
        -------
            tuple of pre, type, arg, where
            pre is the text before '@',
            type is the type of action (get, set, step),
            arg is the time argument, or -1
        """

        def time_spec(at: str) -> tuple[str, float]:
            """Analyse the specification after '@' and disect into typ and arg."""
            try:
                arg_float = float(at)
                return ("set" if Case._num_elements(value) else "get", arg_float)
            except ValueError:
                arg_float = float("-inf")
                if at.startswith("step"):
                    try:
                        return ("step", float(at[4:]))
                    except Exception:  # noqa: BLE001
                        return ("step", -1)  # this means 'all macro steps'
                else:
                    raise AssertionError(f"Unknown '@{txt}'. Case:{self.name}, value:'{value}'") from None

        pre, _, at = txt.partition("@")
        assert len(pre), f"'{txt}' is not allowed as basis for _disect_at_time"
        if value in ("result", "res"):  # mark variable specification as 'get' or 'step' action
            value = None
        if not len(at):  # no @time spec
            if value is None:
                assert self.special is not None
                return (pre, "get", self.special["stopTime"])  # report final value
            msg = f"Value required for 'set' in _disect_at_time('{txt}','{self.name}','{value}')"
            assert Case._num_elements(value), msg
            return (pre, "set", 0)  # set at startTime
        # time spec provided
        typ, arg = time_spec(at)
        return (pre, typ, arg)

    def read_assertion(self, key: str, expr_descr: list[str] | None = None) -> str:
        """Read an assert statement, compile as sympy expression, register and store the key..

        Args:
            key (str): Identification key for the assertion. Should be unique. Recommended to use numbers

            Also assertion keys can have temporal specifications (@...) with the following possibilities:

               * @A : The expression is expected to be Always (globally) true
               * @F : The expression is expected to be true during the end of the simulation
               * @<val> or @T<val>: The expression is expected to be true at the specific time value
            expr: A python expression using available variables
        """
        key, at_time_type, at_time_arg = self._disect_at_time_tl(key, expr_descr)
        assert isinstance(expr_descr, list), f"Assertion expression {expr_descr} should include a description."
        expr, descr = expr_descr
        _ = self.cases.assertion.expr(key, expr)
        _ = self.cases.assertion.description(key, descr)
        _ = self.cases.assertion.temporal(key, at_time_type, at_time_arg)
        if key not in self.asserts:
            self.asserts.append(key)
        return key

    def read_spec_item(
        self,
        key: str,
        value: Any | None = None,  # noqa: ANN401
    ) -> None:
        """Use the alias variable information (key) and the value to construct an action function,
        which is run when this variable is set/read.

        In the simplest case, the key is a cases variable name. Optionally two elements can be added:

        1. a range, denoted by `[range-spec]` : choosing elements of a multi-valued variable.
           Note: when disecting the key, the actual length of the case variable is unknown, such that checks are limited.
           Rules:

           * no '[]': addresses always the whole variable - scalar or multi-valued. rng = ''
           * '[int]': addresses a single element of a multi-valued variable. rng = 'int'
           * '[int,int, ...]': addresses several elements of a multi-valued variable. rng = 'int,int,...'
           * '[int...int]': addresses a range of elements of a multi-valued variable. rng = 'int:int', i.e. a slice

        2. a time specification, denoted by `@time-spec` : action performed at specified time.
           Rules:

           * no '@': set actions are performed initially. get actions are performed at end of simulation (record final value)
           * @float: set/get action perfomred at specified time
           * @step optional-time-spec: Not allowed for set actions.
             Get actions performed at every communication point (no time-spec),
             or at time-spec time intervals

        Note: 'Get' actions can be specified in a few ways:

           #. All case settings are automatically reported at start time and do not need to be specified.
           #. Within a 'results' section of a case (use the base case to get the same recordings for all cases).
              The results variables specification must be a list and must be explicit strings to conform to Json5.
           #. Usage of a normal variable specification as for 'set',
              but specifying the keyword 'result' or 'res' as value: 'keep the value but record the variable'.

        Args:
            key (str): the key of the spec item
            value (Any])=None: the values with respect to the item. For 'results' this is not used

        Returns
        -------
            updated self.act_*** actions through add_actions() of the SystemInterface***
        """
        if key in ("startTime", "stopTime", "stepSize"):
            assert self.special is not None
            self.special.update({key: value})  # just keep these as a dictionary so far
        else:  # expect a  variable-alias : value(s) specificator
            key, at_time_type, at_time_arg = self._disect_at_time_spec(key, value)
            if at_time_type in ("get", "step"):
                value = None
            key, cvar_info, rng = self.cases.disect_variable(key)
            key = key.strip()
            if value is not None:  # check also the number of supplied values
                if isinstance(value, str | float | int | bool):  # make sure that there are always lists
                    value = [value]
                # assert sum(1 for _ in rng) == Case._num_elements(value), f"Variable {key}: # values {value} != # vars {rng}",
                assert len(rng) == Case._num_elements(value), f"Variable {key}: # values {value} != # vars {rng}"
            varnames = tuple([cvar_info["names"][r] for r in rng])
            # print(f"CASE.read_spec, {key}@{at_time_arg}({at_time_type}):{value}[{rng}], alias={cvar_info}")  # noqa: ERA001
            if not self.cases.simulator.allowed_action(at_time_type, cvar_info["instances"][0], varnames, at_time_arg):
                raise AssertionError(self.cases.simulator.message) from None
            # action allowed. Ask simulator to add actions appropriately
            assert self.special is not None
            self.cases.simulator.add_actions(
                actions=self.act_get if at_time_type in ("get", "step") else self.act_set,
                act_type=at_time_type,
                cvar=key,
                cvar_info=cvar_info,
                values=value,
                at_time=at_time_arg if at_time_arg <= 0 else at_time_arg * self.cases.timefac,
                stoptime=self.special["stopTime"],
                rng=tuple(rng),
            )

    def list_cases(
        self,
        *,
        as_name: bool = True,
        flat: bool = False,
    ) -> list[str] | list[Case]:
        """List this case and all sub-cases recursively, as name or case objects."""
        lst: list[str] | list[Case]
        lst = [self.name] if as_name else [self]  # type: ignore[list-item]
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

        def get_from_config(element: str, default: float | None = None) -> float | None:
            info = from_xml(self.cases.simulator.structure_file, sub=None).findall(".//{*}" + element)
            if not len(info):
                return default
            txt = info[0].text
            if txt is None:
                return default
            try:
                return float(txt)
            except Exception:  # noqa: BLE001
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

    def run(self, dump: str | None = "") -> None:
        """Set up case and run it.

        All get action are recorded in results and get actions always concern whole case variables.
        It is difficult to report initial settings. Therefore all start values are collected,
        changed with initial settings (settings before the main simulation loop) and reported.

        Args:
            dump (str): Optionally save the results as json file.
                None: do not save, '': use default file name, str (with or without '.js5'): save with that file name
        """

        def do_actions(
            _t: float,
            actions: list[tuple[Any, ...]],
            _iter: Iterator[tuple[float, list[tuple[Any, ...]]]],
            time: int | float,
        ) -> tuple[float, list[tuple[Any, ...]]]:
            while time >= _t:  # issue the actions - actions
                if len(actions):
                    for _act in actions:
                        res = self.cases.simulator.do_action(
                            time=time,
                            act_info=_act,
                            typ=self.cases.variables[_act[0]]["type"],
                        )
                        if len(_act) == 3:  # get action. Report  # noqa: PLR2004
                            assert self.res is not None
                            self.res.add(
                                time=time / self.cases.timefac,
                                comp=_act[1],
                                cvar=_act[0],
                                values=res,
                            )
                    try:
                        _t, actions = next(_iter)
                    except StopIteration:
                        _t, actions = 10 * tstop, []
            return (_t, actions)

        _ = self.cases.simulator.init_simulator()
        # Note: final actions are included as _get at stopTime
        assert self.special is not None
        tstart: int = int(self.special["startTime"] * self.cases.timefac)
        time = tstart
        tstop: int = int(self.special["stopTime"] * self.cases.timefac)
        tstep: int = int(self.special["stepSize"] * self.cases.timefac)
        starts = self.cases.get_starts()  # start value of all case variables (where defined)

        set_iter = self.act_set.items().__iter__()  # iterator over set actions => time, action_list
        try:
            t_set, a_set = next(set_iter)
        except StopIteration:
            t_set, a_set = (float(np.inf), [])  # satisfy linter
        get_iter = self.act_get.items().__iter__()  # iterator over get actions => time, action_list
        act_step = []
        self.add_results_object(Results(self))

        while True:
            try:
                t_get, a_get = next(get_iter)
            except StopIteration:
                t_get, a_get = (tstop + 1, [])
            if t_get < 0:  # negative time indicates 'always'
                for a in a_get:
                    act_step.append((*a, self.cases.simulator.action_step(a, self.cases.variables[a[0]]["type"])))
            else:
                break

        for cvar, _comp, refs, values in a_set:  # since there is no hook to get initial values we keep track
            refs, values = self.cases.simulator.update_refs_values(
                self.cases.variables[cvar]["refs"], self.cases.variables[cvar]["refs"], starts[cvar], refs, values
            )
            starts[cvar] = values

        for v, s in starts.items():  # report the start values
            for c in self.cases.variables[cvar]["instances"]:
                self.res.add(tstart, c, v, s if len(s) > 1 else s[0])

        while True:  # main simulation loop
            t_set, a_set = do_actions(t_set, a_set, set_iter, time)

            time += tstep
            if time > tstop:
                break
            if not self.cases.simulator.run_until(time):
                break
            t_get, a_get = do_actions(t_get, a_get, get_iter, time)  # issue the current get actions

            if len(act_step):  # there are step-always actions
                for cvar, comp, _refs, a in act_step:
                    self.res.add(time / self.cases.timefac, comp, cvar, a())

        if dump is not None:
            self.res.save(dump)


class Cases:
    """Global book-keeping of all cases defined for a system model.

    * Ensure uniqueness of case names
    * Access to system model information: system model, component models and instantiated component models information
    * Definition of variable aliases (used throughout the cases)
    * Definition of cases and their relation (case hierarchy)

    Args:
        spec (Path): file name for cases specification
        simulator_type (SystemInterface)=SystemInterfaceOSP: Optional possibility to choose system simulator details
           Default is OSP (libcosimpy), but when only results are read the basic SystemInterface is sufficient.
    """

    __slots__ = (
        "assertion",
        "base",
        "file",
        "js",
        "results_print_type",
        "simulator",
        "spec",
        "timefac",
        "variables",
    )
    assertion_results: list[AssertionResult] = []

    def __init__(self, spec: str | Path):
        self.file = Path(spec)  # everything relative to the folder of this file!
        assert self.file.exists(), f"Cases spec file {spec} not found"
        self.js = Json5(spec)
        name = (self.js.jspath("$.header.name", str) or "",)
        description = (self.js.jspath("$.header.description", str) or "",)
        log_level = self.js.jspath("$.header.logLevel") or "fatal"
        modelfile = self.js.jspath("$.header.modelFile", str) or "OspSystemStructure.xml"
        simulator = self.js.jspath("$.header.simulator", str) or ""
        path = self.file.parent / modelfile
        assert path.exists(), f"System structure file {path} not found"
        if simulator == "":  # without ability to perform simulatiosn
            self.simulator = SystemInterface(path, name, description, log_level)  # type: ignore
        elif simulator == "OSP":
            self.simulator = SystemInterfaceOSP(path, name, description, log_level)  # type: ignore

        self.timefac = self._get_time_unit() * 1e9  # internally OSP uses pico-seconds as integer!
        # read the 'variables' section and generate dict { alias : { (instances), (variables)}}:
        self.variables = self.get_case_variables()
        self.assertion = Assertion()
        self.assertion.register_vars(self.variables)  # register variables as symbols
        self.read_cases()

    def get_case_variables(self) -> dict[str, dict]:
        """Read the 'variables' main key, which defines self.variables (case variables) as a dictionary.

        { c_var_name : {'model':model ID,
                        'instances': tuple of instance names,
                        'names': tuple of variable names,
                        'refs': tuple of ValueReferences
                        'type': python type,
                        'causality': causality (str),
                        'variability': variability (str),
                        'initial': initial (str)
                        'start': tuple of start values}.

        Optionally a description of the alias variable may be provided (and added to the dictionary).
        """
        variables = {}
        model_vars = {}  # cache of variables of models
        for k, v in self.js.jspath("$.header.variables", dict, True).items():
            if not isinstance(v, list):
                raise CaseInitError(f"List of 'component(s)' and 'variable(s)' expected. Found {v}") from None
            assert len(v) in (
                2,
                3,
            ), f"Variable spec should be: instance(s), variables[, description]. Found {v}."
            assert isinstance(v[0], (str | tuple)), f"First argument of variable spec: Component(s)! Found {v[0]}"
            assert isinstance(v[0], str), f"String expected as model name. Found {v[0]}"
            model, comp = self.simulator.match_components(v[0])
            assert len(comp) > 0, f"No component model instances '{v[0]}' found for alias variable '{k}'"
            assert isinstance(v[1], str), f"Second argument of variable sped: Variable name(s)! Found {v[1]}"
            _vars = self.simulator.match_variables(comp[0], v[1])  # tuple of matching variables (name,ref)
            _varnames = tuple([n for n, _ in _vars])
            _varrefs = tuple([r for _, r in _vars])
            if model not in model_vars:  # ensure that model is included in the cache
                model_vars.update({model: self.simulator.variables(comp[0])})
            prototype = model_vars[model][_varnames[0]]
            var: dict = {
                "model": model,
                "instances": comp,
                "names": _varnames,  # variable names from FMU
                "refs": _varrefs,
            }
            assert len(var["names"]), f"No matching variables found for alias {k}:{v}, component '{comp}'"
            if len(v) > 2:
                var.update({"description": v[2]})
            # We add also the more detailed variable info from the simulator (the FMU)
            # The type, causality and variability shall be equal for all variables.
            for n in _varnames:
                for test in ["type", "causality", "variability"]:
                    assert model_vars[model][n][test] == prototype[test], (
                        f"Model {model} variable {n} != {test} as {prototype}"
                    )
            starts = []
            for v, info in self.simulator.models[model]["variables"].items():
                if v in _varnames and "start" in info:
                    starts.append(info["type"](info["start"]))
            var.update(
                {
                    "type": prototype["type"],
                    "causality": prototype["causality"],
                    "variability": prototype["variability"],
                    "initial": prototype.get("initial", ""),
                    "start": tuple(starts),
                }
            )
            variables.update({k: var})
        return variables

    def case_variable(self, component: str, variables: str | tuple):
        """Identify the case variable (as defined in the spec) from the component instance and fmu variable names."""
        if isinstance(variables, (tuple, list)) and len(variables) == 1:
            variables = variables[0]
        for var, info in self.variables.items():
            if component in info["instances"]:
                rng = []
                for i, name in enumerate(info["names"]):
                    if name in variables:
                        rng.append(i)
                if len(rng) == len(variables):  # perfect match
                    return (var, ())
                if len(rng) > 0:
                    return (var, tuple(rng))
        raise KeyError(f"Undefined case variable with component {component}, variables {variables}") from None

    def _get_time_unit(self) -> float:
        """Find system time unit from the spec and return as seconds.
        If the entry is not found, 1 second is assumed.
        """
        # _unit =
        unit = self.js.jspath("$.header.timeUnit", str) or "second"
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
        'base' is defined firsts, since the others build on these
        Return the base case object.
        The others are linked as sub-cases in their parent cases.
        The 'header' is treated elsewhere.
        """
        if self.js.jspath("$.base", dict) is not None and self.js.jspath("$.base.spec", dict) is not None:
            # we need to peek into the base case where startTime and stopTime should be defined
            special: dict[str, float] = {
                "startTime": self.js.jspath("$.base.spec.startTime", float) or 0.0,
                "stopTime": self.js.jspath("$.base.spec.stopTime", float, True),
            }
            # all case definitions are top-level objects in self.spec. 'base' is mandatory
            self.base = Case(self, "base", spec=self.js.jspath("$.base", dict, True), special=special)
            for k in self.js.js_py:
                if k not in ("header", "base"):
                    _ = Case(self, k, spec=self.js.jspath(f"$.{k}", dict, True))
        else:
            raise CaseInitError(f"Main section 'base' is needed. Found {list(self.js.js_py.keys())}") from None

    def case_by_name(self, name: str) -> Case | None:
        """Find the case 'name' amoung all defined cases. Return None if not found.

        Args:
            name (str): the case name to find
        Returns:
            The case object or None
        """
        if name == "header":
            raise ValueError("The name 'header' is reserved and not allowed as case name") from None
        if name == "base":
            return self.base
        found = self.base.case_by_name(name)
        if found is not None:
            return found
        return None

    def disect_variable(self, key: str, err_level: int = 2) -> tuple[str, dict, Sequence]:
        """Extract the variable name, definition and explicit variable range, if relevant
        (multi-valued variables, where only some elements are addressed).
        ToDo: handle multi-dimensional arrays (tables, ...).

        Args:
            key (str): The key as provided in case spec(, with [range] if provided).

        Returns
        -------
            1. The variable name as defined in the 'variables' section of the spec
            2. The variable definition, which the name refers to
            3. An Sequence over indices of the variable, i.e. the range
        """

        def handle_error(msg: str, err: Exception | None, level: int):
            if level > 0:
                if level == 1:
                    print(msg)
                else:
                    raise AssertionError(msg) from err
            return ("", None, range(0))

        pre, _, r = key.partition("[")
        try:
            cvar_info = self.variables[pre]
        except KeyError as err:
            handle_error(
                f"Variable {pre} was not found in list of defined case variables",
                err,
                err_level,
            )

        cvar_len = len(cvar_info["names"])  # len of the tuple of refs
        if len(r):  # range among several variables
            r = r.rstrip("]").strip()  # string version of a non-trivial range
            parts_comma = r.split(",")
            rng: range | list[int] = []
            for i, p in enumerate(parts_comma):
                parts_ellipses = p.split("..")
                if len(parts_ellipses) == 1:  # no ellipses. Should be an index
                    try:
                        idx = int(p)
                    except ValueError as err:
                        return handle_error(
                            f"Unhandled index {p}[{i}] for variable {pre}",
                            err,
                            err_level,
                        )
                    if not 0 <= idx < cvar_len:
                        return handle_error(
                            f"Index {idx} of variable {pre} out of range",
                            None,
                            err_level,
                        )
                    if not isinstance(rng, list):
                        return handle_error(
                            f"A list was expected as range here. Found {rng}",
                            None,
                            err_level,
                        )
                    rng.append(idx)
                else:
                    assert len(parts_ellipses) == 2, f"RangeError: Exactly two indices expected in {p} of {pre}"
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
                        return handle_error(
                            "Unhandled ellipses '{parts_comma}' for variable {pre}",
                            err,
                            err_level,
                        )
                    rng = range(idx0, idx1)
        elif cvar_len == 1:  # scalar variable
            rng = [0]
        else:  # all elements
            rng = range(cvar_len)
        return (pre, cvar_info, rng)

    def get_starts(self):
        """Get a copy of the start values (as advised by FMU) as dict {case-var : (start-values), }."""
        starts: dict = {}
        for v, info in self.variables.items():
            if "start" in info and len(info["start"]):
                starts.update({v: list(info["start"])})
        return starts

    def info(self, case: Case | None = None, level: int = 0) -> str:
        """Show main information and the cases structure as string."""
        txt = ""
        if case is None:
            case = self.base
            txt += "Cases "
            txt += f"{self.js.jspath('$.header.name', str) or 'noName'}. "
            txt += f"{(self.js.jspath('$.header.description', str) or '')}\n"
            modelfile = self.js.jspath("$.header.modelFile", str)
            if modelfile is not None:
                txt += f"System spec '{modelfile}'.\n"
            assert isinstance(case, Case), "At this point a Case object is expected as variable 'case'"
            txt += self.info(case=case, level=level)
        elif isinstance(case, Case):
            txt += "  " * level + case.name + "\n"
            for c in case.subs:
                txt += self.info(case=c, level=level + 1)
        else:
            raise ValueError(f"The argument 'case' shall be a Case object or None. Type {type(case)} found.")
        return txt

    def run_case(self, name: str | Case, dump: str | None = "", run_subs: bool = False, run_assertions: bool = False):
        """Initiate case run. If done from here, the case name can be chosen.
        If run_subs = True, also the sub-cases are run.
        """
        if isinstance(name, str):
            c = self.case_by_name(name)
            assert isinstance(c, Case), f"Case {name} not found"
        elif isinstance(name, Case):
            c = name
        else:
            raise ValueError(f"Invalid argument name:{name}") from None

        c.run(dump)

        if run_assertions and c:
            # Run assertions on every case after running the case -> results will be saved in memory for now
            self.assertion.do_assert_case(c.res)

        if not run_subs:
            return

        for _c in c.subs:
            self.run_case(_c, dump, run_subs, run_assertions)


class Results:
    """Manage the results of a case.

    * Collect results when a case is run
    * Save case results as Json5 file
    * Read results from file and work with them

    Args:
        case (Case,str,Path)=None: The case object, the results relate to.
            When instantiating from Case (for collecting data) this shall be explicitly provided.
            When instantiating from stored results, this should refer to the cases definition,
            or the default file name <cases-name>.cases is expected.
        file (Path,str)=None: The file where results are saved (as Json5).
            When instantiating from stored results (for working with data) this shall be explicitly provided.
            When instantiating from Case, this file name will be used for storing results.
            If "" default file name is used, if None, results are not stored.
    """

    def __init__(
        self,
        case: Case | str | Path | None = None,
        file: str | Path | None = None,
    ) -> None:
        self.file: Path | None  # None denotes that results are not automatically saved
        self.case: Case | None = None
        self.res: Json5
        if (case is None or isinstance(case, (str, Path))) and file is not None:
            self._init_from_existing(file)  # instantiating from existing results file (work with data)
        elif isinstance(case, Case):  # instantiating from cases file (for data collection)
            self._init_new(case)
        else:
            raise ValueError(f"Inconsistent init arguments case:{case}, file:{file}")

    def _init_from_existing(self, file: str | Path) -> None:
        self.file = Path(file)
        assert self.file.exists(), f"File {file} is expected to exist."
        self.res = Json5(self.file)
        case = Path(self.file.parent / (self.res.jspath("$.header.cases", str, True) + ".cases"))
        try:
            cases = Cases(Path(case))
        except ValueError:
            raise CaseInitError(f"Cases {Path(case)} instantiation error") from ValueError
        self.case = cases.case_by_name(name=self.res.jspath(path="$.header.case", typ=str, errorMsg=True))
        assert isinstance(self.case, Case), f"Case {self.res.jspath('$.header.case', str, True)} not found"
        assert isinstance(self.case.cases, Cases), "Cases object not defined"
        self._header_transform(tostring=False)
        self.case.add_results_object(self)  # make Results object known to self.case

    def _init_new(
        self,
        case: Case,
        file: str | Path | None = "",
    ) -> None:
        assert isinstance(case, Case), f"Case object expected as 'case' in Results. Found {type(case)}"
        self.case = case
        if file is not None:  # use that for storing results data as Json5
            if file == "":  # use default file name (can be changed through self.save():
                self.file = self.case.cases.file.parent / (self.case.name + ".js5")
            else:
                self.file = Path(file)
        else:  # do not store data
            self.file = None
        self.res = Json5(str(self._header_make()))  # instantiate the results object
        self._header_transform(tostring=False)

    def _header_make(self) -> dict[str, dict[str, Any]]:
        """Make a standard header for the results of 'case' as dict.
        This function is used as starting point when a new results file is created.
        """
        assert self.case is not None, "Case object not defined"
        assert self.file is not None, "File name not defined"
        _ = self.case.cases.js.jspath("$.header.name", str, True)
        results: dict[str, dict[str, Any]] = {
            "header": {
                "case": self.case.name,
                "dateTime": datetime.today().isoformat(),
                "cases": self.case.cases.js.jspath("$.header.name", str, True),
                "file": relative_path(Path(self.case.cases.file), self.file),
                "casesDate": datetime.fromtimestamp(os.path.getmtime(self.case.cases.file)).isoformat(),
                "timeUnit": self.case.cases.js.jspath("$.header.timeUnit", str) or "sec",
                "timeFactor": self.case.cases.timefac,
            }
        }
        return results

    def _header_transform(self, tostring: bool = True):
        """Transform the header back- and forth between python types and string.
        tostring=True is used when saving to file and =False is used when reading from file.
        """
        assert isinstance(self.file, Path), f"Need a proper file at this point. Found {self.file}"
        res = self.res
        if tostring:
            res.update(
                "$.header.dateTime",
                res.jspath("$.header.dateTime", datetime, True).isoformat(),
            )
            res.update(
                "$.header.casesDate",
                res.jspath("$.header.casesDate", datetime, True).isoformat(),
            )
            res.update(
                "$.header.file",
                relative_path(res.jspath("$.header.file", Path, True), self.file),
            )
        else:
            res.update(
                "$.header.dateTime",
                datetime.fromisoformat(res.jspath("$.header.dateTime", str, True)),
            )
            res.update(
                "$.header.casesDate",
                datetime.fromisoformat(res.jspath("$.header.casesDate", str, True)),
            )
            res.update(
                "$.header.file",
                get_path(res.jspath("$.header.file", str, True), self.file.parent),
            )

    def add(
        self,
        time: float,
        comp: str,
        cvar: str,
        values: TValue | Sequence[TValue],
    ):
        """Add the results of a get action to the results dict for the case.

        Args:
            time (float): the time of the results
            comp (str): the component name
            cvar (str): the case variable name
            values (TValue, Sequence[TValue]): the value(s) to record
        """
        # print(f"Update ({time}): {comp}: {cvar} : {values}")
        _values = values[0] if isinstance(values, Sequence) and len(values) == 1 else values
        self.res.update("$[" + str(time) + "]" + comp, {cvar: _values})

    def save(self, jsfile: str | Path = ""):
        """Dump the results dict to a json5 file.

        Args:
            jsfile (str|Path): Optional possibility to change the default name (self.case.name.js5) to use for dump.
        """
        if self.file is None:
            return
        if jsfile == "":
            jsfile = self.file
        else:  # a new file name is provided
            if isinstance(jsfile, str):
                if not jsfile.endswith(".js5"):
                    jsfile += ".js5"
            jsfile = Path(self.case.cases.file.parent / jsfile)  # type: ignore [union-attr]
            self.file = jsfile  # remember the new file name
        self._header_transform(tostring=True)
        self.res.write(jsfile)

    def inspect(self, component: str | None = None, variable: str | None = None):
        """Inspect the results and return a dictionary on which data are found.

        Args:
            component (str): Possibility to inspect only data with respect to a given component
            variable (str): Possibility to inspect only data with respect to a given variable

        Returns
        -------
            A dictionary {<component.variable> : {'len':#data points, 'range':[tMin, tMax], 'info':info-dict}
            The info-dict is and element of Cases.variables. See Cases.get_case_variables() for definition.
        """
        cont: dict = {}
        assert isinstance(self.case, Case)
        assert isinstance(self.case.cases, Cases)
        for _time, components in self.res.js_py.items():
            if _time != "header":
                time = float(_time)
                for c, variables in components.items():
                    if component is None or c == component:
                        for v, _ in variables.items():
                            if variable is None or variable == v:
                                ident = c + "." + v
                                if ident in cont:  # already registered
                                    cont[ident]["range"][1] = time  # update upper bound
                                    cont[ident]["len"] += 1  # update length
                                else:  # new entry
                                    v_name, v_info, v_range = self.case.cases.disect_variable(v, err_level=0)
                                    assert len(v_name), f"Variable {v} not found in cases spec {self.case.cases.file}"
                                    cont.update(
                                        {
                                            ident: {
                                                "len": 1,
                                                "range": [time, time],
                                                "info": v_info,
                                            }
                                        }
                                    )
        return cont

    def retrieve(self, comp_var: Iterable) -> list:
        """Retrieve from results js5-dict the variables and return (times, values).

        Args:
            comp_var (Iterator): iterator over (<component-name>, <variable_name>[, element])
               Alternatively, the jspath syntax <component-name>.<variable_name>[[element]] can be used as comp_var.
               Time is not explicitly included in comp_var
               A record is only included if all variables are found for a given time
        Returns:
            Data table (list of lists): time and one column per variable
        """
        data = []
        _comp_var = []
        for _cv in comp_var:
            el = None
            if isinstance(_cv, str):  # expect <component-name>.<variable_name> syntax
                comp, var = _cv.split(".")
                if "[" in var and var[-1] == "]":  # explicit element
                    var, _el = var.split("[")
                    el = int(_el[:-1])
            else:  # expect (<component-name>, <variable_name>) syntax
                comp, var = _cv
            _comp_var.append((comp, var, el))

        for key, values in self.res.js_py.items():
            if key != "header":
                time = float(key)
                record = [time]
                is_complete = True
                for comp, var, el in _comp_var:
                    try:
                        _rec = values[comp][var]
                    except KeyError:
                        is_complete = False
                        break  # give up
                    else:
                        record.append(_rec if el is None else _rec[el])

                if is_complete:
                    data.append(record)
        return data

    def plot_time_series(self, comp_var: Sequence, title: str = ""):
        """Extract the provided alias variables and plot the data found in the same plot.

        Args:
            comp_var (Sequence): Sequence of (<component-instance>,<variable>) tuples (as used in retrieve)
               Alternatively, the jspath syntax <component>.<variable> is also accepted
            title (str): optional title of the plot
        """
        data = self.retrieve(comp_var)
        times = [rec[0] for rec in data]
        for i, var in enumerate(comp_var):
            if isinstance(var, str):
                label = var
            else:
                label = var[0] + "." + var[1]
                if len(var) > 2:
                    label += "[" + var[2] + "]"
            values = [rec[i + 1] for rec in data]
            plt.plot(times, values, label=var, linewidth=3)

        if len(title):
            plt.title(title)
        plt.xlabel("Time")
        # plt.ylabel('Values')
        plt.legend()
        plt.show()
