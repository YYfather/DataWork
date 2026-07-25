"""变量角色领域模型。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class VariableRole(str, Enum):
    ID = "id"
    BETWEEN = "between"
    WITHIN = "within"
    COVARIATE = "covariate"
    DEPENDENT = "dependent"
    DERIVED = "derived"
    RANDOM = "random"
    TIME = "time"
    LABEL = "label"
    IGNORE = "ignore"


class RoleAssignment(BaseModel):
    column: str
    role: VariableRole
    confidence: float = 1.0
    source: str = "user"
    note: str = ""


class RoleMap(BaseModel):
    assignments: list[RoleAssignment] = Field(default_factory=list)

    def columns_for(self, role: VariableRole) -> list[str]:
        return [item.column for item in self.assignments if item.role == role]
