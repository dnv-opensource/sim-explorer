from pathlib import Path

import pytest
from case_study.case import Cases
from case_study.json5 import Json5Reader
from case_study.simulator_interface import SimulatorInterface


@pytest.mark.skip("Not yet")
def test_run_casex():
    path = Path(Path(__file__).parent, "data/MobileCrane/MobileCrane.cases")
    assert path.exists(), "MobileCrane cases file not found"
    cases = Cases(path)
    print("RESULTS", cases.run_case("base", "results"))


# @pytest.mark.skip("Alternative step-by step")
def test_start_simulator():
    path = Path(Path(__file__).parent, "data/MobileCrane/OspSystemStructure.xml")
    assert path.exists(), "System structure file not found"
    sim = SimulatorInterface(path)
    assert sim.get_components() == {"mobileCrane": 0}, f"Found component {sim.get_components()}"
    assert sim.match_variables("mobileCrane", "craneAngularVelocity") == (0, 1, 2, 3)
    path = Path(Path(__file__).parent, "data/MobileCrane/MobileCrane.cases")
    assert path.exists(), "Cases file not found"
    spec = Json5Reader(path).js_py
    # print("SPEC", json5_write( spec, None, True))
    assert spec["results"] == {"spec": ["T@step", "x_load@step"]}, f"Results found: {spec['results']}"
    assert list(spec.keys()) == [
        "name",
        "description",
        "modelFile",
        "timeUnit",
        "variables",
        "base",
        "static",
        "results",
    ]
    cases_names = [
        n for n in spec.keys() if n not in ("name", "description", "modelFile", "timeUnit", "variables", "results")
    ]
    assert cases_names == ["base", "static"], f"Found cases names {cases_names}"
    cases = Cases(path, sim)
    print("INFO", cases.info())
    static = cases.case_by_name("static")
    assert static.spec == {"p[2]": "90 deg", "b[1]": "45 deg", "r[0]": 7.657, "load": 1000}
    assert static.act_get[-1][0].args == (0, 0, (9, 10, 11)), f"Step action arguments {static.act_get[-1][0].args}"
    assert sim.get_variable_value(0, 0, (9, 10, 11)) == [0.0, 0.0, 0.0], "Initial value of T"
    assert static.act_set[0][0].args == (0, 0, (13, 15), (3, 0)), f"SET actions argument: {static.act_set[0][0].args}"
    sim.set_initial(0, 0, (13, 15), (3, 0))
    assert sim.get_variable_value(0, 0, (13, 15)) == [3.0, 0.0], "Initial value of T"


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Return code {retcode}"
    # test_run_casex()
