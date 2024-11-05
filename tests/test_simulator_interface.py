from pathlib import Path

import pytest
from libcosimpy.CosimExecution import CosimExecution
from sim_explorer.simulator_interface import SimulatorInterface, match_with_wildcard


def test_match_with_wildcard():
    assert match_with_wildcard("Hello World", "Hello World"), "Match expected"
    assert not match_with_wildcard("Hello World", "Helo World"), "No match expected"
    assert match_with_wildcard("*o World", "Hello World"), "Match expected"
    assert not match_with_wildcard("*o W*ld", "Hello Word"), "No match expected"
    assert match_with_wildcard("*o W*ld", "Hello World"), "Two wildcard matches expected"


def test_pytype():
    assert SimulatorInterface.pytype("REAL", "2.3") == 2.3, "Expected 2.3 as float type"
    assert SimulatorInterface.pytype("Integer", "99") == 99, "Expected 99 as int type"
    assert SimulatorInterface.pytype("Boolean", "fmi2True"), "Expected True as bool type"
    assert not SimulatorInterface.pytype("Boolean", "fmi2false"), "Expected True as bool type"
    assert SimulatorInterface.pytype("String", "fmi2False") == "fmi2False", "Expected fmi2False as str type"
    with pytest.raises(ValueError) as err:
        SimulatorInterface.pytype("Real", "fmi2False")
    assert str(err.value).startswith("could not convert string to float:"), "No error raised as expected"
    assert SimulatorInterface.pytype(0) == float
    assert SimulatorInterface.pytype(1) == int
    assert SimulatorInterface.pytype(2) == str
    assert SimulatorInterface.pytype(3) == bool
    assert SimulatorInterface.pytype(1, 2.3) == 2


def test_component_variable_name():
    path = Path(Path(__file__).parent, "data/BouncingBall0/OspSystemStructure.xml")
    system = SimulatorInterface(str(path), name="BouncingBall")
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
    print("DIR", dir(SimulatorInterface))
    assert SimulatorInterface.default_initial(0, 0) == 3, f"Found {SimulatorInterface._default_initial( 0, 0)}"
    assert SimulatorInterface.default_initial(1, 0) == 3, f"Found {SimulatorInterface._default_initial( 1, 0)}"
    assert SimulatorInterface.default_initial(2, 0) == 0, f"Found {SimulatorInterface._default_initial( 2, 0)}"
    assert SimulatorInterface.default_initial(3, 0) == 3, f"Found {SimulatorInterface._default_initial( 3, 0)}"
    assert SimulatorInterface.default_initial(4, 0) == 0, f"Found {SimulatorInterface._default_initial( 4, 0)}"
    assert SimulatorInterface.default_initial(5, 0) == 3, f"Found {SimulatorInterface._default_initial( 5, 0)}"
    assert SimulatorInterface.default_initial(1, 1) == 0, f"Found {SimulatorInterface._default_initial( 1, 1)}"
    assert SimulatorInterface.default_initial(1, 2) == 0, f"Found {SimulatorInterface._default_initial( 1, 1)}"
    assert SimulatorInterface.default_initial(1, 3) == 3, f"Found {SimulatorInterface._default_initial( 1, 1)}"
    assert SimulatorInterface.default_initial(1, 4) == 3, f"Found {SimulatorInterface._default_initial( 1, 1)}"
    assert SimulatorInterface.default_initial(2, 0) == 0, f"Found {SimulatorInterface._default_initial( 2, 0)}"
    assert SimulatorInterface.default_initial(5, 4) == 3, f"Found {SimulatorInterface._default_initial( 5, 4)}"
    assert SimulatorInterface.default_initial(3, 2) == 2, f"Found {SimulatorInterface._default_initial( 3, 2)}"
    assert SimulatorInterface.default_initial(4, 2) == 2, f"Found {SimulatorInterface._default_initial( 4, 2)}"


def test_simulator_from_system_structure():
    """SimulatorInterface from OspSystemStructure.xml"""
    path = Path(Path(__file__).parent, "data/BouncingBall0/OspSystemStructure.xml")
    system = SimulatorInterface(str(path), name="BouncingBall")
    assert system.name == "BouncingBall", f"System.name should be BouncingBall. Found {system.name}"
    assert "bb" in system.components, f"Instance name 'bb' expected. Found instances {system.components}"
    # assert system.get_models()[0] == 0, f"Component model {system.get_models()[0]}"
    assert "bb" in system.get_components()


def test_simulator_reset():
    """SimulatorInterface from OspSystemStructure.xml"""
    path = Path(Path(__file__).parent, "data/BouncingBall0/OspSystemStructure.xml")
    system = SimulatorInterface(str(path), name="BouncingBall")
    system.simulator.simulate_until(1e9)
    # print("STATUS", system.simulator.status())
    assert system.simulator.status().current_time == 1e9
    system.reset()
    assert system.simulator.status().current_time == 0


def test_simulator_instantiated():
    """Start with an instantiated simulator."""
    path = Path(Path(__file__).parent, "data/BouncingBall0/OspSystemStructure.xml")
    sim = CosimExecution.from_osp_config_file(str(path))
    # print("STATUS", sim.status())
    simulator = SimulatorInterface(
        system=str(path),
        name="BouncingBall System",
        description="Testing info retrieval from simulator (without OspSystemStructure)",
        simulator=sim,
    )
    #    simulator.check_instances_variables()
    assert len(simulator.components) == 3, "Three instantiated (identical) components"
    variables = simulator.get_variables("bb")
    assert variables["g"] == {"reference": 5, "type": 0, "causality": 1, "variability": 1}
    assert simulator.allowed_action("set", "bb", "g", 0)
    assert not simulator.allowed_action("set", "bb", "g", 100)
    assert simulator.message.startswith("Variable g, causality PARAMETER,")
    assert simulator.allowed_action("set", "bb", "e", 100), simulator.message
    assert simulator.allowed_action("set", "bb", "h", 0), simulator.message
    assert not simulator.allowed_action("set", "bb", "h", 100), simulator.message
    assert simulator.allowed_action("set", "bb", "der(h)", 0), simulator.message
    assert not simulator.allowed_action("set", "bb", "der(h)", 100), simulator.message
    assert simulator.allowed_action("set", "bb", "v", 0), simulator.message
    assert not simulator.allowed_action("set", "bb", "v", 100), simulator.message
    assert simulator.allowed_action("set", "bb", "der(v)", 0), simulator.message
    assert not simulator.allowed_action("set", "bb", "der(v)", 100), simulator.message
    assert not simulator.allowed_action("set", "bb", "v_min", 0), simulator.message
    assert simulator.allowed_action("set", "bb", (1, 3), 0), simulator.message  # combination of h,v
    assert not simulator.allowed_action("set", "bb", (1, 3), 100), simulator.message  # combination of h,v


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Return code {retcode}"
    # test_component_variable_name()
