from pathlib import Path

import numpy as np
from case_study.case import Case, Cases
from case_study.simulator_interface import SimulatorInterface


def test_run_casex():
    path = Path(Path(__file__).parent, "data/SimpleTable/test.cases")
    assert path.exists(), "SimpleTable cases file not found"
    cases = Cases(path)
    base = cases.case_by_name("base")
    case1 = cases.case_by_name("case1")
    casex = cases.case_by_name("caseX")
    print("RESULTS", cases.run_case("caseX", "results"))


if __name__ == "__main__":
    test_run_casex()
