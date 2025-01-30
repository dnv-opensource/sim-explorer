from collections.abc import Sequence
from typing import (
    TypeAlias,
)

# ===== Arguments (Variables) =====================================================================
TNumeric: TypeAlias = int | float
TValue: TypeAlias = int | float | bool | str  # single (scalar) value, as e.g. also serialized to/from Json5 atom
TTimeColumn: TypeAlias = list[int] | list[float]  # X column, but limited to numeric types. Typically indicating time.
TDataColumn: TypeAlias = list[int] | list[float] | list[bool]  # | list[str]  # X column
TDataRow: TypeAlias = Sequence[TValue | Sequence[TValue]]  # | TNumeric  # X row without variable names (just values)
TDataTable: TypeAlias = Sequence[TDataRow]  # X table
# TArguments: TypeAlias = Mapping[str, TValue]  # X row with variable names  # noqa: ERA001
# TArgs: TypeAlias = dict[str, TValue]  # noqa: ERA001


# ===== System Interface =====================================================================
#: Arguments for 'get' action functions (component_variable_name, component_name, variable_references)
TGetActionArgs: TypeAlias = tuple[str, str, tuple[int, ...]]
#: Arguments for 'set' action functions (component_variable_name, component_name, variable_references, variable_values)
TSetActionArgs: TypeAlias = tuple[str, str, tuple[int, ...], tuple[TValue, ...]]
#: Arguments for action functions
TActionArgs: TypeAlias = TGetActionArgs | TSetActionArgs
