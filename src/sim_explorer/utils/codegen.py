from collections.abc import Callable
from types import CodeType
from typing import Any, cast


def get_callable_function(
    compiled: CodeType,
    function_name: str,
    global_ns: dict[str, Any] | None = None,
    local_ns: dict[str, Any] | None = None,
) -> Callable[..., Any]:
    """Execute compiled code and return a named callable from the local namespace."""
    globals_dict = global_ns if global_ns is not None else {}
    locals_dict = local_ns if local_ns is not None else globals_dict
    exec(compiled, globals_dict, locals_dict)  # noqa: S102

    if function_name not in locals_dict:
        raise KeyError(f"Function '{function_name}' not found after execution")

    func = locals_dict[function_name]
    if not callable(func):
        raise TypeError(f"Name '{function_name}' is not callable")

    return cast("Callable[..., Any]", func)
