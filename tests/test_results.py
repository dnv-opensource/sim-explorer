from datetime import datetime
from pathlib import Path

import pytest
from case_study.case import Cases, Results

@pytest.mark.skip(reason="File contains harcoded absolute path")
def test_init():
    # init through existing results file
    file = Path.cwd().parent / "data" / "BouncingBall3D" / "test_results.js5"
    print("FILE", file)
    res = Results(file=file)
    assert res.res.jspath("$.header.file", Path, True).exists()
    print("DATE", res.res.jspath("$.header.dateTime", datetime, True).isoformat())
    assert res.res.jspath("$.header.dateTime", datetime, True).isoformat() == "1924-01-14T00:00:00"
    assert res.res.jspath("$.header.casesDate", datetime, True).isoformat() == "1924-01-13T00:00:00"
    # init making a new file
    cases = Cases(Path.cwd().parent / "data" / "BouncingBall3D" / "BouncingBall3D.cases")
    case = cases.case_by_name("base")
    res = Results(case=case)
    assert res.res.jspath("$.header.file", Path, True).exists()
    assert isinstance(res.res.jspath("$.header.dateTime", datetime, True).isoformat(), str)
    assert isinstance(res.res.jspath("$.header.casesDate", datetime, True).isoformat(), str)


def test_add():
    cases = Cases(Path.cwd().parent / "data" / "BouncingBall3D" / "BouncingBall3D.cases")
    case = cases.case_by_name("base")
    res = Results(case=case)
    res._header_transform(tostring=True)
    res.add(0.0, 0, 0, (6,), (9.81,))
    # print( res.res.write( pretty_print=True))
    assert res.res.jspath("$['0.0'].bb.g") == 9.81

@pytest.mark.skip(reason="Plots cannot be tested in CI")
def test_plot_time_series():
    file = Path(__file__).parent / "data" / "BouncingBall3D" / "test_results.js5"
    assert file.exists(), f"File {file} not found"
    res = Results(file=file)
    res.plot_time_series(("bb.x[2]", "bb.v[2]"), "Test plot")


def test_inspect():
    file = Path.cwd().parent / "data" / "BouncingBall3D" / "test_case.js5"
    res = Results(file=file)
    cont = res.inspect()
    assert cont["bb.e"]["len"] == 1, "Not a scalar??"
    assert cont["bb.e"]["range"][1] == 0.01, "Not at time 0.01??"
    assert cont["bb.e"]["info"]["description"] == "Coefficient of restitution"
    assert list(cont.keys()) == ["bb.e", "bb.g", "bb.x", "bb.v", "bb.x_b[0]"]
    assert cont["bb.x"]["len"] == 300
    assert cont["bb.x"]["range"] == [0.01, 3.0]
    assert cont["bb.x"]["info"]["description"] == "3D Position of the ball in meters"
    assert cont["bb.x"]["info"]["variables"] == (0, 1, 2), "ValueReferences"


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Non-zero return code {retcode}"
    # import os
    # os.chdir(Path(__file__).parent.absolute() / "test_working_directory")
    # test_init()
    # test_add()
    # test_plot_time_series()
    # test_inspect()
