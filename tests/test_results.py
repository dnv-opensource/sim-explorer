from datetime import datetime
from pathlib import Path

import pytest

from sim_explorer.case import Cases, Results


def test_init():
    # sourcery skip: extract-duplicate-method
    # init through existing results file
    file = Path(__file__).parent / "data" / "BouncingBall3D" / "test_results"
    print("FILE", file)
    res = Results(file=file)
    # assert res.res.jspath("$.header.file", Path, True).exists()
    _date_time = res.res.jspath(path="$.header.dateTime", typ=datetime, error_msg=True)
    assert _date_time is not None
    print("DATE", _date_time.isoformat())
    assert _date_time.isoformat() == "1924-01-14T00:00:00"
    _cases_date = res.res.jspath(path="$.header.casesDate", typ=datetime, error_msg=True)
    assert _cases_date is not None
    assert _cases_date.isoformat() == "1924-01-13T00:00:00"
    # init making a new file
    cases = Cases(Path(__file__).parent / "data" / "BouncingBall3D" / "BouncingBall3D.cases")
    case = cases.case_by_name("base")
    res = Results(case=case)
    # assert res.res.jspath("$.header.file", Path, True).exists()
    _date_time = res.res.jspath(path="$.header.dateTime", typ=datetime, error_msg=True)
    assert _date_time is not None
    assert isinstance(_date_time.isoformat(), str)
    _cases_date = res.res.jspath(path="$.header.casesDate", typ=datetime, error_msg=True)
    assert _cases_date is not None
    assert isinstance(_cases_date.isoformat(), str)


def test_add():
    cases = Cases(Path(__file__).parent / "data" / "BouncingBall3D" / "BouncingBall3D.cases")
    case = cases.case_by_name("base")
    res = Results(case=case)
    res._header_transform(to_string=True)
    res.add(time=0.0, comp="bb", cvar="g", values=(9.81,))
    # print( res.res.write( pretty_print=True))
    assert res.res.jspath("$['0.0'].bb.g") == 9.81


def test_plot_time_series(show: bool) -> None:
    # sourcery skip: move-assign
    file = Path(__file__).parent / "data" / "BouncingBall3D" / "test_results"
    assert file.exists(), f"File {file} not found"
    res = Results(file=file)
    if show:
        res.plot_time_series(comp_var=["bb.x[2]", "bb.v[2]"], title="Test plot")


def test_inspect():
    file = Path(__file__).parent / "data" / "BouncingBall3D" / "test_case"
    res = Results(file=file)
    cont = res.inspect()
    assert cont["bb.e"]["len"] == 1, "Not a scalar??"
    assert cont["bb.e"]["range"][1] == 0.01, "Not at time 0.01??"
    assert cont["bb.e"]["info"]["description"] == "Coefficient of restitution"
    assert list(cont.keys()) == ["bb.e", "bb.g", "bb.x", "bb.v", "bb.x_b[0]"]
    assert cont["bb.x"]["len"] == 300
    assert cont["bb.x"]["range"] == [0.01, 3.0]
    assert cont["bb.x"]["info"]["description"] == "3D Position of the ball in meters"
    assert cont["bb.x"]["info"]["refs"] == (0, 1, 2), "ValueReferences"


def test_retrieve():
    file = Path(__file__).parent / "data" / "BouncingBall3D" / "test_results"
    res = Results(file=file)
    data = res.retrieve(comp_var=(("bb", "g"), ("bb", "e")))
    assert data == [[0.01, 9.81, 0.5]]
    data = res.retrieve(comp_var=(("bb", "x"), ("bb", "v")))
    assert len(data) == 300
    assert data[0] == [0.01, [0.01, 0.0, 39.35076771653544], [1.0, 0.0, -0.0981]]


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__, "--show", "True"])
    assert retcode == 0, f"Non-zero return code {retcode}"
    # import os
    # os.chdir(Path(__file__).parent.absolute() / "test_working_directory")
    # test_retrieve()
    # test_init()
    # test_add()
    # test_plot_time_series(show=True)
    # test_inspect()
