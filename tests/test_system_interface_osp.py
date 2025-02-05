from pathlib import Path

import pytest
from libcosimpy.CosimExecution import CosimExecution
from libcosimpy.CosimManipulator import CosimManipulator
from libcosimpy.CosimObserver import CosimObserver

from sim_explorer.system_interface_osp import SystemInterfaceOSP
from sim_explorer.utils.misc import match_with_wildcard


def test_match_with_wildcard():
    assert match_with_wildcard(findtxt="Hello World", matchtxt="Hello World"), "Match expected"
    assert not match_with_wildcard(findtxt="Hello World", matchtxt="Helo World"), "No match expected"
    assert match_with_wildcard(findtxt="*o World", matchtxt="Hello World"), "Match expected"
    assert not match_with_wildcard(findtxt="*o W*ld", matchtxt="Hello Word"), "No match expected"
    assert match_with_wildcard(findtxt="*o W*ld", matchtxt="Hello World"), "Two wildcard matches expected"


def test_pytype():
    assert SystemInterfaceOSP.pytype(fmu_type="REAL", val="2.3") == 2.3, "Expected 2.3 as float type"
    assert SystemInterfaceOSP.pytype(fmu_type="Integer", val="99") == 99, "Expected 99 as int type"
    assert SystemInterfaceOSP.pytype(fmu_type="Boolean", val="fmi2True"), "Expected True as bool type"
    assert not SystemInterfaceOSP.pytype(fmu_type="Boolean", val="fmi2false"), "Expected True as bool type"
    assert (
        SystemInterfaceOSP.pytype(fmu_type="String", val="fmi2False") == "fmi2False"
    ), "Expected fmi2False as str type"
    with pytest.raises(ValueError) as err:
        _ = SystemInterfaceOSP.pytype(fmu_type="Real", val="fmi2False")
    assert str(err.value).startswith("could not convert string to float:"), "No error raised as expected"
    assert SystemInterfaceOSP.pytype(fmu_type="Real", val=0) == 0.0
    assert SystemInterfaceOSP.pytype(fmu_type="Integer", val=1) == 1
    assert SystemInterfaceOSP.pytype(fmu_type="String", val=2) == "2"
    assert SystemInterfaceOSP.pytype(fmu_type="Boolean", val=3)


def test_component_variable_name():
    path = Path(Path(__file__).parent, "data/BouncingBall0/OspSystemStructure.xml")
    system = SystemInterfaceOSP(path, name="BouncingBall")
    """
        Slave order is not guaranteed in different OS
        assert 1 == system.simulator.slave_index_from_instance_name("bb")
        assert 0 == system.simulator.slave_index_from_instance_name("bb2")
        assert 2 == system.simulator.slave_index_from_instance_name("bb3")
        assert system.components["bb"] == 0, f"Error in unique model index. Found {system.components['bb']}"
    """
    assert system.variable_name_from_ref(comp="bb", ref=0) == "time"
    assert system.variable_name_from_ref(comp="bb", ref=1) == "h"
    assert system.variable_name_from_ref(comp="bb", ref=2) == "der(h)"
    assert system.variable_name_from_ref(comp="bb", ref=3) == "v"
    assert system.variable_name_from_ref(comp="bb", ref=4) == "der(v)"
    assert system.variable_name_from_ref(comp="bb", ref=5) == "g"
    assert system.variable_name_from_ref(comp="bb", ref=6) == "e"
    assert system.variable_name_from_ref(comp="bb", ref=7) == "v_min"
    assert system.variable_name_from_ref(comp="bb", ref=8) == ""


def test_default_initial():
    def di(
        var: str,
        caus: str,
        expected: str | int | tuple[str, ...],
        *,
        only_default: bool = True,
    ):
        res = SystemInterfaceOSP.default_initial(causality=caus, variability=var, only_default=only_default)
        assert res == expected, f"default_initial({var}, {caus}): Found {res} but expected {expected}"

    di(var="constant", caus="parameter", expected=-1)
    di(var="constant", caus="calculated_parameter", expected=-1)
    di(var="constant", caus="input", expected=-1)
    di(var="constant", caus="output", expected="exact")
    di(var="constant", caus="local", expected="exact")
    di(var="constant", caus="independent", expected=-3)
    di(var="fixed", caus="parameter", expected="exact")
    di(var="fixed", caus="calculated_parameter", expected="calculated")
    di(var="fixed", caus="local", expected="calculated")
    di(var="fixed", caus="input", expected=-4)
    di(var="tunable", caus="parameter", expected="exact")
    di(var="tunable", caus="calculated_parameter", expected="calculated")
    di(var="tunable", caus="output", expected=-5)
    di(var="tunable", caus="local", expected="calculated")
    di(var="tunable", caus="input", expected=-4)
    di(var="discrete", caus="calculated_parameter", expected=-2)
    di(var="discrete", caus="input", expected=5)
    di(var="discrete", caus="output", expected="calculated")
    di(var="discrete", caus="local", expected="calculated")
    di(var="continuous", caus="calculated_parameter", expected=-2)
    di(var="continuous", caus="independent", expected=15)
    di(var="discrete", caus="output", expected=("calculated", "exact", "approx"), only_default=False)


def test_simulator_from_system_structure():
    """SystemInterfaceOSP from OspSystemStructure.xml"""
    # sourcery skip: extract-duplicate-method
    path = Path(Path(__file__).parent, "data/BouncingBall0/OspSystemStructure.xml")
    system = SystemInterfaceOSP(str(path), name="BouncingBall")
    assert system.name == "BouncingBall", f"System.name should be BouncingBall. Found {system.name}"
    assert "bb" in system.components, f"Instance name 'bb' expected. Found instances {list(system.components.keys())}"
    assert len(system.components) == 3
    assert len(system.models) == 1
    assert "BouncingBall" in system.models
    #    system.check_instances_variables()
    variables = system.variables("bb")
    # print(f"g: {variables['g']}")
    assert variables["g"]["reference"] == 5
    assert variables["g"]["type"] is float
    assert variables["g"]["causality"] == "parameter"
    assert variables["g"]["variability"] == "fixed"

    assert system.allowed_action(action="set", comp="bb", var="g", time=0)
    assert not system.allowed_action(action="set", comp="bb", var="g", time=100)
    assert system.message == "Change of g at communication point"
    assert system.allowed_action(action="set", comp="bb", var="e", time=100), system.message
    assert system.allowed_action(action="set", comp="bb", var="h", time=0), system.message
    assert not system.allowed_action(action="set", comp="bb", var="h", time=100), system.message
    assert not system.allowed_action(action="set", comp="bb", var="der(h)", time=0), system.message
    assert not system.allowed_action(action="set", comp="bb", var="der(h)", time=100), system.message
    assert system.allowed_action(action="set", comp="bb", var="v", time=0), system.message
    assert not system.allowed_action(action="set", comp="bb", var="v", time=100), system.message
    assert not system.allowed_action(action="set", comp="bb", var="der(v)", time=0), system.message
    assert not system.allowed_action(action="set", comp="bb", var="der(v)", time=100), system.message
    assert system.allowed_action(action="set", comp="bb", var="v_min", time=0), system.message
    assert system.allowed_action(action="set", comp="bb", var=(1, 3), time=0), system.message  # combination of h,v
    assert not system.allowed_action(
        action="set", comp="bb", var=(1, 3), time=100
    ), system.message  # combination of h,v


def test_simulator_reset():
    """SystemInterfaceOSP from OspSystemStructure.xml"""
    # sourcery skip: extract-duplicate-method
    path = Path(Path(__file__).parent, "data/BouncingBall0/OspSystemStructure.xml")
    system = SystemInterfaceOSP(str(path), name="BouncingBall")
    assert system.init_simulator(), f"Simulator initialization failed {system.simulator.status()}"
    assert system.simulator.status().current_time == 0.0
    h0, g0 = (9.9, -4.81)
    system.simulator.real_initial_value(slave_index=0, variable_reference=1, value=h0)  # initial height h
    system.simulator.real_initial_value(slave_index=0, variable_reference=5, value=g0)  # g
    assert system.observer.last_real_values(slave_index=0, variable_references=(1, 5)) == [
        0.0,
        0.0,
    ], "Values only when the simulation starts!"
    _ = system.simulator.simulate_until(target_time=1e9)
    assert system.simulator.status().current_time == 1e9
    values = system.observer.last_real_values(slave_index=0, variable_references=(1, 5))
    assert values[1] == g0, "Initial values set now"
    assert abs(values[0] - (h0 + 0.5 * g0 * 1.0 * 1.0)) < 1e-2, "Height calculated (not very accurate!)"
    system.manipulator.slave_real_values(slave_index=0, variable_references=(5,), values=(0.0,))  # zero gravity
    _ = system.simulator.simulate_until(target_time=2e9)
    assert system.simulator.status().current_time == 2e9
    values = system.observer.last_real_values(slave_index=0, variable_references=(1, 5))
    assert values[1] == 0.0
    assert abs(values[0] - (h0 + 3 / 2 * g0 * 1.0 * 1.0)) < 1e-2, "No acceleration in second step"
    # reset and start simulator with new values
    assert system.init_simulator(), f"Simulator resetting failed {system.simulator.status()}"
    assert system.simulator.status().current_time == 0
    h0, g0 = (19.9, -2.81)
    system.simulator.real_initial_value(slave_index=0, variable_reference=1, value=h0)  # initial height h
    system.simulator.real_initial_value(slave_index=0, variable_reference=5, value=g0)  # g
    assert system.observer.last_real_values(slave_index=0, variable_references=(1, 5)) == [
        0.0,
        0.0,
    ], "Values only when the simulation starts!"
    _ = system.simulator.simulate_until(target_time=1e9)
    assert system.simulator.status().current_time == 1e9
    values = system.observer.last_real_values(slave_index=0, variable_references=(1, 5))
    assert values[1] == g0, "Initial values set now"
    assert abs(values[0] - (h0 + 0.5 * g0 * 1.0 * 1.0)) < 1e-2, "Height calculated (not very accurate!)"


def test_simulator_instantiated():
    """Start with an instantiated simulator."""
    path = Path(Path(__file__).parent, "data/BouncingBall0/OspSystemStructure.xml")
    sim = CosimExecution.from_osp_config_file(str(path))
    assert sim.status().current_time == 0
    system = SystemInterfaceOSP(
        structure_file=str(path),
        name="BouncingBall System",
        description="Testing info retrieval from simulator (without OspSystemStructure)",
        log_level="warning",
    )
    assert isinstance(system, SystemInterfaceOSP)
    # not yet initialized:
    with pytest.raises(AttributeError):
        assert isinstance(system.manipulator, CosimManipulator)
    with pytest.raises(AttributeError):
        assert isinstance(system.observer, CosimObserver)
    assert system.init_simulator()
    assert isinstance(system.manipulator, CosimManipulator), "Ok now"
    h0, g0 = (9.9, -4.81)
    system.simulator.real_initial_value(slave_index=0, variable_reference=1, value=h0)  # initial height h
    system.simulator.real_initial_value(slave_index=0, variable_reference=5, value=g0)  # g
    assert system.observer.last_real_values(slave_index=0, variable_references=(1, 5)) == [0.0, 0.0]
    _ = system.run_until(time=1e9)
    assert system.simulator.status().current_time == int(1e9), f"STATUS: {system.simulator.status()}"
    values = system.observer.last_real_values(slave_index=0, variable_references=(1, 5))
    values = system.observer.last_real_values(slave_index=0, variable_references=(1, 5))
    assert values[1] == g0, "Initial values set now"
    assert abs(values[0] - (h0 + 0.5 * g0 * 1.0 * 1.0)) < 1e-2, "Height calculated (not very accurate!)"


if __name__ == "__main__":
    retcode = pytest.main(args=["-rA", "-v", __file__])
    assert retcode == 0, f"Return code {retcode}"
    # test_pytype()
    # test_component_variable_name()
    # test_default_initial()
    # test_simulator_from_system_structure()
    # test_simulator_reset()
    # test_simulator_instantiated()
