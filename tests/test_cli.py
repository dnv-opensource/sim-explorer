import os
import subprocess
from pathlib import Path

import pytest


def check_command(cmd: str, expected: str | None = None):
    ret = subprocess.check_output(cmd, shell=True, text=True).strip()
    if expected is None:
        print("OUTPUT:", ret)
    else:
        assert ret.startswith(expected), f"{cmd}: {ret} != {expected}"

@pytest.mark.skip("Doesn't work with new results display")
def test_cli():
    os.chdir(str(Path(__file__).parent / "data" / "BouncingBall3D"))
    check_command("sim-explorer -V", "0.1.2")
    check_command(
        "sim-explorer BouncingBall3D.cases --info",
        "Cases BouncingBall3D. Simple sim explorer with the 3D BouncingBall FMU (3D position and",
    )
    check_command("sim-explorer BouncingBall3D.cases --run restitution", "")
    check_command("sim-explorer BouncingBall3D.cases --Run base", "")


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__, "--show", "True"])
    assert retcode == 0, f"Non-zero return code {retcode}"
    # test_cli()
