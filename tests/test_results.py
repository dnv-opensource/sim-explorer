from datetime import datetime
from pathlib import Path

import pytest
from case_study.case import Cases, Results


def test_init():
    # init through existing file
    file = Path.cwd().parent / "data" / "BouncingBall3D" / "test_results.js5"
    print("FILE", file)
    res = Results(file=file)
    assert res.res.jspath("$.header.file", Path, True).exists()
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


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Non-zero return code {retcode}"
    # os.chdir(Path(__file__).parent.absolute() / "test_working_directory")
    # test_init()
    # test_add()
