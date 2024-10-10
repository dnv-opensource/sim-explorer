from math import sqrt
from pathlib import Path
from shutil import copy

from component_model.model import Model
from fmpy import plot_result, simulate_fmu


def nearly_equal(res: tuple, expected: tuple, eps=1e-7):
    assert len(res) == len(
        expected
    ), f"Tuples of different lengths cannot be equal. Found {len(res)} != {len(expected)}"
    for i, (x, y) in enumerate(zip(res, expected, strict=False)):
        assert abs(x - y) < eps, f"Element {i} not nearly equal in {x}, {y}"


def test_make_fmu():  # chdir):
    fmu_path = Model.build(
        str(Path(__file__).parent / "data" / "BouncingBall3D" / "bouncing_ball_3d.py"), dest=Path(Path.cwd())
    )
    copy(fmu_path, Path(__file__).parent / "data" / "BouncingBall3D")


def test_run_fmpy(show):
    """Test and validate the basic BouncingBall using fmpy and not using OSP or case_study."""
    path = Path("BouncingBall3D.fmu")
    assert path.exists(), f"File {path} does not exist"
    dt = 0.01
    result = simulate_fmu(
        path,
        start_time=0.0,
        stop_time=3.0,
        step_size=dt,
        validate=True,
        solver="Euler",
        debug_logging=False,
        visible=True,
        logger=print,  # fmi_call_logger=print,
        start_values={
            "e": 0.71,
            "g": 9.81,
        },
    )
    if show:
        plot_result(result)
    t_bounce = sqrt(2 * 10 * 0.0254 / 9.81)
    v_bounce = 9.81 * t_bounce  # speed in z-direction
    x_bounce = t_bounce / 1.0  # x-position where it bounces in m
    # Note: default values are reported at time 0!
    nearly_equal(result[0], (0, 0, 0, 10, 1, 0, 0, sqrt(2 * 10 / 9.81), 0, 0))  # time,pos-3, speed-3, p_bounce-3
    print(result[1])
    """
    arrays_equal(
        result(bb),
        (
            0.01,
            0.01,
            0,
            (10 * 0.0254 - 0.5 * 9.81 * 0.01**2) / 0.0254,
            1,
            0,
            -9.81 * 0.01,
            sqrt(2 * 10 * 0.0254 / 9.81),
            0,
            0,
        ),
    )
    """
    t_before = int(sqrt(2 / 9.81) / dt) * dt  # just before bounce
    print("BEFORE", t_before, result[int(t_before / dt)])
    nearly_equal(
        result[int(t_before / dt)],
        (t_before, 1 * t_before, 0, 1.0 - 0.5 * 9.81 * t_before * t_before, 1, 0, -9.81 * t_before, x_bounce, 0, 0),
        eps=0.003,
    )
    nearly_equal(
        result[int(t_before / dt) + 1],
        (
            t_before + dt,
            v_bounce * 0.71 * (t_before + dt - t_bounce) - 0.5 * 9.81 * (t_before + dt - t_bounce) ** 2,
            v_bounce * 0.71 - 9.81 * (t_before + dt - t_bounce),
        ),
        eps=0.03,
    )
    nearly_equal(result[int(2.5 / dt)], (2.5, 0, 0), eps=0.4)
    nearly_equal(result[int(3 / dt)], (3, 0, 0))
    print("RESULT", result[int(t_before / dt) + 1])


if __name__ == "__main__":
    #    retcode = pytest.main(["-rA", "-v", __file__, "--show", "True"])
    #    assert retcode == 0, f"Non-zero return code {retcode}"
    import os

    os.chdir(Path(__file__).parent.absolute() / "test_working_directory")
    test_make_fmu()
    test_run_fmpy(show=True)
