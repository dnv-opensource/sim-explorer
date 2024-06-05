from pathlib import Path

import numpy as np
from case_study.case import Case, Cases
from case_study.simulator_interface import SimulatorInterface


def expected_actions(case: Case, act: dict, expect: dict):
    """Check whether a given action dict 'act' conforms to expectations 'expect',
    where expectations are specified in human-readable form:
    ('get/set', instance_name, type, (var_names,)[, (var_values,)])
    """
    sim = case.cases.simulator  # the simulatorInterface
    for time, actions in act.items():
        assert time in expect, f"time entry {time} not found in expected dict"
        a_expect = expect[time]
        for i, action in enumerate(actions):
            msg = f"Case {case.name}({time})[{i}]"  # , expect: {a_expect[i]}")
            aname = {"set_initial": "set", "set_variable_value": "set", "get_variable_value": "get"}[
                action.func.__name__
            ]
            assert aname == a_expect[i][0], f"{msg}. Erroneous action type {aname}"
            arg = [
                sim.component_name_from_idx(action.args[0]),
                SimulatorInterface.pytype(action.args[1]),
                tuple(sim.variable_name_from_ref(action.args[0], ref) for ref in action.args[2]),
            ]
            for k in range(1, len(action.args)):
                if k == 3:
                    assert len(a_expect[i]) == 5, f"{msg}. Need also a value argument in expect:{expect}"
                    assert tuple(action.args[3]) == a_expect[i][4], f"{msg}. Erroneous value argument {action.args[3]}."
                else:
                    assert (
                        arg[k] == a_expect[i][k + 1]
                    ), f"{msg}. Erroneous argument {k}: {arg[k]}. Expect: {a_expect[i]}"


def test_step_by_step():
    """Do the simulation step-by step, only using libcosimpy"""
    path = Path(Path(__file__).parent, "data/BouncingBall0/OspSystemStructure.xml")
    assert path.exists(), "System structure file not found"
    sim = SimulatorInterface(path)
    assert sim.simulator.real_initial_value(0, 6, 0.35), "Setting of 'e' did not work"
    for t in np.linspace(1, 1e9, 100):
        sim.simulator.simulate_until(t)
        print(sim.observer.last_real_values(0, [0, 1, 6]))
        if t == int(0.11 * 1e9):
            assert sim.observer.last_real_values(0, [0, 1, 6]) == [0.11, 0.9411890500000001, 0.35]


def test_step_by_step_interface():
    """Do the simulation step by step, using the simulatorInterface"""
    path = Path(Path(__file__).parent, "data/BouncingBall0/OspSystemStructure.xml")
    assert path.exists(), "System structure file not found"
    sim = SimulatorInterface(path)
    assert sim.components["bb"] == 0
    print(f"Variables: {sim.get_variables( 0, as_numbers = False)}")
    assert sim.get_variables(0)["e"] == {"reference": 6, "type": 0, "causality": 1, "variability": 2}
    sim.set_initial(0, 0, (6,), (0.35,))
    for t in np.linspace(1, 1e9, 1):
        sim.simulator.simulate_until(t)
        print(sim.get_variable_value(0, 0, (0, 1, 6)))
        if t == int(0.11 * 1e9):
            assert sim.get_variable_value(0, 0, (0, 1, 6)) == [0.11, 0.9411890500000001, 0.35]


def test_run_case1():
    path = Path(Path(__file__).parent, "data/BouncingBall0/BouncingBall.cases")
    assert path.exists(), "BouncingBall cases file not found"
    cases = Cases(path)
    base = cases.case_by_name("base")
    case1 = cases.case_by_name("case1")
    case2 = cases.case_by_name("case2")
    case3 = cases.case_by_name("case3")
    expected_actions(
        case3,
        case3.act_get,
        {
            -1: [
                ("get", "bb", float, ("h",)),
            ],
            1e9: [
                ("get", "bb", float, ("v",)),
            ],
            3e9: [("get", "bb", float, ("e",)), ("get", "bb", float, ("g",))],
        },
    )
    expected_actions(
        base, base.act_set, {0: [("set", "bb", float, ("g",), (-9.81,)), ("set", "bb", float, ("e",), (0.71,))]}
    )
    print("CASE1", case1.act_set)
    expected_actions(
        case1, case1.act_set, {0: [("set", "bb", float, ("g",), (-9.81,)), ("set", "bb", float, ("e",), (0.35,))]}
    )
    expected_actions(
        case2, case2.act_set, {0: [("set", "bb", float, ("g",), (-1.5,)), ("set", "bb", float, ("e",), (0.35,))]}
    )
    expected_actions(
        case3, case3.act_set, {0: [("set", "bb", float, ("g",), (-9.81,)), ("set", "bb", float, ("e",), (1.4,))]}
    )
    print("Actions checked")
    print("RESULTS", cases.run_case("base", "results"))


if __name__ == "__main__":
    #    test_step_by_step()
    #    test_step_by_step_interface()
    test_run_case1()
