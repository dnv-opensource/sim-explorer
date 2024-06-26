from pathlib import Path

from case_study.case import Cases
from case_study.simulator_interface import SimulatorInterface

if __name__ == "__main__":
    cases = Cases(
        Path(Path(__file__).parent.parent / "tests/data/BouncingBall0/BouncingBall.cases"),
        SimulatorInterface(Path(__file__).parent.parent / "tests/data/BouncingBall0/OspSystemStructure.xml"),
    )

    print("RESULTS", cases.run_case(cases.case_by_name("case1"), "results"))
