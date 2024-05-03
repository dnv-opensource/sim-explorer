# pyright: reportMissingImports=false, reportGeneralTypeIssues=false
import os
import time
from pathlib import Path
from typing import TypeAlias

from .case import Case
from .json5 import Json5Reader
from .simulator_interface import SimulatorInterface

# type definitions
PyVal: TypeAlias = str | float | int | bool  # simple python types / Json5 atom
Json5: TypeAlias = dict[str, PyVal | "Json5" | "Json5List"]  # Json5 object
Json5List: TypeAlias = list[Json5 | PyVal]  # Json5 list


"""
case_study module for definition and execution of simulation experiments
* read and compile the case definitions from configuration file
  Note that Json5 is here restriced to 'ordered keys' and 'unique keys within an object'
* set the start variables for a given case
* manipulate variables according to conditions during the simulation run
* save requested variables at given communication points during a simulation run
* check the validity of results when saving variables

With respect to MVx in general, this module serves the preparation of start conditions for smart testing.
"""


class CaseInitError(Exception):
    """Special error indicating that something is wrong during initialization of cases."""

    pass


class CaseUseError(Exception):
    """Special error indicating that something is wrong during usage of cases."""

    pass


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
                parent, case = self.read_case(k, v)
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
        assert "spec" in spec and isinstance(spec["spec"], dict), f"Case spec expected. Found {spec.get('spec')}"
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
                if None in actions_get:
                    actions_get.update({None: alist})
                else:
                    actions_get[None].extend(alist)
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
                    #                    print("GET args", a.args)
                    results_add(time, a.args[0], a.args[3], a.args[4], a())
                t_get, a_get = next(next_get)
            if None in settings["actions_get"]:  # there are step-always actions
                for a in settings["actions_get"][None]:  # observed at every step
                    #                print("STEP args", a.args)
                    results_add(time, a.args[0], a.args[3], a.args[4], a())

            time += tstep
        #            print("TIME ", time)

        if dump:
            case.save_results(results, dump)
        case.results = results
        return results
