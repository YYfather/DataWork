"""设计角色建议与计划预检服务。"""

from __future__ import annotations

from datawork.core.roles import RoleAssignment, RoleMap, VariableRole
from datawork.core.validation import ValidationReport, validate_plan_dataframe
from datawork.io.profiler import DataProfile


class DesignService:
    def suggest_roles(self, profile: DataProfile) -> RoleMap:
        assignments: list[RoleAssignment] = []
        for column in profile.columns:
            try:
                role = VariableRole(column.inferred_role)
            except ValueError:
                role = VariableRole.IGNORE
            assignments.append(RoleAssignment(
                column=column.name,
                role=role,
                confidence=float(column.role_confidence),
                source="rules",
                note=column.note,
            ))
        return RoleMap(assignments=assignments)

    def validate(self, frame, plan) -> ValidationReport:
        return validate_plan_dataframe(plan, frame)
