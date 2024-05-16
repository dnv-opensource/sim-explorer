from pathlib import Path

import pytest
from case_study.case import Case, Cases
from case_study.simulator_interface import SimulatorInterface


def _file(file: str = "BouncingBall.cases"):
    path = Path(__file__).parent.joinpath(file)
    assert path.exists(), f"File {file} does not exist at {Path(__file__).parent}"
    return path


@pytest.mark.parametrize(
    "txt, case, value, expected",
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
def test_case_at_time(txt, case, value, expected):
    """Test the Case.disect_at_time function"""
    if isinstance(expected, str):  # error case
        with pytest.raises(AssertionError) as err:
            Case._disect_at_time(txt, case, value)
        assert str(err.value).startswith(expected)
    else:
        assert Case._disect_at_time(txt, case, value) == expected


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
def test_case_range(txt, case, value, expected):
    """Test the Case.disect_at_time function"""
    if isinstance(expected, str):  # error case
        with pytest.raises(AssertionError) as err:
            Case._disect_range(txt, case, value)
        assert str(err.value).startswith(expected)
    else:
        assert Case._disect_range(txt, case, value) == expected


def check_value(case: Case, var: str, val: float):
    assert isinstance(case.spec, dict), "dict expected as .spec. Found {case.spec}"
    if var in case.spec:
        assert case.spec[var] == val, f"Wrong value {case.spec[var]} for variable {var}. Expected: {val}"
    else:  # not explicitly defined for this case. Shall be defined in the hierarchy!
        assert case.parent is not None, "Parent case needed"
        check_value(case.parent, var, val)


def test_case_set_get():
    """Test of the features provided by the Case class"""
    cases = Cases(
        _file("data/BouncingBall_0.cases"), SimulatorInterface(_file("data/BouncingBall/OspSystemStructure.xml"))
    )
    assert cases.base.list_cases()[2] == ["case3"], "Error in list_cases"
    assert cases.base.special == {
        "stopTime": 3,
        "startTime": 0.0,
        "stepSize": 0.1,
    }, f"Base case special not as expected. Found {cases.base.special}"
    # iter()
    case2 = cases.case_by_name("case2")
    assert case2 is not None, "Case2 does not seem to exist"
    assert [c.name for c in case2.iter()] == ["base", "case1", "case2"], "Hierarchy of case2 not as expected"
    check_value(case2, "g", 1.5)
    check_value(case2, "e", 0.35)
    assert case2.act_set[0.0][0].func.__name__ == "set_initial", "function name"
    assert case2.act_set[0.0][0].args[0] == "bb", "model instance"
    assert case2.act_set[0.0][0].args[1] == 0, f"variable type {case2.act_set[0.0][0].args[1]}"
    assert case2.act_set[0.0][0].args[2] == (5,), f"variable ref {case2.act_set[0.0][0].args[2]}"
    assert case2.act_set[0.0][0].args[3] == (1.5,), f"variable value {case2.act_set[0.0][0].args[3]}"
    assert cases.results.act_get[1.0][0].func.__name__ == "get_variable_value", "get @time function"
    assert cases.results.act_get[1.0][0].args[0] == "bb", "model instance"
    assert cases.results.act_get[1.0][0].args[1] == 0, "variable type"
    assert cases.results.act_get[1.0][0].args[2] == (3,), "variable refs"
    assert cases.results.act_step[None][0].args[2] == (1,), "variable refs of act_step"
    assert cases.results.act_final[0].args[2] == (6,), "variable refs of act_final"
    # print("RESULTS", cases.run_case(cases.base, dump=True))


#    cases.base.plot_time_series( ['h'], 'TestPlot')


def run_tests(func):
    #     args = func.pytestmark[0].args[0]
    vals = func.pytestmark[0].args[1]
    for v in vals:
        func(*v)


if __name__ == "__main__":
    run_tests(test_case_at_time)
    run_tests(test_case_range)
    test_case_set_get()
