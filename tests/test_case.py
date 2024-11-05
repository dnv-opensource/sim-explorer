import xml.etree.ElementTree as ET  # noqa: N817
from pathlib import Path
from typing import Any

import pytest
from sim_explorer.case import Case, Cases
from sim_explorer.json5 import Json5
from sim_explorer.simulator_interface import SimulatorInterface


@pytest.fixture
def simpletable(scope="module", autouse=True):
    return _simpletable()


def _simpletable():
    path = Path(__file__).parent / "data" / "SimpleTable" / "test.cases"
    assert path.exists(), "SimpleTable cases file not found"
    return Cases(path)


def test_fixture(simpletable):
    assert isinstance(simpletable, Cases), f"Cases object expected. Found:{simpletable}"


def _make_cases():
    """Make an example cases file for use in the tests"""

    root = ET.Element(
        "OspSystemStructure", {"xmlns": "http://opensimulationplatform.com/MSMI/OSPSystemStructure", "version": "0.1"}
    )
    simulators = ET.Element("Simulators")
    simulators.append(ET.Element("Simulator", {"name": "tab", "source": "SimpleTable.fmu", "stepSize": "0.1"}))
    root.append(simulators)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="   ", level=0)
    tree.write("data/OspSystemStructure.xml", encoding="utf-8")

    json5 = {
        "name": "Testing",
        "description": "Simple sim explorer for testing purposes",
        "timeUnit": "second",
        "variables": {
            "x": ["tab", "outs", "Outputs (3-dim)"],
            "i": ["tab", "interpolate", "Interpolation setting"],
        },
        "base": {
            "description": "Mandatory base settings. No interpolation",
            "spec": {
                "stepSize": 0.1,
                "stopTime": 1,
                "i": False,
            },
            "results": ["x@step", "x[0]@1.0", "i"],
        },
        "case1": {
            "description": "Interpolation ON",
            "spec": {
                "i": True,
            },
        },
        "caseX": {"description": "Based case1 longer simulation", "parent": "case1", "spec": {"stopTime": 10}},
    }
    js = Json5(json5)
    js.write("data/test.cases")
    _ = SimulatorInterface("data/OspSystemStructure.xml", "testSystem")
    _ = Cases("data/test.cases")


# @pytest.mark.skip(reason="Deactivated")
def test_case_at_time(simpletable):
    # print("DISECT", simpletable.case_by_name("base")._disect_at_time("x@step", ""))
    do_case_at_time("v@1.0", "base", "res", ("v", "get", 1.0), simpletable)
    return
    do_case_at_time("x@step", "base", "res", ("x", "step", -1), simpletable)
    do_case_at_time("x@step 2.0", "base", "res", ("x", "step", 2.0), simpletable)
    do_case_at_time("v@1.0", "base", "res", ("v", "get", 1.0), simpletable)
    do_case_at_time(
        "v@1.0", "caseX", "res", ("v", "get", 1.0), simpletable
    )  # value retrieval per case at specified time
    do_case_at_time("@1.0", "base", "result", "'@1.0' is not allowed as basis for _disect_at_time", simpletable)
    do_case_at_time("i", "base", "res", ("i", "get", 1), simpletable)  # "report the value at end of sim!"
    do_case_at_time("y", "caseX", 99.9, ("y", "set", 0), simpletable)  # "Initial value setting!"


def do_case_at_time(txt, casename, value, expected, simpletable):
    """Test the Case.disect_at_time function"""
    # print(f"TEST_AT_TIME {txt}, {casename}, {value}, {expected}")
    case = simpletable.case_by_name(casename)
    assert case is not None, f"Case {casename} was not found"
    if isinstance(expected, str):  # error case
        with pytest.raises(AssertionError) as err:
            case._disect_at_time(txt, value)
        assert str(err.value).startswith(expected)
    else:
        assert case._disect_at_time(txt, value) == expected, f"Found {case._disect_at_time(txt, value)}"


# @pytest.mark.skip(reason="Deactivated")
def test_case_range(simpletable):
    x_inf = simpletable.variables["x"]
    # print("RNG", simpletable.case_by_name("results").cases.disect_variable("x"))
    do_case_range("x", "base", ("x", x_inf, range(0, 3)), simpletable)
    do_case_range("x[2]", "base", ("x", x_inf, [2]), simpletable)
    do_case_range("x[2]", "caseX", ("x", x_inf, [2]), simpletable)
    do_case_range("x[1..2]", "base", ("x", x_inf, range(1, 2)), simpletable)
    do_case_range("x[0,1,2]", "base", ("x", x_inf, [0, 1, 2]), simpletable)
    do_case_range("x[0...2]", "caseX", ("x", x_inf, range(0, 2)), simpletable)
    do_case_range("x", "caseX", ("x", x_inf, range(0, 3)), simpletable)  # assume all values
    do_case_range("x[3]", "caseX", "Index 3 of variable x out of range", simpletable)
    do_case_range("x[1,2,4]", "caseX", "Index 4 of variable x out of range", simpletable)
    do_case_range("x[1.3]", "caseX", "Unhandled index", simpletable)
    assert simpletable.case_by_name("caseX").cases.disect_variable("x[99]", err_level=0) == ("", None, range(0, 0))
    assert simpletable.case_by_name("caseX").cases.disect_variable("x[1]")[2] == [1]
    assert simpletable.case_by_name("caseX").cases.disect_variable("i")[1]["instances"] == ("tab",)


def do_case_range(txt: str, casename: str, expected: tuple | str, simpletable):
    """Test the .cases.disect_variable function"""
    case = simpletable.case_by_name(casename)
    if isinstance(expected, str):  # error case
        with pytest.raises(Exception) as err:
            case.cases.disect_variable(txt)
        # print(f"ERROR:{err.value}")
        assert str(err.value).startswith(expected), f"{str(err.value)} does not start with {expected}"
    else:
        assert case.cases.disect_variable(txt) == expected, f"Found {case.cases.disect_variable(txt)}"


def check_value(case: Case, var: str, val: Any):
    found = case.js.jspath(f"$.spec.{var}")
    if found is not None:
        assert found == val, f"Wrong value {found} for variable {var}. Expected: {val}"
    else:  # not explicitly defined for this case. Shall be defined in the hierarchy!
        assert case.parent is not None, f"Parent case needed for {case.name}"
        check_value(case.parent, var, val)


def str_act(action) -> str:
    """Prepare a human readable view of the action"""
    if len(action.args) == 3:
        return f"{action.func.__name__}(inst={action.args[0]}, type={action.args[1]}, ref={action.args[2]}"
    else:
        return f"{action.func.__name__}(inst={action.args[0]}, type={action.args[1]}, ref={action.args[2]}, val={action.args[3]}"


# @pytest.mark.skip(reason="Deactivated")
def test_case_set_get(simpletable):
    """Test of the features provided by the Case class"""
    print(simpletable.base.list_cases())
    assert simpletable.base.list_cases()[1] == ["case1", ["caseX"]], "Error in list_cases"
    assert simpletable.base.special == {
        "stopTime": 1,
        "startTime": 0.0,
        "stepSize": 0.1,
    }, f"Base case special not as expected. Found {simpletable.base.special}"
    # iter()
    caseX = simpletable.case_by_name("caseX")
    assert caseX is not None, "CaseX does not seem to exist"
    assert [c.name for c in caseX.iter()] == ["base", "case1", "caseX"], "Hierarchy of caseX not as expected"
    check_value(caseX, "i", True)
    check_value(caseX, "stopTime", 10)
    print("caseX, act_set[0.0]:")
    for act in caseX.act_set[0.0]:
        print(str_act(act))
    assert caseX.special["stopTime"] == 10, f"Erroneous stopTime {caseX.special['stopTime']}"
    # print(f"ACT_SET: {caseX.act_set[0.0][0]}") #! set_initial, therefore no tuples!
    assert caseX.act_set[0.0][0].func.__name__ == "set_initial", "function name"
    assert caseX.act_set[0.0][0].args[0] == 0, "model instance"
    assert caseX.act_set[0.0][0].args[1] == 3, f"variable type {caseX.act_set[0.0][0].args[1]}"
    assert caseX.act_set[0.0][0].args[2] == 3, f"variable ref {caseX.act_set[0.0][0].args[2]}"
    assert caseX.act_set[0.0][0].args[3], f"variable value {caseX.act_set[0.0][0].args[3]}"
    # print(caseX.act_set[0.0][0])
    assert caseX.act_set[0.0][0].args[0] == 0, "model instance"
    assert caseX.act_set[0.0][0].args[1] == 3, f"variable type {caseX.act_set[0.0][0].args[1]}"
    assert caseX.act_set[0.0][0].args[2] == 3, f"variable ref {caseX.act_set[0.0][0].args[2]}"
    assert caseX.act_set[0.0][0].args[3] is True, f"variable value {caseX.act_set[0.0][0].args[3]}"
    # print(f"ACT_GET: {caseX.act_get}")
    assert caseX.act_get[1e9][0].args[0] == 0, "model instance"
    assert caseX.act_get[1e9][0].args[1] == 0, "variable type"
    assert caseX.act_get[1e9][0].args[2] == (0,), f"variable refs {caseX.act_get[1e9][0].args[2]}"
    # print( "PRINT", caseX.act_get[-1][0].args[2])
    assert caseX.act_get[-1][0].args[2] == (
        0,
        1,
        2,
    ), f"variable refs of step actions {caseX.act_get[-1][0]}"
    for t in caseX.act_get:
        for act in caseX.act_get[t]:
            print(str_act(act))
    # print("RESULTS", simpletable.run_case(simpletable.base, dump=True))


#    cases.base.plot_time_series( ['h'], 'TestPlot')


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Non-zero return code {retcode}"
    # import os
    # os.chdir(Path(__file__).parent.absolute() / "test_working_directory")
    # test_fixture(_simpletable())
    # test_case_at_time(_simpletable())
    # test_case_range(_simpletable())
    # test_case_set_get(_simpletable())
