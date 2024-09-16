from pathlib import Path

from fmpy import simulate_fmu

""" Test and validate the basic BouncingBall using fmpy and not using OSP or case_study."""


def test_run_fmpy():
    path = Path(Path(__file__).parent, "data/BouncingBall0/BouncingBall.fmu")
    assert path.exists(), f"File {path} does not exist"

    _ = simulate_fmu(  # type: ignore
        path,
        start_time=0.0,
        stop_time=3.0,
        step_size=0.1,
        validate=True,
        solver="Euler",
        debug_logging=False,
        visible=True,
        logger=print,  # fmi_call_logger=print,
        start_values={
            "e": 0.71,
            "g": -9.82,
        },
    )
