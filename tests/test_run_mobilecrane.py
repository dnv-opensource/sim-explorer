from pathlib import Path

import pytest
from case_study.case import Cases
from case_study.json5 import Json5Reader
from case_study.simulator_interface import SimulatorInterface


@pytest.mark.skip("Basic reading of js5 cases  definition")
def test_read_cases():
    path = Path(Path(__file__).parent, "data/MobileCrane/MobileCrane.cases")
    assert path.exists(), "System structure file not found"
    json5 = Json5Reader(path)
    # print(f"COMMENTS: {json5.comments}")
    assert json5.comments[2263] == "#'90 deg/sec'"
    # for e in json5.js_py:
    #    print(f"{e}: {json5.js_py[e]}")
    assert json5.js_py["dynamic"]["spec"]["db_dt"] == 0.7854


@pytest.mark.skip("Alternative step-by step")
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
        "dynamic",
        "results",
    ]
    cases_names = [
        n for n in spec.keys() if n not in ("name", "description", "modelFile", "timeUnit", "variables", "results")
    ]
    assert cases_names == ["base", "static", "dynamic"], f"Found cases names {cases_names}"
    cases = Cases(path, sim)
    print("INFO", cases.info())
    static = cases.case_by_name("static")
    assert static.spec == {"p[2]": 1.5708, "b[1]": 0.7854, "r[0]": 7.657, "load": 1000}
    assert static.act_get[-1][0].args == (0, 0, (9, 10, 11)), f"Step action arguments {static.act_get[-1][0].args}"
    assert sim.get_variable_value(0, 0, (9, 10, 11)) == [0.0, 0.0, 0.0], "Initial value of T"
    assert static.act_set[0][0].args == (
        0,
        0,
        (13, 15),
        (3, 1.5708),
    ), f"SET actions argument: {static.act_set[0][0].args}"
    sim.set_initial(0, 0, (13, 15), (3, 0))
    # assert sim.get_variable_value(0, 0, (13, 15)) == [3.0, 0.0], "Initial value of T"
    print(f"Special: {static.special}")
    print("Actions SET")
    for t in static.act_set:
        print(f"   Time {t}: ")
        for a in static.act_set[t]:
            print("      ", static.str_act(a))
    print("Actions GET")
    for t in static.act_get:
        print(f"   Time {t}: ")
        for a in static.act_get[t]:
            print("      ", static.str_act(a))

    for t in range(1, 10):
        sim.simulator.simulate_until(t * 1e10)
        for a in static.act_get[-1]:
            print(f"Time {t/1e9}, {a.args}: {a()}")


@pytest.mark.skip("Alternative only using SimulatorInterface")
def test_run_basic():
    path = Path(Path(__file__).parent, "data/MobileCrane/OspSystemStructure.xml")
    assert path.exists(), "System structure file not found"
    sim = SimulatorInterface(path)
    sim.simulator.simulate_until(1e9)


# @pytest.mark.skip("Not yet")
def test_run_cases():
    path = Path(Path(__file__).parent, "data/MobileCrane/MobileCrane.cases")
    assert path.exists(), "MobileCrane cases file not found"
    cases = Cases(path, results_print_type="names")
    # for v, info in cases.variables.items():
    #     print(v, info)
    static = cases.case_by_name("static")
    for t, at in static.act_get.items():
        for a in at:
            print(t, static.str_act(a))
    print("Running case 'base'...")
    # res = cases.run_case("base", dump="results_base")
    print("Running case 'static'...")
    # res = cases.run_case("static", dump="results_static")
    print("Running case 'dynamic'...")
    res = cases.run_case("dynamic", dump="results_dynamic")
    assert len(res) > 0


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Return code {retcode}"
