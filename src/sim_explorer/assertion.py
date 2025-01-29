import ast
from collections.abc import Callable, Iterable, Iterator
from logging import warning
from types import CodeType
from typing import Any, cast

import numpy as np

from sim_explorer.case import Case, Results
from sim_explorer.models import AssertionResult, Temporal
from sim_explorer.utils.types import (
    TDataColumn,
    TDataRow,
    TDataTable,
    TNumeric,
    TTimeColumn,
    TValue,
)


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

    def __init__(self, imports: dict[str, list[str]] | None = None) -> None:
        if imports is None:
            self._imports = {"math": ["sin", "cos", "sqrt"]}  # default imports
        else:
            self._imports = imports
        #: list of all symbols and their length
        # TODO @EisDNV: The meaning of self._symbols is not clear to me.
        #      On one hand, you write that it is a list of all symbols and their length,
        #      but on the other hand, in method `symbol` you add numpy array as value for a symbol.
        #      I hence had difficulties to derive the correct type hint for this attribute
        #      (and with that, difficulties to understand the meaning of this attribute).
        #      ClaasRostock, 2025-01-27
        self._symbols: dict[str, int | np.ndarray[Any, np.dtype[np.float64]]] = {"t": 1}
        self._functions: list[str] = []  # list of all functions used in expressions
        # per expression as key:
        self._syms: dict[str, list[str]] = {}  # the symbols used in expression
        self._funcs: dict[str, list[str]] = {}  # the functions used in expression
        self._expr: dict[str, str] = {}  # the raw expression
        self._compiled: dict[str, CodeType] = {}  # the byte-compiled expression
        self._temporal: dict[str, dict[str, Any]] = {}  # additional information for evaluation as time series
        self._description: dict = {}
        self._cases_variables: dict[str, dict[str, Any]] = {}  #: set to Cases.variables when calling self.register_vars
        self._assertions: dict = {}  #: assertion results, set by do_assert

    def info(self, sym: str, typ: str = "instance") -> str | int:
        """Retrieve detailed information related to the registered symbol 'sym'."""
        if sym == "t":  # the independent variable
            sym_info: dict[str, str | int] = {
                "instance": "none",
                "variable": "t",
                "length": 1,
                "model": "none",
            }
            return sym_info[typ]

        parts = sym.split("_")
        var = parts.pop()
        while True:
            if var in self._cases_variables:  # found the variable
                if not len(parts):  # abbreviated variable without instance information
                    assert len(self._cases_variables[var]["instances"]) == 1, f"Non-unique instance for variable {var}"
                    instance = self._cases_variables[var]["instances"][0]  # use the unique instance
                else:
                    instance = parts[0] + "".join(f"_{x}" for x in parts[1:])
                    assert instance in self._cases_variables[var]["instances"], f"No instance {instance} of {var}"
                break
            if not len(parts):
                raise KeyError(f"The symbol {sym} does not seem to represent a registered variable") from None
            var = f"{parts.pop()}_{var}"
        if typ == "instance":  # get the instance
            return instance
        if typ == "variable":  # get the generic variable name
            return var
        if typ == "length":  # get the number of elements
            return len(self._cases_variables[var]["refs"])
        if typ == "model":  # get the basic (FMU) model
            return self._cases_variables[var]["model"]
        raise KeyError(f"Unknown typ {typ} within info()") from None

    def symbol(self, name: str, length: int = 1) -> Any:  # noqa: ANN401
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
                self._symbols.update({name: np.ones(length, dtype=float)})
            else:
                self._symbols.update({name: 1})
            sym = self._symbols[name]
        return sym

    def expr(self, key: str, ex: str | None = None) -> str | CodeType:
        """Get or set an expression.

        Args:
            key (str): the expression identificator
            ex (str): Optional expression as string. If not None, register/update the expression as key

        Returns: the sympified expression
        """

        def make_func(name: str, args: list[str], body: str) -> str:
            """Make a python function from the body."""
            code = f"def _{name}("
            for a in args:
                code += f"{a}, "
            code += "):\n"
            code += f"    return {body}" + "\n"
            return code

        if ex is None:  # getter
            try:
                ex = self._expr[key]
            except KeyError as e:
                raise KeyError(f"Expression with identificator {key} is not found") from e
            else:
                return ex
        else:  # setter
            syms, funcs = self.expr_get_symbols_functions(expr=ex)
            self._syms.update({key: syms})
            self._funcs.update({key: funcs})
            code = make_func(name=key, args=syms, body=ex)
            try:
                # exec( code, globals(), locals())  # compile using the defined symbols  # noqa: ERA001
                compiled: CodeType = compile(code, "<string>", "exec")  # compile using the defined symbols
            except ValueError as e:
                raise ValueError(f"Something wrong with expression {ex}. Cannot compile.") from e
            else:
                self._expr.update({key: ex})
                self._compiled.update({key: compiled})
            # print("KEY", key, ex, syms, compiled)  # noqa: ERA001
            return compiled

    def syms(self, key: str) -> list[str]:
        """Get the symbols of the expression 'key'."""
        try:
            syms = self._syms[key]
        except KeyError as e:
            raise KeyError(f"Expression {key} was not found") from e
        else:
            return syms

    def expr_get_symbols_functions(self, expr: str) -> tuple[list[str], list[str]]:
        """Get the symbols used in the expression.

        1. Symbol as listed in expression and function body. In general <instant>_<variable>[<index>]
        2. Argument as used in the argument list of the function call. In general <instant>_<variable>
        3. Fully qualified symbol: (<instant>, <variable>, <index>|None)

        If there is only a single instance, it is allowed to skip <instant> in 1 and 2

        Returns
        -------
            tuple of (symbols, functions),
               where symbols is a dict {<instant>_<variable> : fully-qualified-symbol tuple, ...}

               functions is a list of functions used in the expression.
        """

        def ast_walk(
            node: ast.AST,
            syms: list[str] | None = None,
            funcs: list[str] | None = None,
        ) -> tuple[list[str], list[str]]:
            """Recursively walk an ast node (width first) and collect symbol and function names."""
            syms = syms or []
            funcs = funcs or []
            for n in ast.iter_child_nodes(node):
                if isinstance(n, ast.Name):
                    if n.id in self._symbols:
                        if n.id not in syms:
                            syms.append(n.id)
                    elif isinstance(node, ast.Call):
                        if n.id not in funcs:
                            funcs.append(n.id)
                    else:
                        raise KeyError(f"Unknown symbol {n.id}")
                syms, funcs = ast_walk(node=n, syms=syms, funcs=funcs)
            return (syms, funcs)

        if expr in self._expr:  # assume that actually a key is queried
            expr = self._expr[expr]
        syms, funcs = ast_walk(node=ast.parse(source=expr, filename="<string>", mode="exec"))
        syms = sorted(syms, key=list(self._symbols.keys()).index)
        return (syms, funcs)

    def temporal(
        self,
        key: str,
        typ: Temporal | str | None = None,
        args: tuple[TValue, ...] | None = None,
    ) -> dict[str, Any]:
        """Get or set a temporal instruction.

        Args:
            key (str): the assert key
            typ (str): optional temporal type
        """
        if typ is None:  # getter
            try:
                temp = self._temporal[key]
            except KeyError as e:
                raise KeyError(f"Temporal instruction for {key} is not found") from e
            else:
                return temp
        else:  # setter
            if isinstance(typ, Temporal):
                self._temporal.update({key: {"type": typ, "args": args}})
            assert isinstance(typ, str), f"Unknown temporal type {typ}"
            self._temporal.update({key: {"type": Temporal[typ], "args": args}})
            return self._temporal[key]

    def description(self, key: str, descr: str | None = None) -> str:
        """Get or set a description."""
        if descr is None:  # getter
            try:
                _descr = self._description[key]
            except KeyError as e:
                raise KeyError(f"Description for {key} not found") from e
            else:
                return _descr
        else:  # setter
            self._description.update({key: descr})
            return descr

    def assertions(
        self,
        key: str,
        res: bool | None = None,
        details: str | None = None,
        case_name: str | None = None,
    ) -> int | float | bool:
        """Get or set an assertion result."""
        if res is None:  # getter
            try:
                _res = self._assertions[key]
            except KeyError as e:
                raise KeyError(f"Assertion results for {key} not found") from e
            else:
                return _res
        else:  # setter
            self._assertions.update({key: {"passed": res, "details": details, "case": case_name}})
            return self._assertions[key]

    def register_vars(self, variables: dict[str, dict[str, Any]]) -> None:
        """Register the variables in varnames as symbols.

        Can be used directly from Cases with varnames = tuple( Cases.variables.keys())
        """
        self._cases_variables = variables  # remember the full dict for retrieval of details
        for key, info in variables.items():
            for inst in info["instances"]:
                if len(info["instances"]) == 1:  # the instance is unique
                    _ = self.symbol(key, len(info["names"]))  # we allow to use the 'short name' if unique
                _ = self.symbol(f"{inst}_{key}", len(info["names"]))  # fully qualified name can always be used

    def make_locals(self, loc: dict[str, Any]) -> dict[str, Any]:
        """Adapt the locals with 'allowed' functions."""
        from importlib import import_module

        for modulename, funclist in self._imports.items():
            module = import_module(modulename)
            for func in funclist:
                loc[func] = getattr(module, func)
        loc["np"] = import_module("numpy")
        return loc

    def _eval(
        self, func: Callable[..., int | float | bool], kvargs: dict[str, Any] | list[Any] | tuple[Any, ...]
    ) -> int | float | bool:
        """Call a function of multiple arguments and return the single result.
        All internal vecor arguments are transformed to np.arrays.
        """
        if isinstance(kvargs, dict):
            for k, v in kvargs.items():
                if isinstance(v, Iterable):
                    kvargs[k] = np.array(v, float)
            return func(**kvargs)
        if isinstance(kvargs, list):
            for i, v in enumerate(kvargs):
                if isinstance(v, Iterable):
                    kvargs[i] = np.array(v, dtype=float)
            return func(*kvargs)
        assert isinstance(kvargs, tuple), f"Unknown type of kvargs {kvargs}"
        _args = []  # make new, because tuple is not mutable
        for v in kvargs:
            if isinstance(v, Iterable):
                _args.append(np.array(v, dtype=float))
            else:
                _args.append(v)
        return func(*_args)

    def eval_single(self, key: str, kvargs: dict[str, Any] | list[Any] | tuple[Any, ...]) -> int | float | bool:
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
        exec(self._compiled[key], loc, loc)  # noqa: S102
        # print("kvargs", kvargs, self._syms[key], self.expr_get_symbols_functions(key))  # noqa: ERA001
        return self._eval(locals()[f"_{key}"], kvargs)

    def eval_series(  # noqa: C901, PLR0912, PLR0915
        self,
        key: str,
        data: TDataTable | TDataColumn,
        ret: float | str | Callable[[TDataColumn], TDataColumn | TValue] | None = None,
    ) -> tuple[TNumeric | TTimeColumn, TValue | TDataColumn]:
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
        bool_type: bool = (ret is None and self.temporal(key)["type"] in (Temporal.A, Temporal.F)) or (
            isinstance(ret, str) and (ret in ["A", "F"] or ret.startswith("bool"))
        )

        argument_names = self._syms[key]

        # Execute the compiled expression. This will create a function with name _<key> in the local namespace.
        _locals = self.make_locals(locals())
        exec(self._compiled[key], _locals, _locals)  # noqa: S102
        # Save a reference to the created function in a local variable, for easier access.
        func = locals()[f"_{key}"]

        _temp = self._temporal[key]["type"] if ret is None else Temporal.UNDEFINED

        # `times`and `results` are, by intention, lists of invariant type `TTimeColumn` and `TDataColumn`, respectively,
        # meaning all elements in the lists are expected to be of the same type.
        # However, the _specific_ types of the elements in the lists are not known at this point.
        # Therefore, we use temporary variables `_times`and `_results` of covariant type `list[TValue]`
        # to first store the elements in the lists, (theoretically) allowing for elements of different types.
        # After the loop, we assert that all elements in the temporary lists are of the same type,
        # and then cast the temporary lists to the invariant types `TTimeColumn` and `TDataColumn`, respectively.
        times: TTimeColumn = []  # the independent variable values (normally time) (invariant)
        results: TDataColumn = []  # the scalar results at all times (invariant)
        _times: list[TNumeric] = []  # temporary variable (covariant)
        _results: list[TValue] = []  # temporary variable (covariant)
        for _row in data:
            time: TNumeric
            row: TDataRow
            result: TValue
            if isinstance(_row, TNumeric):  # can happen if the time itself is evaluated
                time = _row
                row = [_row]
            assert isinstance(row[0], TNumeric), f"Time data in eval_series is not numeric: {row}"
            time = row[0]
            if "t" not in argument_names:
                # The independent variable is not explicitly used in the expressionm
                # -> remove it from the data row before evaluating the expression.
                row = row[1:]
                assert len(row), f"Time data in eval_series seems to be lacking. Data:{data}, Argnames:{argument_names}"
            result = func(*row)
            if bool_type:
                result = bool(result)
            _times.append(time)
            _results.append(result)  # NOTE: result is always a scalar

        # Times: Assert that all values in temporary list `_times` are numeric and of the same type,
        # then cast the temporary list `_times` into list `times` of invariant type `TTimeColumn`.
        if _times:
            assert all(isinstance(t, TNumeric) for t in _times), f"Time data in eval_series is not numeric: {_times}"
            if not all(isinstance(t, type(_times[0])) for t in _times):
                warning("Time data in eval_series has varying type. All time values will be converted to float.")
                _times = [float(t) for t in _times]
            times = cast(TTimeColumn, list(_times))

        # Results: Assert that all values in temporary list `_results` are of a valid type and of the same type,
        # then cast the temporary list `_results` into list `results` of invariant type `TDataColumn`.
        if _results:
            assert all(isinstance(r, TValue) for r in _results), (
                f"Result data in eval_series is of an invalid type: {_results}"
            )
            if not all(isinstance(r, type(_results[0])) for r in _results):
                warning("Result data in eval_series has varying type. All result values will be converted to bool.")
                _results = [bool(r) for r in _results]
            results = cast(TDataColumn, list(_results))

        # Apply an evaluation metric on the result values, specified through parameter `ret`.
        # Depending on the value of `ret`, either temporal logic, interpolation, or a user-defined callable function is applied.

        if (ret is None and _temp == Temporal.A) or (isinstance(ret, str) and ret in ("A", "bool")):  # Always True
            # TODO @EisDNV: Check if this is correct. Irrespective of that I slightly changed the code,
            #      in both your original version and in the below modified version, the return value will
            #      be true if _any_ result value in the series is true. I'm not sure if that's the intended behavior.
            #      The temporal qualifier is set to Temporal.A, which I assume means "Always true for the whole time-series".
            #      Following that logic, I would expect the return value to be True if, and only if, _all_ results are True.
            #      ClaasRostock, 2025-01-23
            return next(
                ((t, True) for t, r in zip(times, results, strict=False) if r),  # time of first True value
                (times[-1], False),  # Fallback to (end time, False) if no True value was found in the series
            )

        if (ret is None and _temp == Temporal.F) or (isinstance(ret, str) and ret == "F"):  # Finally True
            # TODO @EisDNV: Check if this is correct. If I read the code correctly, the return value will
            #      be False if the last result value is True. I'm not sure if that's the intended behavior.
            #      The temporal qualifier is set to Temporal.F, which I assume means "Finally true at the end of the time-series".
            #      Following that logic, I would expect the return value to be True if the last result value is True.
            #      ClaasRostock, 2025-01-23
            t_true = times[-1]
            for t, r in zip(times, results, strict=False):
                if r and t_true > t:
                    t_true = t
                elif not r and t_true < t:  # detected False after expression became True
                    t_true = times[-1]
            return (t_true, t_true < times[-1])

        if isinstance(ret, str) and ret == "bool-list":
            assert all(isinstance(r, bool) for r in results), "Only boolean results can be returned as bool-list"
            return (times, results)

        if (ret is None and _temp == Temporal.T) or (isinstance(ret, float)):
            t0: float
            if isinstance(ret, float):
                t0 = ret
            else:
                assert len(self._temporal[key]["args"]), "Need a temporal argument (time at which to interpolate)"
                t0 = float(self._temporal[key]["args"][0])
            interpolated: float = float(np.interp(t0, times, results))
            return (t0, bool(interpolated) if all(isinstance(r, bool) for r in results) else interpolated)

        if callable(ret):
            return (times, ret(results))

        raise ValueError(f"Unknown return type '{ret}'")

    def do_assert(
        self,
        key: str,
        result: Results,
        case_name: str | None = None,
    ) -> bool:
        """Perform assert action 'key' on data of 'result' object."""
        assert isinstance(key, str), f"Key should be a string. Found {key}"
        assert key in self._temporal, f"Assertion key {key} not found"
        from sim_explorer.case import Results

        assert isinstance(result, Results), f"Results object expected. Found {result}"
        inst: list[str] = []
        var: list[str] = []
        for sym in self._syms[key]:
            _inst = self.info(sym=sym, typ="instance")
            _var = self.info(sym=sym, typ="variable")
            assert isinstance(_inst, str), f"Instance should be a string. Found {_inst}"
            assert isinstance(_var, str), f"Variable should be a string. Found {_var}"
            inst.append(_inst)
            var.append(_var)
        assert len(var), "No variables to retrieve"
        if var[0] == "t":  # the independent variable is always the first column in data
            _ = inst.pop(0)
            _ = var.pop(0)

        data = result.retrieve(comp_var=zip(inst, var, strict=False))
        res = self.eval_series(key=key, data=data, ret=None)
        assert isinstance(res[1], bool), f"Result of evaluation should be bool. Found {res[1]}"
        if self._temporal[key]["type"] == Temporal.A:
            _ = self.assertions(key=key, res=res[1], details=None, case_name=case_name)
        elif self._temporal[key]["type"] == Temporal.F:
            _ = self.assertions(key=key, res=res[1], details=f"@{res[0]}", case_name=case_name)
        elif self._temporal[key]["type"] == Temporal.T:
            _ = self.assertions(key=key, res=res[1], details=f"@{res[0]} (interpolated)", case_name=case_name)
        return res[1]

    def do_assert_case(self, result: Results) -> list[int]:
        """Perform all assertions defined for the case related to the result object."""
        count: list[int] = [0, 0]
        assert result.case is not None, "No case found in result object"
        for key in result.case.asserts:
            _ = self.do_assert(key=key, result=result, case_name=result.case.name)
            count[0] += self._assertions[key]["passed"]
            count[1] += 1
        return count

    def report(self, case: Case | None = None) -> Iterator[AssertionResult]:
        """Report on all registered asserts.
        If case denotes a case object, only the results for this case are reported.
        """

        def do_report(key: str) -> AssertionResult:
            time_arg = self._temporal[key].get("args", None)
            return AssertionResult(
                key=key,
                expression=self._expr[key],
                time=(time_arg[0] if len(time_arg) > 0 and (isinstance(time_arg[0], int | float)) else None),
                result=self._assertions[key].get("passed", False),
                description=self._description[key],
                temporal=self._temporal[key].get("type", None),
                case=self._assertions[key].get("case", None),
                details="No details",
            )

        from sim_explorer.case import Case

        if isinstance(case, Case):
            for key in case.asserts:
                yield do_report(key)
        else:  # report all
            for key in self._assertions:
                yield do_report(key)
