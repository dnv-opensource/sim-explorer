from math import cos, sin
from pathlib import Path

import matplotlib.pyplot as plt
import pytest
from sympy import symbols

from sim_explorer.assertion import Assertion, N
from sim_explorer.case import Cases, Results

_t = [0.1 * float(x) for x in range(100)]
_x = [0.3 * sin(t) for t in _t]
_y = [1.0 * cos(t) for t in _t]


def show_data():
    fig, ax = plt.subplots()
    ax.plot(_x, _y)
    plt.title("Data (_x, _y)", loc="left")
    plt.show()


@pytest.fixture(scope="session")
def init():
    return _init()


def _init():
    """Initialize what is needed for the other tests."""
    t, x, y, a, b = symbols("t x y a b")  # so that they are known here
    ass = Assertion()
    for s in ("t", "x", "y", "a", "b"):
        ass.symbol(s)
    assert ass.symbol("t").name == t.name, "Only the names are equal! The python objects are different"
    ass.expr("1", "t>8")
    assert tuple(ass._symbols.keys()) == ("t", "x", "y", "a", "b")
    ass.expr("2", "(t>8) & (x>0.1)")
    ass.expr("3", "(y<=4) & (y>=4)")
    ass.prefer_lambdify = False
    print(ass.expr("3").__doc__, len(ass.syms("3")))


def test_assertion(init):
    # show_data()print("Analyze", analyze( "t>8 & x>0.1"))
    ass = Assertion()
    ass.expr("1", "t>8")
    ass.prefer_lambdify = True
    assert ass.eval_single("1", (9.0,))
    ass.prefer_lambdify = False
    assert ass.eval_single("1", (9.0,))
    assert not ass.eval_single("1", (7,))
    res = ass.eval_series("1", _t, "bool-list")
    assert True in res, "There is at least one point where the assertion is True"
    assert res.index(True) == 81, f"Element {res.index(True)} is True"
    assert all(res[i] for i in range(81, 100)), "Assertion remains True"
    ass.prefer_lambdify = False
    assert res == ass.eval_series("1", _t, "bool-list")
    ass.prefer_lambdify = True
    assert ass.eval_series("1", _t, max), "Also this is True"
    assert ass.eval_series("1", _t, "bool"), "There is at least one point where the assertion is True"
    assert ass.eval_series("1", _t, "bool-interval") == (81, 100), "Index-interval where the assertion is True"
    ass.symbol("x")
    ass.expr("2", "(t>8) & (x>0.1)")
    res = ass.eval_series("2", zip(_t, _x, strict=False))
    assert res, f"Should be 'True' (at some point). Found {res}. Expr: {ass.expr('2')}"
    assert ass.eval_series("2", zip(_t, _x, strict=False), "bool-interval") == (81, 91)
    assert ass.eval_series("2", zip(_t, _x, strict=False), "bool-count") == 10
    with pytest.raises(ValueError, match="Unknown return type 'Hello'") as err:
        ass.eval_series("2", zip(_t, _x, strict=False), "Hello")
    assert str(err.value) == "Unknown return type 'Hello'"
    # Checking equivalence. '==' does not work
    ass.symbol("y")
    ass.expr("3", "(y<=4) & (y>=4)")
    assert list(ass._symbols.keys()) == ["t", "x", "y"]
    assert ass.expr_get_symbols("3") == {"y": ass.symbol("y")}
    assert ass.eval_single("3", (4,))
    ass.prefer_lambdify = True
    assert not ass.eval_series("3", zip(_t, _y, strict=False), ret="bool")
    with pytest.raises(ValueError, match="Cannot use '==' to check equivalence. Use 'a-b' and check against 0") as _:
        ass.expr("4", "y==4")
    ass.expr("4", "y-4")
    assert 0 == ass.eval_single("4", (4,))
    ass.expr("5", "abs(y-4)<0.11")  # abs function can also be used
    assert ass.eval_single("5", (4.1,))
    ass.expr("6", "sin(t)**2 + cos(t)**2")
    assert abs(ass.eval_series("6", _t, ret=max) - 1.0) < 1e-15, "sin and cos accepted"
    ass.expr("7", "sqrt(t)")
    assert abs(ass.eval_series("7", _t, ret=max) ** 2 - _t[-1]) < 1e-14, "Also sqrt works out of the box"


def test_assertion_spec():
    cases = Cases(Path(__file__).parent / "data" / "SimpleTable" / "test.cases")
    _c = cases.case_by_name("case1")
    _c.read_assertion("1", "t-1")
    assert _c.asserts == ["1"]
    assert _c.cases.assertion.temporal("1") == ("G",)
    assert _c.cases.assertion.eval_single("1", (1,)) == 0
    _c.read_assertion("2@F", "t-1")
    assert _c.cases.assertion.temporal("2") == ("F",), f"Found {_c.cases.assertion.temporal('2')}"
    assert _c.cases.assertion.eval_single("2", (1,)) == 0
    _c.cases.assertion.symbol("y")
    found = list(_c.cases.assertion._symbols.keys())
    assert found == ["t", "x#0", "x#1", "x#2", "x", "i", "y"], f"Found: {found}"
    _c.read_assertion("3@9.85", "x*t")
    assert _c.asserts == ["1", "2", "3"]
    assert _c.cases.assertion.temporal("3") == ("T", 9.85)
    res = _c.cases.assertion.eval_series("3", zip(_t, _x, _y, _y, strict=False), ret=9.85)
    assert res[0] == 9.85
    assert abs(res[1] - 0.5 * (_x[-1] * _y[-1] + _x[-2] * _y[-2])) < 1e-10


def test_vector():
    """Test sympy vector operations."""
    ass = Assertion()
    ass.symbol("x", length=3)
    print(ass.symbol("x"), type(ass.symbol("x")))
    print(ass.symbol("x").dot(ass.symbol("x")))
    print(ass.symbol("x").dot(N.j))
    ass.symbol("y", -1)  # a vector without explicit components
    print(ass.symbol("y"), type(ass.symbol("y")))
    y = ass.vector("y", (1, 2, 3))
    print("Y", y.dot(y))


def test_do_assert():
    res = Results(file=Path(__file__).parent / "data" / "BouncingBall3D" / "gravity.js5")
    cases = res.case.cases
    assert res.case.name == "gravity"
    assert cases.file.name == "BouncingBall3D.cases"
    for key, inf in res.inspect().items():
        print(key, inf["len"], inf["range"])
    info = res.inspect()["bb.v"]
    assert info["len"] == 300
    assert info["range"] == [0.01, 3.0]
    ass = cases.assertion
    # ass.vector('x', (1,0,0))
    # ass.vector('v', (0,1,0))
    _ = ass.expr("1", "x.dot(v)")
    assert list(ass._syms["1"].keys()) == ["x#0", "x#1", "x#2", "v#0", "v#1", "v#2"]
    ass.prefer_lambdify = False
    assert ass.eval_single("1", (1, 2, 3, 4, 5, 6)) == 32
    ass.prefer_lambdify = True
    assert ass.eval_single("1", (1, 2, 3, 4, 5, 6)) == 32


if __name__ == "__main__":
    # retcode = pytest.main(["-rA", "-v", __file__])
    # assert retcode == 0, f"Non-zero return code {retcode}"
    import os

    os.chdir(Path(__file__).parent.absolute() / "test_working_directory")
    # test_assertion(_init())
    # test_vector()
    test_assertion_spec()
    # test_do_assert()
