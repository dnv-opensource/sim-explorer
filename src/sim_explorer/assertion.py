from typing import Any, Callable, Iterable

import numpy as np
from sympy import Symbol, lambdify, sympify
from sympy.vector import (
    CoordSys3D,  # type: ignore
)
from sympy.vector.vector import Vector

N = CoordSys3D("N")  # global cartesian coordinate system


class Assertion:
    """Defines a common Assertion object for checking expectations with respect to simulation results.

    The class uses sympy, where the symbols are

    * all variables defined as variables in cases file,
    * the independent variable t (time)
    * other sympy symbols

    These can then be combined to boolean expressions and be checked against
    single points of a data series (see `assert_single()` or against a whole series (see `assert_series()`).

    Single assertion expressions are stored in the dict self._expr with their key as given in cases file.
    All assertions have a common symbol basis in self._symbols

    Args:
        expr (str): The boolean expression definition as string.
            Any unknown symbol within the expression is defined as sympy.Symbol and is expected to match a variable.
    """

    def __init__(self, prefer_lambdify=True):
        self.prefer_lambdify = prefer_lambdify
        self._symbols = {"t": Symbol("t", positive=True)}  # all symbols by all expressions
        # per expression as key:
        self._syms = {}  # the symbols used in expression
        self._expr = {}  # the expression. Evaluation with .subs
        self._lambdified = {}  # the lambdified expression. Evaluated with values in correct order
        self._temporal = {}  # additional information for evaluation as time series

    def symbol(self, key: str, length: int = 1):
        """Get or set a symbol.

        Args:
            key (str): The symbol identificator (name)
            length (int)=1: Optional length. 1,2,3 allowed.
               Vectors are registered as <key>#<index> + <key> for the whole vector

        Returns: The sympy Symbol corresponding to the name 'key'
        """
        try:
            sym = self._symbols[key]
        except KeyError:  # not yet registered
            if length != 1:
                assert length > 1 and length < 4, f"Vector of size {length} is currently not implemented"
                for i in range(length):
                    _ = self.symbol(key + "#" + str(i))  # define components

                sym = self.symbol(key + "#0") * N.i + self.symbol(key + "#1") * N.j
                if length > 2:
                    sym += self.symbol(key + "#2") * N.k
            else:
                sym = Symbol(key)
            self._symbols.update({key: sym})
        return sym

    def vector(self, key: str, coordinates: Iterable):
        """Update the vector using the provided coordinates."""
        assert key in self._symbols, f"Vector symbol {key} not found"
        sym = Vector.zero
        if len(coordinates) >= 0:
            sym += coordinates[0] * N.i
        if len(coordinates) >= 1:
            sym += coordinates[1] * N.j
        if len(coordinates) >= 2:
            sym += coordinates[2] * N.k
        self._symbols.update({key: sym})
        return sym

    def expr(self, key: str, ex: str | None = None):
        """Get or set an expression.

        Args:
            key (str): the expression identificator
            ex (str): Optional expression as string. If not None, register/update the expression as key

        Returns: the sympified expression
        """
        if ex is None:  # getter
            try:
                if self.prefer_lambdify:
                    ex = self._lambdified[key]
                else:
                    ex = self._expr[key]
            except KeyError as err:
                raise Exception(f"Expression with identificator {key} is not found") from err
            else:
                return ex
        else:  # setter
            if "==" in ex:
                raise ValueError("Cannot use '==' to check equivalence. Use 'a-b' and check against 0") from None
            try:
                expr = sympify(ex, locals=self._symbols)  # compile using the defined symbols
            except ValueError as err:
                raise Exception(f"Something wrong with expression {expr}: {err}|. Cannot sympify.") from None
            syms = self.expr_get_symbols(expr)
            self._syms.update({key: syms})
            self._expr.update({key: expr})
            print("KEY", key, expr, syms.values())
            if isinstance(expr, Vector):
                self._lambdified.update(
                    {
                        key: [
                            lambdify(syms.values(), expr.dot(N.i)),
                            lambdify(syms.values(), expr.dot(N.j)),
                            lambdify(syms.values(), expr.dot(N.k)),
                        ]
                    }
                )
            else:
                self._lambdified.update({key: lambdify(syms.values(), expr)})
            if self.prefer_lambdify:
                return self._lambdified[key]
            else:
                return expr

    def syms(self, key: str):
        """Get the symbols of the expression 'key'."""
        try:
            syms = self._syms[key]
        except KeyError as err:
            raise Exception(f"Expression {key} was not found") from err
        else:
            return syms

    def expr_get_symbols(self, expr: Any):
        """Get the atom symbols used in the expression. Return the symbols as dict of `name : symbol`."""
        if isinstance(expr, str):  # registered expression
            expr = self._expr[expr]
        _syms = expr.atoms(Symbol)

        syms = {}
        for n, s in self._symbols.items():  # do it this way to keep the order as in self._symbols
            if s in _syms:
                syms.update({n: s})
        if len(syms) != len(_syms):  # something missing
            for s in _syms:
                assert s in syms.values(), f"Symbol {s.name} not registered"
        return syms

    def temporal(self, key: str, temporal: tuple | None = None):
        """Get or set a temporal instruction."""
        if temporal is None:  # getter
            try:
                temp = self._temporal[key]
            except KeyError as err:
                raise Exception(f"Temporal instruction for {key} is not found") from err
            else:
                return temp
        else:  # setter
            self._temporal.update({key: temporal})
            return temporal

    def register_vars(self, vars: dict):
        """Register the variables in varnames as symbols.

        Can be used directly from Cases with varnames = tuple( Cases.variables.keys())
        """
        for key, info in vars.items():
            for inst in info["instances"]:
                if len(info["instances"]) == 1:  # the instance is unique
                    varname = key
                else:
                    varname = inst + "." + key
                if len(info["variables"]) == 1:
                    self.symbol(varname)
                elif 1 < len(info["variables"]) <= 3:
                    self.symbol(varname, len(info["variables"]))  # a vector
                else:
                    raise ValueError(f"Symbols of length {len( info['variables'])} not implemented") from None

    def eval_single(self, key: str, subs: Iterable):
        """Perform assertion of 'key' on a single data point.

        Args:
            key (str): The expression identificator to be used
            subs (Iterable): variable substitution list - tuple of values in order of arguments,
                where the independent variable (normally the time) shall be listed first.
                All required variables for the evaluation shall be listed.
                For the subs method the variable symbols are calculated from the definition before evaluation.
        Results:
            (bool) result of assertion
        """
        expr = self._expr[key]
        if self.prefer_lambdify:
            if isinstance(expr, list):
                return [lam(*subs) for lam in self._lambdified[key]]
            else:
                return self._lambdified[key](*subs)
        else:
            _subs = zip(self.expr_get_symbols(expr).values(), subs, strict=False)
            return expr.subs(_subs)

    def eval_series(self, key: str, subs: Iterable, ret: str | Callable = "bool"):
        """Perform assertion on a (time) series.

        Args:
            key (str): Expression identificator
            subs (tuple): substitution list - tuple of tuples of values,
                where the independent variable (normally the time) shall be listed first in each row.
                All required variables for the evaluation shall be listed
                For the subs method the variable symbols are calculated from the definition before evaluation.
            ret (str)='bool': Determines how to return the result of the assertion:

                float : Linear interpolation of result at the gi
                `bool` : True if any element of the assertion of the series is evaluated to True
                `bool-list` : List of True/False for each data point in the series
                `bool-interval` : tuple of interval of indices for which the assertion is True
                `bool-count` : Count the number of points where the assertion is True
                `G` : Always true for the whole time-series
                `F` : May be False initially, but becomes True as some point in time and remains True.
                Callable : run the given callable on the series
            lambdified (bool)=True: Use the lambdified expression. Otherwise substitution is used
        Results:
            bool, list[bool], tuple[int] or int, depending on `ret` parameter.
            Default: True/False on whether at least one record is found where the assertion is True.
        """
        result = []
        bool_type = not isinstance(ret, (Callable, float)) and (ret.startswith("bool") or ret in ("G", "F"))
        syms = self._syms[key]
        if self.prefer_lambdify:
            expr = self._lambdified[key]
        else:
            expr = self._expr[key]

        for row in subs:
            if not isinstance(row, Iterable):  # can happen if the time itself is evaluated
                row = [row]
            if "t" not in syms:  # the independent variable is not explicitly used in the expression
                time = row[0]
                row = row[1:]
                assert len(row), "Time data in eval_series seems to be lacking"
            if self.prefer_lambdify:
                if isinstance(expr, list):
                    print("TYPE", type(expr[0]), row, expr[0].__doc__)
                    res = [ex(*row) for ex in expr]
                else:
                    res = expr(*row)
            else:
                _subs = zip(syms.values(), row, strict=False)
                res = expr.subs(_subs)
            if bool_type:
                res = bool(res)
            if "t" in syms:
                result.append(res)
            else:
                result.append([time, res])

        if ret == "bool":
            return True in result
        elif ret == "bool-list":
            return result
        elif ret == "bool-interval":
            if True in result:
                idx0 = result.index(True)
                if False in result[idx0:]:
                    return (idx0, idx0 + result[idx0:].index(False))
                else:
                    return (idx0, len(subs))
            else:
                return None
        elif ret == "bool-count":
            return sum(x for x in result)
        elif ret == "G":  # globally True
            return all(x for x in result)
        elif ret == "F":  # finally True
            fin = False
            for x in result:
                if x and not fin:
                    fin = True
                elif not x and fin:  # detected False after expression became True
                    return False
            return fin
        elif isinstance(ret, float):  # linear interpolation of results at time=ret
            res = np.array(result, float)
            _t = res[:, 0]
            interpolated = [ret]
            for c in range(1, len(res[0])):
                _x = res[:, c]
                interpolated.append(np.interp(ret, _t, _x))
            return interpolated
        elif isinstance(ret, Callable):
            return ret(result)
        else:
            raise ValueError(f"Unknown return type '{ret}'") from None

    def auto_assert(self, key: str, result: Any):
        """Perform assert action 'key' on data of 'result' object."""
        assert isinstance(key, str) and key in self._temporal, f"Assertion key {key} not found"
        from sim_explorer.case import Results

        assert isinstance(result, Results), f"Results object expected. Found {result}"
        _ = self._syms[key]
