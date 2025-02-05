from pathlib import Path

import pytest

from sim_explorer.case import Case, Cases


def test_cases_management():
    cases = Cases(Path(__file__).parent / "data" / "SimpleTable" / "test.cases")
    assert isinstance(cases.base.act_get, dict)
    assert len(cases.base.act_get) > 0

    assert cases.simulator.comp_model_var(0, 1) == ("tab", "SimpleTable", ["outs[1]"])
    assert cases.simulator.comp_model_var(0, 1) == ("tab", "SimpleTable", ["outs[1]"])
    assert cases.simulator.component_name_from_id(0) == "tab"


def test_cases():
    """Test of the features provided by the Cases class"""
    # sourcery skip: extract-duplicate-method

    cases = Cases(Path(__file__).parent / "data" / "BouncingBall0" / "BouncingBall.cases")

    c: str | list[str] | Case | list[Case]
    print(cases.info())
    # cases.spec
    assert (
        cases.js.jspath(path="$.header.name", typ=str, error_msg=True) == "BouncingBall"
    ), "BouncingBall expected as cases name"
    descr = cases.js.jspath(path="$.header.description", typ=str, error_msg=True)
    assert isinstance(descr, str), f"Error description: {descr}"
    assert descr.startswith("Simple sim explorer with the"), f"Error description: {descr}"
    assert (
        cases.js.jspath(path="$.header.modelFile", typ=str, error_msg=True) == "OspSystemStructure.xml"
    ), "modelFile not as expected"
    for c in ("base", "restitution", "restitutionAndGravity", "gravity"):
        assert c in cases.js.js_py, f"The case '{c}' is expected to be defined in {list(cases.js.js_py.keys())}"
    assert cases.js.jspath("$.header.variables.g[0]") == "bb"
    assert cases.js.jspath("$.header.variables.g[1]") == "g", f"Found {cases.js.jspath('$.variables.g[1]')}"
    assert cases.js.jspath("$.header.variables.g[2]") == "Gravity acting on the ball"
    # find_by_name
    for c in cases.base.list_cases(as_name=False, flat=True):
        assert isinstance(c, Case)
        case_by_name = cases.case_by_name(c.name)
        assert case_by_name is not None
        assert case_by_name.name == c.name, f"Case {c.name} not found in hierarchy"
    assert cases.case_by_name("case99") is None, "Case99 was not expected to be found"
    c_gravity = cases.case_by_name("gravity")
    assert c_gravity is not None, "'gravity' is expected to exist"
    assert c_gravity.name == "gravity", "'gravity' is expected to exist"
    msg = "'restitution' should not exist within the sub-hierarchy of 'gravity'"
    assert c_gravity is not None, msg
    assert c_gravity.case_by_name("restitution") is None, msg
    c_r = cases.case_by_name("restitution")
    msg = "'restitutionAndGravity' should exist within the sub-hierarchy of 'restitution'"
    assert c_r is not None, msg
    assert c_r.case_by_name("restitutionAndGravity") is not None, msg
    gravity_case = cases.case_by_name("gravity")
    assert gravity_case is not None, "'gravity' is expected to exist"
    assert gravity_case.name == "gravity", "'gravity' is expected to exist"
    msg = "'case2' should not exist within the sub-hierarchy of 'gravity'"
    assert gravity_case is not None, msg
    assert gravity_case.case_by_name("case2") is None, msg
    restitution_case = cases.case_by_name("restitution")
    msg = "'restitutionAndGravity' should exist within the sub-hierarchy of 'restitution_case'"
    assert restitution_case is not None, msg
    assert restitution_case.case_by_name("restitutionAndGravity") is not None, msg
    # variables (aliases)
    assert cases.variables["h"]["instances"] == ("bb",)
    assert cases.variables["h"]["refs"] == (1,)
    assert cases.variables["h"]["description"] == "Position (z) of the ball"
    assert cases.variables["h"]["type"] is float
    assert cases.variables["h"]["causality"] == "output", f"Found {cases.variables['h']['causality']}"
    assert cases.variables["h"]["variability"] == "continuous", f"Found {cases.variables['h']['variability']}"
    vs = {k: v for k, v in cases.variables.items() if k.startswith("v")}
    assert all(x in vs for x in ("v_min", "v_z", "v"))


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Non-zero return code {retcode}"
    # test_cases_management()
    # test_cases()
