from math import sqrt
from pathlib import Path

import pytest
from fmpy import plot_result, simulate_fmu


def nearly_equal(res: tuple, expected: tuple, eps=1e-7):
    assert len(res) == len(
        expected
    ), f"Tuples of different lengths cannot be equal. Found {len(res)} != {len(expected)}"
    for i, (x, y) in enumerate(zip(res, expected, strict=False)):
        assert abs(x - y) < eps, f"Element {i} not nearly equal in {x}, {y}"


def test_run_fmpy(show):
    """Test and validate the basic BouncingBall using fmpy and not using OSP or sim_explorer."""
    path = Path(Path(__file__).parent, "data/BouncingBall0/BouncingBall.fmu")
    assert path.exists(), f"File {path} does not exist"
    stepsize = 0.01
    result = simulate_fmu(
        path,
        start_time=0.0,
        stop_time=3.0,
        step_size=stepsize,
        validate=True,
        solver="Euler",
        debug_logging=False,
        visible=True,
        logger=print,  # fmi_call_logger=print,
        start_values={
            "e": 0.71,
            "g": -9.81,
        },
    )
    if show:
        plot_result(result)
    nearly_equal(result[0], (0, 1, 0))
    t_before = int(sqrt(2 / 9.81) / stepsize) * stepsize  # just before bounce
    nearly_equal(
        result[int(t_before / stepsize)],
        (t_before, 1.0 - 0.5 * 9.81 * t_before * t_before, -9.81 * t_before),
        eps=0.003,
    )
    t_bounce = sqrt(2 / 9.81)
    v_bounce = 9.81 * t_bounce
    nearly_equal(
        result[int(t_before / stepsize) + 1],
        (
            t_before + stepsize,
            v_bounce * 0.71 * (t_before + stepsize - t_bounce) - 0.5 * 9.81 * (t_before + stepsize - t_bounce) ** 2,
            v_bounce * 0.71 - 9.81 * (t_before + stepsize - t_bounce),
        ),
        eps=0.03,
    )
    nearly_equal(result[int(2.5 / stepsize)], (2.5, 0, 0), eps=0.4)
    nearly_equal(result[int(3 / stepsize)], (3, 0, 0))
    print("RESULT", result[int(t_before / stepsize) + 1])


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__, "--show", "True"])
    assert retcode == 0, f"Non-zero return code {retcode}"
