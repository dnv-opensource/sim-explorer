# pyright: reportMissingImports=false, reportGeneralTypeIssues=false
import os
import re
from enum import Enum
import time
from functools import partial
import xml.etree.ElementTree as ET  # noqa: N817
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Callable
from zipfile import BadZipFile, ZipFile, is_zipfile
import matplotlib.pyplot as plt

from libcosimpy.CosimEnums import CosimVariableType, CosimVariableCausality, CosimVariableVariability
from libcosimpy.CosimExecution import CosimExecution
from libcosimpy.CosimManipulator import CosimManipulator
from libcosimpy.CosimObserver import CosimObserver

# from component_model.model import Model, model_from_fmu
# from component_model.variable import Variable
from .json5 import Json5Reader, json5_write

# type definitions
PyVal = Union[str, float, int, bool]  # simple python types
Json5 = dict[str, Union[PyVal, dict[str, "Json5"], list["Json5"]]]
#    dict[ str, str | float | int | bool | dict[str, "Json5"] | list["Json5"]]  # defines the python representation of Json5 files
Json5List = list["Json5"]
# PyVal = str | float | int | bool  # simple python types
# Json5 = dict[str, PyVal | dict[str, "Json5"] | list["Json5"]]  # defines the python representation of Json5 files


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

def warn( test:bool, msg:str) -> bool:
    """Same as 'assert' statement, only that it is a function and that it does not throw an error"""
    if __debug__:
        if not test:
            raise Warning(msg)
            return True
    return False

class SimulatorInterface:
    """Class providing the interface to the simulator itself.
    This is designed for OSP and needs to be overridden for other types of simulator.
    Provides the following functions

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
        system: Union[Path, str] = "",
        name: Optional[str] = None,
        description: str = "",
        simulator: Optional[CosimExecution] = None,
    ):
        self.name = name  # overwrite if the system includes that
        self.description = description  # overwrite if the system includes that
        if (isinstance(system, Path) or len(system)) and simulator is None:  # instantiate the simulator through the system config file
            self._file = Path(system)
            assert self._file.exists(), f"File {self._file.name} not found"
            self.simulator = self._simulator_from_config( self._file)
        else:
            self._file = None
            self.simulator = simulator
        self.components = self.get_components() # dict of {component name : modelId}    
        # Instantiate a suitable manipulator for changing variables.
        self.manipulator = CosimManipulator.create_override()
        self.simulator.add_manipulator(manipulator=self.manipulator)

        # Instantiate a suitable observer for collecting results.
        self.observer = CosimObserver.create_last_value()
        self.simulator.add_observer(observer=self.observer)

    @property
    def path(self):
        return self._file.resolve().parent

    def _simulator_from_config(self, file: Path):
        """Instantiate a simulator object through the a suitable configuration file.
        Intended for use case 1 when Cases are in charge."""
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

    def get_components(self, model:Optional[any]=None) -> Dict[str,any]:
        """Provide a dict of component models (instances) in the system model.
        For each component either the modelDescription path (if available) is added or an int ID unique per model.
        In this way, if comps[x]==comps[y] the components x and y relate to the same model.
        If model is provided, only the components related to model are returned
        """
        if self.simulator is None: return {}
        comp_infos = list(self.simulator.slave_infos())
        comps = {}
        
        all_variables = []
        for comp in comp_infos:
            name = comp.name.decode()
            variables = self.get_variables( name)
            idx = -1
            for i,v in enumerate(all_variables):
                if v == variables:
                    idx = i
                    break
            if idx < 0:
                all_variables.append( variables)
                idx = len( all_variables)-1
            comps.update( { name: idx})
            
        if model is None:
            return comps
        else:
            model_comps = {}
            for c,m in comps.items():
                if m==model:
                    model_comps.update( {c:m})
            return model_comps
        

    def get_models(self) -> List[any]:
        """Get the list of basic models based on self.components"""
        models = []
        for c,m in self.components.items():
            if m not in models:
                models.append( m)
        return models
    
    def match_components(self, comps:Union[str, Tuple[str]]) -> Tuple[str]:
        """Identify component (instances) based on 'comps' (component alias or tuple of aliases).
        comps can be a (tuple of) full component names or component names with wildcards.
        Returned components shall are based on the same model.
        """
        if isinstance( comps, str):
            comps = ( comps, )
        collect = []
        model = ""
        for c in comps:
            for k,v in self.components.items():
                if match_with_wildcard( c, k):
                    if not len( model):
                        model = v
                    if v==model and k not in collect:
                        collect.append( k)
        return ( model, tuple( collect))
    

    def match_variables(self, component:str, varname: str) -> Tuple[int]:
        """Based on an example component (instance), identify unique variables starting with 'varname'.
        The returned information applies to all instances of the same model.
        The variables shall all be of the same type, causality and variability.

        Args:
            component: component instance varname.
            varname (str): the varname to search for. This can be the full varname or only the start of the varname
              If only the start of the varname is supplied, all matching variables are collected.
        Returns:
            Tuple of value references
        """
        def accept_as_alias(org:str) -> bool:
            """ Decide whether the alias can be accepted with respect to org (uniqueness)."""
            if not org.startswith(varname): # necessary requirement
                return False
            rest = org[ len(varname):]
            if not len(rest) or any( rest.startswith(c) for c in ('[','.')):
                return True
            return False
        
        var = []
        assert len(self.components), "Need the dictionary of components befor maching variables"

        accepted = None
        variables = self.get_variables( component)
        for k,v in variables.items():
            if accept_as_alias( k):
                if accepted is None:
                    accepted = v
                assert all( v[e] == accepted[e] for e in ('type', 'causality', 'variability')),\
                       f"Variable {k} matches {varname}, but properties do not match"
                var.append( v['reference']) 
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


    def get_variables(self, component: Union[str, int], single:Optional[any]=None, as_numbers:bool=True):
        """Get the registered variables for a given component from the simulator.

        Args:
            component (str, int): The component name or its index within the model
            single (int,str): Optional possibility to return a single variable.
              If int: by valueReference, else by name.
            as_numbers (bool): Return the enumerations as integer numbers (if True) or as names (if False

        Returns:
            A dictionary of variable names : info, where info is a dictionary containing reference, type, causality and variability
        """
        
        if isinstance(component, str):
            component = self.simulator.slave_index_from_instance_name(component)
            if component is None:  # component not found
                return {}
        else:
            if component < 0 or component >= self.simulator.num_slaves():  # invalid id
                return {}
        variables = {}
        for idx in range(self.simulator.num_slave_variables(component)):
            struct = self.simulator.slave_variables(component)[idx]
            if ( single is None or
                 (isinstance(single,int) and struct.reference==single) or
                 struct.name.decode()==single):
                typ = struct.type if as_numbers else CosimVariableType(struct.type).name
                causality = struct.causality if as_numbers else CosimVariableCausality(struct.causality).name
                variability = struct.variability if as_numbers else CosimVariableVariability(struct.variability).name
                variables.update({
                    struct.name.decode(): {
                        "reference": struct.reference,
                        "type": typ,
                        "causality": causality,
                        "variability": variability
                    }
                })
        return variables

    def identify_variable_groups(self, component: str, include_all:bool=False) -> Dict[str,any]:
        """ Try to identify variable groups of the 'component', based on the assumption that variable names are structured.
        
        This function is experimental and designed as an aid to define variable aliases in case studies.
        Rule: variables must be of same type, causality and variability and must start with a common name to be in the same group.
        Note: The function assumes access to component model fmu files.
        """
        def max_match( txt1:str, txt2:str) -> int:
            """ Check equality of txt1 and txt2 letter for letter and return the position of first divergence."""
            for i,c in enumerate( txt1):
                if txt2[i] != c: return(i)
            return( i)
        
        assert component in self.components, f"Component {component} was not found in the system model"

        if warn( isinstance( self.components[component], Path), f"The fmu of of {component} does not seem to be accessible. {component} is registered as {self.components[component]}"):
            return {}
        variables = to_et( self.components[component], 'modelDescription.xml').findall(".//ScalarVariable")
        groups = {}
        for i,var in  enumerate( variables):
            if var is not None: # treated elements are set to None!
                group_name = ""
                for k in range( i+1, len(variables)): # go through all other variables
                    if variables[k] is not None:
                        nm = variables[k].attrib['name']
                        if ( var.attrib['causality'] == variables[k].attrib['causality'] and
                             var.attrib['variability'] == variables[k].attrib['variability'] and
                             var[0].tag == variables[k][0].tag and
                             variables[k].attrib['name'].startswith(group_name)): # is a candidate
                            pos = max_match( var.attrib['name'], variables[k].attrib['name'])
                            if pos > len( group_name): # there is more commonality than so far identified
                                group_name = var.attrib['name'][:pos]
                                group = [i, k]
                            elif len( group_name) and pos == len( group_name): # same commonality than so far identified
                                group.append(k)
                if len( group_name): # var is in a group
                    groups.update( { group_name : {'members':(variables[k].attrib['name'] for k in group),
                                                   'description':var.get('description',""),
                                                   'references':(variables[k].attrib['valueReference'] for k in group)}})
                    for k in group: variables[k] = None # treated
        if include_all:
            for var in variables:
                if var is not None: # non-grouped variable. Add that since include_all has been chosen
                    groups.update( { var.attrib['name'] : {'members':(var.attrib['name'], ), 'description':var.get('description', ""), 'references':(var.attrib['valueReference'],)}})
        return groups

    def set_initial(self, instance: int, typ: int, var_refs: Tuple[int], var_vals: Tuple[str]):
        """Helper function to set initial values of variables, based on tuples of var_refs and var_vals (OSP only allows simple variables).
        The signature is the same as the manipulator functions slave_real_values()..., only that variables are set individuallythe type is added as argument.
        """
        print(f"SET initial refs:{var_refs}, vals:{var_vals}")
        assert len(var_refs)==len(var_vals), f"Got #refs:{len(var_refs)} != #vals:{len(var_vals)}"
        _instance = self.simulator.slave_index_from_instance_name(instance)
        res = []
        if typ == CosimVariableType.REAL.value:
            for i in range(len(var_refs)):
                res.append( self.simulator.real_initial_value(_instance, var_refs[i], var_vals[i]))
        elif typ == CosimVariableType.INTEGER.value:
            for i in range(len(var_refs)):
                res.append( self.simulator.integer_initial_value(_instance, var_refs[i], var_vals[i]))
        elif typ == CosimVariableType.STRING.value:
            for i in range(len(var_refs)):
                res.append( self.simulator.string_initial_value(_instance, var_refs[i], var_vals[i]))
        elif typ == CosimVariableType.BOOLEAN.value:
            for i in range(len(var_refs)):
                res.append( self.simulator.boolean_initial_value(_instance, var_refs[i], var_vals[i]))
        assert all( x for x in res), f"Initial setting of ref:{var_refs} to val:{var_vals} failed. Status: {res}"

    def set_variable_value(
        self, instance: str, typ: int, var_refs: Tuple[int], var_vals: Tuple[str, float, int, bool]) -> Callable:
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

    def get_variable_value(self, instance: str, typ: int, var_refs: Tuple[int]) -> Callable:
        """Provide an observer function which gets the 'variable' value (of the given 'instance' model) at the time when called

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
    def pytype(fmu_type:Union[str,int], val:str="" ):
        """Return the python type of the FMU type provided as string or int (CosimEnums).
        If val="", the python type object is returned. Else if boolean, true or false is returned
        """
        if isinstance(fmu_type, int):
            fmu_type = CosimVariableType( fmu_type).name
        typ = {"real": float, "integer": int, "boolean": bool, "string": str, "enumeration": Enum}[fmu_type.lower()]
                
        if val == "":
            return typ
        elif typ == bool:
            return "true" in val.lower()  # should be fmi2True and fmi2False
        else:
            return typ(val)


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
        parent: Optional["Case"] = None,
        spec: Optional[Json5] = None,
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
            for k, v in self.spec.items():
                self.read_spec_item(k, v)
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

    def case_by_name(self, name: str) -> Optional["Case"]:
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

    def add_action(self, typ: str, action: Callable, args: Tuple[str, float, Dict], at_time: Optional[float] = None):
        """Add an action to one of the properties act_set, act_get, act_final, act_step - used for results.
        We use functools.partial to return the functions with fully filled in arguments.
        Compared to lambda... this allows for still accessible (testable) argument lists.

        Args:
            typ (str): the action type 'final', 'single' or 'step'
            action (Callable): the relevant action (manipulator/observer) function to perform
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
                except:  # new time
                    self.act_set.update({at_time: [partial(action, *args)]})
            elif typ == "get":
                try:
                    self.act_get[at_time].append(partial(action, *args))
                except:  # new time
                    self.act_get.update({at_time: [partial(action, *args)]})
        elif typ == "step":
            if at_time in self.act_step:
                self.act_step[at_time].append(partial(action, *args))
            else:  # new interval argument
                self.act_step.update({at_time: [partial(action, *args)]})

    @staticmethod
    def _num_elements( obj:any):
        if obj is None:
            return 0
        elif isinstance(obj, (tuple,list)):
            return len( obj)
        elif isinstance(obj, str):
            return int(len( obj)>0)
        else:
            return 1

    @staticmethod
    def _disect_at_time( txt:str, case:str, value:str) -> tuple[str,str,float|None]:
        """Disect the @txt argument into 'at_time_type' and 'at_time_arg'"""
        pre, _, at = txt.partition("@")
        assert len(pre), f"'{txt}' is not allowed as basis for _disect_at_time"
        if not len(at):  # no @time spec
            if case == "results":
                return (pre, "final", None)
            else:
                assert Case._num_elements(value),\
                       f"Value required for 'set' in _disect_at_time('{txt}','{case}','{value}')"
                return (pre, "set", 0) # set at startTime
        else: # time spec provided
            try:
                arg = float(at)
            except:
                arg = at
            if isinstance(arg, str):
                if at.startswith("step"):
                    try:
                        return (pre, 'step', float(arg[4:]))
                    except:
                        return (pre, 'step', None) # this means 'all macro steps'
                else:
                    assert False, f"Unknown @time instruction {txt}. Case:{case}, value:'{value}'"
            else:                
                return (pre, "set" if Case._num_elements(value) else "get", arg) 
                    

    @staticmethod
    def _disect_range( txt:str, case:str, value):
        """Extract the explicit variable range, if relevant
        (multi-valued variables where only some all elements are addressed).
        Note: it is not explicitly checked whether 'value' exacly the number of values required for the range."""
        pre, _, rng = txt.partition("[")
        if len(rng):  # range among several variables as python slice or comma-separated list
            rng = rng.rstrip("]").strip()
            assert case == "results" or rng == '0' or isinstance(value, list),\
                   f"More than one value required to handle multi-valued setting [{rng}]"
        elif isinstance(value, list):  # all values (without explicit range)
            rng = ":"
        else:  # no range (single variable)
            rng = ""
        return (pre, rng)


    def read_spec_item(self, key: str, value: Optional[Json5] = None):
        """Use the alias variable information (key) and the value to construct an action function which is run when this variable is set/read.
        Optionally, for multi-valued variables (vectors) a range 'rng' may be provided, setting only part of the vector.

        rng (str): Possibility to set only part of a vector variable:
               '': set a single-valued variable, ':' set all variables of a vector, slice (without []) or comma-separated indexes to set part of vector
               The ClassMethod Cases.tuple2_iter() is designed to iterate over the variable/values with respect to rng.

        Note: Observer actions are normally specified within 'results' and are the same for all cases.
          The possibility to observe specific variables in given cases is added through the syntax var@time : '',
          i.e. empty variable value specification, which says: keep the value but record the variable.

        Args:
            key (str): the key of the spec item
            value (str,float,int,bool,list)=None: the value(s) with respect to the item. For 'results' this is not used
        """
        if key in ("startTime", "stopTime", "stepSize"):
            self.special.update({key: value})  # just keep these as a dictionary so far
        else:  # expect a  variable-alias : value(s) specificator
            key, at_time_type, at_time_arg = Case._disect_at_time( key, self.name, value )
            key, rng = Case._disect_range( key, self.name, value)
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
                    for [k, _] in self.tuple2_iter(var_alias["variables"], var_alias["variables"], rng):
                        var_refs.append( k)
                assert at_time_type in ("final", "get", "step"), f"Unknown @time type '{at_time_type}' for 'results'"
                for inst in var_alias["instances"]:  # ask simulator to provide function to set variables:
                    self.add_action(
                        at_time_type,
                        self.cases.simulator.get_variable_value,
                        (inst, var_alias['type'], tuple(var_refs)),
                        at_time_arg,
                    )

            else:  # manipulator actions
                if rng == "":  # a single variable
                    var_refs.append( var_alias["variables"][0])
                    var_vals.append(SimulatorInterface.pytype(var_alias['type'], value))
                else:  # multiple variables
                    for [k, v] in self.tuple2_iter(var_alias["variables"], value, rng):
                        var_refs.append( k)
                        var_vals.append(SimulatorInterface.pytype(var_alias['type'], v))
                assert at_time_type in ("set"), f"Unknown @time type {at_time-type} for case '{self.name}'"
                if at_time_arg == 0.0:  # initial settings use set_initial
                    for inst in var_alias["instances"]:  # ask simulator to provide function to set variables:
                        self.add_action(
                            at_time_type,
                            self.cases.simulator.set_initial,
                            (inst, var_alias['type'], tuple(var_refs), tuple(var_vals)),
                            at_time_arg,
                        )
                else:
                    for inst in var_alias["instances"]:  # ask simulator to provide function to set variables:
                        self.add_action(
                            at_time_type,
                            self.cases.simulator.set_variable_value,
                            (inst, var_alias['type'], tuple(var_refs), tuple(var_vals)),
                            at_time_arg,
                        )

    def list_cases(self, as_name=True, flat=False):
        """List this case and all sub-cases recursively, as name or case objects."""
        lst = [self.name if as_name else self]
        for s in self.subs:
            if flat:
                lst.extend(s.list_cases(as_name, flat))
            else:
                lst.append(s.list_cases(as_name, flat))
        return lst

    def _ensure_specials(self, special: Dict[str, any]) -> Dict[str, any]:
        """The base case shall specify some special variables, needed by the simulator.
        These can be overridden by the hierarchy of a given case.
        The values of the base case ensure that critical values are always avalable
        """
        if "startTime" not in special:
            try: time = float( self.cases.simulator.from_structure(".//{*}StartTime")[0].text)
            except: time = 0.0
            special.update({"startTime":  time})
        assert "stopTime" in special, "'stopTime' should be specified as part of the 'base' specification."
        if "stepSize" not in special:
            try:
                special.update({'stepSize': float( self.cases.simulator.from_structure(".//{*}BaseStepSize")[0].text)})
            except Exception as err:
                raise CaseInitError( "'stepSize' should be specified as part of the 'base' specification.")
        return special


    def save_results(self, results: Dict[float, List], jsfile: Union[bool, str]):
        """Dump the results dict to a json5 file

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

    def plot_time_series(self, aliases: List[str], title=""):
        """Use self.results to extract the provided alias variables and plot the data found in the same plot."""
        assert len(self.results), "The results dictionary is empty. Cannot plot results"
        time_fac = self.cases.time_fac
        for var in aliases:
            times = []
            values = []
            for key in self.results:
                if isinstance(key, int):  # time value
                    if var in self.results[key]:
                        times.append(key / time_fac)
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

    def __init__(self, spec: Union[str, os.PathLike[str]], simulator: Optional[SimulatorInterface]=None):
        self.casesFile = spec
        self.spec = Json5Reader(spec).js_py
        if simulator is None:
            assert (
                "modelFile" in self.spec and Path(self.spec["modelFile"]).exists()
            ), "When the simulator engine is not pre-instantiated, 'modelFile' shall be listed in the spec and shall exist"
            self.simulator = SimulatorInterface( system = Path(self.spec["modelFile"]).resolve(),
                                                 name = self.spec.get('name', ''),
                                                 description = self.spec.get('description', ''))
        else:
            self.simulator = simulator #SimulatorInterface( simulator = simulator)
            
        self.time_fac = self._get_time_unit() * 1e9  # internally OSP uses pico-seconds as integer!
        # read the 'variables' section and generate dict { alias : { (instances), (variables)}}:
        self.variables = self.get_alias_variables()
        for k, v in self.spec.items():  # all case definitions are top-level objects in self.spec
            if k in ("name", "description", "modelFile", "variables", "timeUnit"):  # ignore 'header'
                pass
            else:
                parent, case = self.read_case(k, v)
                if k in ("base","results"): # should always be included. Define properties.
                    setattr(self, k, case)
                    if k=='base': print(self.base)
                else:
                    parent.append(case)
                    

    def get_alias_variables(self) -> Dict[str, ET.Element]:
        """Read the 'variables' main key, which defines self.variables (aliases) as a dictionary:
        { alias : {'model':modelDescription ET.Element, 'instances': tuple of instance names, 'variables': tuple of <ScalarVariable> ET.Element s}, ...}.
        Optionally a description of the alias variable may be provided (and added to the dictionary).
        """
        assert "variables" in self.spec,\
               "Expecting the key 'variables' in the case study specification, defining the model variables in terms of component model instances and variable names"
        assert isinstance( self.spec["variables"], dict),\
               "Expecting the 'variables' section of the spec to be a dictionary of variable alias : [component(s), variable(s), [description]]"
        variables = {}
        for k, v in self.spec["variables"].items():
            assert len(v) in (2,3),\
                   f"The variable specification should be a list of 2 or 3 elements: [instances, variables[, description]]. Found {len(v)}."    
            model, comp = self.simulator.match_components(v[0])
            assert len(comp), f"No component model instances '{v[0]}' found for alias variable '{k}'"
            var = {
                "model": model,
                "instances": comp,
                "variables": self.simulator.match_variables( comp[0], v[1]), # variables from same model!
            }
            assert len(var['variables']), f"No matching variables found for alias {k}:{v}, component '{comp}'"
            if len(v) > 2:
                var.update({"description": v[2]})
            # We add also the more detailed variable info from the simulator (the FMU)
            # The type, causality and variability shall be equal for all variables.
            # The 'reference' element is the same as 'variables'.
            var0 = next( iter( self.simulator.get_variables(model, var['variables'][0]).values()))
            for i in range(1,len( var['variables'])):
                var_i = self.simulator.get_variables(model, var['variables'][i])
                for test in ['type', 'causality', 'variability']:
                    assert var_i[test] == var0[test],\
                        f"Variable with ref {var['variables'][i]} not same {test} as {var0} in model {model}"
            var.update( {'type':var0['type'], 'causality':var0['causality'], 'variability':var0['variability']})
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
        If the entry is not found, 1 second is assumed"""
        unit = self.spec.get("timeUnit", "second")
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

    def read_case(self, name: str, spec: Json5):
        """Define the case 'name'Based on the cases specification 'spec' as json5 python dict, register case 'name
        Generate case objects and store as 'self.base' or in list 'self.subs' of sub-cases.
        """
        if name in ("base", "results"):  # these two are top level objects, linking to Cases
            parent_name, parent_case = ("", None)
        else:
            parent_name = spec.get("parent", "base")
            parent_case = self.case_by_name(str(parent_name))
            assert parent_case is not None, f"For case {name} with parent {parent_name} the parent case was not found"
        case = Case(
            self, name, description=str(spec.get("description", "")), parent=parent_case,
            spec=spec.get("spec", None)
        )
        return (parent_case, case)

    def case_by_name(self, name: str) -> Optional["Case"]:
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

    @classmethod
    def tuple2_iter(self, tpl1: Tuple[any], tpl2: Tuple[any], rng: str):
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
        except:
            if ":" in rng:  # seems to be a slice
                rng = rng.split(":")
                if not len(rng[1]):
                    end = len(tpl1) - 1
                else:
                    try:
                        end = int(rng[1])
                        if end < -1:
                            end += len(tpl1)
                    except ValueError as err:
                        raise CaseInitError(f"Unreadable range specification '{rng}'")
                idx = int(rng[0]) if rng[0].isnumeric() else 0
                while idx <= end:
                    yield (tpl1[idx], tpl2[idx])
                    idx += 1
            elif "," in rng:  # seems to be a comma-separated list
                for e in rng.split(","):
                    try:
                        idx = int(e)
                    except ValueError as err:
                        raise CaseInitError(f"A comma-separated range must consist of integers. Found {rng}")
                    yield (tpl1[idx], tpl2[idx])
            else:
                assert True, f"Only single integer, slice of comma-separated list allowed as range. Found {rng}"

    def info(self, case: Optional[Union[List[Case], Case]] = None, level: int = 0) -> str:
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

    def collect_settings(self, case: "Case", tfac: float) -> Tuple[Dict, List]:
        """Iterate through the case hierarchy of this case, collecting 'special' settings and time-based actions.
        tfac is a time scaling factor. Time becomes an integer (in OSP)
        special is returned as updated dict.
        actions is returned as dictionary of scaled int times with lists of actions
        actions_step is returned as list of (observer) actions to be performed at every macro step
        Each case contains the following:
        self.act_set = {} # dict of manipulator actions for specific times and this case. Updated by read_spec_item
        self.act_get = {} # dict of observer actions for specific times and this case. Updated by read_spec_item
        self.act_final = [] # observer actions at end of simulation
        self.act_step = {} # observer actions at intervals: {dt1:[actions...],...} where dt=None denotes all macro time steps
        """

        def add_action(dct, time, action_list):
            try:
                dct[time].extend(action_list)
            except:
                dct.update({time: action_list})

        special = {}  # 1. Get the 'special' settings, which also contain 'startTime', 'stepSize' and 'stopTime'
        for c in case.iter():
            special.update( c.special)  # update the special variables through the hierarchy, keeping the last value

        tstart = special["startTime"]
        tstop = special["stopTime"]
        actions_set = {}  # dict of absolute times and list of manipulator actions issued at these times

        for c in case.iter():  # 2. Do another iteration to collect actions_set
            for t, alist in c.act_set.items():
                add_action(actions_set, int(t * tfac) if t < tstart else int(tstart * tfac), alist)

        # 3. Collect actions_get
        actions_get = {}  # dict of absolute times and list of observer actions issued at these times
        actions_step = []  # list of (observer) actions to be performed at each step in the simulation
        for t, alist in self.results.act_get.items():
            add_action(actions_get, int(t * tfac) if t < tstart else int(tstart * tfac), alist)

        if len(self.results.act_final):  # add these at stopTime
            add_action(actions_get, int(tstop * tfac), c.act_final)

        for dt, alist in self.results.act_step.items():  # step actions. Time value represents an interval time!
            if dt is None:  # do this at all macro steps (which may be unknown at this point, i.e. variable)
                actions_step.extend(alist)
            else:  # a step interval explicitly provided. We add the (known) times to the actions dict.
                t = int(tstart * tfac)
                dt = int(dt * tfac)
                while t <= int(tstop * tfac):
                    add_action(actions_get, t, alist)
                    t += dt

        return (special, actions_set, actions_get, actions_step)

    def _make_results_header(self, case: "Case"):
        """Make a standard header for the results of 'case'.
        The data is added in run_case():
        """
        results = {
            "Header": {
                "case": case.name,
                "dateTime": time.time(),
                "cases": self.spec.get("name", "None"),
                "casesFile": str(self.casesFile),
                "casesDate": os.path.getmtime(self.casesFile),
                "timeUnit": self.spec.get("timeUnit", "None"),
                "timeFactor": self.time_fac,
            }
        }
        return results

    def run_case(self, name: Union[str, "Case"], dump: Union[bool, str] = False):
        """Set up case 'name' and run it.
        Args:
            name (str,Case): case name as str or case object. The case to be run
            dump (bool,str): Optionally save the results as json file.
              False: results only as string, True: json file with automatic file name, str: explicit filename.json"""

        def action_iter(dct):
            for t, lst in dct.items():
                yield t, lst

        def results_add(time, instance, alias, rng, values):
            try:
                results[time].update({alias: [instance, rng, values]})
            except:  # first set for this time
                results.update({time: {alias: [instance, rng, values]}})

        if isinstance(name, Case):
            case = name
        else:
            case = self.case_by_name(name)
        special, actions_set, actions_get, actions_step = self.collect_settings(
            case, self.time_fac
        )  # Note: final actions are included as _get at end time
        #        print("ACTIONS_SET", actions_set)
        #        print("ACTIONS_GET", actions_get)
        #        print("ACTIONS_STEP", actions_step)
        time = int(special["startTime"] * self.time_fac)
        tstop = int(case.special["stopTime"] * self.time_fac)
        tstep = int(case.special["stepSize"] * self.time_fac)
        next_set = action_iter(actions_set)
        try:
            t_set, a_set = next(next_set)
        except StopIteration:
            pass
        next_get = action_iter(actions_get)
        try:
            t_get, a_get = next(next_get)
        except StopIteration:
            t_get = tstop + 1
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
            for a in actions_step:  # observed at every step
                #                print("STEP args", a.args)
                results_add(time, a.args[0], a.args[3], a.args[4], a())

            time += tstep
        #            print("TIME ", time)

        if dump:
            case.save_results(results, dump)
        case.results = results
        return results


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


def to_et(file: Path, sub: Optional[str] = None) -> ET.Element:
    """Retrieve the Element root from a zipped file (retrieve sub), or an xml file (sub unused)."""
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
            et = ET.parse(file)
            return et.getroot()
        except ParseError as err:
            raise CaseInitError(f"File '{file}' does not seem to be a proper xml file") from err
    else:
        raise CaseInitError(f"It was not possible to read an XML from file {file}, sub {sub}")
