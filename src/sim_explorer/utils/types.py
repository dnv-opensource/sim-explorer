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
