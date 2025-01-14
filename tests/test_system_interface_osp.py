from pathlib import Path

import pytest
from libcosimpy.CosimExecution import CosimExecution
from libcosimpy.CosimManipulator import CosimManipulator
from libcosimpy.CosimObserver import CosimObserver

from sim_explorer.system_interface_osp import SystemInterfaceOSP
from sim_explorer.utils.misc import match_with_wildcard


def test_match_with_wildcard():
    assert match_with_wildcard("Hello World", "Hello World"), "Match expected"
    assert not match_with_wildcard("Hello World", "Helo World"), "No match expected"
    assert match_with_wildcard("*o World", "Hello World"), "Match expected"
    assert not match_with_wildcard("*o W*ld", "Hello Word"), "No match expected"
    assert match_with_wildcard("*o W*ld", "Hello World"), "Two wildcard matches expected"


def test_pytype():
    assert SystemInterfaceOSP.pytype("REAL", "2.3") == 2.3, "Expected 2.3 as float type"
    assert SystemInterfaceOSP.pytype("Integer", "99") == 99, "Expected 99 as int type"
    assert SystemInterfaceOSP.pytype("Boolean", "fmi2True"), "Expected True as bool type"
    assert not SystemInterfaceOSP.pytype("Boolean", "fmi2false"), "Expected True as bool type"
    assert SystemInterfaceOSP.pytype("String", "fmi2False") == "fmi2False", "Expected fmi2False as str type"
    with pytest.raises(ValueError) as err:
        SystemInterfaceOSP.pytype("Real", "fmi2False")
    assert str(err.value).startswith("could not convert string to float:"), "No error raised as expected"
    assert SystemInterfaceOSP.pytype("Real", 0) == 0.0
    assert SystemInterfaceOSP.pytype("Integer", 1) == 1
    assert SystemInterfaceOSP.pytype("String", 2) == "2"
    assert SystemInterfaceOSP.pytype("Boolean", 3)


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
    assert system.variable_name_from_ref("bb", 0) == "time"
    assert system.variable_name_from_ref("bb", 1) == "h"
    assert system.variable_name_from_ref("bb", 2) == "der(h)"
    assert system.variable_name_from_ref("bb", 3) == "v"
    assert system.variable_name_from_ref("bb", 4) == "der(v)"
    assert system.variable_name_from_ref("bb", 5) == "g"
    assert system.variable_name_from_ref("bb", 6) == "e"
    assert system.variable_name_from_ref("bb", 7) == "v_min"
    assert system.variable_name_from_ref("bb", 8) == ""


def test_default_initial():
    def di(var: str, caus: str, expected: str | int | tuple, only_default: bool = True):
        res = SystemInterfaceOSP.default_initial(caus, var, only_default)
        assert res == expected, f"default_initial({var}, {caus}): Found {res} but expected {expected}"

    di("constant", "parameter", -1)
    di("constant", "calculated_parameter", -1)
    di("constant", "input", -1)
    di("constant", "output", "exact")
    di("constant", "local", "exact")
    di("constant", "independent", -3)
    di("fixed", "parameter", "exact")
    di("fixed", "calculated_parameter", "calculated")
    di("fixed", "local", "calculated")
    di("fixed", "input", -4)
    di("tunable", "parameter", "exact")
    di("tunable", "calculated_parameter", "calculated")
    di("tunable", "output", -5)
    di("tunable", "local", "calculated")
    di("tunable", "input", -4)
    di("discrete", "calculated_parameter", -2)
    di("discrete", "input", 5)
    di("discrete", "output", "calculated")
    di("discrete", "local", "calculated")
    di("continuous", "calculated_parameter", -2)
    di("continuous", "independent", 15)
    di("discrete", "output", ("calculated", "exact", "approx"), False)


def test_simulator_from_system_structure():
    """SystemInterfaceOSP from OspSystemStructure.xml"""
    path = Path(Path(__file__).parent, "data/BouncingBall0/OspSystemStructure.xml")
    system = SystemInterfaceOSP(str(path), name="BouncingBall")
    assert system.name == "BouncingBall", f"System.name should be BouncingBall. Found {system.name}"
    comps = {k: v for (k, v) in system.components}
    assert "bb" in comps, f"Instance name 'bb' expected. Found instances {list(comps.keys())}"
    assert len(comps) == 3
    assert len(system.models) == 1
    assert "BouncingBall" in system.models
    #    system.check_instances_variables()
    variables = system.variables("bb")
    print(f"g: {variables['g']}")
    assert variables["g"]["reference"] == 5
    assert variables["g"]["type"] is float
    assert variables["g"]["causality"] == "parameter"
    assert variables["g"]["variability"] == "fixed"

    assert system.allowed_action("set", "bb", "g", 0)
    assert not system.allowed_action("set", "bb", "g", 100)
    assert system.message == "Change of g at communication point"
    assert system.allowed_action("set", "bb", "e", 100), system.message
    assert system.allowed_action("set", "bb", "h", 0), system.message
    assert not system.allowed_action("set", "bb", "h", 100), system.message
    assert not system.allowed_action("set", "bb", "der(h)", 0), system.message
    assert not system.allowed_action("set", "bb", "der(h)", 100), system.message
    assert system.allowed_action("set", "bb", "v", 0), system.message
    assert not system.allowed_action("set", "bb", "v", 100), system.message
    assert not system.allowed_action("set", "bb", "der(v)", 0), system.message
    assert not system.allowed_action("set", "bb", "der(v)", 100), system.message
    assert system.allowed_action("set", "bb", "v_min", 0), system.message
    assert system.allowed_action("set", "bb", (1, 3), 0), system.message  # combination of h,v
    assert not system.allowed_action("set", "bb", (1, 3), 100), system.message  # combination of h,v


def test_simulator_reset():
    """SystemInterfaceOSP from OspSystemStructure.xml"""
    path = Path(Path(__file__).parent, "data/BouncingBall0/OspSystemStructure.xml")
    system = SystemInterfaceOSP(str(path), name="BouncingBall")
    assert system.init_simulator(), f"Simulator initialization failed {system.simulator.status()}"
    assert system.simulator.status().current_time == 0.0
    h0, g0 = (9.9, -4.81)
    system.simulator.real_initial_value(0, 1, h0)  # initial height h
    system.simulator.real_initial_value(0, 5, g0)  # g
    assert system.observer.last_real_values(0, (1, 5)) == [0.0, 0.0], "Values only when the simulation starts!"
    system.simulator.simulate_until(1e9)
    assert system.simulator.status().current_time == 1e9
    values = system.observer.last_real_values(0, (1, 5))
    assert values[1] == g0, "Initial values set now"
    assert abs(values[0] - (h0 + 0.5 * g0 * 1.0 * 1.0)) < 1e-2, "Height calculated (not very accurate!)"
    system.manipulator.slave_real_values(0, (5,), (0.0,))  # zero gravity
    system.simulator.simulate_until(2e9)
    assert system.simulator.status().current_time == 2e9
    values = system.observer.last_real_values(0, (1, 5))
    assert values[1] == 0.0
    assert abs(values[0] - (h0 + 3 / 2 * g0 * 1.0 * 1.0)) < 1e-2, "No acceleration in second step"
    # reset and start simulator with new values
    assert system.init_simulator(), f"Simulator resetting failed {system.simulator.status()}"
    assert system.simulator.status().current_time == 0
    h0, g0 = (19.9, -2.81)
    system.simulator.real_initial_value(0, 1, h0)  # initial height h
    system.simulator.real_initial_value(0, 5, g0)  # g
    assert system.observer.last_real_values(0, (1, 5)) == [0.0, 0.0], "Values only when the simulation starts!"
    system.simulator.simulate_until(1e9)
    assert system.simulator.status().current_time == 1e9
    values = system.observer.last_real_values(0, (1, 5))
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
    with pytest.raises(AttributeError) as _:
        assert isinstance(system.manipulator, CosimManipulator)
    with pytest.raises(AttributeError) as _:
        assert isinstance(system.observer, CosimObserver)
    assert system.init_simulator()
    assert isinstance(system.manipulator, CosimManipulator), "Ok now"
    h0, g0 = (9.9, -4.81)
    system.simulator.real_initial_value(0, 1, h0)  # initial height h
    system.simulator.real_initial_value(0, 5, g0)  # g
    assert system.observer.last_real_values(0, (1, 5)) == [0.0, 0.0]
    system.run_until(1e9)
    assert system.simulator.status().current_time == int(1e9), f"STATUS: {system.simulator.status()}"
    values = system.observer.last_real_values(0, (1, 5))
    values = system.observer.last_real_values(0, (1, 5))
    assert values[1] == g0, "Initial values set now"
    assert abs(values[0] - (h0 + 0.5 * g0 * 1.0 * 1.0)) < 1e-2, "Height calculated (not very accurate!)"


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Return code {retcode}"
    # test_pytype()
    # test_component_variable_name()
    # test_default_initial()
    # test_simulator_from_system_structure()
    # test_simulator_reset()
    # test_simulator_instantiated()
