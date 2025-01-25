from collections.abc import Mapping, Sequence
from typing import (
    TypeAlias,
)

# ===== Arguments (Variables) =====================================================================
TNumeric: TypeAlias = int | float
TValue: TypeAlias = int | float | bool | str  # single (scalar) value, as e.g. also serialized to/from Json5 atom
TTimeColumn: TypeAlias = list[int] | list[float]  # X column, but limited to numeric types. Typically indicating time.
TDataColumn: TypeAlias = list[int] | list[float] | list[bool]  # X column
TDataRow: TypeAlias = Sequence[TValue] | TNumeric  # X row without variable names (just values)
TDataTable: TypeAlias = Sequence[TDataRow]  # X table
TArguments: TypeAlias = Mapping[str, TValue]  # X row with variable names
TArgs: TypeAlias = dict[str, TValue]


# ===== System Interface =====================================================================
#: Arguments for 'get' action functions (component_variable_name, component_name, variable_references)
TGetActionArgs: TypeAlias = tuple[str, str, tuple[int, ...]]
#: Arguments for 'set' action functions (component_variable_name, component_name, variable_references, variable_values)
TSetActionArgs: TypeAlias = tuple[str, str, tuple[int, ...], tuple[TValue, ...]]
#: Arguments for action functions
TActionArgs: TypeAlias = TGetActionArgs | TSetActionArgs

#: Function signature for action functions
TActionFunc: TypeAlias = callable[[int | float, TActionArgs, type], bool]
#: Function signature for action step functions
TActionStepFunc: TypeAlias = callable[[TActionArgs, type], callable[..., TValue]]

#: Function signature for initial action functions
TInitialActionFunc: TypeAlias = callable[[int | float, TSetActionArgs], bool]
#: Function signature for initial action functions
TInitialActionStepFunc: TypeAlias = callable[[TSetActionArgs], callable[..., TValue]]

#: Function signature for get action functions
TGetActionFunc: TypeAlias = callable[[TGetActionArgs], TValue]
#: Function signature for set action functions
TSetActionFunc: TypeAlias = callable[[TSetActionArgs], bool]
#: Function signature for get action step functions
TGetActionStepFunc: TypeAlias = callable[[TGetActionArgs], callable[..., TValue]]
#: Function signature for set action step functions
TSetActionStepFunc: TypeAlias = callable[[TSetActionArgs], callable[..., TValue]]
