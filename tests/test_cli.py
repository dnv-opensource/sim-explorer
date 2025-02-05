import os
from importlib.metadata import version
from pathlib import Path
from subprocess import run

# from types import SimpleNamespace as Namespace
from typing import Any, TypedDict


class CommandResult(TypedDict):
    exit_code: int
    stdout: str
    stderr: str


def shell(command: str, **kwargs: Any) -> CommandResult:
    """
    Execute a shell command capturing output and exit code.

    This is a better version of ``os.system()`` that captures output and
    returns a convenient dict object.
    This code is inspired by the same command from cli_test_helpers.
    """
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    completed = run(
        command, shell=True, capture_output=True, check=False, encoding="cp437", errors="replace", env=env, **kwargs
    )
    return {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def test_entrypoint():
    exit_status = os.system("sim-explorer --help")
    assert exit_status == 0


def test_info():
    """Does info display the correct information."""
    cases = Path(__file__).parent / "data" / "BouncingBall3D" / "BouncingBall3D.cases"
    #    "Cases BouncingBall3D. Simple sim explorer with the 3D BouncingBall FMU (3D position and speed\r\nSystem spec 'OspSystemStructure.xml'.\r\nbase\r\n  restitution\r\n    restitutionAndGravity\r\n  gravity\r\n\r\n"
    result = shell(f"sim-explorer {cases} --info")
    assert result["exit_code"] == 0
    assert result["stdout"].startswith("Cases BouncingBall3D. Simple sim explorer with the 3D BouncingBall FMU (3D")
    assert "'OspSystemStructure.xml'" in result["stdout"]
    assert "base" in result["stdout"]
    assert "restitution" in result["stdout"]
    assert "restitutionAndGravity" in result["stdout"]
    assert "gravity" in result["stdout"]


def test_help():
    """Does info display the correct information."""
    result = shell("sim-explorer --help")
    assert result["exit_code"] == 0
    assert result["stdout"].startswith("usage: sim-explorer cases [options [args]]")
    assert "sim-explorer cases --info" in result["stdout"]
    assert "cases                 The sim-explorer specification file." in result["stdout"]
    assert "-h, --help            show this help message and exit" in result["stdout"]
    assert "--info                Display the structure of the defined cases." in result["stdout"]
    assert "--run run             Run a single case." in result["stdout"]
    assert "--Run Run             Run a case and all its sub-cases." in result["stdout"]
    assert "-q, --quiet           console output will be quiet." in result["stdout"]
    assert "-v, --verbose         console output will be verbose." in result["stdout"]
    assert "--log LOG             name of log file. If specified, this will activate" in result["stdout"]
    assert "--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}" in result["stdout"]
    assert "-V, --version         show program's version number and exit" in result["stdout"]


def test_version():
    """Does info display the correct information."""
    result = shell("sim-explorer --version")
    assert result["exit_code"] == 0
    expected = version("sim-explorer")
    assert result["exit_code"] == 0
    assert result["stdout"].strip() == expected


def test_run():
    """Test running single case."""
    case = "gravity"
    path = Path(__file__).parent / "data" / "BouncingBall3D"
    cases = path / "BouncingBall3D.cases"
    res = path / (case + ".js5")
    log = Path(__file__).parent / "test_working_directory" / "test.log"
    if res.exists():
        res.unlink()
    if log.exists():
        log.unlink()
    result = shell(f"sim-explorer {cases} --run {case} --log test.log --log-level DEBUG")
    assert result["exit_code"] == 1
    assert case in result["stdout"]
    assert "6@A(g==9.81): Check wrong gravity." in result["stdout"]
    assert "Error: Assertion has failed" in result["stdout"]
    assert "1 tests failed" in result["stdout"]
    assert res.exists(), f"No results file {res} produced"
    assert log.exists(), f"log file {log} was not produced as requested"
    # print(result)


def test_Run():
    """Test running single case."""
    case = "restitution"
    path = Path(__file__).parent / "data" / "BouncingBall3D"
    cases = path / "BouncingBall3D.cases"
    res = path / (case + ".js5")
    res2 = path / "restitutionAndGravity.js5"
    if res.exists():
        res.unlink()
    if res2.exists():
        res2.unlink()
    result = shell(f"sim-explorer {cases} --Run {case}")
    assert result["exit_code"] == 0
    assert case in result["stdout"], "Note: only the results from restitutionAndGravity are in stdout!"
    assert res.exists(), f"No results file {res} produced"
    assert res2.exists(), f"No results file {res2} produced"


if __name__ == "__main__":
    retcode = 0  # pytest.main(["-rA", "-v", __file__, "--show", "True"])
    assert retcode == 0, f"Non-zero return code {retcode}"
    os.chdir(Path(__file__).parent.absolute() / "test_working_directory")
    # test_entrypoint()
    # test_help()
    # test_version()
    # test_info()
    test_run()
    # test_Run()
    # test_cli()
