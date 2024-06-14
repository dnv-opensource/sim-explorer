from pathlib import Path

import pytest
from case_study.case import Cases
from case_study.json5 import Json5Reader
from case_study.simulator_interface import SimulatorInterface
from libcosimpy.CosimEnums import CosimExecutionState
from libcosimpy.CosimExecution import CosimExecution
from libcosimpy.CosimManipulator import CosimManipulator
from libcosimpy.CosimObserver import CosimObserver
from libcosimpy.CosimSlave import CosimLocalSlave


@pytest.mark.skip("Basic reading of js5 cases  definition")
def test_read_cases():
    path = Path(Path(__file__).parent, "data/MobileCrane/MobileCrane.cases")
    assert path.exists(), "System structure file not found"
    json5 = Json5Reader(path)
    # print(f"COMMENTS: {json5.comments}")
    assert json5.comments[2458] == "#'90 deg/sec'"
    # for e in json5.js_py:
    #    print(f"{e}: {json5.js_py[e]}")
    assert json5.js_py["dynamic"]["spec"]["db_dt"] == 0.7854


@pytest.mark.skip("Alternative step-by step, only using libcosimpy")
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
    bav = sim.slave_variables(slave)[34]
    assert bav.name.decode() == "boom_angularVelocity"
    assert bav.reference == 34
    assert bav.type == 0
    assert set_initial("pedestal_boom[0]", 3.0)
    assert set_initial("boom_boom[0]", 8.0)
    assert set_initial("boom_boom[1]", 0.7854)
    assert set_initial("rope_boom[0]", 1e-6)
    assert set_initial("changeLoad", 50.0)
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
        sim.step()  # simulate_until(t * 1e9)


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
        cases.simulator.set_initial(0, 0, (get_ref("pedestal_boom[0]"),), (3.0,))
        cases.simulator.set_initial(0, 0, (get_ref("boom_boom[0]"), get_ref("boom_boom[1]")), (8.0, 0.7854))
        cases.simulator.set_initial(0, 0, (get_ref("rope_boom[0]"),), (1e-6,))
        cases.simulator.set_initial(0, 0, (get_ref("changeLoad"),), (50.0,))

    system = Path(Path(__file__).parent, "data/MobileCrane/OspSystemStructure.xml")
    assert system.exists(), f"OspSystemStructure file {system} not found"
    sim = SimulatorInterface(system)
    assert sim.get_components() == {"mobileCrane": 0}, f"Found component {sim.get_components()}"
    assert sim.match_variables("mobileCrane", "craneAngularVelocity") == (0, 1, 2, 3)

    path = Path(Path(__file__).parent, "data/MobileCrane/MobileCrane.cases")
    assert path.exists(), "Cases file not found"
    spec = Json5Reader(path).js_py
    # print("SPEC", json5_write( spec, None, True))

    expected_spec = {"spec": ["T@step", "x_pedestal@step", "x_boom@step", "x_load@step"]}
    assert spec["results"] == expected_spec, f"Results found: {spec['results']}"
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
    bav = sim.slave_variables(slave)[34]
    assert bav.name.decode() == "boom_angularVelocity"
    assert bav.reference == 34
    assert bav.type == 0

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
            manipulator.slave_real_values(slave, [34], [0.1])
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


@pytest.mark.skip("Alternative only using SimulatorInterface")
def test_run_basic():
    path = Path(Path(__file__).parent, "data/MobileCrane/OspSystemStructure.xml")
    assert path.exists(), "System structure file not found"
    sim = SimulatorInterface(path)
    sim.simulator.simulate_until(1e9)


@pytest.mark.skip("Run all cases defined in MobileCrane.cases")
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
    res = cases.run_case("base", dump="results_base")
    print("Running case 'static'...")
    res = cases.run_case("static", dump="results_static")
    print("Running case 'dynamic'...")
    res = cases.run_case("dynamic", dump="results_dynamic")
    assert len(res) > 0


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Return code {retcode}"
