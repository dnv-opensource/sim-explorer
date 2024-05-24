import xml.etree.ElementTree as ET  # noqa: N817
from pathlib import Path

import pytest
from case_study.case import Case, Cases
from case_study.json5 import json5_write
from case_study.simulator_interface import SimulatorInterface

global cases


def _file(file: str = "BouncingBall.cases"):
    path = Path(__file__).parent.joinpath(file)
    assert path.exists(), f"File {file} does not exist at {Path(__file__).parent}"
    return path


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
    global cases
    cases = Cases("data/test.cases")


@pytest.mark.parametrize(
    "txt, casename, value, expected",
    [
        ("x@step", "results", "", ("x", "step", None)),
        ("x@step 2.0", "results", "", ("x", "step", 2.0)),
        ("v@1.0", "results", "", ("v", "get", 1.0)),
        ("v@1.0", "CaseX", "", ("v", "get", 1.0)),  # value retrieval per case at specified time
        ("@1.0", "results", "", "'@1.0' is not allowed as basis for _disect_at_time"),
        ("y", "results", "", ("y", "final", None)),  # "report the value at end of sim!"
        ("y", "CaseX", "", "Value required for 'set' in _disect_at_time("),
        ("y", "CaseX", 99.9, ("y", "set", 0)),  # "Initial value setting!"
    ],
)
def test_case_at_time(txt, casename, value, expected):
    """Test the Case.disect_at_time function"""
    global cases
    case = cases.case_by_name(casename)
    print(f"TEST_AT_TIME {txt}, {case}, {value}, {expected}")
    if isinstance(expected, str):  # error case
        with pytest.raises(AssertionError) as err:
            case._disect_at_time(txt, value)
        assert str(err.value).startswith(expected)
    else:
        assert case._disect_at_time(txt, value) == expected


@pytest.mark.parametrize(
    "txt, case, value, expected",
    [
        ("x", "results", "", ("x", "")),
        ("x[3]", "results", "", ("x", "3")),
        ("x[1:3]", "results", "", ("x", "1:3")),
        ("x[1,2,5]", "results", "", ("x", "1,2,5")),
        ("x[1:3]", "CaseX", "", "More than one value required to handle multi-valued setting"),
        ("x[1:3]", "CaseX", [1, 2, 3], ("x", "1:3")),
        ("x", "CaseX", [1, 2, 3], ("x", ":")),  # assume all values
    ],
)
def test_case_range(txt, casename, value, expected):
    """Test the Case.disect_at_time function"""
    global cases
    case = cases.case_by_name(casename)
    if isinstance(expected, str):  # error case
        with pytest.raises(AssertionError) as err:
            case._disect_range(txt, value)
        assert str(err.value).startswith(expected)
    else:
        assert case._disect_range(txt, value) == expected


def check_value(case: Case, var: str, val: float):
    assert isinstance(case.spec, dict), "dict expected as .spec. Found {case.spec}"
    if var in case.spec:
        assert case.spec[var] == val, f"Wrong value {case.spec[var]} for variable {var}. Expected: {val}"
    else:  # not explicitly defined for this case. Shall be defined in the hierarchy!
        assert case.parent is not None, "Parent case needed"
        check_value(case.parent, var, val)


def str_act(action: list):
    """Prepare a human readable view of the action"""
    return f"{action.func.__name__}(inst={action.args[0]}, type={action.args[1]}, ref={action.args[2]}, val={action.args[3]}"


def test_case_set_get():
    """Test of the features provided by the Case class"""
    global cases
    print(cases.base.list_cases())
    assert cases.base.list_cases()[1] == ["case1", ["caseX"]], "Error in list_cases"
    assert cases.base.special == {
        "stopTime": 1,
        "startTime": 0.0,
        "stepSize": 0.1,
    }, f"Base case special not as expected. Found {cases.base.special}"
    # iter()
    caseX = cases.case_by_name("caseX")
    assert caseX is not None, "CaseX does not seem to exist"
    assert [c.name for c in caseX.iter()] == ["base", "case1", "caseX"], "Hierarchy of caseX not as expected"
    check_value(caseX, "i", True)
    check_value(caseX, "stopTime", 10)
    print("caseX, act_set[0.0]:")
    for act in caseX.act_set[0.0]:
        print(str_act(act))
    assert caseX.special["stopTime"] == 10, f"Erroneous stopTime {caseX.special['stopTime']}"
    assert caseX.act_set[0.0][0].func.__name__ == "set_initial", "function name"
    print(caseX.act_set[0.0][0])
    assert caseX.act_set[0.0][0].args[0] == 0, "model instance"
    assert caseX.act_set[0.0][0].args[1] == 3, f"variable type {caseX.act_set[0.0][0].args[1]}"
    assert caseX.act_set[0.0][0].args[2] == (3,), f"variable ref {caseX.act_set[0.0][0].args[2]}"
    assert caseX.act_set[0.0][0].args[3] == (True,), f"variable value {caseX.act_set[0.0][0].args[3]}"
    assert caseX.act_get[1.0][0].func.__name__ == "get_variable_value", "get @time function"
    assert caseX.act_get[1.0][0].args[0] == 0, "model instance"
    assert caseX.act_get[1.0][0].args[1] == 0, "variable type"
    assert caseX.act_get[1.0][0].args[2] == (0,), f"variable refs {caseX.act_get[1.0][0].args[2]}"
    assert caseX.act_step[None][0].args[2] == (0,), f"variable refs of act_step {caseX.act_step[None][0]}"
    for t in caseX.act_get:
        for act in caseX.act_get[t]:
            print(str_act(act))
    #    print( caseX
    assert caseX.act_get[10.0][0].args[2] == (3,), "variable refs of act_get[stopTime]"
    # print("RESULTS", cases.run_case(cases.base, dump=True))


#    cases.base.plot_time_series( ['h'], 'TestPlot')


def run_tests(func):
    #     args = func.pytestmark[0].args[0]
    _ = _make_cases()
    vals = func.pytestmark[0].args[1]
    for v in vals:
        func(*v)


if __name__ == "__main__":
    _make_cases()
    print("CASES", cases)
    #    run_tests(test_case_at_time)
    #     run_tests(test_case_range)
    test_case_set_get()
