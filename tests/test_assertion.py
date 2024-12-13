import ast
from math import cos, sin
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

from sim_explorer.assertion import Assertion, Temporal
from sim_explorer.case import Cases, Results

_t = [0.1 * float(x) for x in range(100)]
_x = [0.3 * sin(t) for t in _t]
_y = [1.0 * cos(t) for t in _t]


def test_globals_locals():
    """Test the usage of the globals and locals arguments within exec."""
    from importlib import __import__

    module = __import__("math", fromlist=["sin"])
    locals().update({"sin": module.sin})
    code = "def f(x):\n    return sin(x)"
    compiled = compile(code, "<string>", "exec")
    exec(compiled, locals(), locals())
    # print(f"locals:{locals()}")
    assert abs(locals()["f"](3.0) - sin(3.0)) < 1e-15


def test_ast(show):
    expr = "1+2+x.dot(x) + sin(y)"
    if show:
        a = ast.parse(expr, "<source>", "exec")
        print(a, ast.dump(a, indent=4))

    ass = Assertion()
    ass.register_vars(
        {"x": {"instances": ("dummy",), "variables": (1, 2, 3)}, "y": {"instances": ("dummy2",), "variables": (1,)}}
    )
    syms, funcs = ass.expr_get_symbols_functions(expr)
    assert syms == ["x", "y"], f"SYMS: {syms}"
    assert funcs == ["sin"], f"FUNCS: {funcs}"

    expr = "abs(y-4)<0.11"
    if show:
        a = a = ast.parse(expr)
        print(a, ast.dump(a, indent=4))
    syms, funcs = ass.expr_get_symbols_functions(expr)
    assert syms == ["y"]
    assert funcs == ["abs"]

    ass = Assertion()
    ass.symbol("t", 1)
    ass.symbol("x", 3)
    ass.symbol("y", 1)
    ass.expr("1", "1+2+x.dot(x) + sin(y)")
    syms, funcs = ass.expr_get_symbols_functions("1")
    assert syms == ["x", "y"]
    assert funcs == ["sin"]
    syms, funcs = ass.expr_get_symbols_functions("abs(y-4)<0.11")
    assert syms == ["y"]
    assert funcs == ["abs"]

    ass = Assertion()
    ass.register_vars(
        {"g": {"instances": ("bb",), "variables": (1,)}, "x": {"instances": ("bb",), "variables": (2, 3, 4)}}
    )
    expr = "sqrt(2*bb_x[2] / bb_g)"  # fully qualified variables with components
    a = ast.parse(expr, "<source>", "exec")
    if show:
        print(a, ast.dump(a, indent=4))
    syms, funcs = ass.expr_get_symbols_functions(expr)
    assert syms == ["bb_g", "bb_x"]
    assert funcs == ["sqrt"]


def show_data():
    fig, ax = plt.subplots()
    ax.plot(_x, _y)
    plt.title("Data (_x, _y)", loc="left")
    plt.show()


def test_temporal():
    print(Temporal.ALWAYS.name)
    for name, member in Temporal.__members__.items():
        print(name, member, member.value)
    assert Temporal["A"] == Temporal.A, "Set through name as string"
    assert Temporal["ALWAYS"] == Temporal.A, "Alias works also"
    with pytest.raises(KeyError) as err:
        _ = Temporal["G"]
    assert str(err.value) == "'G'", f"Found:{err.value}"


def test_assertion():
    # show_data()print("Analyze", analyze( "t>8 & x>0.1"))
    ass = Assertion()
    ass.symbol("t")
    ass.register_vars(
        {
            "x": {"instances": ("dummy",), "variables": (2,)},
            "y": {"instances": ("dummy",), "variables": (3,)},
            "z": {"instances": ("dummy",), "variables": (4, 5)},
        }
    )
    ass.expr("1", "t>8")
    assert ass.eval_single("1", {"t": 9.0})
    assert not ass.eval_single("1", {"t": 7})
    times, results = ass.eval_series("1", _t, "bool-list")
    assert True in results, "There is at least one point where the assertion is True"
    assert results.index(True) == 81, f"Element {results.index(True)} is True"
    assert all(results[i] for i in range(81, 100)), "Assertion remains True"
    assert ass.eval_series("1", _t, max)[1]
    assert results == ass.eval_series("1", _t, "bool-list")[1]
    assert ass.eval_series("1", _t, "F") == (8.1, True), "Finally True"
    ass.symbol("x")
    ass.expr("2", "(t>8) and (x>0.1)")
    times, results = ass.eval_series("2", zip(_t, _x, strict=True), "bool")
    assert times == 8.1, f"Should be 'True' (at some point). Found {times}, {results}. Expr: {ass.expr('2')}"
    times, results = ass.eval_series("2", zip(_t, _x, strict=True), "bool-list")
    time_interval = [r[0] for r in filter(lambda res: res[1], zip(times, results, strict=False))]
    assert (time_interval[0], time_interval[-1]) == (8.1, 9.0)
    assert len(time_interval) == 10
    with pytest.raises(ValueError, match="Unknown return type 'Hello'") as err:
        ass.eval_series("2", zip(_t, _x, strict=True), "Hello")
    assert str(err.value) == "Unknown return type 'Hello'"
    # Checking equivalence. '==' does not work
    ass.symbol("y")
    ass.expr("3", "(y<=4) & (y>=4)")
    expected = ["t", "x", "dummy_x", "y", "dummy_y", "z", "dummy_z"]
    assert list(ass._symbols.keys()) == expected, f"Found: {list(ass._symbols.keys())}"
    assert ass.expr_get_symbols_functions("3") == (["y"], [])
    assert ass.eval_single("3", {"y": 4})
    assert not ass.eval_series("3", zip(_t, _y, strict=True), ret="bool")[1]
    ass.expr("4", "y==4"), "Also equivalence check is allowed here"
    assert ass.eval_single("4", {"y": 4})
    ass.expr("5", "abs(y-4)<0.11")  # abs function can also be used
    assert ass.eval_single("5", (4.1,))
    ass.expr("6", "sin(t)**2 + cos(t)**2")
    assert abs(ass.eval_series("6", _t, ret=max)[1] - 1.0) < 1e-15, "sin and cos accepted"
    ass.expr("7", "sqrt(t)")
    assert abs(ass.eval_series("7", _t, ret=max)[1] ** 2 - _t[-1]) < 1e-14, "Also sqrt works out of the box"
    ass.expr("8", "dummy_x*dummy_y")
    assert abs(ass.eval_series("8", zip(_t, _x, _y, strict=False), ret=max)[1] - 0.14993604045622577) < 1e-14
    ass.expr("9", "dummy_x*dummy_y* z[0]")
    assert (
        abs(
            ass.eval_series("9", zip(_t, _x, _y, zip(_x, _y, strict=False), strict=False), ret=max)[1]
            - 0.03455981729517478
        )
        < 1e-14
    )


def test_assertion_spec():
    cases = Cases(Path(__file__).parent / "data" / "SimpleTable" / "test.cases")
    _c = cases.case_by_name("case1")
    _c.read_assertion("3@9.85", ["x*t", "Description"])
    assert _c.cases.assertion.expr_get_symbols_functions("3") == (["t", "x"], [])
    res = _c.cases.assertion.eval_series("3", zip(_t, _x, strict=False), ret=9.85)
    assert _c.cases.assertion.info("x", "instance") == "tab"
    _c.read_assertion("1", ["t-1", "Description"])
    assert _c.asserts == ["3", "1"]
    assert _c.cases.assertion.temporal("1")["type"] == Temporal.A
    assert _c.cases.assertion.eval_single("1", (1,)) == 0
    with pytest.raises(AssertionError) as err:
        _c.read_assertion("2@F", "t-1")
    assert str(err.value).startswith("Assertion spec expected: [expression, description]. Found")
    _c.read_assertion("2@F", ["t-1", "Subtract 1 from time"])

    assert _c.cases.assertion.temporal("2")["type"] == Temporal.F
    assert _c.cases.assertion.temporal("2")["args"] == ()
    assert _c.cases.assertion.eval_single("2", (1,)) == 0
    _c.cases.assertion.symbol("y")
    found = list(_c.cases.assertion._symbols.keys())
    assert found == ["t", "x", "tab_x", "i", "tab_i", "y"], f"Found: {found}"
    _c.read_assertion("3@9.85", ["x*t", "Test assertion"])
    assert _c.asserts == ["3", "1", "2"], f"Found: {_c.asserts}"
    assert _c.cases.assertion.temporal("3")["type"] == Temporal.T
    assert _c.cases.assertion.temporal("3")["args"][0] == 9.85
    assert _c.cases.assertion.expr_get_symbols_functions("3") == (["t", "x"], [])
    res = _c.cases.assertion.eval_series("3", zip(_t, _x, strict=False), ret=9.85)
    assert res[0] == 9.85
    assert abs(res[1] - 0.5 * (_x[-1] * _t[-1] + _x[-2] * _t[-2])) < 1e-10


def test_vector():
    """Test sympy vector operations."""
    ass = Assertion()
    ass.symbol("x", length=3)
    print("Symbol x", ass.symbol("x"), type(ass.symbol("x")))
    ass.expr("1", "x.dot(x)")
    assert ass.expr_get_symbols_functions("1") == (["x"], [])
    ass.eval_single("1", ((1, 2, 3),))
    ass.eval_single("1", {"x": (1, 2, 3)})
    assert ass.symbol("x").dot(ass.symbol("x")) == 3.0, "Initialized as ones"
    assert ass.symbol("x").dot(np.array((0, 1, 0), dtype=float)) == 1.0, "Initialized as ones"
    ass.symbol("y", 3)  # a vector without explicit components
    assert all(ass.symbol("y")[i] == 1.0 for i in range(3))
    y = ass.symbol("y")
    assert y.dot(y) == 3.0, "Initialized as ones"


def test_do_assert(show):
    cases = Cases(spec=Path(__file__).parent / "data" / "BouncingBall3D" / "BouncingBall3D.cases")
    case = cases.case_by_name("restitutionAndGravity")
    case.run()
    #res = Results(file=Path(__file__).parent / "data" / "BouncingBall3D" / "restitutionAndGravity.js5")
    res = case.res
    # cases = res.case.cases
    assert res.case.name == "restitutionAndGravity"
    assert cases.file.name == "BouncingBall3D.cases"
    for key, inf in res.inspect().items():
        print(key, inf["len"], inf["range"])
    info = res.inspect()["bb.v"]
    assert info["len"] == 300
    assert info["range"] == [0.01, 3.0]
    ass = cases.assertion
    # ass.vector('x', (1,0,0))
    # ass.vector('v', (0,1,0))
    _ = ass.expr("0", "x.dot(v)")  # additional expression (not in .cases)
    assert ass._syms["0"] == ["x", "v"]
    assert all(ass.symbol("x")[i] == np.ones(3, dtype=float)[i] for i in range(3)), "Initialized to ones"
    assert ass.eval_single("0", ((1, 2, 3), (4, 5, 6))) == 32
    assert ass.expr("1") == "g==1.5"
    assert ass.temporal("1")["type"] == Temporal.A
    assert ass.syms("1") == ["g"]
    assert ass.do_assert("1", res)
    assert ass.assertions("1") == {"passed": True, "details": None}
    ass.do_assert("2", res)
    assert ass.assertions("2") == {"passed": True, "details": None}, f"Found {ass.assertions('2')}"
    if show:
        res.plot_time_series(["bb.x[2]"])
    ass.do_assert("3", res)
    assert ass.assertions("3") == {"passed": True, "details": "@2.22"}, f"Found {ass.assertions('3')}"
    ass.do_assert("4", res)
    assert ass.assertions("4") == {"passed": True, "details": "@1.1547 (interpolated)"}, f"Found {ass.assertions('4')}"
    count = ass.do_assert_case(res)  # do all
    assert count == [4, 4], "Expected 4 of 4 passed"
    for rep in ass.report():
        print(rep)


if __name__ == "__main__":
    # retcode = pytest.main(["-rA", "-v", __file__, "--show", "False"])
    # assert retcode == 0, f"Non-zero return code {retcode}"
    import os

    os.chdir(Path(__file__).parent.absolute() / "test_working_directory")
    # test_temporal()
    # test_ast( show=True)
    # test_globals_locals()
    # test_assertion()
    # test_assertion_spec()
    # test_vector()
    test_do_assert(show=True)
