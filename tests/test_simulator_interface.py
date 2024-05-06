from pathlib import Path

import pytest
from case_study.simulator_interface import SimulatorInterface, match_with_wildcard
from libcosimpy.CosimExecution import CosimExecution


def _file(file: str = "BouncingBall.cases"):
    path = Path(__file__).parent.joinpath(file)
    assert path.exists(), f"File {file} does not exist at {Path(__file__).parent}"
    return path


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


def test_simulator_from_system_structure():
    """SimulatorInterface from OspSystemStructure.xml"""
    systemfile = _file("data/BouncingBall/OspSystemStructure.xml")
    system = SimulatorInterface(systemfile, name="BouncingBall")
    assert system.name == "BouncingBall", f"System.name should be BouncingBall. Found {system.name}"
    assert "bb" in system.components, f"Instance name 'bb' expected. Found instances {system.components}"
    assert system.get_models()[0] == 0, f"Component model {system.get_models()[0]}"
    assert "bb" in system.get_components()


def test_simulator_instantiated():
    """Start with an instantiated simulator."""
    systemfile = _file("data/BouncingBall/OspSystemStructure.xml")
    path = systemfile.parent
    sim = CosimExecution.from_osp_config_file(str(path))
    simulator = SimulatorInterface(
        system=systemfile,
        name="BouncingBall System",
        description="Testing info retrieval from simulator (without OspSystemStructure)",
        simulator=sim,
    )
    #    simulator.check_instances_variables()
    assert len(simulator.components) == 1, "Single instantiated component"
    assert simulator.components["bb"] == 0, f"... given a unique identifier {simulator.components['bb']}"
    variables = simulator.get_variables("bb")
    assert variables["g"] == {"reference": 5, "type": 0, "causality": 1, "variability": 1}
    assert simulator.get_variables(0) == simulator.get_variables("bb"), "Two ways of accessing variables"
    assert simulator.get_variables(0, "h"), {"h": {"reference": 1, "type": 0, "causality": 2, "variability": 4}}
    assert simulator.get_variables(0, 1), {"h": {"reference": 1, "type": 0, "causality": 2, "variability": 4}}


if __name__ == "__main__":
    test_match_with_wildcard()
    test_pytype()
    test_simulator_from_system_structure()
    test_simulator_instantiated()
