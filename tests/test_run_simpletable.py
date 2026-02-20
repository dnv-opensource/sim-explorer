from pathlib import Path

import pytest
from libcosimpy.CosimExecution import CosimExecution

from sim_explorer.case import Case, Cases  # noqa: F401


def test_run_casex():
    path = Path(__file__).parent / "data/TimeTable/test.cases"
    assert path.exists(), "TimeTable cases file not found"
    cases = Cases(path)
    _ = cases.case_by_name("base")
    _ = cases.case_by_name("case1")
    _ = cases.case_by_name("caseX")
    print("RESULTS")
    cases.run_case(name="caseX", dump="results")


def test_run_time_table_base_case():
    path = Path(__file__).parent / "data/TimeTable/test.cases"
    assert path.exists(), "TimeTable cases file not found"
    cases = Cases(spec=path)
    cases.run_case(name="base", dump="results")


@pytest.mark.parametrize(
    "osp_system_structure",
    [
        Path(__file__).parent / "data/TimeTable/OspSystemStructure.xml",
        Path(__file__).parent / "data/BouncingBall0/OspSystemStructure.xml",
        Path(__file__).parent / "data/BouncingBall3D/OspSystemStructure.xml",
        Path(__file__).parent / "data/Oscillator/ForcedOscillator.xml",
        Path(__file__).parent / "data/MobileCrane/OspSystemStructure.xml",
    ],
)
def test_get_cosim_execution(osp_system_structure: Path):
    assert osp_system_structure.exists(), "OSP system structure file not found"
    _simulator = CosimExecution.from_osp_config_file(str(osp_system_structure))


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Return code {retcode}"
    # test_run_casex()
