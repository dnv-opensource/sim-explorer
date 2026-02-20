from pathlib import Path

import pytest

from sim_explorer.utils.codegen import get_callable_function
from sim_explorer.utils.paths import get_path, relative_path


@pytest.fixture(scope="module", autouse=True)
def simexp() -> Path:
    return _simexp()


def _simexp() -> Path:
    return Path(__file__).parent.parent


def test_relative_path(simexp: Path):
    cases = simexp / "tests" / "data" / "BouncingBall3D" / "BouncingBall3D.cases"
    res = simexp / "tests" / "data" / "BouncingBall3D" / "test_results"
    cases0 = simexp / "tests" / "data" / "BouncingBall0" / "BouncingBall.cases"
    assert relative_path(cases, res) == "./BouncingBall3D.cases", f"Found {relative_path(cases, res)}"
    rel0 = relative_path(cases, cases0)
    assert rel0 == "../../BouncingBall3D/BouncingBall3D.cases", f"Found {relative_path(cases, cases0)}"

    expected = simexp / "tests" / "data" / "BouncingBall3D" / "BouncingBall3D.cases"
    found = get_path("BouncingBall3D.cases", res.parent)
    assert found == expected, f"Got {found}, expected {expected}"
    found = get_path(rel0, cases0)
    assert found == expected, f"Got {found}, expected {expected}"


def test_get_callable_function():
    compiled = compile("def f(x):\n    return x + 1", "<string>", "exec")
    f = get_callable_function(compiled=compiled, function_name="f")
    assert f(2) == 3


def test_get_callable_function_not_callable():
    compiled = compile("f = 7", "<string>", "exec")
    with pytest.raises(TypeError, match="not callable"):
        _ = get_callable_function(compiled=compiled, function_name="f")


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__, "--show", "True"])
    assert retcode == 0, f"Non-zero return code {retcode}"
    # import os
    # os.chdir(Path(__file__).parent.absolute() / "test_working_directory")
    # test_relative_path(_simexp())
