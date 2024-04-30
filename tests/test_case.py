from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Callable

import pytest
from libcosimpy.CosimExecution import CosimExecution

from mvx.case_study.case import Case, Cases, SimulatorInterface, match_with_wildcard


def _file(file: str = "BouncingBall.cases"):
    path = Path(__file__).parent.joinpath(file)
    assert path.exists(), f"File {file} does not exist at {Path(__file__).parent}"
    return path


def test_match_with_wildcard():
    assert match_with_wildcard("Hello World", "Hello World"), "Match expected"
    assert not match_with_wildcard("Hello World", "Helo World"), "No match expected"
    assert match_with_wildcard("*o World", "Hello World"), "Match expected"
    assert not match_with_wildcard("*o W*ld", "Hello Word"), "No match expected"
    assert match_with_wildcard("*o W*ld", "Hello World"), "Two wildcard matches expected"


def test_tuple_iter():
    """Test of the features provided by the Case class"""

    def check(gen:Tuple[any], expectation:Tuple[any]):
        lst = [x[0] for x in gen]
        assert lst == expectation, f"Expected: {expectation}. Found: {lst}"

    tpl20 = tuple(range(20))
    check(Cases.tuple2_iter(tpl20, tpl20, "3"), [3])
    check(Cases.tuple2_iter(tpl20, tpl20, "3:7"), [3, 4, 5, 6, 7])
    check(Cases.tuple2_iter(tpl20, tpl20, ":3"), list(range(0, 4)))
    check(Cases.tuple2_iter(tpl20, tpl20, "17:"), list(range(17, 20)))
    check(Cases.tuple2_iter(tpl20, tpl20, "10:-5"), list(range(10, 16)))
    check(Cases.tuple2_iter(tpl20, tpl20, ":"), list(range(20)))
    check(Cases.tuple2_iter(tpl20, tpl20, "1,3,4,9"), [1, 3, 4, 9])


#     print( [ lst[i] for i in Case.tuple2_iter( tpl20, tpl20, ':-1')])


def test_pytype():
    assert SimulatorInterface.pytype("REAL", "2.3") == 2.3, "Expected 2.3 as float type"
    assert SimulatorInterface.pytype("Integer", "99") == 99, "Expected 99 as int type"
    assert SimulatorInterface.pytype("Boolean", "fmi2True"), "Expected True as bool type"
    assert not SimulatorInterface.pytype("Boolean", "fmi2false"), "Expected True as bool type"
    assert SimulatorInterface.pytype("String", "fmi2False") == "fmi2False", "Expected fmi2False as str type"
    with pytest.raises(ValueError) as err:
        SimulatorInterface.pytype("Real", "fmi2False")
    assert str(err.value).startswith("could not convert string to float:"), "No error raised as expected"
    assert SimulatorInterface.pytype(0, "") == float
    assert SimulatorInterface.pytype(1, "") == int
    assert SimulatorInterface.pytype(2, "") == str
    assert SimulatorInterface.pytype(3, "") == bool
    assert SimulatorInterface.pytype(1, 2.3) == 2


@pytest.mark.parameterize(
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


@pytest.mark.parameterize(
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


def test_simulator_from_system_structure():
    """SimulatorInterface from OspSystemStructure.xml"""
    systemfile = _file("../data/BouncingBall/OspSystemStructure.xml")
    system = SimulatorInterface(systemfile, name="BouncingBall")
    assert system.name == "BouncingBall", f"System.name should be BouncingBall. Found {system.name}"
    assert "bb" in system.components, f"Instance name 'bb' expected. Found instances {system.instances}"
    assert system.get_models()[0] == 0, f"Component model {system.get_models()[0]}"
    assert "bb" in system.get_components()


def test_simulator_instantiated():
    """Start with an instantiated simulator."""
    systemfile = _file("../data/BouncingBall/OspSystemStructure.xml")
    path = systemfile.parent
    sim = CosimExecution.from_osp_config_file(str(path))
    simulator = SimulatorInterface(
        system=systemfile,
        name="BouncingBall System",
        description="Testing info retrieval from simulator (without OspSystemStructure)",
        simulator=sim,
    )
    #    simulator.check_instances_variables()
    assert len(simulator.components) == 1, "Single instantiated component"
    assert simulator.components["bb"] == 0, f"... given a unique identifier {simulator.components['bb']}"
    variables = simulator.get_variables("bb")
    assert variables["g"] == {"reference": 5, "type": 0, "causality": 1, "variability": 1}
    assert simulator.get_variables(0) == simulator.get_variables("bb"), "Two ways of accessing variables"
    assert simulator.get_variables(0, "h"), {"h": {"reference": 1, "type": 0, "causality": 2, "variability": 4}}
    assert simulator.get_variables(0, 1), {"h": {"reference": 1, "type": 0, "causality": 2, "variability": 4}}


def test_cases():
    """Test of the features provided by the Cases class"""
    sim = SimulatorInterface(_file("../data/BouncingBall/OspSystemStructure.xml"))
    cases = Cases(_file("Bouncingball_0.cases"), sim)
    return

    print(cases.info())
    # cases.spec
    assert cases.spec["name"] == "BouncingBall", "BouncingBall expected as cases name"
    assert cases.spec["description"].startswith(
        "Simple Case Study with the"
    ), f"Description: {cases.spec['description']}"
    assert cases.spec["modelFile"] == "../data/BouncingBall/OspSystemStructure.xml", "modelFile not as expected"
    for c in ("base", "case1", "case2", "case3"):
        assert c in cases.spec, f"The case '{c}' is expected to be defined in {cases.spec['name']}"
    # find_by_name
    for c in cases.base.list_cases(as_name=False, flat=True):
        assert cases.case_by_name(c.name).name == c.name, f"Case {c.name} not found in hierarchy"
    assert cases.case_by_name("case99") is None, "Case99 was not expected to be found"
    case3 = cases.case_by_name("case3")
    assert case3.name == "case3", "'case3' is expected to exist"
    assert case3.case_by_name("case2") is None, "'case2' should not exist within the sub-hierarchy of 'case3'"
    case1 = cases.case_by_name("case1")
    assert case1.case_by_name("case2") is not None, "'case2' should exist within the sub-hierarchy of 'case1'"
    # variables (aliases)
    assert cases.variables["h"]["model"] == 0
    assert cases.variables["h"]["instances"] == ("bb",)
    assert cases.variables["h"]["variables"] == (1,)
    assert cases.variables["h"]["description"] == "Position (z) of the ball"
    assert cases.variables["h"]["type"] == 0
    assert cases.variables["h"]["causality"] == 2
    assert cases.variables["h"]["variability"] == 4
    vs = dict((k, v) for k, v in cases.variables.items() if k.startswith("v"))
    assert all(x in vs for x in ("v_min", "v_z", "v"))


def check_value(case: "Case", var: str, val: float):
    if var in case.spec:
        assert case.spec[var] == val, f"Wrong value {case.spec[var]} for variable {var}. Expected: {val}"
    else:  # not explicitly defined for this case. Shall be defined in the hierarchy!
        check_value(case.parent, var, val)


def test_case():
    """Test of the features provided by the Case class"""
    cases = Cases(
        _file("BouncingBall_0.cases"), SimulatorInterface(_file("../data/BouncingBall/OspSystemStructure.xml"))
    )
    assert cases.base.list_cases()[2] == ["case3"], "Error in list_cases"
    assert cases.base.special == {
        "stopTime": 3,
        "startTime": 0.0,
        "stepSize": 0.1,
    }, f"Base case special not as expected. Found {cases.base.special}"
    # iter()
    case2 = cases.case_by_name("case2")
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
    print("RESULTS", cases.run_case(cases.base, dump=True))


#    cases.base.plot_time_series( ['h'], 'TestPlot')


def run_tests(func):
    #     args = func.pytestmark[0].args[0]
    vals = func.pytestmark[0].args[1]
    for v in vals:
        func(*v)


if __name__ == "__main__":
    test_match_with_wildcard()
    test_tuple_iter()
    test_pytype()
    run_tests(test_case_at_time)
    run_tests(test_case_range)

    test_simulator_from_system_structure()
    test_simulator_instantiated()
    #    test_cases()
    test_case()
