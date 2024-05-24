from pathlib import Path

from fmpy import plot_result, simulate_fmu

""" Test and validate the basic BouncingBall using fmpy and not using OSP or case_study."""


def test_run_fmpy():
    path = Path(Path(__file__).parent, "data/BouncingBall0/BouncingBall.fmu")
    assert path.exists(), f"File {path} does not exist"

    result = simulate_fmu(  # type: ignore
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
    plot_result(result)


# def test_dll():
#     bb = WinDLL(os.path.abspath(os.path.curdir) + "\\BouncingBall.dll")
#     bb.fmi2GetTypesPlatform.restype = c_char_p
#     print(bb.fmi2GetTypesPlatform(None))
#     bb.fmi2GetVersion.restype = c_char_p
#     print(bb.fmi2GetVersion(None))

if __name__ == "__main__":
    test_run_fmpy()
