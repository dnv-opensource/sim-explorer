# pyright: reportMissingImports=false, reportGeneralTypeIssues=false
import re
import xml.etree.ElementTree as ET  # noqa: N817
from enum import Enum
from pathlib import Path
from typing import TypeAlias
from zipfile import BadZipFile, ZipFile, is_zipfile

from libcosimpy.CosimEnums import CosimVariableCausality, CosimVariableType, CosimVariableVariability
from libcosimpy.CosimExecution import CosimExecution
from libcosimpy.CosimManipulator import CosimManipulator
from libcosimpy.CosimObserver import CosimObserver

# from component_model.model import Model, model_from_fmu
# from component_model.variable import Variable

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


def warn(test: bool, msg: str) -> bool:
    """Warn the user. Same as 'assert' statement, only that it is a function and that it does not throw an error."""
    if __debug__:
        if not test:
            raise Warning(msg)
            return True
    return False


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

    def __init__(
        self,
        system: Path | str = "",
        name: str | None = None,
        description: str = "",
        simulator: CosimExecution | None = None,
    ):
        self.name = name  # overwrite if the system includes that
        self.description = description  # overwrite if the system includes that
        if simulator is None:  # instantiate the simulator through the system config file
            self.sysconfig = Path(system)
            assert self.sysconfig.exists(), f"File {self.sysconfig.name} not found"
            self.simulator = self._simulator_from_config(self.sysconfig)
        else:
            self.sysconfig = None
            self.simulator = simulator
        self.components = self.get_components()  # dict of {component name : modelId}
        # Instantiate a suitable manipulator for changing variables.
        self.manipulator = CosimManipulator.create_override()
        self.simulator.add_manipulator(manipulator=self.manipulator)

        # Instantiate a suitable observer for collecting results.
        self.observer = CosimObserver.create_last_value()
        self.simulator.add_observer(observer=self.observer)

    @property
    def path(self):
        return self.sysconfig.resolve().parent if self.sysconfig is not None else None

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

    def get_components(self, model: str | None = None) -> dict:
        """Provide a dict of component models (instances) in the system model.
        For each component either the modelDescription path (if available) is added or an int ID unique per model.
        In this way, if comps[x]==comps[y] the components x and y relate to the same model.
        If model is provided, only the components related to model are returned.
        """
        if self.simulator is None:
            return {}
        comp_infos = list(self.simulator.slave_infos())
        comps = {}

        all_variables = []
        for comp in comp_infos:
            name = comp.name.decode()
            variables = self.get_variables(name)
            idx = -1
            for i, v in enumerate(all_variables):
                if v == variables:
                    idx = i
                    break
            if idx < 0:
                all_variables.append(variables)
                idx = len(all_variables) - 1
            comps.update({name: idx})

        if model is None:
            return comps
        else:
            model_comps = {}
            for c, m in comps.items():
                if m == model:
                    model_comps.update({c: m})
            return model_comps

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
        Returned components shall are based on the same model.
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
        assert len(self.components), "Need the dictionary of components befor maching variables"

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

    def get_variables(self, comp: str | int, single: int | str | None = None, as_numbers: bool = True) -> dict:
        """Get the registered variables for a given component from the simulator.

        Args:
            component (str, int): The component name or its index within the model
            single (int,str): Optional possibility to return a single variable.
              If int: by valueReference, else by name.
            as_numbers (bool): Return the enumerations as integer numbers (if True) or as names (if False

        Returns
        -------
            A dictionary of variable names : info, where info is a dictionary containing reference, type, causality and variability
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
    #         if warn(
    #             isinstance(self.components[component], Path),
    #             f"The fmu of of {component} does not seem to be accessible. {component} is registered as {self.components[component]}",
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

    def set_initial(self, instance: int, typ: int, var_refs: tuple[int, ...], var_vals: tuple[str, ...]):
        """Set initial values of variables, based on tuples of var_refs and var_vals (OSP only allows simple variables).
        The signature is the same as the manipulator functions slave_real_values()..., only that variables are set individuallythe type is added as argument.
        """
        print(f"SET initial refs:{var_refs}, vals:{var_vals}")
        assert len(var_refs) == len(var_vals), f"Got #refs:{len(var_refs)} != #vals:{len(var_vals)}"
        _instance = self.simulator.slave_index_from_instance_name(instance)
        res = []
        if typ == CosimVariableType.REAL.value:
            for i in range(len(var_refs)):
                res.append(self.simulator.real_initial_value(_instance, var_refs[i], var_vals[i]))
        elif typ == CosimVariableType.INTEGER.value:
            for i in range(len(var_refs)):
                res.append(self.simulator.integer_initial_value(_instance, var_refs[i], var_vals[i]))
        elif typ == CosimVariableType.STRING.value:
            for i in range(len(var_refs)):
                res.append(self.simulator.string_initial_value(_instance, var_refs[i], var_vals[i]))
        elif typ == CosimVariableType.BOOLEAN.value:
            for i in range(len(var_refs)):
                res.append(self.simulator.boolean_initial_value(_instance, var_refs[i], var_vals[i]))
        assert all(x for x in res), f"Initial setting of ref:{var_refs} to val:{var_vals} failed. Status: {res}"

    def set_variable_value(
        self, instance: str, typ: int, var_refs: tuple[int, ...], var_vals: tuple[str | float | int | bool, ...]
    ) -> callable:
        """Provide a manipulator function which sets the 'variable' (of the given 'instance' model) to 'value'.

        Args:
            instance (str): identifier of the instance model for which the variable is to be set
            var_refs (tuple): Tuple of variable references for which the values shall be set
            var_vals (tuple): Tuple of values (of the correct type), used to set model variables
        """
        print(f"SET refs:{var_refs}, vals:{var_vals}")
        _instance = self.simulator.slave_index_from_instance_name(instance)
        assert (
            _instance is not None
        ), f"Model instance name {instance} was not found within the system model {self.name}"
        if typ == CosimVariableType.REAL.value:
            return self.manipulator.slave_real_values(_instance, var_refs, var_vals)
        if typ == CosimVariableType.INTEGER.value:
            return self.manipulator.slave_integer_values(_instance, var_refs, var_vals)
        if typ == CosimVariableType.BOOLEAN.value:
            return self.manipulator.slave_boolean_values(_instance, var_refs, var_vals)
        if typ == CosimVariableType.STRING.value:
            return self.manipulator.slave_string_values(_instance, var_refs, var_vals)

    def get_variable_value(self, instance: str, typ: int, var_refs: tuple[int, ...]) -> callable:
        """Provide an observer function which gets the 'variable' value (of the given 'instance' model) at the time when called.

        Args:
            instance (str): identifier of the instance model for which the variable is to be set
            var_refs (tuple): Tuple of variable references for which the values shall be retrieved
        """
        print(f"GET refs:{var_refs}")
        _instance = self.simulator.slave_index_from_instance_name(instance)
        assert (
            _instance is not None
        ), f"Model instance name {instance} was not found within the system model {self.name}"
        if typ == CosimVariableType.REAL.value:
            return self.observer.last_real_values(_instance, var_refs)
        if typ == CosimVariableType.INTEGER.value:
            return self.observer.last_integer_values(_instance, var_refs)
        if typ == CosimVariableType.BOOLEAN.value:
            return self.observer.last_boolean_values(_instance, var_refs)
        if typ == CosimVariableType.STRING.value:
            return self.observer.last_string_values(_instance, var_refs)

    @staticmethod
    def pytype(fmu_type: str | int, val: PyVal | None = None):
        """Return the python type of the FMU type provided as string or int (CosimEnums).
        If val is None, the python type object is returned. Else if boolean, true or false is returned.
        """
        if isinstance(fmu_type, int):
            fmu_type = CosimVariableType(fmu_type).name
        typ = {"real": float, "integer": int, "boolean": bool, "string": str, "enumeration": Enum}[fmu_type.lower()]

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
                xml = zp.read(sub)
            except BadZipFile as err:
                raise CaseInitError(f"File '{sub}' not found in {file}: {err}") from err
            else:
                return ET.fromstring(xml)
    elif not is_zipfile(file) and file.exists() and sub is None:  # expect an xml file
        try:
            et = ET.parse(file).getroot()
        except ET.ParseError as err:
            raise CaseInitError(f"File '{file}' does not seem to be a proper xml file") from err
    else:
        raise CaseInitError(f"It was not possible to read an XML from file {file}, sub {sub}")

    if xpath is None:
        return et
    else:
        return et.findall(xpath)
