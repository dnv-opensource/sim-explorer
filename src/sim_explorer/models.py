from typing import List
from pydantic import BaseModel

class AssertionResult(BaseModel):
    key: str
    expression: str
    result: bool
    descriptions: str
    case: str | None
    details: str
