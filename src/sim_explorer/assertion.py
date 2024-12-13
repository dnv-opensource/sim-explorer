import ast
from enum import Enum
from typing import Any, Callable, Iterable

import numpy as np


class Temporal(Enum):
    UNDEFINED = 0
    A = 1
    ALWAYS = 1
    F = 2
    FINALLY = 2
    T = 3
    TIME = 3


class Assertion:
    """Defines a common Assertion object for checking expectations with respect to simulation results.

    The class uses eval/exec, where the symbols are

    * the independent variable t (time)
    * all variables defined as variables in cases file,
    * functions from any loaded module

    These can then be combined to boolean expressions and be checked against
    single points of a data series (see `assert_single()` or against a whole series (see `assert_series()`).

    Single assertion expressions are stored in the dict self._expr with their key as given in cases file.
    All assertions have a common symbol basis in self._symbols

    Args:
        funcs (dict) : Dictionary of module : <list-of-functions> of allowed functions inside assertion expressions.
    """

    def __init__(self, imports: dict | None = None):
        if imports is None:
            self._imports = {"math": ["sin", "cos", "sqrt"]}  # default imports
        else:
            self._imports = imports
        self._symbols = {"t": 1}  # list of all symbols and their length
        self._functions: list = []  # list of all functions used in expressions
        # per expression as key:
        self._syms: dict = {}  # the symbols used in expression
        self._funcs: dict = {}  # the functions used in expression
        self._expr: dict = {}  # the raw expression
        self._compiled: dict = {}  # the byte-compiled expression
        self._temporal: dict = {}  # additional information for evaluation as time series
        self._description: dict = {}
        self._cases_variables: dict = {}  # is set to Cases.variables when calling self.register_vars
        self._assertions: dict = {}  # assertion results, set by do_assert

    def info(self, sym: str, typ: str = "instance") -> str | int:
        """Retrieve detailed information related to the registered symbol 'sym'."""
        if sym == "t":  # the independent variable
            return {"instance": "none", "variable": "t", "length": 1, "model": "none"}[typ]  # type: ignore

        parts = sym.split("_")
        var = parts.pop()
        while True:
            if var in self._cases_variables:  # found the variable
                if not len(parts):  # abbreviated variable without instance information
                    assert len(self._cases_variables[var]["instances"]) == 1, f"Non-unique instance for variable {var}"
                    instance = self._cases_variables[var]["instances"][0]  # use the unique instance
                else:
                    instance = parts[0] + "".join("_" + x for x in parts[1:])
                    assert instance in self._cases_variables[var]["instances"], f"No instance {instance} of {var}"
                break
            else:
                if not len(parts):
                    raise KeyError(f"The symbol {sym} does not seem to represent a registered variable") from None
                var = parts.pop() + "_" + var
        if typ == "instance":  # get the instance
            return instance
        elif typ == "variable":  # get the generic variable name
            return var
        elif typ == "length":  # get the number of elements
            return len(self._cases_variables[var]["variables"])
        elif typ == "model":  # get the basic (FMU) model
            return self._cases_variables[var]["model"]
        else:
            raise KeyError(f"Unknown typ {typ} within info()") from None

    def symbol(self, name: str, length: int = 1):
        """Get or set a symbol.

        Args:
            key (str): The symbol identificator (name)
            length (int)=1: Optional length. 1,2,3 allowed.
               Vectors are registered as <key>#<index> + <key> for the whole vector

        Returns: The sympy Symbol corresponding to the name 'key'
        """
        try:
            sym = self._symbols[name]
        except KeyError:  # not yet registered
            assert length > 0, f"Vector length should be positive. Found {length}"
            if length > 1:
                self._symbols.update({name: np.ones(length, dtype=float)})  # type: ignore
            else:
                self._symbols.update({name: 1})
            sym = self._symbols[name]
        return sym

    def expr(self, key: str, ex: str | None = None):
        """Get or set an expression.

        Args:
            key (str): the expression identificator
            ex (str): Optional expression as string. If not None, register/update the expression as key

        Returns: the sympified expression
        """

        def make_func(name: str, args: dict, body: str):
            """Make a python function from the body."""
            code = "def _" + name + "("
            for a in args:
                code += a + ", "
            code += "):\n"
            #            code += "    print('dir:', dir())\n"
            code += "    return " + body + "\n"
            return code

        if ex is None:  # getter
            try:
                ex = self._expr[key]
            except KeyError as err:
                raise Exception(f"Expression with identificator {key} is not found") from err
            else:
                return ex
        else:  # setter
            syms, funcs = self.expr_get_symbols_functions(ex)
            self._syms.update({key: syms})
            self._funcs.update({key: funcs})
            code = make_func(key, syms, ex)
            try:
                #               print("GLOBALS", globals())
                #               print("LOCALS", locals())
                #               exec( code, globals(), locals())  # compile using the defined symbols
                compiled = compile(code, "<string>", "exec")  # compile using the defined symbols
            except ValueError as err:
                raise Exception(f"Something wrong with expression {ex}: {err}|. Cannot compile.") from None
            else:
                self._expr.update({key: ex})
                self._compiled.update({key: compiled})
            # print("KEY", key, ex, syms, compiled)
            return compiled

    def syms(self, key: str):
        """Get the symbols of the expression 'key'."""
        try:
            syms = self._syms[key]
        except KeyError as err:
            raise Exception(f"Expression {key} was not found") from err
        else:
            return syms

    def expr_get_symbols_functions(self, expr: str) -> tuple:
        """Get the symbols used in the expression.

        1. Symbol as listed in expression and function body. In general <instant>_<variable>[<index>]
        2. Argument as used in the argument list of the function call. In general <instant>_<variable>
        3. Fully qualified symbol: (<instant>, <variable>, <index>|None)

        If there is only a single instance, it is allowed to skip <instant> in 1 and 2

        Returns
        -------
            tuple of (syms, funcs),
               where syms is a dict {<instant>_<variable> : fully-qualified-symbol tuple, ...}

               funcs is a list of functions used in the expression.
        """

        def ast_walk(node: ast.AST, syms: list | None = None, funcs: list | None = None):
            """Recursively walk an ast node (width first) and collect symbol and function names."""
            if syms is None:
                syms = []
            if funcs is None:
                funcs = []
            for n in ast.iter_child_nodes(node):
                if isinstance(n, ast.Name):
                    if n.id in self._symbols:
                        if isinstance(syms, list) and n.id not in syms:
                            syms.append(n.id)
                    elif isinstance(node, ast.Call):
                        if isinstance(funcs, list) and n.id not in funcs:
                            funcs.append(n.id)
                    else:
                        raise KeyError(f"Unknown symbol {n.id}")
                syms, funcs = ast_walk(n, syms, funcs)
            return (syms, funcs)

        if expr in self._expr:  # assume that actually a key is queried
            expr = self._expr[expr]
        syms, funcs = ast_walk(ast.parse(expr, "<string>", "exec"))
        syms = sorted(syms, key=list(self._symbols.keys()).index)
        return (syms, funcs)

    def temporal(self, key: str, typ: Temporal | str | None = None, args: tuple | None = None):
        """Get or set a temporal instruction.

        Args:
            key (str): the assert key
            typ (str): optional temporal type
        """
        if typ is None:  # getter
            try:
                temp = self._temporal[key]
            except KeyError as err:
                raise Exception(f"Temporal instruction for {key} is not found") from err
            else:
                return temp
        else:  # setter
            if isinstance(typ, Temporal):
                self._temporal.update({key: {"type": typ, "args": args}})
            elif isinstance(typ, str):
                self._temporal.update({key: {"type": Temporal[typ], "args": args}})
            else:
                raise ValueError(f"Unknown temporal type {typ}") from None
            return self._temporal[key]

    def description(self, key: str, descr: str | None = None):
        """Get or set a description."""
        if descr is None:  # getter
            try:
                _descr = self._description[key]
            except KeyError as err:
                raise Exception(f"Description for {key} not found") from err
            else:
                return _descr
        else:  # setter
            self._description.update({key: descr})
            return descr

    def assertions(self, key: str, res: bool | None = None, details: str | None = None):
        """Get or set an assertion result."""
        if res is None:  # getter
            try:
                _res = self._assertions[key]
            except KeyError as err:
                raise Exception(f"Assertion results for {key} not found") from err
            else:
                return _res
        else:  # setter
            self._assertions.update({key: {"passed": res, "details": details}})
            return self._assertions[key]

    def register_vars(self, variables: dict):
        """Register the variables in varnames as symbols.

        Can be used directly from Cases with varnames = tuple( Cases.variables.keys())
        """
        self._cases_variables = variables  # remember the full dict for retrieval of details
        for key, info in variables.items():
            for inst in info["instances"]:
                if len(info["instances"]) == 1:  # the instance is unique
                    self.symbol(key, len(info["variables"]))  # we allow to use the 'short name' if unique
                self.symbol(inst + "_" + key, len(info["variables"]))  # fully qualified name can always be used

    def make_locals(self, loc: dict):
        """Adapt the locals with 'allowed' functions."""
        from importlib import import_module

        for modulename, funclist in self._imports.items():
            module = import_module(modulename)
            for func in funclist:
                loc.update({func: getattr(module, func)})
        loc.update({"np": import_module("numpy")})
        return loc

    def _eval(self, func: Callable, kvargs: dict | list | tuple):
        """Call a function of multiple arguments and return the single result.
        All internal vecor arguments are transformed to np.arrays.
        """
        if isinstance(kvargs, dict):
            for k, v in kvargs.items():
                if isinstance(v, Iterable):
                    kvargs[k] = np.array(v, float)
            return func(**kvargs)
        elif isinstance(kvargs, list):
            for i, v in enumerate(kvargs):
                if isinstance(v, Iterable):
                    kvargs[i] = np.array(v, dtype=float)
            return func(*kvargs)
        elif isinstance(kvargs, tuple):
            _args = []  # make new, because tuple is not mutable
            for v in kvargs:
                if isinstance(v, Iterable):
                    _args.append(np.array(v, dtype=float))
                else:
                    _args.append(v)
            return func(*_args)

    def eval_single(self, key: str, kvargs: dict | list | tuple):
        """Perform assertion of 'key' on a single data point.

        Args:
            key (str): The expression identificator to be used
            kvargs (dict|list|tuple): variable substitution kvargs as dict or args as tuple/list
                All required variables for the evaluation shall be listed.
        Results:
            (bool) result of assertion
        """
        assert key in self._compiled, f"Expression {key} not found"
        loc = self.make_locals(locals())
        exec(self._compiled[key], loc, loc)
        # print("kvargs", kvargs, self._syms[key], self.expr_get_symbols_functions(key))
        return self._eval(locals()["_" + key], kvargs)

    def eval_series(self, key: str, data: list[list], ret: float | str | Callable | None = None):
        """Perform assertion on a (time) series.

        Args:
            key (str): Expression identificator
            data (tuple): data table with arguments as columns and series in rows,
                where the independent variable (normally the time) shall be listed first in each row.
                All required variables for the evaluation shall be listed (columns)
                The names of variables correspond to self._syms[key], but is taken as given here.
            ret (str)='bool': Determines how to return the result of the assertion:

                float : Linear interpolation of result at the given float time
                `bool` : (time, True/False) for first row evaluating to True.
                `bool-list` : (times, True/False) for all data points in the series
                `A` : Always true for the whole time-series. Same as 'bool'
                `F` : is True at end of time series.
                Callable : run the given callable on times, expr(data)
                None : Use the internal 'temporal(key)' setting
        Results:
            tuple of (time(s), value(s)), depending on `ret` parameter
        """
        times = []  # return the independent variable values (normally time)
        results = []  # return the scalar results at all times
        bool_type = (ret is None and self.temporal(key)["type"] in (Temporal.A, Temporal.F)) or (
            isinstance(ret, str) and (ret in ["A", "F"] or ret.startswith("bool"))
        )
        argnames = self._syms[key]
        loc = self.make_locals(locals())
        exec(self._compiled[key], loc, loc)  # the function is then available as _<key> among locals()
        func = locals()["_" + key]  # scalar function of all used arguments
        _temp = self._temporal[key]["type"] if ret is None else Temporal.UNDEFINED

        for row in data:
            if not isinstance(row, Iterable):  # can happen if the time itself is evaluated
                time = row
                row = [row]
            elif "t" not in argnames:  # the independent variable is not explicitly used in the expression
                time = row[0]
                row = row[1:]
                assert len(row), f"Time data in eval_series seems to be lacking. Data:{data}, Argnames:{argnames}"
            else:  # time used also explicitly in the expression
                time = row[0]
            res = func(*row)
            if bool_type:
                res = bool(res)

            times.append(time)
            results.append(res)  # Note: res is always a scalar result

        if (ret is None and _temp == Temporal.A) or (isinstance(ret, str) and ret in ("A", "bool")):  # always True
            for t, v in zip(times, results, strict=False):
                if v:
                    return (t, True)
            return (times[-1], False)
        elif (ret is None and _temp == Temporal.F) or (isinstance(ret, str) and ret == "F"):  # finally True
            t_true = times[-1]
            for t, v in zip(times, results, strict=False):
                if v and t_true > t:
                    t_true = t
                elif not v and t_true < t:  # detected False after expression became True
                    t_true = times[-1]
            return (t_true, t_true < times[-1])
        elif isinstance(ret, str) and ret == "bool-list":
            return (times, results)
        elif (ret is None and _temp == Temporal.T) or (isinstance(ret, float)):
            if isinstance(ret, float):
                t0 = ret
            else:
                assert len(self._temporal[key]["args"]), "Need a temporal argument (time at which to interpolate)"
                t0 = self._temporal[key]["args"][0]
            #     idx = min(range(len(times)), key=lambda i: abs(times[i]-t0))
            #     print("INDEX", t0, idx, results[idx-10:idx+10])
            #     return (t0, results[idx])
            # else:
            interpolated = np.interp(t0, times, results)
            return (t0, bool(interpolated) if all(isinstance(res, bool) for res in results) else interpolated)
        elif callable(ret):
            return (times, ret(results))
        else:
            raise ValueError(f"Unknown return type '{ret}'") from None

    def do_assert(self, key: str, result: Any):
        """Perform assert action 'key' on data of 'result' object."""
        assert isinstance(key, str) and key in self._temporal, f"Assertion key {key} not found"
        from sim_explorer.case import Results

        assert isinstance(result, Results), f"Results object expected. Found {result}"
        inst = []
        var = []
        for sym in self._syms[key]:
            inst.append(self.info(sym, "instance"))
            var.append(self.info(sym, "variable"))
        assert len(var), "No variables to retrieve"
        if var[0] == "t":  # the independent variable is always the first column in data
            inst.pop(0)
            var.pop(0)

        data = result.retrieve(zip(inst, var, strict=False))
        res = self.eval_series(key, data, ret=None)
        if self._temporal[key]["type"] == Temporal.A:
            self.assertions(key, res[1])
        elif self._temporal[key]["type"] == Temporal.F:
            self.assertions(key, res[1], f"@{res[0]}")
        elif self._temporal[key]["type"] == Temporal.T:
            self.assertions(key, res[1], f"@{res[0]} (interpolated)")
        return res[1]

    def do_assert_case(self, result: Any) -> list[int]:
        """Perform all assertions defined for the case related to the result object."""
        count = [0, 0]
        for key in result.case.asserts:
            self.do_assert(key, result)
            count[0] += self._assertions[key]["passed"]
            count[1] += 1
        return count

    def report(self, case: Any = None):
        """Report on all registered asserts.
        If case denotes a case object, only the results for this case are reported.
        """

        def do_report(key: str):
            return {
                "key": key,
                "description": self._description[key],
                "temporal": self._temporal[key],
                "expression": self._expr[key],
                "passed": self._assertions[key].get("passed", "unknown"),
                "assert-details": self._assertions[key].get("passed", "none"),
            }

        from sim_explorer.case import Case

        if isinstance(case, Case):
            for key in case.asserts:
                yield do_report(key)
        else:  # report all
            for key in self._assertions:
                yield do_report(key)
