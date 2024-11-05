from math import sqrt
from pathlib import Path

import pytest
from libcosimpy.CosimEnums import CosimExecutionState
from libcosimpy.CosimExecution import CosimExecution
from libcosimpy.CosimManipulator import CosimManipulator
from libcosimpy.CosimObserver import CosimObserver
from libcosimpy.CosimSlave import CosimLocalSlave
from sim_explorer.case import Cases
from sim_explorer.json5 import Json5
from sim_explorer.simulator_interface import SimulatorInterface


def is_nearly_equal(x: float | list, expected: float | list, eps: float = 1e-10) -> int:
    if isinstance(x, float):
        if abs(x - expected) < eps:
            return True
        else:
            raise AssertionError(f"{x} is not nealry equal to {expected}") from None
    else:
        for i, y in enumerate(x):
            if not abs(y - expected[i]) < eps:
                raise AssertionError(f"{x}[{i}] is not as expected: {expected}")
                return False
        return True


# @pytest.mark.skip("Basic reading of js5 cases  definition")
def test_read_cases():
    path = Path(Path(__file__).parent, "data/MobileCrane/MobileCrane.cases")
    assert path.exists(), "System structure file not found"
    json5 = Json5(path)
    assert "# lift 1m / 0.1sec" in list(json5.comments.values())
    # for e in json5.js_py:
    #   print(f"{e}: {json5.js_py[e]}")
    assert json5.jspath("$.base.spec.df_dt", list) == [0.0, 0.0]
    # json5_write( json5.js_py, "MobileCrane.js5")
    assert json5.jspath("$.dynamic.spec.db_dt", float) == 0.785498


# @pytest.mark.skip("Alternative step-by step, only using libcosimpy")
def test_step_by_step_cosim():
    def set_var(name: str, value: float, slave: int = 0):
        for idx in range(sim.num_slave_variables(slave)):
            if sim.slave_variables(slave)[idx].name.decode() == name:
                return manipulator.slave_real_values(slave, [idx], [value])

    def set_initial(name: str, value: float, slave: int = 0):
        for idx in range(sim.num_slave_variables(slave)):
            if sim.slave_variables(slave)[idx].name.decode() == name:
                return sim.real_initial_value(slave, idx, value)

    sim = CosimExecution.from_step_size(0.1 * 1.0e9)
    fmu = Path(Path(__file__).parent, "data/MobileCrane/MobileCrane.fmu").resolve()
    assert fmu.exists(), f"FMU {fmu} not found"
    local_slave = CosimLocalSlave(fmu_path=f"{fmu}", instance_name="mobileCrane")
    sim.add_local_slave(local_slave=local_slave)
    manipulator = CosimManipulator.create_override()
    assert sim.add_manipulator(manipulator=manipulator)
    observer = CosimObserver.create_last_value()
    sim.add_observer(observer=observer)

    slave = sim.slave_index_from_instance_name("mobileCrane")
    assert slave == 0, f"Slave index should be '0', found {slave}"

    expected_names = ("boom_angularVelocity[0]", "pedestal_boom[0]", "boom_boom[1]", "rope_boom[2]")
    found_expected = [False] * len(expected_names)
    for i in range(len(sim.slave_variables(slave))):
        for k, name in enumerate(expected_names):
            if sim.slave_variables(slave)[i].name.decode() == name:
                assert sim.slave_variables(slave)[i].reference == i
                assert sim.slave_variables(slave)[i].type == 0
                found_expected[k] = True
    assert (
        False not in found_expected
    ), f"Not all expected names were found: {expected_names[found_expected.index(False)]}"
    assert set_initial("pedestal_boom[0]", 3.0)
    assert set_initial("boom_boom[0]", 8.0)
    assert set_initial("boom_boom[1]", 0.7854)
    assert set_initial("rope_boom[0]", 1e-6)
    #    for idx in range( sim.num_slave_variables(slave)):
    #        print(f"{sim.slave_variables(slave)[idx].name.decode()}: {observer.last_real_values(slave, [idx])}")
    step_count = 0
    while True:
        step_count += 1
        status = sim.status()
        print(f"STATUS:{status}, {status.state}={CosimExecutionState.ERROR}")
        if status.current_time > 1e9:
            break
        if status.state == CosimExecutionState.ERROR.value:
            raise AssertionError(f"Error state at time {status.current_time}") from None
        if step_count > 10:
            break
        elif step_count == 9:
            manipulator.slave_real_values(slave, [34], [0.1])
        # sim.step()  #
        sim.simulate_until(step_count * 1e9)


# @pytest.mark.skip("Alternative step-by step, using SimulatorInterface and Cases")
def test_step_by_step_cases():
    def get_ref(name: str):
        variable = cases.simulator.get_variables(0, name)
        assert len(variable), f"Variable {name} not found"
        return next(iter(variable.values()))["reference"]

    def set_initial(name: str, value: float, slave: int = 0):
        for idx in range(sim.num_slave_variables(slave)):
            if sim.slave_variables(slave)[idx].name.decode() == name:
                return sim.real_initial_value(slave, idx, value)

    def initial_settings():
        cases.simulator.set_initial(0, 0, get_ref("pedestal_boom[0]"), 3.0)
        cases.simulator.set_initial(0, 0, get_ref("boom_boom[0]"), 8.0)
        cases.simulator.set_initial(0, 0, get_ref("boom_boom[1]"), 0.7854)
        cases.simulator.set_initial(0, 0, get_ref("rope_boom[0]"), 1e-6)
        cases.simulator.set_initial(0, 0, get_ref("dLoad"), 50.0)

    system = Path(Path(__file__).parent, "data/MobileCrane/OspSystemStructure.xml")
    assert system.exists(), f"OspSystemStructure file {system} not found"
    sim = SimulatorInterface(system)
    assert sim.get_components() == {"mobileCrane": 0}, f"Found component {sim.get_components()}"

    path = Path(Path(__file__).parent, "data/MobileCrane/MobileCrane.cases")
    assert path.exists(), "Cases file not found"
    js = Json5(path)
    print("CASES", js.write(None, True))
    expected_results = ["T@step", "x_pedestal@step", "x_boom@step", "x_load@step"]
    assert js.jspath("$.base.results") == expected_results, f"Results found: {js.jspath('$.base.results')}"
    assert list(js.js_py.keys()) == [
        "header",
        "base",
        "static",
        "dynamic",
    ]
    assert list(js.jspath("$.header", dict).keys()) == ["name", "description", "modelFile", "timeUnit", "variables"]
    cases = Cases(path, sim)
    print("INFO", cases.info())
    static = cases.case_by_name("static")
    assert static.js.jspath("$.spec", dict) == {"p[2]": 1.570796, "b[1]": 0.785398, "r[0]": 7.657, "load": 1000}
    assert static.act_get[-1][0].args == (0, 0, (10, 11, 12)), f"Step action arguments {static.act_get[-1][0].args}"
    assert sim.get_variable_value(0, 0, (10, 11, 12)) == [0.0, 0.0, 0.0], "Initial value of T"
    # msg = f"SET actions argument: {static.act_set[0][0].args}"
    # assert static.act_set[0][0].args == (0, 0, (13, 15), (3, 1.5708)), msg
    # sim.set_initial(0, 0, (13, 15), (3, 0))
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
    sim = cases.simulator.simulator
    slave = sim.slave_index_from_instance_name("mobileCrane")
    assert slave == 0, f"Slave index should be '0', found {slave}"

    expected_names = ("boom_angularVelocity[0]", "pedestal_boom[0]", "boom_boom[1]", "rope_boom[2]", "dLoad")
    found_expected = [-1] * len(expected_names)
    for i in range(len(sim.slave_variables(slave))):
        for k, name in enumerate(expected_names):
            if sim.slave_variables(slave)[i].name.decode() == name:
                assert sim.slave_variables(slave)[i].reference == i
                assert sim.slave_variables(slave)[i].type == 0
                found_expected[k] = True
    assert -1 not in found_expected, f"Not all expected names were found: {expected_names[found_expected.index(-1)]}"
    i_bav = found_expected[0]

    #    for idx in range( sim.num_slave_variables(slave)):
    #        print(f"{sim.slave_variables(slave)[idx].name.decode()}: {observer.last_real_values(slave, [idx])}")
    initial_settings()
    manipulator = cases.simulator.manipulator
    assert isinstance(manipulator, CosimManipulator)
    observer = cases.simulator.observer
    assert isinstance(observer, CosimObserver)
    step_count = 0
    while True:
        step_count += 1
        status = sim.status()
        if status.current_time > 1e9:
            break
        if status.state == CosimExecutionState.ERROR.value:
            raise AssertionError(f"Error state at time {status.current_time}") from None
        if step_count > 10:
            break
        elif step_count == 8:
            manipulator.slave_real_values(slave, [i_bav], [0.1])
        print(f"Step {step_count}, time {status.current_time}, state: {status.state}")
        sim.step()

    # initial_settings()


#     for t in range(1, 2):
#         status = sim.status()
#         if status.state != CosimExecutionState.ERROR.value:
#             pass
#            assert sim.simulate_until( int(t * 1e9)), "Error in simulation at time {t}"
#         for a in static.act_get[-1]:
#             print(f"Time {t/1e9}, {a.args}: {a()}")
#         if t == 5:
#             cases.simulator.set_variable_value(0, 0, (get_ref("boom_angularVelocity"),), (0.7,))


# @pytest.mark.skip("Alternative only using SimulatorInterface")
def test_run_basic():
    path = Path(Path(__file__).parent, "data/MobileCrane/OspSystemStructure.xml")
    assert path.exists(), "System structure file not found"
    sim = SimulatorInterface(path)
    sim.simulator.simulate_until(1e9)


# @pytest.mark.skip("Run all cases defined in MobileCrane.cases")
def test_run_cases():
    path = Path(Path(__file__).parent, "data/MobileCrane/MobileCrane.cases")
    # system_structure = Path(Path(__file__).parent, "data/MobileCrane/OspSystemStructure.xml")
    assert path.exists(), "MobileCrane cases file not found"
    cases = Cases(path)
    # for v, info in cases.variables.items():
    #     print(v, info)
    static = cases.case_by_name("static")
    assert static.act_get[-1][0].func.__name__ == "get_variable_value"
    assert static.act_get[-1][0].args == (0, 0, (10, 11, 12))
    assert static.act_get[-1][1].args == (0, 0, (21, 22, 23))
    assert static.act_get[-1][2].args == (0, 0, (37, 38, 39))
    assert static.act_get[-1][3].args == (0, 0, (53, 54, 55))

    print("Running case 'base'...")
    cases.run_case("base", dump="results_base")
    res = cases.case_by_name("base").res.res
    # ToDo: expected Torque?
    assert is_nearly_equal(res.jspath("$['1.0'].mobileCrane.x_pedestal"), [0.0, 0.0, 3.0])
    # assert is_nearly_equal(res[1.0]["mobileCrane"]["x_boom"], [8, 0.0, 3], 1e-5)
    # assert is_nearly_equal(res[1.0]["mobileCrane"]["x_load"], [8, 0, 3.0 - 1e-6], 1e-5)

    cases = Cases(path)
    cases.run_case("static", dump="results_static")
    res = cases.case_by_name("static").res.res
    print("RES(1.0)", res.jspath("$['1.0'].mobileCrane"))
    assert is_nearly_equal(res.jspath("$['1.0'].mobileCrane.x_pedestal"), [0.0, 0.0, 3.0])
    x_load = res.jspath("$['1.0'].mobileCrane.x_load")
    print(f"x_load: {x_load} <-> {[0, 8/sqrt(2),0]}")


#     print("Running case 'static'...")
#     res = cases.run_case("static", dump="results_static")
#     print("RES(1.0)", res[1.0]['mobileCrane'])
#     assert is_nearly_equal( res[1.0]['mobileCrane']['x_pedestal'], [0.0,0.0,3.0])
#     print(f"x_load: {res[1.0]['mobileCrane']['x_load']} <-> {[0, 8/sqrt(2),0]}")
#     assert is_nearly_equal( res[1.0]['mobileCrane']['x_boom'], [0, 8/sqrt(2),3.0+8/sqrt(2)], 1e-4)
# #    assert is_nearly_equal( res[1.0]['mobileCrane']['x_load'], [0, 8,1.0-1e-6,0])
#     print("Running case 'dynamic'...")
# #    res = cases.run_case("dynamic", dump="results_dynamic")
#     assert len(res) > 0


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Return code {retcode}"
    # test_read_cases()
    # test_run_cases()
    # test_step_by_step_cases()
