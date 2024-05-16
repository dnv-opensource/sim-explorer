from pathlib import Path
from typing import Generator

from case_study.case import Cases, tuple2_iter
from case_study.simulator_interface import SimulatorInterface

# , SimulatorInterface, match_with_wildcard


def _file(file: str = "BouncingBall.cases"):
    path = Path(__file__).parent.joinpath(file)
    assert path.exists(), f"File {file} does not exist at {Path(__file__).parent}"
    return path


def test_tuple_iter():
    """Test of the features provided by the Case class"""

    def check(gen: Generator, expectation: list):
        lst = [x[0] for x in gen]
        assert lst == expectation, f"Expected: {expectation}. Found: {lst}"

    tpl20 = tuple(range(20))
    check(tuple2_iter(tpl20, tpl20, "3"), [3])
    check(tuple2_iter(tpl20, tpl20, "3:7"), [3, 4, 5, 6, 7])
    check(tuple2_iter(tpl20, tpl20, ":3"), list(range(0, 4)))
    check(tuple2_iter(tpl20, tpl20, "17:"), list(range(17, 20)))
    check(tuple2_iter(tpl20, tpl20, "10:-5"), list(range(10, 16)))
    check(tuple2_iter(tpl20, tpl20, ":"), list(range(20)))
    check(tuple2_iter(tpl20, tpl20, "1,3,4,9"), [1, 3, 4, 9])


def test_cases():
    """Test of the features provided by the Cases class"""
    sim = SimulatorInterface(_file("data/BouncingBall/OspSystemStructure.xml"))
    cases = Cases(_file("data/Bouncingball_0.cases"), sim)

    print(cases.info())
    # cases.spec
    assert cases.spec["name"] == "BouncingBall", "BouncingBall expected as cases name"
    msg = f"Description: {cases.spec['description']}"
    descr = cases.spec["description"]
    assert isinstance(descr, str) and descr.startswith("Simple Case Study with the"), msg
    assert cases.spec.get("modelFile", "") == "../data/BouncingBall/OspSystemStructure.xml", "modelFile not as expected"
    for c in ("base", "case1", "case2", "case3"):
        assert c in cases.spec, f"The case '{c}' is expected to be defined in {cases.spec['name']}"
    # find_by_name
    for c in cases.base.list_cases(as_name=False, flat=True):
        assert cases.case_by_name(c.name).name == c.name, f"Case {c.name} not found in hierarchy"
    assert cases.case_by_name("case99") is None, "Case99 was not expected to be found"
    case3 = cases.case_by_name("case3")
    assert case3 is not None and case3.name == "case3", "'case3' is expected to exist"
    msg = "'case2' should not exist within the sub-hierarchy of 'case3'"
    assert case3 is not None and case3.case_by_name("case2") is None, msg
    case1 = cases.case_by_name("case1")
    msg = "'case2' should exist within the sub-hierarchy of 'case1'"
    assert case1 is not None and case1.case_by_name("case2") is not None, msg
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


#    cases.base.plot_time_series( ['h'], 'TestPlot')


def run_tests(func):
    #     args = func.pytestmark[0].args[0]
    vals = func.pytestmark[0].args[1]
    for v in vals:
        func(*v)


if __name__ == "__main__":
    test_tuple_iter()
    test_cases()