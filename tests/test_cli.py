import importlib
import os
import subprocess
import sys

# from types import SimpleNamespace as Namespace
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pytest


def run_in_subprocess(
    *args: Any,  # noqa: ANN401
    **kwargs: Any,  # noqa: ANN401
) -> subprocess.CompletedProcess[str]:
    """Runs a command in a subprocess.

    Returns a CompletedProcess object capturing return code as well as stdout and stderr.

    When running under debugpy and the CLI entry point shall be executed,
    then indirect the call to the Python executable, and let Python run the CLI script
    as a module. This allows the debugger to follow into the subprocess.
    """
    CLI_ENTRY_POINT = "sim-explorer"
    is_debug_session = "VSCODE_DEBUGPY_ADAPTER_ENDPOINTS" in os.environ

    if is_debug_session and args and args[0] == CLI_ENTRY_POINT:
        cmd_args = [sys.executable, "-m", "sim_explorer.cli.__main__", *args[1:]]
    else:
        cmd_args = list(args)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        args=cmd_args,
        shell=False,  # Must be False for debugger attachment
        capture_output=True,
        check=False,
        # encoding="utf-8",
        encoding="cp437",  # Use cp437 to avoid decoding errors on Windows with non-UTF-8 locale
        errors="replace",  # Replace undecodable bytes to avoid errors on Windows with non-UTF-8 locale
        env=env,
        **kwargs,
    )
    return result


def test_libcosimpy_import():
    """Test that libcosimpy can be imported without errors."""
    try:
        import libcosimpy.CosimLibrary  # noqa: F401, PLC0415
    except ImportError as e:
        pytest.fail(f"Failed to import libcosimpy: {e}")


def test_libcosimpy_import_and_reload():
    """Test that libcosimpy can be imported without errors."""
    try:
        import libcosimpy.CosimLibrary  # noqa: PLC0415
    except ImportError as e:
        pytest.fail(f"Failed to import libcosimpy: {e}")
    try:
        _module = importlib.reload(libcosimpy.CosimLibrary)
    except ImportError as e:
        pytest.fail(f"Failed to re-import libcosimpy: {e}")


def test_entrypoint():
    result = run_in_subprocess("sim-explorer", "--help")
    assert result.returncode == 0


def test_info():
    """Does info display the correct information."""
    cases = Path(__file__).parent / "data" / "BouncingBall3D" / "BouncingBall3D.cases"
    #    "Cases BouncingBall3D. Simple sim explorer with the 3D BouncingBall FMU (3D position and speed\r\nSystem spec 'OspSystemStructure.xml'.\r\nbase\r\n  restitution\r\n    restitutionAndGravity\r\n  gravity\r\n\r\n"
    result = run_in_subprocess("sim-explorer", str(cases), "--info")
    assert result.returncode == 0
    assert result.stdout.startswith("Cases BouncingBall3D. Simple sim explorer with the 3D BouncingBall FMU (3D")
    assert "'OspSystemStructure.xml'" in result.stdout
    assert "base" in result.stdout
    assert "restitution" in result.stdout
    assert "restitutionAndGravity" in result.stdout
    assert "gravity" in result.stdout


def test_help():
    """Does info display the correct information."""
    result = run_in_subprocess("sim-explorer", "--help")
    assert result.returncode == 0
    assert result.stdout.startswith("usage: sim-explorer cases [options [args]]")
    assert "sim-explorer cases --info" in result.stdout
    assert "cases                 The sim-explorer specification file." in result.stdout
    assert "-h, --help            show this help message and exit" in result.stdout
    assert "--info                Display the structure of the defined cases." in result.stdout
    assert "--run run             Run a single case." in result.stdout
    assert "--Run Run             Run a case and all its sub-cases." in result.stdout
    assert "-q, --quiet           console output will be quiet." in result.stdout
    assert "-v, --verbose         console output will be verbose." in result.stdout
    assert "--log LOG             name of log file. If specified, this will activate" in result.stdout
    assert "--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}" in result.stdout
    assert "-V, --version         show program's version number and exit" in result.stdout


def test_version():
    """Does info display the correct information."""
    result = run_in_subprocess("sim-explorer", "--version")
    assert result.returncode == 0
    expected = version("sim-explorer")
    assert result.returncode == 0
    assert result.stdout.strip() == expected


def test_run():
    """Test running single case."""
    case = "gravity"
    path = Path(__file__).parent / "data" / "BouncingBall3D"
    cases = path / "BouncingBall3D.cases"
    res = Path(f"{case}.js5")
    log = Path("test.log")
    if res.exists():
        res.unlink()
    if log.exists():
        log.unlink()
    result = run_in_subprocess("sim-explorer", str(cases), "--run", case, "--log", "test.log", "--log-level", "DEBUG")
    assert result.returncode == 1
    assert case in result.stdout
    assert "6@A(g==9.81): Check wrong gravity." in result.stdout
    assert "Error: Assertion has failed" in result.stdout
    assert "1 tests failed" in result.stdout
    assert res.exists(), f"No results file {res} produced"
    assert log.exists(), f"log file {log} was not produced as requested"
    # print(result)


def test_Run():
    """Test running single case."""
    case = "restitution"
    path = Path(__file__).parent / "data" / "BouncingBall3D"
    cases = path / "BouncingBall3D.cases"
    res = Path(f"{case}.js5")
    res2 = Path("restitutionAndGravity.js5")
    if res.exists():
        res.unlink()
    if res2.exists():
        res2.unlink()
    result = run_in_subprocess("sim-explorer", str(cases), "--Run", case)
    assert result.returncode == 0
    assert case in result.stdout, "Note: only the results from restitutionAndGravity are in stdout!"
    assert res.exists(), f"No results file {res} produced"
    assert res2.exists(), f"No results file {res2} produced"


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__, "--show"])
    assert retcode == 0, f"Non-zero return code {retcode}"
    # os.chdir(Path(__file__).parent.absolute() / "test_working_directory")
    # test_entrypoint()
    # test_help()
    # test_version()
    # test_info()
    # test_run()
    # test_Run()
    # test_cli()
