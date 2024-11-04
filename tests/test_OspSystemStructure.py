from pathlib import Path

import pytest
from libcosimpy.CosimEnums import CosimVariableCausality, CosimVariableType, CosimVariableVariability
from libcosimpy.CosimExecution import CosimExecution  # type: ignore


def test_system_structure():
    path = Path(Path(__file__).parent, "data", "BouncingBall0", "OspSystemStructure.xml")
    assert path.exists(), "OspSystemStructure.xml not found"
    sim = CosimExecution.from_osp_config_file(str(path))
    assert sim.execution_status.current_time == 0
    assert sim.execution_status.state == 0
    assert len(sim.slave_infos()) == 3, "Three bouncing balls were included!"
    assert len(sim.slave_infos()) == 3
    variables = sim.slave_variables(0)
    assert variables[0].name.decode() == "time"
    assert variables[0].reference == 0
    assert variables[0].type == CosimVariableType.REAL.value
    assert variables[0].causality == CosimVariableCausality.LOCAL.value
    assert variables[0].variability == CosimVariableVariability.CONTINUOUS.value


if __name__ == "__main__":
    retcode = pytest.main(
        [
            "-rA",
            "-v",
            __file__,
        ]
    )
    assert retcode == 0, f"Non-zero return code {retcode}"
