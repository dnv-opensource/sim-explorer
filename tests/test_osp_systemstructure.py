from pathlib import Path

import pytest
from libcosimpy.CosimEnums import (
    CosimVariableCausality,
    CosimVariableType,
    CosimVariableVariability,
)
from libcosimpy.CosimExecution import CosimExecution

from sim_explorer.utils.osp import make_osp_system_structure, osp_system_structure_from_js5


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


def test_osp_structure():
    _ = make_osp_system_structure(
        name="systemModel",
        version="0.1",
        simulators={
            "simpleTable": {"source": "SimpleTable.fmu", "interpolate": True},
            "mobileCrane": {"source": "MobileCrane.fmu", "pedestal.pedestalMass": 5000.0, "boom.boom[0]": 20.0},
        },
        connections_variable=[("simpleTable", "outputs[0]", "mobileCrane", "pedestal.angularVelocity")],
        path=Path.cwd(),
    )


def test_system_structure_from_js5():
    _ = osp_system_structure_from_js5(Path(__file__).parent / "data" / "MobileCrane" / "crane_table.js5")


if __name__ == "__main__":
    retcode = pytest.main(args=["-rA", "-v", __file__])
    assert retcode == 0, f"Non-zero return code {retcode}"
    # import os

    # os.chdir(Path(__file__).parent / "test_working_directory")
    # test_system_structure()
    # test_osp_structure()
    # test_system_structure_from_js5()
