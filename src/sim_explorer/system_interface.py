from enum import Enum
from pathlib import Path
from typing import Any, TypeAlias

from sim_explorer.json5 import Json5
from sim_explorer.utils.misc import from_xml, match_with_wildcard
from sim_explorer.utils.osp import read_system_structure_xml

PyVal: TypeAlias = str | float | int | bool  # simple python types / Json5 atom


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
    """

    def __init__(
        self,
        structure_file: Path | str = "",
        name: str | None = None,
        description: str = "",
        log_level: str = "fatal",
    ):
        self.structure_file = Path(structure_file)
        self.name = name  # overwrite if the system includes that
        self.description = description  # overwrite if the system includes that
        self.system_structure = SystemInterface.read_system_structure(self.structure_file)
        self._models = self._get_models()
        # self.simulator=None # derived classes override this to instantiate the system simulator
        self.message = ""  # possibility to save additional message for (optional) retrieval by client
        self.full_simulator_available = False  # only system and components specification available. No simulation!

    @property
    def path(self):
        return self.structure_file.resolve().parent

    @staticmethod
    def read_system_structure(file: Path, fmus_exist: bool = True):
        """Read the systemStructure file and perform checks.

        Returns
        -------
            The system structure as (json) dict as if the structure was read through osp_system_structure_from_js5
        """
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

    @property
    def components(self):
        """Return an iterator over all components (instances).
        Each component is represented by a dict , together with the stem of their fmu files.

        Note: there can be several instances per model (FMU)
        """
        for k, v in self.system_structure["Simulators"].items():
            source = v["source"]
            yield (k, {"model": source.stem, "source": source})

    def _get_models(self) -> dict:
        """Get a dict of the models in the system:
        {<name> : {'source':<source>, 'components':[component-list], 'variables':{variables-dict}.
        """
        mods = {}
        for k, v in self.components:
            if v["model"] not in mods:
                mods.update(
                    {
                        v["model"]: {
                            "source": v["source"],
                            "components": [k],
                            "variables": self._get_variables(v["source"]),
                        }
                    }
                )
            else:
                mods[v["model"]]["components"].append(k)
        return mods

    @property
    def models(self) -> dict:
        return self._models

    def match_components(self, comps: str | tuple[str, ...]) -> tuple[str, tuple]:
        """Identify component (instances) based on 'comps' (component alias or tuple of aliases).
        comps can be a (tuple of) full component names or component names with wildcards.
        Returned components shall be based on the same model.
        """
        if isinstance(comps, str):
            comps = (comps,)
        collect = []
        model = None
        for c in comps:
            for k, v in self.components:
                if match_with_wildcard(c, k):
                    if model is None:
                        model = v["model"]
                    if v["model"] == model and k not in collect:
                        collect.append(k)
        assert model is not None and len(collect), f"No component match for {comps}"
        return (model, tuple(collect))

    def _get_variables(self, source: Path) -> dict[str, dict]:
        """Get the registered variables for a given model (added to _models dict).

        Returns
        -------
            A dictionary of variable {names:info, ...}, where info is a dictionary containing reference, type, causality and variability
        """
        assert source.exists() and source.suffix == ".fmu", f"FMU file {source} not found or wrong suffix"
        md = from_xml(source, sub="modelDescription.xml")
        variables = {}
        for sv in md.findall(".//ScalarVariable"):
            name = sv.attrib.pop("name")
            vr = int(sv.attrib.pop("valueReference"))
            var: dict[str, Any] = {k: v for k, v in sv.attrib.items()}
            var.update({"reference": vr})
            typ = sv[0]
            var.update({"type": SystemInterface.pytype(typ.tag)})
            var.update(typ.attrib)
            variables.update({name: var})
        return variables

    def variables(self, comp: str | int) -> dict:
        """Get the registered variables for a given component from the system.

        Args:
            comp (str, int): The component name or its index within the model

        Returns
        -------
            A dictionary of variable {names:info, ...}, where info is a dictionary containing reference, type, causality and variability
        """
        if isinstance(comp, str):
            for k, c in self.components:
                if k == comp:
                    return self.models[c["model"]]["variables"]
        elif isinstance(comp, int):
            for i, (_, c) in enumerate(self.components):
                if i == comp:
                    return self.models[c["model"]]["variables"]
        else:
            raise AssertionError(f"Unallowed argument {comp} in 'variables'")
        raise KeyError(f"Component {comp} not found. Avalable components: {list(self.components)}") from None

    def variable_iter(self, variables: dict, flt: int | str | tuple | list):
        """Get the variable dicts of the variables refered to by ids.

        Returns: Iterator over the dicts of the selected variables
        """
        if isinstance(flt, (int, str)):
            ids = [flt]
        elif isinstance(flt, (tuple, list)):
            ids = list(flt)
        else:
            raise ValueError(f"Unknown filter specification {flt} for variables") from None
        if isinstance(ids[0], str):  # by name
            for i in ids:
                if i in variables:
                    yield (i, variables[i])
        else:  # by reference
            for v, info in variables.items():
                if info["reference"] in ids:
                    yield (v, info)

    def match_variables(self, component: str, varname: str) -> tuple[int]:
        """Based on an example component (instance), identify unique variables starting with 'varname'.
        The returned information applies to all instances of the same model.
        The variables shall all be of the same type, causality and variability.

        Args:
            component: component instance varname.
            varname (str): the varname to search for. This can be the full varname or only the start of the varname
              If only the start of the varname is supplied, all matching variables are collected.

        Returns
        -------
            Tuple of value references
        """

        def accept_as_alias(org: str) -> bool:
            """Decide whether the alias can be accepted with respect to org (uniqueness)."""
            if not org.startswith(varname):  # necessary requirement
                return False
            rest = org[len(varname) :]
            if not len(rest) or any(rest.startswith(c) for c in ("[", ".")):
                return True
            return False

        var = []
        assert hasattr(self, "components"), "Need the dictionary of components before maching variables"

        accepted = None
        for k, v in self.variables(component).items():
            if accept_as_alias(k):
                if accepted is None:
                    accepted = v
                assert all(
                    v[e] == accepted[e] for e in ("type", "causality", "variability")
                ), f"Variable {k} matches {varname}, but properties do not match"
                var.append(v["reference"])
        return tuple(var)

    def variable_name_from_ref(self, comp: int | str, ref: int) -> str:
        """Get the variable name from its component instant (id or name) and its valueReference."""
        for name, info in self.variables(comp).items():
            if info["reference"] == ref:
                return name
        return ""

    def component_name_from_id(self, idx: int) -> str:
        """Retrieve the component name from the given index.
        Return an empty string if not found.
        """
        for i, (k, _) in enumerate(self.components):
            if i == idx:
                return k
        return ""

    def component_id_from_name(self, name: str) -> int:
        """Get the component id from the name. -1 if not found."""
        for i, (k, _) in enumerate(self.components):
            if k == name:
                return i
        return -1

    @staticmethod
    def pytype(fmu_type: str, val: PyVal | None = None):
        """Return the python type of the FMU type provided as string.
        If val is None, the python type object is returned. Else if boolean, true or false is returned.
        """
        typ = {
            "real": float,
            "integer": int,
            "boolean": bool,
            "string": str,
            "enumeration": Enum,
        }[fmu_type.lower()]

        if val is None:
            return typ
        elif typ is bool:
            if isinstance(val, str):
                return "true" in val.lower()  # should be fmi2True and fmi2False
            elif isinstance(val, int):
                return bool(val)
            else:
                raise KeyError(f"The value {val} could not be converted to boolean")
        else:
            return typ(val)

    @staticmethod
    def default_initial(causality: str, variability: str, only_default: bool = True) -> str | int | tuple:
        """Return default initial setting as str. See p.50 FMI2.
        With only_default, the single allowed value, or '' is returned.
        Otherwise a tuple of possible values is returned where the default value is always listed first.
        """
        col = {"parameter": 0, "calculated_parameter": 1, "input": 2, "output": 3, "local": 4, "independent": 5}[
            causality
        ]
        row = {"constant": 0, "fixed": 1, "tunable": 2, "discrete": 3, "continuous": 4}[variability]
        init = (
            (-1, -1, -1, 7, 10, -3),
            (1, 3, -4, -5, 11, -3),
            (2, 4, -4, -5, 12, -3),
            (-2, -2, 5, 8, 13, -3),
            (-2, -2, 6, 9, 14, 15),
        )[row][col]
        if init < 0:  # "Unallowed combination {variability}, {causality}. See '{chr(96-init)}' in FMI standard"
            return init if only_default else (init,)
        elif init in (1, 2, 7, 10):
            return "exact" if only_default else ("exact",)
        elif init in (3, 4, 11, 12):
            return "calculated" if only_default else ("calculated", "approx")
        elif init in (8, 9, 13, 14):
            return "calculated" if only_default else ("calculated", "exact", "approx")
        else:
            return init if only_default else (init,)

    def allowed_action(self, action: str, comp: int | str, var: int | str | tuple | list, time: float):
        """Check whether the action would be allowed according to FMI2 rules, see FMI2.01, p.49.

        * if a tuple of variables is provided, the variables shall have equal properties
          in addition to the normal allowed rules.

        Args:
            action (str): Action type, 'set', 'get', including init actions (set at time 0)
            comp (int,str): The instantiated component within the system (as index or name)
            var (int,str,tuple): The variable(s) (of component) as reference or name
            time (float): The time at which the action will be performed
        """

        def _description(name: str, info: dict, initial: int) -> str:
            descr = f"Variable {name}, causality {var_info['causality']}"
            descr += f", variability {var_info['variability']}"
            descr += f", initial {_initial}"
            return descr

        def _check(cond, msg):
            if not cond:
                self.message = msg
                return False
            return True

        _type, _causality, _variability = ("", "", "")  # unknown

        variables = self.variables(comp)
        for name, var_info in self.variable_iter(variables, var):
            # if not _check(name in variables, f"Variable {name} of component {comp} was not found"):
            #    print("VARIABLES", variables)
            #    return False
            # var_info = variables[name]
            if _type == "" or _causality == "" or _variability == "":  # define the properties and check whether allowed
                _type = var_info["type"]
                _causality = var_info["causality"]
                _variability = var_info["variability"]
                _initial = var_info.get("initial", SystemInterface.default_initial(_causality, _variability))

                if action == "get":  # no restrictions on get
                    pass
                elif action == "set":
                    if (
                        time < 0  # before EnterInitializationMode
                        and not _check(
                            (_variability != "constant" and _initial in ("exact", "approx")),
                            f"Change of {name} before EnterInitialization",
                        )
                    ):
                        return False

                    elif (
                        time == 0  # before ExitInitializationMode
                        and not _check(
                            (_variability != "constant" and (_initial == "exact" or _causality == "input")),
                            f"Change of {name} during Initialization",
                        )
                    ):
                        return False
                    elif (
                        time > 0  # at communication points
                        and not _check(
                            (_causality == "parameter" and _variability == "tunable") or _causality == "input",
                            f"Change of {name} at communication point",
                        )
                    ):
                        return False
                    # additional rule for ModelExchange, not listed here
            else:  # check whether the properties are equal
                if not _check(_type == var_info["type"], _description(name, var_info, _initial) + f" != type {_type}"):
                    return False
                if not _check(
                    _causality == var_info["causality"],
                    _description(name, var_info, _initial) + f" != causality { _causality}",
                ):
                    return False
                if not _check(
                    _variability == var_info["variability"],
                    _description(name, var_info, _initial) + f" != variability {_variability}",
                ):
                    return False
        return True

    def set_variable_value(self, instance: int, typ: type, var_refs: tuple[int, ...], var_vals: tuple) -> bool:
        """Provide a manipulator function which sets the 'variable' (of the given 'instance' model) to 'value'.

        Args:
            instance (int): identifier of the instance model for which the variable is to be set
            var_refs (tuple): Tuple of variable references for which the values shall be set
            var_vals (tuple): Tuple of values (of the correct type), used to set model variables
        """
        raise NotImplementedError("The method 'set_variable_value()' cannot be used in SystemInterface") from None

    def get_variable_value(self, instance: int, typ: type, var_refs: tuple[int, ...]):
        """Provide an observer function which gets the 'variable' value (of the given 'instance' model) at the time when called.

        Args:
            instance (int): identifier of the instance model for which the variable is to be set
            var_refs (tuple): Tuple of variable references for which the values shall be retrieved
        """
        raise NotImplementedError("The method 'get_variable_value()' cannot be used in SystemInterface") from None
