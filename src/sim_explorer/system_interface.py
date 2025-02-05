"""Python module providing the interface to the simulator.
Currently only Open Simulation Platform (OSP) is supported.
"""

# pyright: reportUnnecessaryTypeIgnoreComment=false

from collections.abc import Callable, Generator, Sequence
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np

from sim_explorer.json5 import Json5
from sim_explorer.utils.misc import from_xml, match_with_wildcard
from sim_explorer.utils.osp import read_system_structure_xml
from sim_explorer.utils.types import TActionArgs, TGetActionArgs, TSetActionArgs, TValue

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element


class SystemInterface:
    """Class providing the interface to the system itself, i.e. system information, component interface information
    and the system co-simulation orchestrator (if simulations shall be run).

    This model provides the base class and is able to read system and component information.
    To run simulations it must be overridden by a super class, e.g. SystemInterfaceOSP

    Provides the following functions:

    * set_variable_value: Set variable values initially or at communication points
    * get_variable_value: Get variable values at communication points
    * match_components: Identify component instances based on (tuple of) (short) names
    * match_variables: Identify component variables of component (instance) matching a (short) name


    A system model might be defined through an instantiated simulator or explicitly through the .fmu files.
    Unfortunately, an instantiated simulator does not seem to have functions to access the FMU,
    therefore only the (reduced) info from the simulator is used here (FMUs not used directly).

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
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        self.structure_file = Path(structure_file)
        self.name = name  # overwrite if the system includes that
        self.description = description  # overwrite if the system includes that
        self.system_structure = SystemInterface.read_system_structure(self.structure_file)
        self._models, self.components = self._get_models_components()
        # self.simulator=None # derived classes override this to instantiate the system simulator  # noqa: ERA001
        self.message = ""  # possibility to save additional message for (optional) retrieval by client
        self.log_level = log_level
        self.full_simulator_available = kwargs.get("full_simulator_available", False)
        if not self.full_simulator_available:  # we need a minimal version of variable info (no full ModelDescription)
            for m, info in self._models.items():
                self._models[m].update({"variables": self._get_variables(info["source"])})

    @property
    def path(self) -> Path:
        return self.structure_file.resolve().parent

    @staticmethod
    def read_system_structure(
        file: Path,
        *,
        fmus_exist: bool = True,
    ) -> dict[str, Any]:
        """Read the systemStructure file and perform checks.

        Returns
        -------
            The system structure as (json) dict as if the structure was read through osp_system_structure_from_js5
        """
        system_structure: dict[str, Any] | Json5
        assert file.exists(), f"System structure {file} not found"
        if file.suffix == ".xml":  # assume the standard OspSystemStructure.xml file
            system_structure = read_system_structure_xml(file)
        elif file.suffix in (".js5", ".json"):  # assume the js5 variant of the OspSystemStructure
            system_structure = Json5(file).js_py
        elif file.suffix == ".ssp":
            # see https://ssp-standard.org/publications/SSP10/SystemStructureAndParameterization10.pdf
            raise NotImplementedError("The SSP file variant is not yet implemented") from None
        else:
            raise KeyError(f"Unknown file type {file.suffix} for System Structure file") from None
        for comp in system_structure["Simulators"].values():
            comp["source"] = (file.parent / comp["source"]).resolve()
            assert not fmus_exist or comp["source"].exists(), f"FMU {comp['source']} not found"
        return system_structure

    def _get_models_components(self) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        """Get a dict of the models and a dict of components in the system:
        {model-name : {'source':<source>, 'components':[component-list], 'variables':{variables-dict}}
        {component-name : model-name}.
        """
        mods: dict[str, dict[str, Any]] = {}
        components: dict[str, str] = {}
        for k, v in self.system_structure["Simulators"].items():
            source = Path(v["source"])
            model: str = source.stem
            if model not in mods:
                mods[model] = {
                    "source": source,
                    "components": [k],
                }
            else:
                mods[model]["components"].append(k)
            assert k not in components, f"Duplicate component name {k} related to model {model} encountered"
            components[k] = model
        return (mods, components)

    @property
    def models(self) -> dict[str, dict[str, Any]]:
        return self._models

    def match_components(self, comps: str | tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
        """Identify component (instances) based on 'comps' (component alias or tuple of aliases).
        comps can be a (tuple of) full component names or component names with wildcards.
        Returned components shall be based on the same model.
        """
        if isinstance(comps, str):
            comps = (comps,)
        collect: list[str] = []
        model: str | None = None
        for c in comps:
            for k, m in self.components.items():
                if match_with_wildcard(findtxt=c, matchtxt=k):
                    if model is None:
                        model = m
                    if m == model and k not in collect:
                        collect.append(k)
        assert model is not None, f"No model match for {comps}"
        assert len(collect), f"No component match for {comps}"
        return (model, tuple(collect))

    def _get_variables(self, source: Path) -> dict[str, dict[int | str, Any]]:
        """Get the registered variables for a given model (added to _models dict).

        Returns
        -------
            A dictionary of variable {names:info, ...},
            where info is a dictionary containing reference, type, causality, variability and initial
        """
        assert source.exists(), f"FMU file {source} not found"
        assert source.suffix == ".fmu", f"FMU file {source} not found or wrong suffix"
        md: Element = from_xml(source, sub="modelDescription.xml")
        variables: dict[str, dict[int | str, Any]] = {}
        var: dict[int | str, Any]
        typ: Element
        for sv in md.findall(".//ScalarVariable"):
            name = sv.attrib.pop("name")
            vr = int(sv.attrib.pop("valueReference"))
            var = dict(sv.attrib.items())
            var["reference"] = vr
            typ = sv[0]
            var["type"] = SystemInterface.pytype(typ.tag)
            var |= typ.attrib  # type: ignore[arg-type]
            variables[name] = var
        return variables

    def model_from_component(self, comp: str | int) -> str:
        """Find the model name from the component name or index."""
        if isinstance(comp, str):
            return self.components[comp]
        # int
        return next(
            (mod for i, mod in enumerate(self.components.values()) if i == comp),
            "",
        )

    def variables(self, comp: str | int) -> dict[str, dict[str, Any]]:
        """Get the registered variables for a given component from the system.
        This is the default version which works without the full modelDescription inside self._models.
        Can be overridden by super-classes which have the modelDescription available.

        Args:
            comp (str, int): The component name or its index within the model

        Returns
        -------
            A dictionary of variable {names:info, ...}, where info is a dictionary containing reference, type, causality and variability
        """
        try:
            mod = self.model_from_component(comp)
        except KeyError as e:
            raise KeyError(f"Component {comp} not found: {e}") from e
        try:
            return self.models[mod]["variables"]
        except Exception as e:
            raise KeyError(f"Variables for {comp} not found. Components: {list(self.components.keys())}") from e

    def variable_iter(
        self,
        variables: dict[str, dict[str, Any]],
        flt: int | str | Sequence[int] | Sequence[str],
    ) -> Generator[tuple[str, dict[str, Any]], None, None]:
        """Get the variable dicts of the variables refered to by ids.

        Returns: Iterator over the dicts of the selected variables
        """
        ids: list[int] | list[str]
        if isinstance(flt, int | str):
            ids = [flt]  # type: ignore[assignment]
        elif isinstance(flt, tuple | list):
            if len(flt) > 1:
                assert all(type(f) is type(flt[0]) for f in flt), "All elements in filter must be of the same type"
            ids = list(flt)  # pyright: ignore[reportAssignmentType]
        else:
            raise TypeError(f"Unknown filter specification {flt} for variables")
        if isinstance(ids[0], str):  # by name
            for i in ids:
                if i in variables:
                    assert isinstance(i, str)
                    yield (i, variables[i])
        else:  # by reference
            for v, info in variables.items():
                if info["reference"] in ids:
                    yield (v, info)

    def match_variables(
        self,
        component: str,
        varname: str,
    ) -> tuple[tuple[str, Any], ...]:
        """Based on an example component (instance), identify unique variables starting with 'varname'.
        The returned information applies to all instances of the same model.
        The variables shall all be of the same type, causality and variability.

        Args:
            component: component instance varname.
            varname (str): the varname to search for. This can be the full varname or only the start of the varname
              If only the start of the varname is supplied, all matching variables are collected.

        Returns
        -------
            Tuple of tuples (name,value reference)
        """

        def accept_as_alias(org: str) -> bool:
            """Decide whether the alias can be accepted with respect to org (uniqueness)."""
            if not org.startswith(varname):  # necessary requirement
                return False
            rest = org[len(varname) :]
            return not len(rest) or any(rest.startswith(c) for c in ("[", "."))

        var: list[tuple[str, Any]] = []
        assert hasattr(self, "components"), "Need the dictionary of components before maching variables"

        accepted = None
        for k, v in self.variables(component).items():
            if accept_as_alias(k):
                if accepted is None:
                    accepted = v
                assert all(
                    v[e] == accepted[e] for e in ("type", "causality", "variability")
                ), f"Variable {k} matches {varname}, but properties do not match"
                var.append((k, v["reference"]))
        return tuple(var)

    def variable_name_from_ref(self, comp: int | str, ref: int) -> str:
        """Get the variable name from its component instant (id or name) and its valueReference."""
        return next(
            (str(name) for name, info in self.variables(comp).items() if info["reference"] == ref),
            "",
        )

    def component_name_from_id(self, idx: int) -> str:
        """Retrieve the component name from the given index.
        Return an empty string if not found.
        """
        return next((k for i, k in enumerate(self.components.keys()) if i == idx), "")

    def component_id_from_name(self, name: str) -> int:
        """Get the component id from the name. -1 if not found."""
        return next((i for i, k in enumerate(self.components.keys()) if k == name), -1)

    @staticmethod
    def pytype(fmu_type: str, val: TValue | None = None) -> type | bool:
        """Return the python type of the FMU type provided as string.
        If val is None, the python type object is returned. Else if boolean, true or false is returned.
        """
        typ: type = {
            "real": float,
            "integer": int,
            "boolean": bool,
            "string": str,
            "enumeration": Enum,
        }[fmu_type.lower()]

        if val is None:
            return typ
        if typ is bool:
            if isinstance(val, str):
                return "true" in val.lower()  # should be fmi2True and fmi2False
            if isinstance(val, int):
                return bool(val)
            raise KeyError(f"The value {val} could not be converted to boolean")
        return typ(val)

    @staticmethod
    def default_initial(
        causality: str,
        variability: str,
        *,
        only_default: bool = True,
    ) -> str | int | tuple[int] | tuple[str, ...]:
        """Return default initial setting as str. See p.50 FMI2.
        With only_default, the single allowed value, or '' is returned.
        Otherwise a tuple of possible values is returned where the default value is always listed first.
        """
        col: int = {
            "parameter": 0,
            "calculated_parameter": 1,
            "input": 2,
            "output": 3,
            "local": 4,
            "independent": 5,
        }[causality]

        row: int = {
            "constant": 0,
            "fixed": 1,
            "tunable": 2,
            "discrete": 3,
            "continuous": 4,
        }[variability]

        init: int = (
            (-1, -1, -1, 7, 10, -3),
            (1, 3, -4, -5, 11, -3),
            (2, 4, -4, -5, 12, -3),
            (-2, -2, 5, 8, 13, -3),
            (-2, -2, 6, 9, 14, 15),
        )[row][col]

        if init < 0:  # "Unallowed combination {variability}, {causality}. See '{chr(96-init)}' in FMI standard"
            return init if only_default else (init,)
        if init in {1, 2, 7, 10}:
            return "exact" if only_default else ("exact",)
        if init in {3, 4, 11, 12}:
            return "calculated" if only_default else ("calculated", "approx")
        if init in {8, 9, 13, 14}:
            return "calculated" if only_default else ("calculated", "exact", "approx")
        return init if only_default else (init,)

    def allowed_action(  # noqa: C901
        self,
        action: str,
        comp: int | str,
        var: int | str | Sequence[int] | Sequence[str],
        time: float,
    ) -> bool:
        """Check whether the action would be allowed according to FMI2 rules, see FMI2.01, p.49.

        * if a tuple of variables is provided, the variables shall have equal properties
          in addition to the normal allowed rules.

        Args:
            action (str): Action type, 'set', 'get', including init actions (set at time 0)
            comp (int,str): The instantiated component within the system (as index or name)
            var (int,str,tuple): The variable(s) (of component) as reference or name
            time (float): The time at which the action will be performed
        """

        def _description(
            name: str,
            info: dict[str, Any],  # noqa: ARG001
            initial: str | int | tuple[int] | tuple[str, ...],  # noqa: ARG001
        ) -> str:
            descr = f"Variable {name}, causality {var_info['causality']}"
            descr += f", variability {var_info['variability']}"
            descr += f", initial {_initial}"
            return descr

        def _check(*, cond: bool, msg: str) -> bool:
            if not cond:
                self.message = msg
                return False
            return True

        _type, _causality, _variability = ("", "", "")  # unknown

        variables = self.variables(comp)
        for name, var_info in self.variable_iter(variables=variables, flt=var):
            if _type == "" or _causality == "" or _variability == "":  # define the properties and check whether allowed
                _type = var_info["type"]
                _causality = var_info["causality"]
                _variability = var_info["variability"]
                _initial = var_info.get("initial", SystemInterface.default_initial(_causality, _variability))
                if action in {"get", "step"}:  # no restrictions on get
                    pass
                elif action == "set" and (
                    (
                        time < 0  # before EnterInitializationMode
                        and not _check(
                            cond=(_variability != "constant" and _initial in ("exact", "approx")),
                            msg=f"Change of {name} before EnterInitialization",
                        )
                    )
                    or (
                        time == 0  # before ExitInitializationMode
                        and not _check(
                            cond=(_variability != "constant" and (_initial == "exact" or _causality == "input")),
                            msg=f"Change of {name} during Initialization",
                        )
                    )
                    or (
                        time > 0  # at communication points
                        and not _check(
                            cond=(_causality == "parameter" and _variability == "tunable") or _causality == "input",
                            msg=f"Change of {name} at communication point",
                        )
                    )
                ):
                    return False
                    # additional rule for ModelExchange, not listed here
            else:  # check whether the properties are equal
                _initial = var_info.get("initial", SystemInterface.default_initial(_causality, _variability))
                if not _check(
                    cond=_type == var_info["type"],
                    msg=f"{_description(name=name, info=var_info, initial=_initial)} != type {_type}",
                ):
                    return False
                if not _check(
                    cond=_causality == var_info["causality"],
                    msg=f"{_description(name=name, info=var_info, initial=_initial)} != causality {_causality}",
                ):
                    return False
                if not _check(
                    cond=_variability == var_info["variability"],
                    msg=f"{_description(name=name, info=var_info, initial=_initial)} != variability {_variability}",
                ):
                    return False
        return True

    @classmethod
    def update_refs_values(
        cls,
        allrefs: Sequence[int],
        baserefs: Sequence[int],
        basevals: Sequence[TValue],
        refs: Sequence[int],
        values: Sequence[TValue],
    ) -> tuple[tuple[int, ...], tuple[TValue, ...]]:
        """Update baserefs and basevals with refs and values according to all possible refs."""
        allvals: list[TValue | None] = [None] * len(allrefs)
        for i, r in enumerate(baserefs):
            allvals[allrefs.index(r)] = basevals[i]
        for i, r in enumerate(refs):
            allvals[allrefs.index(r)] = values[i]
        _refs: list[int] = []
        _vals: list[TValue] = []
        for i, v in enumerate(allvals):
            if v is not None:
                _refs.append(allrefs[i])
                _vals.append(v)
        return (tuple(_refs), tuple(_vals))

    def comp_model_var(
        self,
        cref: int,
        vref: int | tuple[int],
    ) -> tuple[str, str, list[str]]:
        """Find the component name and the variable names from the provided reference(s)."""
        comp: str | None = None
        model: str | None = None
        for i, (_comp, m) in enumerate(self.components.items()):
            if i == cref:
                model = m
                comp = _comp
                break
        assert model is not None, f"Model for component id {cref} not found"
        assert comp is not None, f"Component id {cref} not found"
        refs = (vref,) if isinstance(vref, int) else vref
        var_names: list[str] = []
        for vr in refs:
            var = next(
                (v for v, info in self.models[model]["variables"].items() if info["reference"] == vr),
                None,
            )
            assert var is not None, f"Reference {vr} not found in model {model}"
            var_names.append(var)
        return (comp, model, var_names)

    def _add_set(
        self,
        actions: dict[float, list[TSetActionArgs]],
        time: float,
        cvar: str,
        comp: str,
        cvar_info: dict[str, Any],
        values: tuple[TValue, ...],
        rng: tuple[int, ...] | None = None,
    ) -> None:
        """Perform final processing and add the set action to the list (if appropriate).

        Properties of set actions:

        * both full case variable settings and partial settings are allowed and must be considered
        * actions are recorded as tuples of (case-variable, component-name, value-references, values)

        Args:
            actions (dict): dict of get actions. The time slot is beforehand ensured.
            time (float): the time at which the action is issued
            cvar (str): the case variable name for which the action is performed
            comp (str): the component name
            cvar_info (dict): info about the case variable
            values (tuple): tuple of values (correct type made sure)
            rng (tuple)=None: Optional sub-range among the variables of cvar. None: whole variable
        """
        refs = cvar_info["refs"] if rng is None else tuple(cvar_info["refs"][i] for i in rng)
        assert len(refs) == len(values), f"Number of variable refs {refs} != values {values} in {cvar}, {comp}"
        for i, (_cvar, _comp, _refs, _values) in enumerate(actions[time]):  # go through existing actions for time
            if cvar == _cvar and comp == _comp:  # the case variable and the component name match
                refs, values = self.update_refs_values(
                    allrefs=cvar_info["refs"],
                    baserefs=_refs,
                    basevals=_values,
                    refs=refs,
                    values=values,
                )
                actions[time][i] = (cvar, comp, refs, values)  # replace action
                return
        # new set action
        actions[time].append((cvar, comp, refs, values))

    def _add_get(
        self,
        actions: dict[float, list[TGetActionArgs]],
        time: float,
        cvar: str,
        comp: str,
        cvar_info: dict[str, Any],
    ) -> None:
        """Perform final processing and add the get action to the list (if appropriate).

        Properties of get actions:

        * concern always the whole case-variable (all elements. rng not used)
        * are tuples of (case-variable, component-name, variable-references)
        * are never overridden for same time (no duplicate get actions for same component and cvar)

        Args:
            actions (dict): dict of get actions. The time slot is beforehand ensured.
            time (float): the time at which the action is issued
            cvar (str): the case variable name for which the action is performed
            component (str): the component name for which the action is performed
            cvar_info (dict): info about the case variable
        """
        for _cvar, _comp, _vars in actions[time]:  # go through existing actions for same time
            if cvar == _cvar and comp == _comp:  # match on case variable and component
                return  # the get action is already registered
        actions[time].append((cvar, comp, cvar_info["refs"]))

    def add_actions(  # noqa: PLR0913
        self,
        actions: dict[float, list[TGetActionArgs]] | dict[float, list[TSetActionArgs]],
        act_type: str,
        cvar: str,
        cvar_info: dict[str, Any],
        values: tuple[TValue, ...] | None,
        at_time: float,
        stoptime: float,
        rng: tuple[int, ...] | None = None,
    ) -> None:
        """Add specified actions to the provided action dict.
        The action list is simulator-agnostic and need 'compilation' before they are used in a simulation.

        Args:
            actions (dict): actions ('get' or 'set') registered so far
            act_type (str): action type 'get', 'step' or 'set'
            cvar (str): name of the case variable
            cvar_info (dict): dict of variable info: {model, instances, names, refs, type, causality, variability}
                see Cases.get_case_variables() for details.
            values (TValue) = None: Optional values (mandatory for 'set' actions)
            at_time (float): time at which actions shall be triggered (may be scaled)
            stoptime (float): simulation stop time (needed to handle 'step' actions)
            rng (Iterable)=None: Optional range specification for compound variables (indices to address)

        Returns
        -------
            Updated actions dict, where the whole dict is specific for get/set and new actions are added as
            {at_time : [ (cvar, component-name, (variable-name-list)[, value-list, rng])},
            where value-list and rng are only present for set actions
            at-time=-1 for get actions denote step actions
        """
        assert isinstance(at_time, float | int), f"Actions require a defined time as float. Found {at_time}"
        if at_time not in actions:
            actions[at_time] = []  # make sure that there is a suitable slot
        for comp in cvar_info["instances"]:
            if act_type == "get" or (act_type == "step" and at_time == -1):  # normal get or step without time spec
                assert all(len(args) == 3 for t in actions for args in actions[t]), (  # noqa: PLR2004
                    "Get actions must be tuples of (cvar, comp, refs)"
                )
                self._add_get(
                    actions=cast(dict[float, list[TGetActionArgs]], actions),
                    time=at_time,
                    cvar=cvar,
                    comp=comp,
                    cvar_info=cvar_info,
                )
            elif act_type == "step" and at_time >= 0:  # step actions with specified interval
                assert isinstance(actions, dict)
                assert all(len(args) == 3 for t in actions for args in actions[t]), (  # noqa: PLR2004
                    "Get actions must be tuples of (cvar, comp, refs)"
                )
                for time in np.arange(start=at_time, stop=stoptime, step=at_time):
                    self._add_get(
                        actions=cast(dict[float, list[TGetActionArgs]], actions),
                        time=time,
                        cvar=cvar,
                        comp=comp,
                        cvar_info=cvar_info,
                    )

            elif act_type == "set":
                assert values is not None, f"Variable {cvar}: Value needed for 'set' actions."
                assert isinstance(actions, dict)
                assert all(len(args) == 4 for t in actions for args in actions[t]), (  # noqa: PLR2004
                    "Get actions must be tuples of (cvar, comp, refs, values)"
                )
                self._add_set(
                    actions=cast(dict[float, list[TSetActionArgs]], actions),
                    time=at_time,
                    cvar=cvar,
                    comp=comp,
                    cvar_info=cvar_info,
                    values=tuple(cvar_info["type"](x) for x in values),
                    rng=rng,
                )
            else:
                raise KeyError(f"Unknown action type {act_type} at time {at_time}")

    def do_action(self, time: int | float, act_info: TActionArgs, typ: type) -> bool:
        """Do the action described by the tuple using OSP functions."""
        raise NotImplementedError("The method 'do_action()' cannot be used in SystemInterface") from None

    def action_step(self, act_info: TActionArgs, typ: type) -> Callable[..., Any]:
        """Pre-compile the step action and return the partial function
        so that it can be called at communication points.
        """
        raise NotImplementedError("The method 'action_step()' cannot be used in SystemInterface") from None

    def init_simulator(self) -> bool:
        """Instantiate and initialize the simulator, so that simulations can be run.
        Perforemd separately from __init__ so that it can be repeated before simulation runs.
        """
        raise NotImplementedError("The method 'init_simulator()' cannot be used in SystemInterface") from None

    def run_until(self, time: int | float) -> bool:
        """Instruct the simulator to simulate until the given time."""
        raise NotImplementedError("The method 'run_until()' cannot be used in SystemInterface") from None
