from sympy import Symbol, sympify
from sympy.vector import CoordSys3D


class Assertion:
    """Define Assertion objects for checking expectations with respect to simulation results.

    The class uses sympy, where the symbols are expected to be results variables,
    as defined in the variable definition section of Cases.
    These can then be combined to boolean expressions and be checked against
    single points of a data series (see `assert_single()` or against a whole series (see `assert_series()`).

    The symbols used in the expression are accessible as `.symbols` (dict of `name : symbol`).
    All symbols used by all defined Assertion objects are accessible as Assertion.ns

    Args:
        expr (str): The boolean expression definition as string.
            Any unknown symbol within the expression is defined as sympy.Symbol and is expected to match a variable.
    """

    ns: dict = {}
    N = CoordSys3D("N")

    def __init__(self, expr: str):
        self._expr = Assertion.do_sympify(expr)
        self._symbols = self.get_symbols()
        # t = Symbol('t', positive=True) # default symbol for time
        # self._symbols.update( {'t':t})
        Assertion.update_namespace(self._symbols)

    @property
    def expr(self):
        return self._expr

    @property
    def symbols(self):
        return self._symbols

    def symbol(self, name: str):
        try:
            return self._symbols[name]
        except KeyError:
            return None

    @staticmethod
    def do_sympify(_expr):
        """Evaluate the initial expression as sympy expression.
        Return the sympified expression or throw an error if sympification is not possible.
        """
        if "==" in _expr:
            raise ValueError("'==' cannot be used to check equivalence. Use 'a-b' and check against 0") from None
        try:
            expr = sympify(_expr)
        except ValueError as err:
            raise Exception(f"Something wrong with expression {_expr}: {err}|. Cannot sympify.") from None
        return expr

    def get_symbols(self):
        """Get the atom symbols used in the expression. Return the symbols as dict of `name : symbol`."""
        syms = self._expr.atoms(Symbol)
        return {s.name: s for s in syms}

    @staticmethod
    def casesvar_to_symbol(variables: dict):
        """Register all variables defined in cases as sympy symbols.

        Args:
            variables (dict): The variables dict as registered in Cases
        """
        for var in variables:
            sym = sympify(var)
            Assertion.update_namespace({var: sym})

    @staticmethod
    def reset():
        """Reset the global dictionary of symbols used by all Assertions."""
        Assertion.ns = {}

    @staticmethod
    def update_namespace(sym: dict):
        """Ensure that the symbols of this expression are registered in the global namespace `ns`
        and include all global namespace symbols in the symbol list of this class.

        Args:
            sym (dict): dict of {symbol-name : symbol}
        """
        for n, s in sym.items():
            if n not in Assertion.ns:
                Assertion.ns.update({n: s})

    #         for name, sym in Assertion.ns:
    #             if name not in self._symbols:
    #                 sym = sympify( name)
    #                 self._symbols.update( {name : sym})

    @staticmethod
    def vector(x: tuple | list):
        assert isinstance(x, (tuple, list)) and len(x) == 3, f"Vector of length 3 expected. Found {x}"
        return x[0] * Assertion.N.i + x[1] * Assertion.N.j + x[2] * Assertion.N.k  # type: ignore

    def assert_single(self, subs: list[tuple]):
        """Perform assertion on a single data point.

        Args:
            subs (list): list of tuples of `(variable-name, value)`,
                where the independent variable (normally the time) shall be listed first.
                All required variables for the evaluation shall be listed.
                The variable-name provided as string is translated to its symbol before evaluation.
        Results:
            (bool) result of assertion
        """
        _subs = [(self._symbols[s[0]], s[1]) for s in subs]
        return self._expr.subs(_subs)

    def assert_series(self, subs: list[tuple], ret: str = "bool"):
        """Perform assertion on a (time) series.

        Args:
            subs (list): list of tuples of `(variable-symbol, list-of-values)`,
                where the independent variable (normally the time) shall be listed first.
                All required variables for the evaluation shall be listed
                The variable-name provided as string is translated to its symbol before evaluation.
            ret (str)='bool': Determines how to return the result of the assertion:

                `bool` : True if any element of the assertion of the series is evaluated to True
                `bool-list` : List of True/False for each data point in the series
                `interval` : tuple of interval of indices for which the assertion is True
                `count` : Count the number of points where the assertion is True
        Results:
            bool, list[bool], tuple[int] or int, depending on `ret` parameter.
            Default: True/False on whether at least one record is found where the assertion is True.
        """
        _subs = [(self._symbols[s[0]], s[1]) for s in subs]
        length = len(subs[0][1])
        result = [False] * length

        for i in range(length):
            s = []
            for k in range(len(_subs)):  # number of variables in substitution
                s.append((_subs[k][0], _subs[k][1][i]))
            res = self._expr.subs(s)
            if res:
                result[i] = True
        if ret == "bool":
            return True in result
        elif ret == "bool-list":
            return result
        elif ret == "interval":
            if True in result:
                idx0 = result.index(True)
                if False in result[idx0:]:
                    return (idx0, idx0 + result[idx0:].index(False))
                else:
                    return (idx0, length)
            else:
                return None
        elif ret == "count":
            return sum(x for x in result)
        else:
            raise ValueError(f"Unknown return type '{ret}'") from None
