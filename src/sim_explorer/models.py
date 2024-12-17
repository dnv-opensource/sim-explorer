from enum import Enum

from pydantic import BaseModel


class Temporal(Enum):
    UNDEFINED = 0
    A = 1
    ALWAYS = 1
    F = 2
    FINALLY = 2
    T = 3
    TIME = 3


class AssertionResult(BaseModel):
    key: str
    expression: str
    result: bool
    temporal: Temporal
    time: float | int | None
    description: str
    case: str | None
    details: str
