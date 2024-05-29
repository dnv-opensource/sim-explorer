from pathlib import Path

import pytest
from case_study.case import Cases
from case_study.simulator_interface import SimulatorInterface


# @pytest.mark.skip("Not yet")
def test_run_casex():
    path = Path(Path(__file__).parent, "data/MobileCrane/MobileCrane.cases")
    assert path.exists(), "MobileCrane cases file not found"
    _ = Cases(path)
    # print("RESULTS", cases.run_case("base", "results"))


@pytest.mark.skip("Alternative step-by step")
def test_start_simulator():
    path = Path(Path(__file__).parent, "data/MobileCrane/OspSystemStructure.xml")
    assert path.exists(), "System structure file not found"
    sim = SimulatorInterface(path)
    assert sim.get_components() == {"mobileCrane": 0}, f"Found component {sim.get_components()}"
    assert sim.match_variables("mobileCrane", "craneAngularVelocity") == (0, 1, 2, 3)


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Return code {retcode}"
    # test_run_casex()
