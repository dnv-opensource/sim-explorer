from math import radians
from pathlib import Path

import numpy as np
from case_study.case import Case, Cases
from case_study.simulator_interface import SimulatorInterface, from_xml

# import pytest
# import inspect
from fmpy import dump, plot_result, simulate_fmu
from fmpy.validation import validate_fmu
from libcosimpy.CosimExecution import CosimExecution
from libcosimpy.CosimManipulator import CosimManipulator
from libcosimpy.CosimObserver import CosimObserver


def _file(file: str = "MobileCrane.cases"):
    path = Path(__file__).parent.joinpath(file)
    assert path.exists(), f"File {file} does not exist at {Path(__file__).parent.joinpath(file)}"
    return path


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


def find_index(lst: list, el: tuple, eps=1e-7):
    for idx, e in enumerate(lst):
        if len(e) == len(el) and all(abs(e[i] - el[i]) < eps for i in range(len(el))):
            return idx
    return None


def test_simpletable(interpolate=True):
    """Test the SimpleTable FMU, copied into the OSP_MobileCrane folder, using fmpy"""
    validate("OSP_MobileCrane/SimpleTable.fmu")
    assert Path("OSP_MobileCrane/SimpleTable.fmu").exists(), "SimpleTable.fmu not found"
    result = simulate_fmu(  # type: ignore
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
    assert 71 == find_index(list(result), (7.1, 8, 7, 6)), "Element not found"


def test_mobilecrane():
    validate("OSP_MobileCrane/MobileCrane.fmu", msg=True)
    result = simulate_fmu(  # type: ignore
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
    sim = SimulatorInterface(systemfile, name="MobileCrane", description="test")  # components, manipulator, observer
    assert isinstance(sim, SimulatorInterface), "Basic OSP simulator interface"
    assert sim.name == "MobileCrane", "Simulator interface name"
    assert sim.description == "test", "sim.description"
    assert sim.sysconfig is not None and sim.sysconfig.name == "OspSystemStructure.xml", "sim config file"
    assert (
        from_xml(sim.sysconfig)[0].tag
        == "{http://opensimulationplatform.com/MSMI/OSPSystemStructure}OspSystemStructure"
    ), "sim._system.tag"
    assert type(sim.simulator) == CosimExecution, "type(sim.simulator)"
    assert "mobileCrane" in sim.components and len(sim.components) == 2, "sim.components"
    assert type(sim.observer) == CosimObserver, "sim.observer"
    assert type(sim.manipulator) == CosimManipulator, "sim.manipulator"
    assert "pedestal_centerOfMass[2]" in sim.get_variables("mobileCrane"), "Variable pedestal_centerOfMass[2] expected"
    assert (
        sim.get_variables("mobileCrane")["pedestal_centerOfMass[2]"]["reference"] == 21
    ), "Variable pedestal_centerOfMass[2] reference"
    assert (
        sim.get_variables("mobileCrane")["pedestal_centerOfMass[2]"]["type"] == 0
    ), "Variable pedestal_centerOfMass[2] type"
    assert (
        sim.get_variables("mobileCrane")["pedestal_centerOfMass[2]"]["causality"] == 0
    ), "Variable pedestal_centerOfMass[2] causality"
    assert (
        sim.get_variables("mobileCrane")["pedestal_centerOfMass[2]"]["variability"] == 4
    ), "Variable pedestal_centerOfMass[2] variability"


#     groups = sim.identify_variable_groups("mobileCrane", include_all=True)
#     for g in groups:
#         print(f"'mobileCrane', {g}, {groups[g]['description']}")


def test_cases():
    """Test of the features provided by the Cases class"""
    sim = SimulatorInterface(_file("OSP_MobileCrane/OspSystemStructure.xml"))
    assert len(sim.components) == 2, "Number of components"
    assert "mobileCrane" in sim.components, "mobileCrane is a components"
    assert "simpleTable" in sim.components, "simpleTable is a components"
    variables = sim.get_variables("mobileCrane")
    assert all(f"craneTorque[{i}]" in variables for i in range(3)), "Vector 'craneTorque'"
    variables = sim.get_variables("simpleTable")
    assert all(f"outs[{i}]" in variables for i in range(3)), "Vector 'outs' of simpleTable"
    cases = Cases(_file("MobileCrane.cases"), sim)
    print(cases.info())
    # cases.spec
    assert isinstance(cases.spec, dict), f"dict expected as cases.spec. Found {cases.spec}"
    assert cases.spec["name"] == "MobileCrane", f"MobileCrane expected as cases name. Found {cases.spec['name']}"
    assert isinstance(cases.spec["description"], str), f"str expected as description. Found:{cases.spec['description']}"
    assert cases.spec["description"].startswith("Case Study with the Crane"), "description not as expected"
    assert cases.spec["modelFile"] == "../data/BouncingBall/OspSystemStructure.xml", "modelFile not as expected"
    # ?? to be extended when working actively with the FMU


def check_value(case: "Case", var: str, val: float):
    assert isinstance(case.spec, dict), f"Dict expected. Found {case.spec}"
    if var in case.spec:
        assert case.spec[var] == val, f"Wrong value {case.spec[var]} for variable {var}. Expected: {val}"
    else:  # not explicitly defined for this case. Shall be defined in the hierarchy!
        assert case.parent is not None, "Parent needed at this stage"
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
    case2 = cases.case_by_name("case2")
    assert case2 is not None, "None is not acceptable for case2"
    assert [c.name for c in case2.iter()] == ["base", "case1", "case2"], "Hierarchy of case2 not as expected"
    check_value(case2, "v", 9.0)
    check_value(case2, "h", 5.0)
    check_value(case2, "e", 0.7)
    assert case2.act_set[0.0][0].func.__name__ == "_set_initial", "function name"
    assert case2.act_set[0.0][0].args[0] == "bb", "model instance"
    assert case2.act_set[0.0][0].args[1] == "real", "variable type"
    assert case2.act_set[0.0][0].args[2] == (3,), "variable ref"
    assert case2.act_set[0.0][0].args[3] == (9.0,), "variable value"
    assert cases.results.act_get[1.0][0].func.__name__ == "get_variable_value", "get @time function"
    assert cases.results.act_get[1.0][0].args[0] == "bb", "model instance"
    assert cases.results.act_get[1.0][0].args[1] == "real", "variable type"
    assert cases.results.act_get[1.0][0].args[2] == (3,), "variable refs"
    #    assert cases.get_alias_variables( "BouncingBall", "bb", 3) == "v", "alias_name_from_spec"
    assert cases.results.act_step[None][0].args[2] == (1,), "variable refs of act_step"
    assert cases.results.act_final[0].args[2] == (6,), "variable refs of act_final"
    print("RESULTS", cases.run_case(cases.base, dump=True))
    cases.base.plot_time_series(["h"], "TestPlot")


if __name__ == "__main__":
    #    test_simpletable()
    #    test_mobilecrane()
    #    test_simulator_from_system_structure()
    #     test_cases()
    test_case()
