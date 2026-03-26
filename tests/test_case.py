# pyright: reportPrivateUsage=false

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from sim_explorer.case import Case, Cases
from sim_explorer.system_interface import SystemInterface
from sim_explorer.utils.json5 import json5_path, json5_write
from sim_explorer.utils.types import TValue


@pytest.fixture(scope="module", autouse=True)
def timetable():
    return _timetable()


def _timetable():
    path = Path(__file__).parent / "data" / "TimeTable" / "test.cases"
    assert path.exists(), "TimeTable cases file not found"
    return Cases(path)


def test_fixture(timetable: Cases):
    assert isinstance(timetable, Cases), f"Cases object expected. Found:{timetable}"


# TODO @EisDNV: This function is nowhere used in the code base. Maybe remove it? ClaasRostock, 2025-01-27
def _make_cases():
    """Make an example cases file for use in the tests"""

    root = ET.Element(
        "OspSystemStructure",
        attrib={
            "xmlns": "http://opensimulationplatform.com/MSMI/OSPSystemStructure",
            "version": "0.1",
        },
    )
    simulators = ET.Element("Simulators")
    simulators.append(
        ET.Element(
            "Simulator",
            attrib={
                "name": "tab",
                "source": "TimeTableFMU.fmu",
                "stepSize": "0.1",
            },
        )
    )
    root.append(simulators)
    tree = ET.ElementTree(element=root)
    ET.indent(tree, space="   ", level=0)
    tree.write("data/OspSystemStructure.xml", encoding="utf-8")

    js5 = {
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
        "caseX": {
            "description": "Based case1 longer simulation",
            "parent": "case1",
            "spec": {"stopTime": 10},
        },
    }
    json5_write(js5, "data/test.cases")
    _ = SystemInterface("data/OspSystemStructure.xml")
    _ = Cases("data/test.cases")


# @pytest.mark.skip(reason="Deactivated")
def test_case_at_time(timetable: Cases):
    # print("DISECT", timetable.case_by_name("base")._disect_at_time_spec("x@step", ""))
    do_case_at_time(txt="v@1.0", casename="base", value="res", expected=("v", "get", 1.0), timetable=timetable)
    # do_case_at_time(txt="x@step", casename="base", value="res", expected=("x", "step", -1), timetable=timetable)
    # do_case_at_time(
    #     txt="x@step 2.0", casename="base", value="res", expected=("x", "step", 2.0), timetable=timetable
    # )
    # do_case_at_time(txt="v@1.0", casename="base", value="res", expected=("v", "get", 1.0), timetable=timetable)
    # # value retrieval per case at specified time
    # do_case_at_time(txt="v@1.0", casename="caseX", value="res", expected=("v", "get", 1.0), timetable=timetable)
    # do_case_at_time(
    #     txt="@1.0",
    #     casename="base",
    #     value="result",
    #     expected="'@1.0' is not allowed as basis for _disect_at_time_spec",
    #     timetable=timetable,
    # )
    # # "report the value at end of sim"
    # do_case_at_time(txt="i", casename="base", value="res", expected=("i", "get", 1), timetable=timetable)
    # # "Initial value setting"
    # do_case_at_time(txt="y", casename="caseX", value=99.9, expected=("y", "set", 0), timetable=timetable)
    return


def do_case_at_time(
    txt: str,
    casename: str,
    value: TValue,
    expected: tuple[str, str, float],
    timetable: Cases,
):
    """Test the Case.disect_at_time function"""
    # print(f"TEST_AT_TIME {txt}, {casename}, {value}, {expected}")
    case = timetable.case_by_name(casename)
    assert case is not None, f"Case {casename} was not found"
    if isinstance(expected, str):  # error case
        with pytest.raises(AssertionError) as err:
            _ = case._disect_at_time_spec(txt, value)
        assert str(err.value).startswith(expected)
    else:
        disect_result = case._disect_at_time_spec(txt, value)
        assert disect_result == expected, f"Found {disect_result}"


# @pytest.mark.skip(reason="Deactivated")
def test_case_range(timetable: Cases):
    x_inf = timetable.variables["x"]
    # print("RNG", timetable.case_by_name("results").cases.disect_variable("x"))
    do_case_range(txt="x", casename="base", expected=("x", x_inf, list(range(3))), timetable=timetable)
    do_case_range(txt="x[2]", casename="base", expected=("x", x_inf, [2]), timetable=timetable)
    do_case_range(txt="x[2]", casename="caseX", expected=("x", x_inf, [2]), timetable=timetable)
    do_case_range(txt="x[1..2]", casename="base", expected=("x", x_inf, list(range(1, 2))), timetable=timetable)
    do_case_range(txt="x[0,1,2]", casename="base", expected=("x", x_inf, [0, 1, 2]), timetable=timetable)
    do_case_range(txt="x[0...2]", casename="caseX", expected=("x", x_inf, list(range(2))), timetable=timetable)
    do_case_range(
        txt="x", casename="caseX", expected=("x", x_inf, list(range(3))), timetable=timetable
    )  # assume all values
    do_case_range(txt="x[3]", casename="caseX", expected="Index 3 of variable x out of range", timetable=timetable)
    do_case_range(txt="x[1,2,4]", casename="caseX", expected="Index 4 of variable x out of range", timetable=timetable)
    do_case_range(txt="x[1.3]", casename="caseX", expected="Unhandled index", timetable=timetable)
    case_x = timetable.case_by_name("caseX")
    assert case_x is not None, "Case with name 'caseX' does not exist."
    with pytest.raises(ValueError) as err:
        _ = case_x.cases.disect_variable("x[99]")
    assert err.value.args[0] == "Index 99 of variable x out of range"
    assert case_x.cases.disect_variable("x[1]")[2] == [1]
    var_info = case_x.cases.disect_variable("i")[1]
    assert var_info is not None
    assert var_info["instances"] == ("tab",)


def do_case_range(
    txt: str,
    casename: str,
    expected: tuple[str, dict[str, Any] | None, list[int]] | str,
    timetable: Cases,
):
    """Test the .cases.disect_variable function"""
    case = timetable.case_by_name(casename)
    assert case is not None, f"Case {casename} was not found"
    if isinstance(expected, str):  # error case
        with pytest.raises(Exception) as err:  # noqa: PT011
            _ = case.cases.disect_variable(txt)
        # print(f"ERROR:{err.value}")
        assert str(err.value).startswith(expected), f"{err.value!s} does not start with {expected}"
    else:
        disect_result = case.cases.disect_variable(txt)
        assert disect_result == expected, f"Found {disect_result}"


def check_value(case: Case, var: str, val: TValue):
    found = json5_path(case.js_py, f"$.spec.{var}")
    if found is not None:
        assert found == val, f"Wrong value {found} for variable {var}. Expected: {val}"
    else:  # not explicitly defined for this case. Shall be defined in the hierarchy!
        assert case.parent is not None, f"Parent case needed for {case.name}"
        check_value(case=case.parent, var=var, val=val)


# @pytest.mark.skip(reason="Deactivated")
def test_case_set_get(timetable: Cases):
    """Test of the features provided by the Case class"""
    print(timetable.base.list_cases())
    assert timetable.base.list_cases()[1] == [
        "case1",
        ["caseX"],
    ], "Error in list_cases"
    assert timetable.base.special == {
        "stopTime": 1,
        "startTime": 0.0,
        "stepSize": 0.1,
    }, f"Base case special not as expected. Found {timetable.base.special}"
    # iter()
    caseX = timetable.case_by_name("caseX")
    assert caseX is not None, "CaseX does not seem to exist"
    assert [c.name for c in caseX.iter()] == [
        "base",
        "case1",
        "caseX",
    ], "Hierarchy of caseX not as expected"
    check_value(case=caseX, var="i", val=True)
    check_value(case=caseX, var="stopTime", val=10)
    assert caseX.act_set[0.0][0] == ("i", "tab", (0,), (1,)), f"Found {caseX.act_set[0.0][0]}"
    assert caseX.special["stopTime"] == 10, f"Erroneous stopTime {caseX.special['stopTime']}"
    assert list(caseX.act_get.keys()) == [-1, 0.0, 1000000000.0], "Get-action times"
    # print(f"ACT_GET: {caseX.act_get[-1][0]}")
    assert caseX.act_get[-1][0] == ("x", "tab", (1, 2, 3)), f"Found {caseX.act_get[-1][0]}"
    # print(f"ACT_GET: {caseX.act_get[1e9][0]}")
    assert caseX.act_get[1e9][0] == ("x", "tab", (1, 2, 3)), f"Found {caseX.act_get[1e9][0]}"
    assert caseX.act_get[-1][0] == ("x", "tab", (1, 2, 3)), f"Found {caseX.act_get[-1][0]}"
    assert caseX.act_get[0.0][0] == ("i", "tab", (0,))
    assert caseX.act_get[1000000000][0] == ("x", "tab", (1, 2, 3))


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Non-zero return code {retcode}"
    import os

    os.chdir(Path(__file__).parent.absolute() / "test_working_directory")
    # test_fixture(_timetable())
    # test_case_at_time(_timetable())
    # test_case_range(_timetable())
    # test_case_set_get(_timetable())
