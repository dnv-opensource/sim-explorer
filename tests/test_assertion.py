# pyright: reportPrivateUsage=false

import ast
from math import cos, sin
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
import pytest

from sim_explorer.assertion import Assertion, Temporal
from sim_explorer.case import Cases, Results

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sim_explorer.utils.types import (
        TDataColumn,
        TNumeric,
        TTimeColumn,
        TValue,
    )

_t = [0.1 * float(x) for x in range(100)]
_x = [0.3 * sin(t) for t in _t]
_y = [1.0 * cos(t) for t in _t]


def test_globals_locals():
    """Test the usage of the globals and locals arguments within exec."""
    from importlib import import_module

    module = import_module("math")
    locals()["sin"] = module.sin
    code = "def f(x):\n    return sin(x)"
    compiled = compile(source=code, filename="<string>", mode="exec")
    exec(compiled, locals(), locals())  # noqa: S102
    # print(f"locals:{locals()}")
    assert abs(locals()["f"](3.0) - sin(3.0)) < 1e-15


def test_ast(show: bool):
    expr = "1+2+x.dot(x) + sin(y)"
    a = ast.parse(source=expr, filename="<source>", mode="exec")
    if show:
        print(a, ast.dump(node=a, indent=4))

    asserts = Assertion()
    asserts.register_vars(
        variables={
            "x": {"instances": ("dummy",), "names": ("x[0]", "x[1]", "x[2]")},
            "y": {"instances": ("dummy2",), "names": ("y[0]",)},
        }
    )
    syms, funcs = asserts.expr_get_symbols_functions(expr=expr)
    assert syms == ["x", "y"], f"SYMS: {syms}"
    assert funcs == ["sin"], f"FUNCS: {funcs}"

    expr = "abs(y-4)<0.11"
    a = ast.parse(source=expr)
    if show:
        print(a, ast.dump(node=a, indent=4))
    syms, funcs = asserts.expr_get_symbols_functions(expr)
    assert syms == ["y"]
    assert funcs == ["abs"]

    asserts = Assertion()
    asserts.symbol("t", length=1)
    asserts.symbol("x", length=3)
    asserts.symbol("y", length=1)
    _ = asserts.expr(key="1", ex="1+2+x.dot(x) + sin(y)")
    syms, funcs = asserts.expr_get_symbols_functions("1")
    assert syms == ["x", "y"]
    assert funcs == ["sin"]
    syms, funcs = asserts.expr_get_symbols_functions("abs(y-4)<0.11")
    assert syms == ["y"]
    assert funcs == ["abs"]

    asserts = Assertion()
    asserts.register_vars(
        variables={
            "g": {"instances": ("bb",), "names": ("g",)},
            "x": {"instances": ("bb",), "names": ("x[0]", "x[1]", "x[2]")},
        }
    )
    expr = "sqrt(2*bb_x[2] / bb_g)"  # fully qualified variables with components
    a = ast.parse(source=expr, filename="<source>", mode="exec")
    if show:
        print(a, ast.dump(a, indent=4))
    syms, funcs = asserts.expr_get_symbols_functions(expr)
    assert syms == ["bb_g", "bb_x"]
    assert funcs == ["sqrt"]


def show_data():
    fig, ax = plt.subplots()
    _ = ax.plot(_x, _y)
    _ = plt.title("Data (_x, _y)", loc="left")
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


def test_assertion():  # noqa: PLR0915
    # sourcery skip: extract-duplicate-method
    # show_data()print("Analyze", analyze( "t>8 & x>0.1"))
    asserts = Assertion()
    asserts.symbol("t")
    asserts.register_vars(
        variables={
            "x": {"instances": ("dummy",), "names": ("x[0]",)},
            "y": {"instances": ("dummy",), "names": ("y[0]",)},
            "z": {"instances": ("dummy",), "names": ("z[0]", "z[1]")},
        }
    )
    _ = asserts.expr(key="1", ex="t>8")
    assert asserts.eval_single(key="1", kvargs={"t": 9.0})
    assert not asserts.eval_single(key="1", kvargs={"t": 7})
    times: TNumeric | TTimeColumn
    results: TValue | TDataColumn
    times, results = asserts.eval_series(key="1", data=_t, ret="bool-list")
    assert isinstance(times, list)
    assert isinstance(results, list)
    assert True in results, "There is at least one point where the assertion is True"
    assert results.index(True) == 81, f"Element {results.index(True)} is True"
    assert all(results[i] for i in range(81, 100)), "Assertion remains True"
    assert asserts.eval_series(key="1", data=_t, ret=max)[1]
    assert results == asserts.eval_series(key="1", data=_t, ret="bool-list")[1]
    assert asserts.eval_series(key="1", data=_t, ret="F") == (8.1, True), "Finally True"
    asserts.symbol("x")
    _ = asserts.expr(key="2", ex="(t>8) and (x>0.1)")
    times, results = asserts.eval_series(key="2", data=tuple(zip(_t, _x, strict=True)), ret="bool")
    assert times == 8.1, f"Should be 'True' (at some point). Found {times}, {results}. Expr: {asserts.expr(key='2')}"
    times, results = asserts.eval_series(key="2", data=tuple(zip(_t, _x, strict=True)), ret="bool-list")
    assert isinstance(times, list)
    assert isinstance(results, list)
    time_interval = [r[0] for r in filter(lambda res: res[1], zip(times, results, strict=False))]
    assert (time_interval[0], time_interval[-1]) == (8.1, 9.0)
    assert len(time_interval) == 10
    with pytest.raises(ValueError, match="Unknown return type 'Hello'") as err:
        _ = asserts.eval_series(key="2", data=tuple(zip(_t, _x, strict=True)), ret="Hello")
    assert str(err.value) == "Unknown return type 'Hello'"
    # Checking equivalence. '==' does not work
    asserts.symbol("y")
    _ = asserts.expr(key="3", ex="(y<=4) & (y>=4)")
    expected = ["t", "x", "dummy_x", "y", "dummy_y", "z", "dummy_z"]
    assert list(asserts._symbols.keys()) == expected, f"Found: {list(asserts._symbols.keys())}"
    assert asserts.expr_get_symbols_functions(expr="3") == (["y"], [])
    assert asserts.eval_single(key="3", kvargs={"y": 4})
    assert not asserts.eval_series(key="3", data=tuple(zip(_t, _y, strict=True)), ret="bool")[1]
    _ = asserts.expr(key="4", ex="y==4"), "Also equivalence check is allowed here"
    assert asserts.eval_single(key="4", kvargs={"y": 4})
    _ = asserts.expr(key="5", ex="abs(y-4)<0.11")  # abs function can also be used
    assert asserts.eval_single(key="5", kvargs=(4.1,))
    _ = asserts.expr(key="6", ex="sin(t)**2 + cos(t)**2")
    result = asserts.eval_series(key="6", data=_t, ret=max)[1]
    assert isinstance(result, float)
    assert abs(result - 1.0) < 1e-15, "sin and cos accepted"
    _ = asserts.expr(key="7", ex="sqrt(t)")
    result = asserts.eval_series(key="7", data=_t, ret=max)[1]
    assert isinstance(result, float)
    assert abs(result**2 - _t[-1]) < 1e-14, "Also sqrt works out of the box"
    _ = asserts.expr(key="8", ex="dummy_x*dummy_y")
    result = asserts.eval_series(key="8", data=tuple(zip(_t, _x, _y, strict=False)), ret=max)[1]
    assert isinstance(result, float)
    assert abs(result - 0.14993604045622577) < 1e-14
    _ = asserts.expr(key="9", ex="dummy_x*dummy_y* z[0]")
    _x_y: Iterable[TValue] = tuple(zip(_x, _y, strict=False))
    result = asserts.eval_series(
        key="9",
        data=tuple(
            zip(
                _t,
                _x,
                _y,
                _x_y,
                strict=False,
            )
        ),
        ret=max,
    )[1]
    assert isinstance(result, float)
    assert abs(result - 0.03455981729517478) < 1e-14


def test_assertion_spec():
    cases = Cases(spec=Path(__file__).parent / "data" / "SimpleTable" / "test.cases")
    _c = cases.case_by_name("case1")
    assert _c is not None
    _ = _c.read_assertion(key="3@9.85", expr_descr=["x*t", "Description"])
    assert _c.cases.assertion.expr_get_symbols_functions(expr="3") == (["t", "x"], [])
    res = _c.cases.assertion.eval_series(key="3", data=tuple(zip(_t, _x, strict=False)), ret=9.85)
    assert _c.cases.assertion.info(sym="x", typ="instance") == "tab"
    _ = _c.read_assertion(key="1", expr_descr=["t-1", "Description"])
    assert _c.asserts == ["3", "1"]
    assert _c.cases.assertion.temporal(key="1")["type"] == Temporal.A
    assert _c.cases.assertion.eval_single(key="1", kvargs=(1,)) == 0
    with pytest.raises(AssertionError) as err:
        _ = _c.read_assertion(key="2@F", expr_descr="t-1")  # type: ignore[arg-type]
    assert str(err.value).startswith("Assertion spec expected: [expression, description]. Found")
    _ = _c.read_assertion(key="2@F", expr_descr=["t-1", "Subtract 1 from time"])

    assert _c.cases.assertion.temporal(key="2")["type"] == Temporal.F
    assert _c.cases.assertion.temporal(key="2")["args"] == ()
    assert _c.cases.assertion.eval_single(key="2", kvargs=(1,)) == 0
    _c.cases.assertion.symbol("y")
    found = list(_c.cases.assertion._symbols.keys())
    assert found == ["t", "x", "tab_x", "i", "tab_i", "y"], f"Found: {found}"
    _ = _c.read_assertion(key="3@9.85", expr_descr=["x*t", "Test assertion"])
    assert _c.asserts == ["3", "1", "2"], f"Found: {_c.asserts}"
    assert _c.cases.assertion.temporal(key="3")["type"] == Temporal.T
    assert _c.cases.assertion.temporal(key="3")["args"][0] == 9.85
    assert _c.cases.assertion.expr_get_symbols_functions(expr="3") == (["t", "x"], [])
    res = _c.cases.assertion.eval_series(key="3", data=tuple(zip(_t, _x, strict=False)), ret=9.85)
    assert res[0] == 9.85
    assert isinstance(res[1], float)
    assert abs(res[1] - 0.5 * (_x[-1] * _t[-1] + _x[-2] * _t[-2])) < 1e-10


def test_vector():
    """Test sympy vector operations."""
    asserts = Assertion()
    asserts.symbol("x", length=3)
    print("Symbol x", asserts.symbol("x"), type(asserts.symbol("x")))
    _ = asserts.expr(key="1", ex="x.dot(x)")
    assert asserts.expr_get_symbols_functions(expr="1") == (["x"], [])
    _ = asserts.eval_single(key="1", kvargs=((1, 2, 3),))
    _ = asserts.eval_single(key="1", kvargs={"x": (1, 2, 3)})
    assert asserts.symbol("x").dot(asserts.symbol("x")) == 3.0, "Initialized as ones"
    assert asserts.symbol("x").dot(np.array((0, 1, 0), dtype=float)) == 1.0, "Initialized as ones"
    asserts.symbol("y", length=3)  # a vector without explicit components
    assert all(asserts.symbol("y")[i] == 1.0 for i in range(3))
    y = asserts.symbol("y")
    assert y.dot(y) == 3.0, "Initialized as ones"


def test_do_assert(show: bool):
    cases = Cases(spec=Path(__file__).parent / "data" / "BouncingBall3D" / "BouncingBall3D.cases")
    case = cases.case_by_name("restitutionAndGravity")
    assert case is not None
    case.run()
    # res = Results(file=Path(__file__).parent / "data" / "BouncingBall3D" / "restitutionAndGravity.js5")
    res = case.res
    assert isinstance(res, Results)
    # cases = res.case.cases
    assert res.case is not None
    assert res.case.name == "restitutionAndGravity"
    assert cases.file.name == "BouncingBall3D.cases"
    for key, inf in res.inspect().items():
        print(key, inf["len"], inf["range"])
    info = res.inspect()["bb.v"]
    assert info["len"] == 301, f"Found {info['len']}"
    assert info["range"] == [0.0, 3.0]
    asserts = cases.assertion
    # asserts.vector('x', (1,0,0))
    # asserts.vector('v', (0,1,0))
    _ = asserts.expr(key="0", ex="x.dot(v)")  # additional expression (not in .cases)
    assert asserts._syms["0"] == ["x", "v"]
    assert all(asserts.symbol("x")[i] == np.ones(3, dtype=float)[i] for i in range(3)), "Initialized to ones"
    assert asserts.eval_single(key="0", kvargs=((1, 2, 3), (4, 5, 6))) == 32
    assert asserts.expr(key="1") == "g==1.5"
    assert asserts.temporal(key="1")["type"] == Temporal.A
    assert asserts.syms(key="1") == ["g"]
    assert asserts.do_assert(key="1", result=res)
    assert asserts.assertions(key="1") == {
        "passed": True,
        "details": None,
        "case": None,
    }
    _ = asserts.do_assert(key="2", result=res)
    assert asserts.assertions(key="2") == {
        "passed": True,
        "details": None,
        "case": None,
    }, f"Found {asserts.assertions(key='2')}"
    if show:
        res.plot_time_series(comp_var=["bb.x[2]"])
    _ = asserts.do_assert(key="3", result=res)
    assert asserts.assertions(key="3") == {
        "passed": True,
        "details": "@2.22",
        "case": None,
    }, f"Found {asserts.assertions(key='3')}"
    _ = asserts.do_assert(key="4", result=res)
    assert asserts.assertions(key="4") == {
        "passed": True,
        "details": "@1.1547 (interpolated)",
        "case": None,
    }, f"Found {asserts.assertions(key='4')}"
    count = asserts.do_assert_case(result=res)  # do all
    assert count == [4, 4], "Expected 4 of 4 passed"


if __name__ == "__main__":
    retcode = pytest.main(args=["-rA", "-v", __file__, "--show", "False"])
    assert retcode == 0, f"Non-zero return code {retcode}"
    # import os
    # os.chdir(Path(__file__).parent.absolute() / "test_working_directory")
    # test_temporal()
    # test_ast( show=True)
    # test_globals_locals()
    # test_assertion()
    # test_assertion_spec()
    # test_vector()
    # test_do_assert(show=True)
