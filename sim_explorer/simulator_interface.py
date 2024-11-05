# pyright: reportMissingImports=false, reportGeneralTypeIssues=false
import re
import xml.etree.ElementTree as ET  # noqa: N817
from enum import Enum
from pathlib import Path
from typing import TypeAlias
from zipfile import BadZipFile, ZipFile, is_zipfile

from libcosimpy.CosimEnums import CosimVariableCausality, CosimVariableType, CosimVariableVariability  # type: ignore
from libcosimpy.CosimExecution import CosimExecution  # type: ignore
from libcosimpy.CosimManipulator import CosimManipulator  # type: ignore
from libcosimpy.CosimObserver import CosimObserver  # type: ignore

# type definitions
PyVal: TypeAlias = str | float | int | bool  # simple python types / Json5 atom
Json5: TypeAlias = dict[str, "Json5Val"]  # Json5 object
Json5List: TypeAlias = list["Json5Val"]  # Json5 list
Json5Val: TypeAlias = PyVal | Json5 | Json5List  # Json5 values


"""
sim_explorer module for definition and execution of simulation experiments
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


class SimulatorInterface:
    """Class providing the interface to the simulator itself.
    This is designed for OSP and needs to be overridden for other types of simulator.

    Provides the following functions:

    * set_variable_value: Set variable values initially or at communication points
    * get_variable_value: Get variable values at communication points
    * match_components: Identify component instances based on (tuple of) (short) names
    * match_variables: Identify component variables of component (instance) matching a (short) name


    A system model might be defined through an instantiated simulator or explicitly through the .fmu files.
    Unfortunately, an instantiated simulator does not seem to have functions to access the FMU,
    therefore only the (reduced) info from the simulator is used here (FMUs not used directly).

    Args:
        system (Path): Path to system model definition file
        name (str)="System": Possibility to provide an explicit system name (if not provided by system file)
        description (str)="": Optional possibility to provide a system description
        simulator (CosimExecution)=None: Optional possibility to insert an existing simulator object.
           Otherwise this is generated through CosimExecution.from_osp_config_file().
    """

    simulator: CosimExecution

    def __init__(
        self,
        system: Path | str = "",
        name: str | None = None,
        description: str = "",
        simulator: CosimExecution | None = None,
    ):
        self.name = name  # overwrite if the system includes that
        self.description = description  # overwrite if the system includes that
        self.sysconfig: Path | None = None
        if simulator is None:  # instantiate the simulator through the system config file
            self.sysconfig = Path(system)
            assert self.sysconfig.exists(), f"File {self.sysconfig.name} not found"
            ck, msg = self._check_system_structure(self.sysconfig)
            assert ck, msg
            self.simulator = self._simulator_from_config(self.sysconfig)
        else:
            self.simulator = simulator
        self.components = self.get_components()  # dict of {component name : modelId}
        # Instantiate a suitable manipulator for changing variables.
        self.manipulator = CosimManipulator.create_override()
        assert self.simulator.add_manipulator(manipulator=self.manipulator), "Could not add manipulator object"

        # Instantiate a suitable observer for collecting results.
        self.observer = CosimObserver.create_last_value()
        assert self.simulator.add_observer(observer=self.observer), "Could not add observer object"
        self.message = ""  # possibility to save additional message for (optional) retrieval by client

    @property
    def path(self):
        return self.sysconfig.resolve().parent if self.sysconfig is not None else None

    def _check_system_structure(self, file: Path):
        """Check the OspSystemStructure file. Used in cases where the simulatorInterface is instantiated from Cases."""
        el = from_xml(file)
        assert isinstance(el, ET.Element), f"ElementTree element expected. Found {el}"
        ns = el.tag.split("{")[1].split("}")[0]
        msg = ""
        for s in el.findall(".//{*}Simulator"):
            if not Path(Path(file).parent / s.get("source", "??")).exists():
                msg += f"Component {s.get('name')}, source {s.get('source','??')} not found. NS:{ns}"
        return (not len(msg), msg)

    def reset(self):  # , cases:Cases):
        """Reset the simulator interface, so that a new simulation can be run."""
        assert isinstance(self.sysconfig, Path), "Simulator resetting does not work with explicitly supplied simulator."
        assert self.sysconfig.exists(), "Simulator resetting does not work with explicitly supplied simulator."
        assert isinstance(self.manipulator, CosimManipulator)
        assert isinstance(self.observer, CosimObserver)
        # self.simulator = self._simulator_from_config(self.sysconfig)
        self.simulator = CosimExecution.from_osp_config_file(str(self.sysconfig))
        assert self.simulator.add_manipulator(manipulator=self.manipulator), "Could not add manipulator object"
        assert self.simulator.add_observer(observer=self.observer), "Could not add observer object"
        # for case in cases:

    def _simulator_from_config(self, file: Path):
        """Instantiate a simulator object through the a suitable configuration file.
        Intended for use case 1 when Cases are in charge.
        """
        if file.is_file():
            _type = "ssp" if file.name.endswith(".ssp") else "osp"
            file = file.parent
        else:  # a directory. Find type
            for child in file.iterdir():
                if child.is_file() and child.name.endswith(".ssp"):
                    _type = "ssp"
                    break
            _type = "osp"
        if _type == "osp":
            return CosimExecution.from_osp_config_file(str(file))
        else:
            return CosimExecution.from_ssp_file(str(file))

    def same_model(self, ref: int, refs: list[int] | set[int]):
        ref_vars = self.get_variables(ref)
        for r in refs:
            r_vars = self.get_variables(r)
            yield (r, r_vars == ref_vars)

    def get_components(self, model: int = -1) -> dict:
        """Provide a dict of `{ component_instances_name : model_ID, ...}` in the system model.
        For each component a unique ID per basic model (FMU) is used.
        In this way, if comps[x]==comps[y] the components x and y relate to the same basic model.
        If model != -1, only the components (instances) related to model are returned.
        """
        comps = {}
        if self.simulator is None:
            pass  # nothing to do we return an empty dict

        elif model >= 0:  # use self.components to extract only components related to the provided model
            for comp, mod in self.components.items():
                if mod == model:
                    comps.update({comp: self.components[comp]})

        else:
            comp_infos = self.simulator.slave_infos()
            for comp in comp_infos:
                for r, same in self.same_model(comp.index, set(comps.values())):
                    if same:
                        comps.update({comp.name.decode(): r})
                        break
                if comp.name.decode() not in comps:  # new model
                    comps.update({comp.name.decode(): comp.index})
        return comps

    def get_models(self) -> list:
        """Get the list of basic models based on self.components."""
        models = []
        for _, m in self.components.items():
            if m not in models:
                models.append(m)
        return models

    def match_components(self, comps: str | tuple[str, ...]) -> tuple[str, tuple]:
        """Identify component (instances) based on 'comps' (component alias or tuple of aliases).
        comps can be a (tuple of) full component names or component names with wildcards.
        Returned components shall be based on the same model.
        """
        if isinstance(comps, str):
            comps = (comps,)
        collect = []
        model = ""
        for c in comps:
            for k, v in self.components.items():
                if match_with_wildcard(c, k):
                    if not len(model):
                        model = v
                    if v == model and k not in collect:
                        collect.append(k)
        return (model, tuple(collect))

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
        assert len(self.components), "Need the dictionary of components before maching variables"

        accepted = None
        variables = self.get_variables(component)
        for k, v in variables.items():
            if accept_as_alias(k):
                if accepted is None:
                    accepted = v
                assert all(
                    v[e] == accepted[e] for e in ("type", "causality", "variability")
                ), f"Variable {k} matches {varname}, but properties do not match"
                var.append(v["reference"])
        #         for sv in model.findall(".//ScalarVariable"):
        #             if sv.get("varname", "").startswith(varname):
        #                 if len(sv.get("varname")) == len(varname):  # full varname. Not part of vector
        #                     return (sv,)
        #                 if len(var):  # check if the var are compliant so that they fit into a 'vector'
        #                     for prop in ("causality", "variability", "initial"):
        #                         assert var[0].get(prop, "") == sv.get(
        #                             prop, ""
        #                         ), f"Model {model.get('modelvarname')}, alias {varname}: The property {prop} of variable {var[0].get('varname')} and {sv.get('varname')} are not compliant with combining them in a 'vector'"
        #                     assert (
        #                         var[0][0].tag == sv[0].tag
        #                     ), f"Model {model.get('modelName')}, alias {varname}: The variable types of {var[0].get('name')} and {sv.get('name')} shall be equal if they are combined in a 'vector'"
        #                 var.append(sv)
        return tuple(var)

    def is_output_var(self, comp: int, ref: int) -> bool:
        for idx in range(self.simulator.num_slave_variables(comp)):
            struct = self.simulator.slave_variables(comp)[idx]
            if struct.reference == ref:
                return struct.causality == 2
        return False

    def get_variables(self, comp: str | int, single: int | str | None = None, as_numbers: bool = True) -> dict:
        """Get the registered variables for a given component from the simulator.

        Args:
            component (str, int): The component name or its index within the model
            single (int,str): Optional possibility to return a single variable.
              If int: by valueReference, else by name.
            as_numbers (bool): Return the enumerations as integer numbers (if True) or as names (if False)

        Returns
        -------
            A dictionary of variable {names:info, ...}, where info is a dictionary containing reference, type, causality and variability
        """
        if isinstance(comp, str):
            component = self.simulator.slave_index_from_instance_name(comp)
            if component is None:  # component not found
                return {}
        elif isinstance(comp, int):
            if comp < 0 or comp >= self.simulator.num_slaves():  # invalid id
                return {}
            component = comp
        else:
            raise AssertionError(f"Unallowed argument {comp} in 'get_variables'")
        variables = {}
        for idx in range(self.simulator.num_slave_variables(component)):
            struct = self.simulator.slave_variables(component)[idx]
            if (
                single is None
                or (isinstance(single, int) and struct.reference == single)
                or struct.name.decode() == single
            ):
                typ = struct.type if as_numbers else CosimVariableType(struct.type).name
                causality = struct.causality if as_numbers else CosimVariableCausality(struct.causality).name
                variability = struct.variability if as_numbers else CosimVariableVariability(struct.variability).name
                variables.update(
                    {
                        struct.name.decode(): {
                            "reference": struct.reference,
                            "type": typ,
                            "causality": causality,
                            "variability": variability,
                        }
                    }
                )
        return variables

    #     def identify_variable_groups(self, component: str, include_all: bool = False) -> dict[str, any]:
    #         """Try to identify variable groups of the 'component', based on the assumption that variable names are structured.
    #
    #         This function is experimental and designed as an aid to define variable aliases in case studies.
    #         Rule: variables must be of same type, causality and variability and must start with a common name to be in the same group.
    #         Note: The function assumes access to component model fmu files.
    #         """
    #
    #         def max_match(txt1: str, txt2: str) -> int:
    #             """Check equality of txt1 and txt2 letter for letter and return the position of first divergence."""
    #             i = 0
    #             for i, c in enumerate(txt1):
    #                 if txt2[i] != c:
    #                     return i
    #             return i
    #
    #         assert component in self.components, f"Component {component} was not found in the system model"
    #
    #         if not isinstance(self.components[component], Path):
    #             print(f"The fmu of of {component} does not seem to be accessible. {component} is registered as {self.components[component]}",
    #         ):
    #             return {}
    #         variables = from_xml(self.components[component], "modelDescription.xml").findall(".//ScalarVariable")
    #         groups = {}
    #         for i, var in enumerate(variables):
    #             if var is not None:  # treated elements are set to None!
    #                 group_name = ""
    #                 group = []
    #                 for k in range(i + 1, len(variables)):  # go through all other variables
    #                     if variables[k] is not None:
    #                         if (
    #                             var.attrib["causality"] == variables[k].attrib["causality"]
    #                             and var.attrib["variability"] == variables[k].attrib["variability"]
    #                             and var[0].tag == variables[k][0].tag
    #                             and variables[k].attrib["name"].startswith(group_name)
    #                         ):  # is a candidate
    #                             pos = max_match(var.attrib["name"], variables[k].attrib["name"])
    #                             if pos > len(group_name):  # there is more commonality than so far identified
    #                                 group_name = var.attrib["name"][:pos]
    #                                 group = [i, k]
    #                             elif len(group_name) and pos == len(group_name):  # same commonality than so far identified
    #                                 group.append(k)
    #                 if len(group_name):  # var is in a group
    #                     groups.update(
    #                         {
    #                             group_name: {
    #                                 "members": (variables[k].attrib["name"] for k in group),
    #                                 "description": var.get("description", ""),
    #                                 "references": (variables[k].attrib["valueReference"] for k in group),
    #                             }
    #                         }
    #                     )
    #                     for k in group:
    #                         variables[k] = None  # treated
    #         if include_all:
    #             for var in variables:
    #                 if var is not None:  # non-grouped variable. Add that since include_all has been chosen
    #                     groups.update(
    #                         {
    #                             var.attrib["name"]: {
    #                                 "members": (var.attrib["name"],),
    #                                 "description": var.get("description", ""),
    #                                 "references": (var.attrib["valueReference"],),
    #                             }
    #                         }
    #                     )
    #         return groups

    #    def set_initial(self, instance: int, typ: int, var_refs: tuple[int], var_vals: tuple[PyVal]):
    def set_initial(self, instance: int, typ: int, var_ref: int, var_val: PyVal):
        """Provide an _initial_value set function (OSP only allows simple variables).
        The signature is the same as the manipulator functions slave_real_values()...,
        only that variables are set individually and the type is added as argument.
        """
        if typ == CosimVariableType.REAL.value:
            return self.simulator.real_initial_value(instance, var_ref, self.pytype(typ, var_val))
        elif typ == CosimVariableType.INTEGER.value:
            return self.simulator.integer_initial_value(instance, var_ref, self.pytype(typ, var_val))
        elif typ == CosimVariableType.STRING.value:
            return self.simulator.string_initial_value(instance, var_ref, self.pytype(typ, var_val))
        elif typ == CosimVariableType.BOOLEAN.value:
            return self.simulator.boolean_initial_value(instance, var_ref, self.pytype(typ, var_val))

    def set_variable_value(self, instance: int, typ: int, var_refs: tuple[int], var_vals: tuple[PyVal]) -> bool:
        """Provide a manipulator function which sets the 'variable' (of the given 'instance' model) to 'value'.

        Args:
            instance (int): identifier of the instance model for which the variable is to be set
            var_refs (tuple): Tuple of variable references for which the values shall be set
            var_vals (tuple): Tuple of values (of the correct type), used to set model variables
        """
        _vals = [self.pytype(typ, x) for x in var_vals]  # ensure list and correct type
        if typ == CosimVariableType.REAL.value:
            return self.manipulator.slave_real_values(instance, list(var_refs), _vals)
        elif typ == CosimVariableType.INTEGER.value:
            return self.manipulator.slave_integer_values(instance, list(var_refs), _vals)
        elif typ == CosimVariableType.BOOLEAN.value:
            return self.manipulator.slave_boolean_values(instance, list(var_refs), _vals)
        elif typ == CosimVariableType.STRING.value:
            return self.manipulator.slave_string_values(instance, list(var_refs), _vals)
        else:
            raise CaseUseError(f"Unknown type {typ}") from None

    def get_variable_value(self, instance: int, typ: int, var_refs: tuple[int]):
        """Provide an observer function which gets the 'variable' value (of the given 'instance' model) at the time when called.

        Args:
            instance (int): identifier of the instance model for which the variable is to be set
            var_refs (tuple): Tuple of variable references for which the values shall be retrieved
        """
        if typ == CosimVariableType.REAL.value:
            return self.observer.last_real_values(instance, list(var_refs))
        elif typ == CosimVariableType.INTEGER.value:
            return self.observer.last_integer_values(instance, list(var_refs))
        elif typ == CosimVariableType.BOOLEAN.value:
            return self.observer.last_boolean_values(instance, list(var_refs))
        elif typ == CosimVariableType.STRING.value:
            return self.observer.last_string_values(instance, list(var_refs))
        else:
            raise CaseUseError(f"Unknown type {typ}") from None

    @staticmethod
    def pytype(fmu_type: str | int, val: PyVal | None = None):
        """Return the python type of the FMU type provided as string or int (CosimEnums).
        If val is None, the python type object is returned. Else if boolean, true or false is returned.
        """
        fmu_type_str = CosimVariableType(fmu_type).name if isinstance(fmu_type, int) else fmu_type
        typ = {"real": float, "integer": int, "boolean": bool, "string": str, "enumeration": Enum}[fmu_type_str.lower()]

        if val is None:
            return typ
        elif typ == bool:
            if isinstance(val, str):
                return "true" in val.lower()  # should be fmi2True and fmi2False
            elif isinstance(val, int):
                return bool(val)
            else:
                raise CaseInitError(f"The value {val} could not be converted to boolean")
        else:
            return typ(val)

    @staticmethod
    def default_initial(causality: int, variability: int, max_possible: bool = False) -> int:
        """Return default initial setting as int, as initial setting is not explicitly available in OSP. See p.50 FMI2.
        maxPossible = True chooses the the initial setting with maximum allowance.

        * Causality: input=0, parameter=1, output=2, calc.par.=3, local=4, independent=5 (within OSP)
        * Initial:   exact=0, approx=1, calculated=2, none=3.
        """
        code = ((3, 3, 0, 3, 0, 3), (3, 0, 3, 1, 1, 3), (3, 0, 3, 1, 1, 3), (3, 3, 2, 3, 2, 3), (3, 3, 2, 3, 2, 3))[
            variability
        ][causality]
        if max_possible:
            return (0, 1, 0, 3)[code]  # first 'possible value' in table
        else:
            return (0, 2, 2, 3)[code]  # default value in table

    def allowed_action(self, action: str, comp: int | str, var: int | str | tuple, time: float):
        """Check whether the action would be allowed according to FMI2 rules, see FMI2.01, p.49.

        * Unfortunately, the OSP interface does not explicitly provide the 'initial' setting,
          such that we need to assume the default value as listed on p.50.
        * OSP does not provide explicit access to 'before initialization' and 'during initialization'.
          The rules for these two stages are therefore not distinguished
        * if a tuple of variables is provided, the variables shall have equal properties
          in addition to the normal allowed rules.

        Args:
            action (str): Action type, 'set', 'get', including init actions (set at time 0)
            comp (int,str): The instantiated component within the system (as index or name)
            var (int,str,tuple): The variable(s) (of component) as reference or name
            time (float): The time at which the action will be performed
        """

        def _description(name: str, info: dict, initial: int) -> str:
            descr = f"Variable {name}, causality {CosimVariableCausality(info['causality']).name}"
            descr += f", variability {CosimVariableVariability(var_info['variability']).name}"
            descr += f", initial {('exact','approx','calculated','none')[initial]}"
            return descr

        def _check(cond, msg):
            if cond:
                self.message = msg
                return True
            return False

        _type, _causality, _variability = (-1, -1, -1)  # unknown
        if isinstance(var, (int, str)):
            var = (var,)
        for v in var:
            variables = self.get_variables(comp, v)
            if _check(len(variables) != 1, f"Variable {v} of component {comp} was not found"):
                return False
            name, var_info = next(variables.items().__iter__())
            if _type < 0 or _causality < 0 or _variability < 0:  # define the properties and check whether allowed
                _type = var_info["type"]
                _causality = var_info["causality"]
                _variability = var_info["variability"]
                initial = SimulatorInterface.default_initial(_causality, _variability, True)

                if action == "get":  # no restrictions on get
                    pass
                elif action == "set":
                    if _check(_variability == 0, f"Variable {name} is defined as 'constant' and cannot be set"):
                        return False
                    if _check(_variability == 0, f"Variable {name} is defined as 'constant' and cannot be set"):
                        return False

                    if time == 0:  # initialization
                        # initial settings 'exact', 'approx' or 'input'
                        if _check(
                            not (initial in (0, 1) or _causality == 0),
                            _description(name, var_info, initial) + " cannot be set before or during initialization.",
                        ):
                            return False
                    else:  # at communication points
                        # 'parameter', 'tunable' or 'input
                        if _check(
                            not ((_causality == 1 and _variability == 2) or _causality == 0),
                            _description(name, var_info, initial) + " cannot be set at communication points.",
                        ):
                            return False
            else:  # check whether the properties are equal
                if _check(_type != var_info["type"], _description(name, var_info, initial) + f" != type {_type}"):
                    return False
                if _check(
                    _causality != var_info["causality"],
                    _description(name, var_info, initial) + f" != causality { _causality}",
                ):
                    return False
                if _check(
                    _variability != var_info["variability"],
                    _description(name, var_info, initial) + f" != variability {_variability}",
                ):
                    return False
        return True

    def variable_name_from_ref(self, comp: int | str, ref: int) -> str:
        for name, info in self.get_variables(comp).items():
            if info["reference"] == ref:
                return name
        return ""

    def component_name_from_id(self, idx: int) -> str:
        """Retrieve the component name from the given index, or an empty string if not found."""
        for slave_info in self.simulator.slave_infos():
            if slave_info.index == idx:
                return slave_info.name.decode()
        return ""

    def component_id_from_name(self, name: str) -> int:
        """Get the component id from the name. -1 if not found."""
        id = self.simulator.slave_index_from_instance_name(name)
        return id if id is not None else -1


def match_with_wildcard(findtxt: str, matchtxt: str) -> bool:
    """Check whether 'findtxt' matches 'matchtxt'.

    Args:
        findtxt (str): the text string which is checked. It can contain wildcard characters '*', matching zero or more of any character.
        matchtxt (str): the text agains findtxt is checked
    Returns: True/False
    """
    if "*" not in findtxt:  # no wildcard characters
        return matchtxt == findtxt
    else:  # there are wildcards
        m = re.search(findtxt.replace("*", ".*"), matchtxt)
        return m is not None


def from_xml(file: Path, sub: str | None = None, xpath: str | None = None) -> ET.Element | list[ET.Element]:
    """Retrieve the Element root from a zipped file (retrieve sub), or an xml file (sub unused).
    If xpath is provided only the xpath matching element (using findall) is returned.
    """
    if is_zipfile(file) and sub is not None:  # expect a zipped archive containing xml file 'sub'
        with ZipFile(file) as zp:
            try:
                xml = zp.read(sub).decode("utf-8")
            except BadZipFile as err:
                raise CaseInitError(f"File '{sub}' not found in {file}: {err}") from err
    elif not is_zipfile(file) and file.exists() and sub is None:  # expect an xml file
        with open(file, encoding="utf-8") as f:
            xml = f.read()
    else:
        raise CaseInitError(f"It was not possible to read an XML from file {file}, sub {sub}")

    try:
        et = ET.fromstring(xml)
    except ET.ParseError as err:
        raise CaseInitError(f"File '{file}' does not seem to be a proper xml file") from err

    if xpath is None:
        return et
    else:
        return et.findall(xpath)
