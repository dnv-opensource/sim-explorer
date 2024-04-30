from math import radians
from pathlib import Path

import libcosimpy
import numpy as np

# import pytest
# import inspect
from fmpy import dump, plot_result, simulate_fmu
from fmpy.validation import validate_fmu
from libcosimpy.CosimExecution import CosimExecution

from mvx.case_study.case import Case, Cases, SimulatorInterface


def _file(file: str = "MobileCrane.cases"):
    path = Path(__file__).parent.joinpath(file)
    assert path.exists(), f"File {file} does not exist at {Path(__file__).parent.joinpath(file)}"
    return path


def check_expected(value: any, expected: any, feature: str):
    assert value == expected, f"Expected the {feature} '{expected}', but found the value {value}"


def np_arrays_equal(arr1, arr2, dtype="float64", eps=1e-7):
    assert len(arr1) == len(arr2), "Length not equal!"
    if isinstance(arr2, (tuple, list)):
        arr2 = np.array(arr2, dtype=dtype)
    assert isinstance(arr1, np.ndarray) and isinstance(
        arr2, np.ndarray
    ), "At least one of the parameters is not an ndarray!"
    assert arr1.dtype == arr2.dtype, f"Arrays are of type {arr1.dtype} != {arr2.dtype}"

    for i in range(len(arr1)):
        assert abs(arr1[i] - arr2[i]) < eps, f"Component {i}: {arr1[i]} != {arr2[i]}"


def validate(model, msg=False):
    val = validate_fmu(model)
    assert not len(val), f"Validation of the modelDescription of {model} was not successful. Errors: {val}"
    if msg:
        print(f"Validation of {model} ok")
        print(dump(model))


def find_index(lst: list[list[float]], el: list[float], eps=1e-7):
    for idx, e in enumerate(lst):
        if len(e) == len(el) and all(abs(e[i] - el[i]) < eps for i in range(len(el))):
            return idx
    return None


def test_simpletable(interpolate=True):
    """Test the SimpleTable FMU, copied into the OSP_MobileCrane folder, using fmpy"""
    validate("OSP_MobileCrane/SimpleTable.fmu")
    result = simulate_fmu(
        "OSP_MobileCrane/SimpleTable.fmu",
        stop_time=10.0,
        step_size=0.1,
        validate=True,
        solver="Euler",
        debug_logging=True,
        logger=print,  # fmi_call_logger=print,
        start_values={"interpolate": interpolate},
    )
    #    plot_result( result)
    assert 71 == find_index(result, (7.1, 8, 7, 6)), "Element not found"


def test_mobilecrane():
    validate("OSP_MobileCrane/MobileCrane.fmu", msg=True)
    result = simulate_fmu(
        "OSP_MobileCrane/MobileCrane.fmu",
        stop_time=1.0,
        step_size=0.1,
        validate=True,
        solver="Euler",
        debug_logging=True,
        logger=print,  # fmi_call_logger=print,
        start_values={
            "pedestal_mass": 10000.0,
            "pedestal_boom[0]": 3.0,
            "boom_mass": 1000.0,
            "boom_boom[0]": 8,
            "boom_boom[1]": radians(50),
            "craneAngularVelocity[0]": 0.1,
            "craneAngularVelocity[1]": 0.0,
            "craneAngularVelocity[2]": 0.0,
            "craneAngularVelocity[3]": 1.0,
        },
    )
    plot_result(result)


#    print("RESULT", result)


def test_simulator_from_system_structure():
    """SimulatorInterface from OspSystemStructure.xml"""
    systemfile = _file("OSP_mobileCrane/OspSystemStructure.xml")
    system = SimulatorInterface(systemfile, name="MobileCrane", description="test")  # components, manipulator, observer
    check_expected(system.typ, "OSP", "System.typ")
    check_expected(system.name, "MobileCrane", "System.name")
    check_expected(system.description, "test", "System.description")
    check_expected(system._file.name, "OspSystemStructure.xml", "system._file")
    check_expected(
        system._system.tag,
        "{http://opensimulationplatform.com/MSMI/OSPSystemStructure}OspSystemStructure",
        "system._system.tag",
    )
    check_expected(type(system.simulator), CosimExecution, "type(system.simulator)")
    check_expected("mobileCrane" in system.components and len(system.components) == 2, True, "system.components")
    check_expected(type(system.observer), libcosimpy.CosimObserver.CosimObserver, "system.observer")
    check_expected(type(system.manipulator), libcosimpy.CosimManipulator.CosimManipulator, "system.manipulator")
    assert "pedestal_centerOfMass[2]" in system.get_variables(
        "mobileCrane"
    ), "Variable pedestal_centerOfMass[2] expected"
    assert (
        system.get_variables("mobileCrane")["pedestal_centerOfMass[2]"]["reference"] == 21
    ), "Variable pedestal_centerOfMass[2] reference"
    assert (
        system.get_variables("mobileCrane")["pedestal_centerOfMass[2]"]["type"] == 0
    ), "Variable pedestal_centerOfMass[2] type"
    assert (
        system.get_variables("mobileCrane")["pedestal_centerOfMass[2]"]["causality"] == 0
    ), "Variable pedestal_centerOfMass[2] causality"
    assert (
        system.get_variables("mobileCrane")["pedestal_centerOfMass[2]"]["variability"] == 4
    ), "Variable pedestal_centerOfMass[2] variability"
    groups = system.identify_variable_groups("mobileCrane", include_all=True)
    for g in groups:
        print(f"'mobileCrane', {g}, {groups[g]['description']}")


def test_cases():
    """Test of the features provided by the Cases class"""
    sim = SimulatorInterface(_file("OSP_MobileCrane/OspSystemStructure.xml"))
    check_expected(len(sim.components), 2, "Number of components")
    check_expected("mobileCrane" in sim.components, True, "mobileCrane is a components")
    check_expected("simpleTable" in sim.components, True, "simpleTable is a components")
    variables = sim.get_variables("mobileCrane")
    check_expected(all(f"craneTorque[{i}]" in variables for i in range(3)), True, "Vector 'craneTorque'")
    variables = sim.get_variables("simpleTable")
    check_expected(all(f"outs[{i}]" in variables for i in range(3)), True, "Vector 'outs' of simpleTable")
    return
    cases = Cases(_file("MobileCrane.cases"), sim)
    print(cases.info())
    # cases.spec
    assert cases.spec["name"] == "BouncingBall", "BouncingBall expected as cases name"
    assert cases.spec["description"].startswith("Case Study with the"), "description not as expected"
    assert cases.spec["modelFile"] == "../data/BouncingBall/OspSystemStructure.xml", "modelFile not as expected"
    for c in ("base", "case1", "case2", "case3"):
        assert c in cases.spec, f"The case '{c}' is expected to be defined in {cases.spec['name']}"
    # find_by_name
    for c in cases.base.list_cases(as_name=False, flat=True):
        assert cases.find_by_name(c.name).name == c.name, f"Case {c.name} not found in hierarchy"
    assert cases.find_by_name("case99") is None, "Case99 was not expected to be found"
    case3 = cases.find_by_name("case3")
    assert case3.name == "case3", "'case3' is expected to exist"
    assert case3.find_by_name("case2") is None, "'case2' should not exist within the sub-hierarchy of 'case3'"
    case1 = cases.find_by_name("case1")
    assert case1.find_by_name("case2") is not None, "'case2' should exist within the sub-hierarchy of 'case1'"
    # variables (aliases)
    assert (
        cases.get_scalarvariables(cases.simulator.instances["bb"], "h")[0].get("name") == "h"
    ), "Scalar variable 'h' not found"
    vars_der = cases.get_scalarvariables(cases.simulator.instances["bb"], "der")
    assert len(vars_der) == 2 and vars_der[1].get("name") == "der(v)", "Vector variable 'der' not as expected"
    check_expected(cases.get_alias_from_spec("BouncingBall", "bb", 3), "v", "alias name from valueReference")
    check_expected(cases.get_alias_from_spec("BouncingBall", "bb", "v"), "v", "alias name from scalarVariable name")


def check_value(case: "Case", var: str, val: float):
    if var in case.spec:
        assert case.spec[var] == val, f"Wrong value {case.spec[var]} for variable {var}. Expected: {val}"
    else:  # not explicitly defined for this case. Shall be defined in the hierarchy!
        check_value(case.parent, var, val)


def test_case():
    """Test of the features provided by the Case class"""
    sim = SimulatorInterface(_file("OSP_MobileCrane/OspSystemStructure.xml"))
    cases = Cases(_file("OSP_MobileCrane/MobileCrane.cases"), sim)
    assert cases.base.list_cases()[2] == ["case3"], "Error in list_cases"
    assert cases.base.special == {
        "stopTime": 3,
        "startTime": 0.0,
        "stepSize": 0.01,
    }, f"Base case special not as expected. Found {cases.base.special}"
    # iter()
    case2 = cases.find_by_name("case2")
    assert [c.name for c in case2.iter()] == ["base", "case1", "case2"], "Hierarchy of case2 not as expected"
    check_value(case2, "v", 9.0)
    check_value(case2, "h", 5.0)
    check_value(case2, "e", 0.7)
    check_expected(case2.act_set[0.0][0].func.__name__, "_set_initial", "function name")
    check_expected(case2.act_set[0.0][0].args[0], "bb", "model instance")
    check_expected(case2.act_set[0.0][0].args[1], "real", "variable type")
    check_expected(case2.act_set[0.0][0].args[2], (3,), "variable ref")
    check_expected(case2.act_set[0.0][0].args[3], (9.0,), "variable value")
    check_expected(cases.results.act_get[1.0][0].func.__name__, "get_variable_value", "get @time function")
    check_expected(cases.results.act_get[1.0][0].args[0], "bb", "model instance")
    check_expected(cases.results.act_get[1.0][0].args[1], "real", "variable type")
    check_expected(cases.results.act_get[1.0][0].args[2], (3,), "variable refs")
    check_expected(cases.get_alias_from_spec("BouncingBall", "bb", 3), "v", "alias_name_from_spec")
    check_expected(cases.results.act_step[None][0].args[2], (1,), "variable refs of act_step")
    check_expected(cases.results.act_final[0].args[2], (6,), "variable refs of act_final")
    print("RESULTS", cases.run_case(cases.base, dump=True))
    cases.base.plot_time_series(["h"], "TestPlot")


if __name__ == "__main__":
    #    test_simpletable()
    #    test_mobilecrane()
    #    test_simulator_from_system_structure()
    #     test_cases()
    test_case()
