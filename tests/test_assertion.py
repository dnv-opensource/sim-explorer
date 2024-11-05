from math import cos, sin

import matplotlib.pyplot as plt
import pytest
from sim_explorer.assertion import Assertion
from sympy import symbols
from sympy.vector import CoordSys3D

_t = [0.1 * float(x) for x in range(100)]
_x = [0.3 * sin(t) for t in _t]
_y = [1.0 * cos(t) for t in _t]


def show_data():
    fig, ax = plt.subplots()
    ax.plot(_x, _y)
    plt.title("Data (_x, _y)", loc="left")
    plt.show()


def test_init():
    Assertion.reset()
    t, x, y, a, b = symbols("t x y a b")
    ass = Assertion("t>8")
    assert ass.symbols["t"] == t
    assert Assertion.ns == {"t": t}
    ass = Assertion("(t>8) & (x>0.1)")
    assert ass.symbols == {"t": t, "x": x}
    assert Assertion.ns == {"t": t, "x": x}
    ass = Assertion("(y<=4) & (y>=4)")
    assert ass.symbols == {"y": y}
    assert Assertion.ns == {"t": t, "x": x, "y": y}
    Assertion.casesvar_to_symbol({"a": {"info": "some info on a"}, "b": {"info": "some info on b"}})
    assert Assertion.ns == {"t": t, "x": x, "y": y, "a": a, "b": b}


def test_assertion():
    t, x, y = symbols("t x y")
    # show_data()print("Analyze", analyze( "t>8 & x>0.1"))
    Assertion.reset()
    ass = Assertion("t>8")
    assert ass.assert_single([("t", 9.0)])
    assert not ass.assert_single([("t", 7)])
    res = ass.assert_series([("t", _t)], "bool-list")
    assert True in res, "There is at least one point where the assertion is True"
    assert res.index(True) == 81, f"Element {res.index(True)} is True"
    assert all(res[i] for i in range(81, 100)), "Assertion remains True"
    assert ass.assert_series([("t", _t)], "bool"), "There is at least one point where the assertion is True"
    assert ass.assert_series([("t", _t)], "interval") == (81, 100), "Index-interval where the assertion is True"
    ass = Assertion("(t>8) & (x>0.1)")
    res = ass.assert_series([("t", _t), ("x", _x)])
    assert res, "True at some point"
    assert ass.assert_series([("t", _t), ("x", _x)], "interval") == (81, 91)
    assert ass.assert_series([("t", _t), ("x", _x)], "count") == 10
    with pytest.raises(ValueError, match="Unknown return type 'Hello'") as err:
        ass.assert_series([("t", _t), ("x", _x)], "Hello")
    print("ERROR", err.value)
    # Checking equivalence. '==' does not work
    ass = Assertion("(y<=4) & (y>=4)")
    assert ass.symbols == {"y": y}
    assert Assertion.ns == {"t": t, "x": x, "y": y}
    assert ass.assert_single([("y", 4)])
    assert not ass.assert_series([("y", _y)], ret="bool")
    with pytest.raises(
        ValueError, match="'==' cannot be used to check equivalence. Use 'a-b' and check against 0"
    ) as _:
        ass = Assertion("y==4")
    ass = Assertion("y-4")
    assert 0 == ass.assert_single([("y", 4)])
    ass = Assertion("abs(y-4)<0.11")  # abs function can also be used
    assert ass.assert_single([("y", 4.1)])


def test_vector():
    """Test sympy vector operations."""
    from sympy import sqrt

    N = CoordSys3D("N")
    assert (N.i + N.j + N.k).dot(N.i) == 1
    assert (N.i + N.j + N.k).cross(N.i) == N.j - N.k
    assert Assertion.vector((1, 2, 3)).magnitude() == sqrt(1 + 2 * 2 + 3 * 3)


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Non-zero return code {retcode}"
    # test_init()
    # test_assertion()
    # test_vector()
