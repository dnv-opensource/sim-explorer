import xml.etree.ElementTree as ET  # noqa: N817
from pathlib import Path

import pytest
from case_study.case import Case, Cases
from case_study.json5 import json5_write
from case_study.simulator_interface import SimulatorInterface


@pytest.fixture
def simpletable(scope="module", autouse=True):
    path = Path(Path(__file__).parent, "data/SimpleTable/test.cases")
    assert path.exists(), "SimpleTable cases file not found"
    return Cases(path)


@pytest.mark.skip(reason="Causes an error when run with the other tests!")
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
        "description": "Simple Case Study for testing purposes",
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
        },
        "case1": {
            "description": "Interpolation ON",
            "spec": {
                "i": True,
            },
        },
        "caseX": {"description": "Based case1 longer simulation", "parent": "case1", "spec": {"stopTime": 10}},
        "results": {"spec": ["x@step", "x[0]@1.0", "i"]},
    }
    json5_write(json5, "data/test.cases")
    _ = SimulatorInterface("data/OspSystemStructure.xml", "testSystem")
    _ = Cases("data/test.cases")


@pytest.mark.skip(reason="Deactivated")
def test_case_at_time(simpletable):
    # print("DISECT", simpletable.case_by_name("base")._disect_at_time("x@step", ""))
    do_case_at_time("x@step", "results", "", ("x", "step", -1), simpletable)
    do_case_at_time("x@step 2.0", "base", "", ("x", "step", 2.0), simpletable)
    do_case_at_time("v@1.0", "base", "", ("v", "get", 1.0), simpletable)
    do_case_at_time("v@1.0", "caseX", "", ("v", "get", 1.0), simpletable)  # value retrieval per case at specified time
    do_case_at_time("@1.0", "base", "", "'@1.0' is not allowed as basis for _disect_at_time", simpletable)
    do_case_at_time("i", "results", "", ("i", "get", 1), simpletable)  # "report the value at end of sim!"
    do_case_at_time("i", "caseX", "", "Value required for 'set' in _disect_at_time(", simpletable)
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
        assert case._disect_at_time(txt, value) == expected


@pytest.mark.skip(reason="Deactivated")
def test_case_range(simpletable):
    do_case_range("x", "results", ("x", ""), simpletable)
    do_case_range("x[3]", "results", ("x", "3"), simpletable)
    # print("DISECT_RANGE", simpletable.case_by_name("caseX")._disect_range("x[3]", "4.0"))
    do_case_range("x[3]", "caseX", ("x", "3"), simpletable)
    do_case_range("x[1:3]", "results", ("x", "1:3"), simpletable)
    do_case_range("x[1,2,5]", "results", ("x", "1,2,5"), simpletable)
    do_case_range("x[1:3]", "caseX", ("x", "1:3"), simpletable)
    do_case_range("x", "caseX", ("x", ""), simpletable)  # assume all values


def do_case_range(txt: str, casename: str, expected: tuple | str, simpletable):
    """Test the ._disect_range function"""
    case = simpletable.case_by_name(casename)
    if isinstance(expected, str):  # error case
        with pytest.raises(AssertionError) as err:
            case._disect_range(txt)
        # assert str(err.value).startswith(expected)
        print(f"ERROR:{err.value}")
    else:
        assert case._disect_range(txt) == expected


def test_check_adapt_range(simpletable):
    do_check_adapt_range("caseX", "x", "", [1, 2, 3], ":", simpletable)
    do_check_adapt_range("caseX", "x", "Hi", [1, 2, 3], "RangeError:", simpletable)
    do_check_adapt_range("caseX", "x", "1,2,4", [1, 2, 3], "RangeError:", simpletable)
    do_check_adapt_range("caseX", "x", "1...3", [1, 2, 3], "RangeError:", simpletable)
    do_check_adapt_range("caseX", "x", "0...2", [1, 2, 3], "0:2", simpletable)


def do_check_adapt_range(casename: str, var: str, rng: str, value: str, expected: str, simpletable):
    """Test the ._check_adapt_range function"""
    case = simpletable.case_by_name(casename)
    var_info = simpletable.variables[var]
    if expected.startswith("RangeError:"):  # error case
        with pytest.raises(Exception) as err:
            case._check_adapt_range(var, var_info, rng, value)
        print(f"Full error message var={var}, rng={rng}, value={value}: {err.value}")
        assert str(err.value).startswith(expected)
    else:
        assert case._check_adapt_range(var, var_info, rng, value) == expected


def check_value(case: Case, var: str, val: float):
    assert isinstance(case.spec, dict), "dict expected as .spec. Found {case.spec}"
    if var in case.spec:
        assert case.spec[var] == val, f"Wrong value {case.spec[var]} for variable {var}. Expected: {val}"
    else:  # not explicitly defined for this case. Shall be defined in the hierarchy!
        assert case.parent is not None, "Parent case needed"
        check_value(case.parent, var, val)


def str_act(action) -> str:
    """Prepare a human readable view of the action"""
    print("TYPE", type(action))
    if len(action.args) == 3:
        return f"{action.func.__name__}(inst={action.args[0]}, type={action.args[1]}, ref={action.args[2]}"
    else:
        return f"{action.func.__name__}(inst={action.args[0]}, type={action.args[1]}, ref={action.args[2]}, val={action.args[3]}"


@pytest.mark.skip(reason="Deactivated")
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
    assert caseX.act_set[0.0][0].func.__name__ == "set_initial", "function name"
    # print(caseX.act_set[0.0][0])
    assert caseX.act_set[0.0][0].args[0] == 0, "model instance"
    assert caseX.act_set[0.0][0].args[1] == 3, f"variable type {caseX.act_set[0.0][0].args[1]}"
    assert caseX.act_set[0.0][0].args[2] == (3,), f"variable ref {caseX.act_set[0.0][0].args[2]}"
    assert caseX.act_set[0.0][0].args[3] == (True,), f"variable value {caseX.act_set[0.0][0].args[3]}"
    # print(f"ACT_GET: {caseX.act_get}")
    assert caseX.act_get[1e9][0].func.__name__ == "get_variable_value", "get @time function"
    assert caseX.act_get[1e9][0].args[0] == 0, "model instance"
    assert caseX.act_get[1e9][0].args[1] == 0, "variable type"
    assert caseX.act_get[1e9][0].args[2] == (0,), f"variable refs {caseX.act_get[1.0][0].args[2]}"
    assert caseX.act_get[-1][0].args[2] == (0,), f"variable refs of step actions {caseX.act_step[None][0]}"
    for t in caseX.act_get:
        for act in caseX.act_get[t]:
            print(str_act(act))
    # print("RESULTS", simpletable.run_case(simpletable.base, dump=True))


#    cases.base.plot_time_series( ['h'], 'TestPlot')


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Non-zero return code {retcode}"
