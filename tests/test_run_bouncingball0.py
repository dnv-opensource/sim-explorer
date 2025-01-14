from math import sqrt
from pathlib import Path

import numpy as np
import pytest

from sim_explorer.case import Case, Cases
from sim_explorer.json5 import Json5
from sim_explorer.system_interface_osp import SystemInterfaceOSP


def expect_bounce_at(results: Json5, time: float, eps=0.02):
    previous = None
    falling = True
    for t in results.js_py:
        try:
            _t = float(t)
            if previous is not None:
                print(results.jspath(f"$.['{t}'].bb.h"), previous[0])
                falling = results.jspath(f"$.['{t}'].bb.h") < previous[0]
                # if falling != previous[1]:
                #     print(f"EXPECT_bounce @{_t}: {previous[1]} -> {falling}")
                if abs(_t - time) <= eps:  # within intervall where bounce is expected
                    print(_t, previous, falling)
                    if previous[1] != falling:
                        return True
                elif _t + eps > time:  # give up
                    print("Give up")
                    return False
            previous = (results.jspath(f"$.['{t}'].bb.h"), falling)
            assert previous is not None, f"No data 'bb.h' found for time {t}"
        except ValueError:
            pass
    print("Time not found")
    return False


def test_step_by_step():
    """Do the simulation step-by step, only using libcosimpy"""
    path = Path(Path(__file__).parent, "data/BouncingBall0/OspSystemStructure.xml")
    assert path.exists(), "System structure file not found"
    sim = SystemInterfaceOSP(path)
    sim.init_simulator()
    assert sim.simulator.real_initial_value(0, 6, 0.35), "Setting of 'e' did not work"
    for t in np.linspace(1, 1e9, 100):
        sim.simulator.simulate_until(t)
        print(sim.observer.last_real_values(0, [0, 1, 6]))
        if t == int(0.11 * 1e9):
            assert sim.observer.last_real_values(0, [0, 1, 6]) == [
                0.11,
                0.9411890500000001,
                0.35,
            ]


def test_step_by_step_interface():
    """Do the simulation step by step, using the simulatorInterface"""
    path = Path(Path(__file__).parent, "data/BouncingBall0/OspSystemStructure.xml")
    assert path.exists(), "System structure file not found"
    sim = SystemInterfaceOSP(path)
    # Commented out as order of variables and models are not guaranteed in different OS
    # assert sim.components["bb"] == 0
    # print(f"Variables: {sim.get_variables( 0, as_numbers = False)}")
    # assert sim.get_variables(0)["e"] == {"reference": 6, "type": 0, "causality": 1, "variability": 2}
    sim.init_simulator()
    sim.manipulator.slave_real_values(0, (6,), (0.35,))
    for t in np.linspace(1, 1e9, 1):
        sim.simulator.simulate_until(t)
        assert sim.observer.last_real_values(0, (0, 1, 6)) == [0.01, 0.99955855, 0.35]
        if t == int(0.11 * 1e9):
            assert sim.observer.last_real_values(0, (0, 1, 6)) == [0.11, 0.9411890500000001, 0.35]


def test_run_cases():
    path = Path(Path(__file__).parent, "data/BouncingBall0/BouncingBall.cases")
    assert path.exists(), "BouncingBall cases file not found"
    cases = Cases(path)
    case: Case | None
    base = cases.case_by_name("base")
    restitution = cases.case_by_name("restitution")
    restitutionAndGravity = cases.case_by_name("restitutionAndGravity")
    gravity = cases.case_by_name("gravity")
    assert gravity
    assert gravity.act_get == {-1: [("h", "bb", (1,))], 1e9: [("v", "bb", (3,))]}
    assert base
    assert base.act_set == {0: [("g", "bb", (5,), (-9.81,)), ("e", "bb", (6,), (1.0,)), ("h", "bb", (1,), (1.0,))]}
    assert restitution
    print("ACTIONS", restitution.act_set)
    assert restitution.act_set == {
        0: [("g", "bb", (5,), (-9.81,)), ("e", "bb", (6,), (0.5,)), ("h", "bb", (1,), (1.0,))]
    }
    assert restitutionAndGravity
    assert restitutionAndGravity.act_set == {
        0: [("g", "bb", (5,), (-1.5,)), ("e", "bb", (6,), (0.5,)), ("h", "bb", (1,), (1.0,))]
    }
    assert gravity.act_set == {0: [("g", "bb", (5,), (-1.5,)), ("e", "bb", (6,), (1.0,)), ("h", "bb", (1,), (1.0,))]}
    print("Actions checked")
    case = cases.case_by_name("base")
    assert case is not None, "Case 'base' not found"
    print(f"Run {case.name}")
    assert case.special == {"startTime": 0.0, "stopTime": 3, "stepSize": 0.01}
    case.run("base")
    _case = cases.case_by_name("base")
    assert _case is not None
    res = _case.res.res
    """
        Cannot be tested in CI as order of variables and models are not guaranteed in different OSs
        inspect = cases.case_by_name("base").res.inspect()
        assert inspect["bb.h"] == {
        "len": 301,
        "range": [0.0, 3.0],
        "info": {
            "model": 0,
            "instances": ("bb",),
            "variables": (1,),
            "description": "Position (z) of the ball",
            "type": 0,
            "causality": 2,
            "variability": 4,
        },
    }
    """
    # key results data for base case
    h0 = res.jspath("$.['0'].bb.h")
    t0 = sqrt(2 * h0 / 9.81)  # half-period time with full restitution
    v_max = sqrt(2 * h0 * 9.81)  # speed when hitting bottom
    # h_v = lambda v, g: 0.5 * v**2 / g  # calculate height
    assert abs(h0 - 1.0) < 1e-2
    assert expect_bounce_at(results=res, time=t0, eps=0.02), f"Bounce: {t0} != {sqrt(2*h0/9.81)}"
    assert expect_bounce_at(results=res, time=2 * t0, eps=0.02), f"No top point at {2*sqrt(2*h0/9.81)}"

    cases.simulator.init_simulator()
    print("Run restitution")
    cases.run_case(name="restitution", dump="results_restitution")
    _case = cases.case_by_name("restitution")
    assert _case is not None
    res = _case.res.res
    assert expect_bounce_at(results=res, time=sqrt(2 * h0 / 9.81), eps=0.02), f"No bounce at {sqrt(2*h0/9.81)}"
    assert expect_bounce_at(
        res, sqrt(2 * h0 / 9.81) + 0.5 * v_max / 9.81, eps=0.02
    )  # restitution is a factor on speed at bounce
    cases.simulator.init_simulator()
    print("Run gravity", cases.run_case("gravity", "results_gravity"))
    assert expect_bounce_at(res, sqrt(2 * h0 / 1.5), eps=0.02), f"No bounce at {sqrt(2*h0/9.81)}"
    cases.simulator.init_simulator()
    print(
        "Run restitutionAndGravity",
        cases.run_case("restitutionAndGravity", "results_restitutionAndGravity"),
    )
    assert expect_bounce_at(res, sqrt(2 * h0 / 1.5), eps=0.02), f"No bounce at {sqrt(2*h0/9.81)}"
    assert expect_bounce_at(res, sqrt(2 * h0 / 1.5) + 0.5 * sqrt(2 * h0 / 1.5), eps=0.4)
    cases.simulator.init_simulator()


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Non-zero return code {retcode}"
    # test_run_cases()
    # test_step_by_step()
    # test_step_by_step_interface()
