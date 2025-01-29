from math import sqrt
from pathlib import Path
from typing import Any

import pytest
from libcosimpy.CosimEnums import CosimExecutionState
from libcosimpy.CosimExecution import CosimExecution
from libcosimpy.CosimManipulator import CosimManipulator
from libcosimpy.CosimObserver import CosimObserver
from libcosimpy.CosimSlave import CosimLocalSlave

from sim_explorer.case import Case, Cases
from sim_explorer.json5 import Json5
from sim_explorer.system_interface_osp import SystemInterfaceOSP


@pytest.fixture(scope="session")
def mobile_crane_fmu():
    return _mobile_crane_fmu()


def _mobile_crane_fmu():
    return Path(__file__).parent / "data" / "MobileCrane" / "MobileCrane.fmu"


def is_nearly_equal(x: float | list[float], expected: float | list[float], eps: float = 1e-10) -> int:
    if isinstance(x, float):
        assert isinstance(expected, float), f"Argument `expected` is not a float. Found: {expected}"
        if abs(x - expected) < eps:
            return True
        raise AssertionError(f"{x} is not nealry equal to {expected}") from None
    assert isinstance(expected, list), f"Argument `expected` is not a list. Found: {expected}"
    for i, y in enumerate(x):
        if abs(y - expected[i]) >= eps:
            raise AssertionError(f"{x}[{i}] is not as expected: {expected}")
    return True


# @pytest.mark.skip("Basic reading of js5 cases  definition")
def test_read_cases():
    path = Path(Path(__file__).parent / "data" / "MobileCrane" / "MobileCrane.cases")
    assert path.exists(), "System structure file not found"
    json5 = Json5(path)
    assert "# lift 1m / 0.1sec" in list(json5.comments.values())
    # for e in json5.js_py:
    #   print(f"{e}: {json5.js_py[e]}")
    assert json5.jspath(path="$.base.spec.df_dt", typ=list) == [0.0, 0.0]
    # json5_write( json5.js_py, "MobileCrane.js5")
    assert json5.jspath(path="$.dynamic.spec.db_dt", typ=float) == 0.785498


# @pytest.mark.skip("Alternative step-by step, only using libcosimpy")
def test_step_by_step_cosim(mobile_crane_fmu: Path):  # noqa: C901
    def set_var(name: str, value: float, slave: int = 0) -> bool:
        for idx in range(sim.num_slave_variables(slave)):
            if sim.slave_variables(slave)[idx].name.decode() == name:
                return manipulator.slave_real_values(slave_index=slave, variable_references=[idx], values=[value])
        return False

    def set_initial(name: str, value: float, slave: int = 0) -> bool:
        for idx in range(sim.num_slave_variables(slave)):
            if sim.slave_variables(slave)[idx].name.decode() == name:
                return sim.real_initial_value(slave_index=slave, variable_reference=idx, value=value)
        return False

    sim = CosimExecution.from_step_size(step_size=0.1 * 1.0e9)
    assert mobile_crane_fmu.exists(), f"FMU {mobile_crane_fmu} not found"
    local_slave = CosimLocalSlave(fmu_path=f"{mobile_crane_fmu}", instance_name="mobileCrane")
    sim.add_local_slave(local_slave=local_slave)
    manipulator = CosimManipulator.create_override()
    assert sim.add_manipulator(manipulator=manipulator)
    observer = CosimObserver.create_last_value()
    sim.add_observer(observer=observer)

    slave = sim.slave_index_from_instance_name("mobileCrane")
    assert slave == 0, f"Slave index should be '0', found {slave}"

    expected_names = (
        "boom_angularVelocity[0]",
        "pedestal_boom[0]",
        "boom_boom[1]",
        "rope_boom[2]",
    )
    found_expected = [False] * len(expected_names)
    for i in range(len(sim.slave_variables(slave))):
        for k, name in enumerate(expected_names):
            if sim.slave_variables(slave)[i].name.decode() == name:
                assert sim.slave_variables(slave)[i].reference == i
                assert sim.slave_variables(slave)[i].type == 0
                found_expected[k] = True
    assert False not in found_expected, (
        f"Not all expected names were found: {expected_names[found_expected.index(False)]}"
    )
    assert set_initial(name="pedestal_boom[0]", value=3.0)
    assert set_initial(name="boom_boom[0]", value=8.0)
    assert set_initial(name="boom_boom[1]", value=0.7854)
    assert set_initial(name="rope_boom[0]", value=1e-6)
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
        if step_count == 9:
            manipulator.slave_real_values(slave_index=slave, variable_references=[34], values=[0.1])
        # sim.step()  #
        _ = sim.simulate_until(target_time=step_count * 1e9)


# @pytest.mark.skip("Alternative step-by step, using SystemInterfaceOSP and Cases")
def test_step_by_step_cases(mobile_crane_fmu: Path):  # noqa: C901, PLR0915
    sim: SystemInterfaceOSP
    cosim: CosimExecution
    cases: Cases

    def get_ref(name: str) -> Any:  # noqa: ANN401
        variable = cases.simulator.variables(0)[name]
        assert len(variable), f"Variable {name} not found"
        return variable["reference"]

    def set_initial(name: str, value: float, slave: int = 0) -> bool:
        for idx in range(cosim.num_slave_variables(slave_index=slave)):
            if cosim.slave_variables(slave_index=slave)[idx].name.decode() == name:
                return cosim.real_initial_value(slave_index=slave, variable_reference=idx, value=value)
        return False

    def initial_settings():
        assert isinstance(cases.simulator, SystemInterfaceOSP)
        cases.simulator.manipulator.slave_real_values(
            slave_index=0,
            variable_references=(
                get_ref("pedestal_boom[0]"),
                get_ref("boom_boom[0]"),
                get_ref("boom_boom[1]"),
                get_ref("rope_boom[0]"),
                get_ref("dLoad"),
            ),
            values=(3.0, 8.0, 0.7854, 1e-6, 50.0),
        )

    system = Path(Path(__file__).parent / "data" / "MobileCrane" / "OspSystemStructure.xml")
    assert system.exists(), f"OspSystemStructure file {system} not found"
    sim = SystemInterfaceOSP(system)
    _ = sim.init_simulator()
    print("COMP", dict(sim.components.items()))
    expected = dict(sim.components.items())
    assert isinstance(expected["mobileCrane"], str), f"Found components {expected}"

    path = Path(Path(__file__).parent, "data/MobileCrane/MobileCrane.cases")
    assert path.exists(), "Cases file not found"
    js = Json5(path)
    print("CASES", js.write(file=None, pretty_print=True))
    expected_results = ["T@step", "x_pedestal@step", "x_boom@step", "x_load@step"]
    assert js.jspath(path="$.base.results") == expected_results, f"Results found: {js.jspath(path='$.base.results')}"
    assert list(js.js_py.keys()) == [
        "header",
        "base",
        "static",
        "dynamic",
    ]
    assert list((js.jspath(path="$.header", typ=dict) or {}).keys()) == [
        "name",
        "description",
        "modelFile",
        "simulator",
        "logLevel",
        "timeUnit",
        "variables",
    ], f"Found: {list((js.jspath(path='$.header', typ=dict) or {}).keys())}"
    cases = Cases(path)
    print("INFO", cases.info())
    static = cases.case_by_name("static")
    assert static is not None
    assert static.js.jspath(path="$.spec", typ=dict) == {
        "p[2]": 1.570796,
        "b[1]": 45,
        "r[0]": 7.657,
        "load": 1000,
    }
    print("ACT", static.act_get[-1][0])
    assert static.act_get[-1][0] == ("T", "mobileCrane", (10, 11, 12))
    _ = sim.init_simulator()
    assert sim.observer.last_real_values(slave_index=0, variable_references=(10, 11, 12)) == [0.0, 0.0, 0.0], (
        "Initial value of T"
    )
    # msg = f"SET actions argument: {static.act_set[0][0].args}"
    # assert static.act_set[0][0].args == (0, 0, (13, 15), (3, 1.5708)), msg
    # sim.set_initial(0, 0, (13, 15), (3, 0))
    # assert sim.get_variable_value(0, 0, (13, 15)) == [3.0, 0.0], "Initial value of T"
    print(f"Special: {static.special}")
    assert static.act_set == {
        0: [
            ("p", "mobileCrane", (18, 20), (3.0, 1.570796)),
            ("b", "mobileCrane", (34, 35), (8.0, 45.0)),
            ("r", "mobileCrane", (50,), (7.657,)),
            ("df_dt", "mobileCrane", (7, 8), (0.0, 0.0)),
            ("dp_dt", "mobileCrane", (25,), (0.0,)),
            ("db_dt", "mobileCrane", (40,), (0.0,)),
            ("dr_dt", "mobileCrane", (58,), (0.0,)),
            ("v", "mobileCrane", (7, 8), (0.0, 0.0)),
            ("load", "mobileCrane", (16,), (1000.0,)),
        ]
    }
    assert static.act_get == {
        -1: [
            ("T", "mobileCrane", (10, 11, 12)),
            ("x_pedestal", "mobileCrane", (21, 22, 23)),
            ("x_boom", "mobileCrane", (37, 38, 39)),
            ("x_load", "mobileCrane", (53, 54, 55)),
        ]
    }

    _ = cases.simulator.init_simulator()
    assert isinstance(cases.simulator, SystemInterfaceOSP)
    cosim = cases.simulator.simulator
    slave = cosim.slave_index_from_instance_name("mobileCrane")
    assert slave == 0, f"Slave index should be '0', found {slave}"

    expected_names = (
        "boom_angularVelocity[0]",
        "pedestal_boom[0]",
        "boom_boom[1]",
        "rope_boom[2]",
        "dLoad",
    )
    found_expected = [-1] * len(expected_names)
    for i in range(len(cosim.slave_variables(slave))):
        for k, name in enumerate(expected_names):
            if cosim.slave_variables(slave)[i].name.decode() == name:
                assert cosim.slave_variables(slave)[i].reference == i
                assert cosim.slave_variables(slave)[i].type == 0
                found_expected[k] = True
    assert -1 not in found_expected, f"Not all expected names were found: {expected_names[found_expected.index(-1)]}"
    i_bav = found_expected[0]

    #    for idx in range( cosim.num_slave_variables(slave)):
    #        print(f"{cosim.slave_variables(slave)[idx].name.decode()}: {observer.last_real_values(slave, [idx])}")
    assert isinstance(cases.simulator, SystemInterfaceOSP)
    initial_settings()
    manipulator = cases.simulator.manipulator
    assert isinstance(manipulator, CosimManipulator)
    observer = cases.simulator.observer
    assert isinstance(observer, CosimObserver)
    step_count = 0
    while True:
        step_count += 1
        status = cosim.status()
        if status.current_time > 1e9:
            break
        if status.state == CosimExecutionState.ERROR.value:
            raise AssertionError(f"Error state at time {status.current_time}") from None
        if step_count > 10:
            break
        if step_count == 8:
            manipulator.slave_real_values(slave_index=slave, variable_references=[i_bav], values=[0.1])
        print(f"Step {step_count}, time {status.current_time}, state: {status.state}")
        cosim.step()

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


# @pytest.mark.skip("Alternative only using SystemInterfaceOSP")
def test_run_basic():
    path = Path(Path(__file__).parent / "data" / "MobileCrane" / "OspSystemStructure.xml")
    assert path.exists(), "System structure file not found"
    sim = SystemInterfaceOSP(path)
    _ = sim.init_simulator()
    _ = sim.simulator.simulate_until(target_time=1e9)


def test_run_cases():
    path = Path(Path(__file__).parent / "data" / "MobileCrane" / "MobileCrane.cases")
    # system_structure = Path(Path(__file__).parent, "data/MobileCrane/OspSystemStructure.xml")
    assert path.exists(), "MobileCrane cases file not found"
    cases = Cases(spec=path)
    case: Case | None
    # for v, info in cases.variables.items():
    #     print(v, info)
    static = cases.case_by_name("static")
    assert static is not None
    assert static.act_get[-1] == [
        ("T", "mobileCrane", (10, 11, 12)),
        ("x_pedestal", "mobileCrane", (21, 22, 23)),
        ("x_boom", "mobileCrane", (37, 38, 39)),
        ("x_load", "mobileCrane", (53, 54, 55)),
    ]

    print("Running case 'base'...")
    case = cases.case_by_name("base")
    assert case is not None
    case.run(dump="results_base")
    assert case.res is not None
    res = case.res.res
    # TODO @EisDNV: expected Torque?
    assert is_nearly_equal(res.jspath(path="$['1.0'].mobileCrane.x_pedestal", typ=list) or [], expected=[0.0, 0.0, 3.0])
    # assert is_nearly_equal(res[1.0]["mobileCrane"]["x_boom"], [8, 0.0, 3], 1e-5)
    # assert is_nearly_equal(res[1.0]["mobileCrane"]["x_load"], [8, 0, 3.0 - 1e-6], 1e-5)

    cases = Cases(path)
    cases.run_case("static", dump="results_static")
    case = cases.case_by_name("static")
    assert case is not None
    assert case.res is not None
    res = case.res.res
    print("RES(1.0)", res.jspath("$['1.0'].mobileCrane"))
    assert is_nearly_equal(res.jspath(path="$['1.0'].mobileCrane.x_pedestal") or [], expected=[0.0, 0.0, 3.0])
    x_load = res.jspath("$['1.0'].mobileCrane.x_load")
    print(f"x_load: {x_load} <-> {[0, 8 / sqrt(2), 0]}")


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
    retcode = pytest.main(args=["-rA", "-v", __file__])
    assert retcode == 0, f"Return code {retcode}"
    # test_read_cases()
    # test_step_by_step_cosim(_mobile_crane_fmu())
    # test_step_by_step_cases(_mobile_crane_fmu())
    # test_run_basic()
    # test_run_cases()
