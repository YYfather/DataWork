"""分析计划与数据的统一校验。"""
from __future__ import annotations

from itertools import combinations, product
import math

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from .errors import IssueSeverity, PlanValidationError, ValidationIssue
from .method_registry import get_method
from .splitting import (
    SPLIT_TASK_HARD_LIMIT,
    SPLIT_TASK_WARNING_THRESHOLD,
    build_split_groups,
    projected_split_group_count,
)


class ValidationReport(BaseModel):
    issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(issue.severity == IssueSeverity.ERROR for issue in self.issues)

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == IssueSeverity.WARNING]

    def raise_for_errors(self) -> None:
        if not self.valid:
            raise PlanValidationError(self.issues)


def validate_plan_dataframe(plan: "AnalysisPlan", frame: pd.DataFrame) -> ValidationReport:
    from .plan import AnalysisPlan
    if not isinstance(plan, AnalysisPlan):
        raise TypeError("plan 必须是 AnalysisPlan")

    issues: list[ValidationIssue] = []
    spec = get_method(plan.method)
    columns = set(map(str, frame.columns))
    missing = sorted(set(plan.all_columns) - columns)
    if missing:
        issues.append(ValidationIssue(code="missing_columns", field="columns", message=f"数据中不存在这些列: {missing}", details={"columns": missing}))
        return ValidationReport(issues=issues)

    binary_dv_methods = {
        "logistic_regression", "mcnemar_test", "two_proportion_ztest",
        "k_proportion_chi_square", "cochran_mantel_haenszel", "breslow_day",
        "cochran_q_test", "cochran_armitage_trend",
    }
    categorical_paired_methods = {"cohen_kappa", "fleiss_kappa"}
    multicategory_dv_methods = {"bowker_symmetry", "stuart_maxwell", "multinomial_logistic_regression", "ordinal_logistic_regression"}
    for dependent in plan.dependent_variables:
        if plan.method in binary_dv_methods:
            levels = int(frame[dependent].dropna().nunique())
            if levels != 2:
                issues.append(ValidationIssue(code="binary_outcome_required", field=dependent, message=f"{spec.label_zh} 要求 {dependent!r} 恰好有 2 个有效水平，当前为 {levels}", details={"levels": levels}))
        elif plan.method in categorical_paired_methods:
            levels = int(frame[dependent].dropna().nunique())
            if levels < 2:
                issues.append(ValidationIssue(code="categorical_levels_required", field=dependent, message=f"{spec.label_zh} 要求 {dependent!r} 至少有 2 个有效类别，当前为 {levels}", details={"levels": levels}))
        elif plan.method in multicategory_dv_methods:
            levels = int(frame[dependent].dropna().nunique())
            minimum_levels = 3
            if levels < minimum_levels:
                issues.append(ValidationIssue(code="multicategory_outcome_required", field=dependent, message=f"{spec.label_zh} 要求 {dependent!r} 至少有 {minimum_levels} 个有效水平，当前为 {levels}", details={"levels": levels}))
        else:
            numeric = pd.to_numeric(frame[dependent], errors="coerce")
            valid_count = int(numeric.notna().sum())
            if valid_count < 2:
                issues.append(ValidationIssue(code="insufficient_numeric_values", field=dependent, message=f"变量 {dependent!r} 没有足够的有效数值", details={"valid_count": valid_count}))
            if valid_count and float(numeric.dropna().std(ddof=0)) == 0 and plan.method not in {"descriptive_statistics"}:
                issues.append(ValidationIssue(code="constant_numeric_variable", field=dependent, message=f"变量 {dependent!r} 为常数列，无法执行 {spec.label_zh}"))

    for covariate in plan.covariates:
        numeric = pd.to_numeric(frame[covariate], errors="coerce")
        valid_count = int(numeric.notna().sum())
        if valid_count < 3:
            issues.append(ValidationIssue(code="invalid_covariate", field=covariate, message=f"协变量 {covariate!r} 的有效数值不足", details={"valid_count": valid_count}))
        elif float(numeric.dropna().std(ddof=0)) == 0:
            issues.append(ValidationIssue(code="constant_covariate", field=covariate, message=f"协变量 {covariate!r} 为常数列"))

    for factor in plan.fixed_factors:
        levels = int(frame[factor].dropna().nunique())
        if levels < 2:
            issues.append(ValidationIssue(code="insufficient_factor_levels", field=factor, message=f"固定/分类因素 {factor!r} 少于 2 个有效水平", details={"levels": levels}))
        if spec.exact_factor_levels is not None and levels != spec.exact_factor_levels:
            issues.append(ValidationIssue(code="exact_factor_levels_required", field=factor, message=f"{spec.label_zh} 要求因素 {factor!r} 恰好 {spec.exact_factor_levels} 个水平，当前为 {levels}", details={"levels": levels, "required": spec.exact_factor_levels}))

    if plan.random_factors:
        group = plan.random_factors[0]
        levels = int(frame[group].dropna().nunique())
        if levels < 3:
            issues.append(ValidationIssue(code="insufficient_random_groups", field=group, message=f"随机分组因素 {group!r} 至少需要 3 个水平，当前为 {levels}"))
        elif levels < 5:
            issues.append(ValidationIssue(code="few_random_groups", field=group, severity=IssueSeverity.WARNING, message=f"随机分组因素仅 {levels} 个水平，随机效应方差估计可能不稳定"))

    if plan.random_slopes and plan.random_factors:
        group = plan.random_factors[0]
        for slope in plan.random_slopes:
            within_levels = frame[[group, slope]].dropna().groupby(group, observed=True)[slope].nunique()
            insufficient = int((within_levels < 2).sum())
            if insufficient:
                issues.append(ValidationIssue(
                    code="random_slope_no_within_group_variation", field=slope,
                    message=f"随机斜率 {slope!r} 在 {insufficient} 个随机组内没有变化，无法估计该随机斜率",
                    details={"insufficient_groups": insufficient},
                ))

    if plan.subject_id:
        subjects = int(frame[plan.subject_id].dropna().nunique())
        if subjects < 2:
            issues.append(ValidationIssue(code="insufficient_subjects", field=plan.subject_id, message="受试者/样本 ID 至少需要 2 个不同对象"))
    if plan.repeated_factor:
        levels = int(frame[plan.repeated_factor].dropna().nunique())
        minimum = 3 if plan.method == "friedman_test" else 2
        if levels < minimum:
            issues.append(ValidationIssue(code="insufficient_repeated_levels", field=plan.repeated_factor, message=f"{spec.label_zh} 至少需要 {minimum} 个重复/时间水平，当前为 {levels}"))
        if plan.subject_id:
            duplicate_count = int(frame.duplicated([plan.subject_id, plan.repeated_factor]).sum())
            if duplicate_count:
                issues.append(ValidationIssue(code="duplicate_repeated_cells", field=plan.repeated_factor, message=f"发现 {duplicate_count} 条重复的受试者×重复水平记录；每个组合必须只有一条观测"))
            required = [plan.subject_id, plan.repeated_factor] + plan.dependent_variables[:1]
            complete = frame[required].dropna()
            counts = complete.groupby(plan.subject_id)[plan.repeated_factor].nunique()
            expected_levels = int(complete[plan.repeated_factor].nunique())
            incomplete = int((counts < expected_levels).sum())
            if incomplete:
                mixed_mode = str(plan.method_parameters.get("analysis_mode", "auto"))
                requires_complete = plan.method == "repeated_measures_anova" or (plan.method == "mixed_anova" and mixed_mode == "classical")
                severity = IssueSeverity.ERROR if requires_complete else IssueSeverity.WARNING
                suffix = "；将使用 MixedLM 处理可用观测" if plan.method == "mixed_anova" and not requires_complete else ""
                issues.append(ValidationIssue(code="incomplete_repeated_subjects", field=plan.subject_id, severity=severity, message=f"有 {incomplete} 个对象缺少部分重复水平{suffix}", details={"incomplete_subjects": incomplete, "analysis_mode": mixed_mode}))

    if plan.method == "mixed_anova" and plan.subject_id and plan.repeated_factor and plan.fixed_factors:
        mixed_mode = str(plan.method_parameters.get("analysis_mode", "auto"))
        for between in plan.fixed_factors:
            mapping = frame[[plan.subject_id, between]].dropna().groupby(plan.subject_id, observed=True)[between].nunique()
            if (mapping > 1).any():
                issues.append(ValidationIssue(code="subject_multiple_between_levels", field=between, message=f"混合设计中每个对象只能属于对象间因素 {between!r} 的一个水平"))
        subject_cells = frame[[plan.subject_id, *plan.fixed_factors]].dropna().drop_duplicates(plan.subject_id)
        group_sizes = subject_cells.groupby(plan.fixed_factors, observed=False).size()
        if len(group_sizes) >= 2 and group_sizes.nunique() != 1:
            severity = IssueSeverity.ERROR if mixed_mode == "classical" else IssueSeverity.WARNING
            issues.append(ValidationIssue(
                code="unbalanced_mixed_groups", field="fixed_factors", severity=severity,
                message="对象间组合的对象数不平衡" + ("；自动/ MixedLM 模式仍可拟合" if severity == IssueSeverity.WARNING else "；强制经典模式无法执行"),
                details={"group_sizes": {str(k): int(v) for k, v in group_sizes.items()}, "analysis_mode": mixed_mode},
            ))
        if len(plan.fixed_factors) > 1 and mixed_mode == "classical":
            issues.append(ValidationIssue(
                code="classical_mixed_factor_limit", field="fixed_factors",
                message="经典混合 ANOVA 路径只支持一个对象间因素；双对象间因素请选择自动或 MixedLM 模式",
            ))

    if plan.method == "chi_square_goodness_of_fit" and plan.expected_proportions:
        levels = int(frame[plan.fixed_factors[0]].dropna().nunique()) if plan.fixed_factors else 0
        if len(plan.expected_proportions) != levels:
            issues.append(ValidationIssue(code="expected_proportion_length", field="expected_proportions", message=f"期望比例有 {len(plan.expected_proportions)} 个，但分类变量有 {levels} 个水平"))

    minimum_complete = _minimum_complete_cases(plan.method, len(plan.fixed_factors) + len(plan.covariates))
    if plan.factor_combinations_enabled:
        relevant = list(dict.fromkeys(plan.dependent_variables + plan.covariates + plan.random_factors + plan.random_slopes + plan.split_by + ([plan.subject_id] if plan.subject_id else []) + ([plan.repeated_factor] if plan.repeated_factor else [])))
        complete_count = int(frame[relevant].dropna().shape[0]) if relevant else int(len(frame))
        minimum_order = int(plan.factor_combination_min_order or 0)
        maximum_order = int(plan.factor_combination_max_order or 0)
        task_count = sum(
            math.comb(len(plan.fixed_factors), order)
            for order in range(minimum_order, maximum_order + 1)
            if 0 <= order <= len(plan.fixed_factors)
        )
        issues.append(ValidationIssue(
            code="factor_combination_batch", severity=IssueSeverity.WARNING, field="fixed_factors",
            message=(
                f"已明确启用分类因素组合实验：将把 {len(plan.fixed_factors)} 个候选因素展开为 "
                f"{task_count} 个独立模型（组合阶数 {minimum_order}–{maximum_order}），而不是拟合一个包含全部因素的模型。"
            ),
            details={
                "candidate_factor_count": len(plan.fixed_factors),
                "combination_min_order": minimum_order,
                "combination_max_order": maximum_order,
                "factor_model_count": task_count,
                "cross_task_p_adjust": plan.combination_p_adjust,
                "note": "完整案例、因素水平和模型可执行性将在每个组合任务内分别检查。",
            },
        ))
    else:
        relevant = plan.all_columns
        complete_count = int(frame[relevant].dropna().shape[0]) if relevant else int(len(frame))
        if complete_count < minimum_complete:
            issues.append(ValidationIssue(code="insufficient_complete_cases", message=f"完整案例仅 {complete_count} 行，{spec.label_zh} 建议至少 {minimum_complete} 行", details={"complete_cases": complete_count, "recommended_minimum": minimum_complete}))
        elif complete_count < max(10, minimum_complete * 2):
            issues.append(ValidationIssue(code="small_complete_sample", severity=IssueSeverity.WARNING, message=f"完整案例仅 {complete_count} 行，统计功效和诊断结果可能不稳定", details={"complete_cases": complete_count}))

    projected_split_count = projected_split_group_count(frame, plan)
    split_projection_blocked = projected_split_count > SPLIT_TASK_HARD_LIMIT
    if split_projection_blocked:
        issues.append(ValidationIssue(
            code="split_group_limit_exceeded", field="split_by",
            message=(f"当前拆分设置会生成 {projected_split_count} 个组合，超过安全上限 "
                     f"{SPLIT_TASK_HARD_LIMIT}；请减少拆分列或分组数量"),
            details={"split_group_count": projected_split_count, "hard_limit": SPLIT_TASK_HARD_LIMIT},
        ))
        groups: list[tuple[dict[str, str], pd.DataFrame]] = []
    else:
        groups = build_split_groups(frame, plan) if plan.split_by else [({}, frame)]
    if spec.dependent_mode in {"none", "joint"}:
        dependent_task_count = 1
    else:
        dependent_task_count = max(1, len(plan.dependent_variables))
    if plan.factor_combinations_enabled:
        factor_task_count = sum(
            math.comb(len(plan.fixed_factors), order)
            for order in range(
                int(plan.factor_combination_min_order or 1),
                int(plan.factor_combination_max_order or 1) + 1,
            )
        )
    else:
        factor_task_count = 1
    expanded_task_count = dependent_task_count * factor_task_count * (
        projected_split_count if split_projection_blocked else len(groups)
    )
    if expanded_task_count > SPLIT_TASK_HARD_LIMIT:
        issues.append(ValidationIssue(
            code="expanded_task_limit_exceeded", field="split_by",
            message=(f"当前计划会生成 {expanded_task_count} 个分析任务，超过安全上限 "
                     f"{SPLIT_TASK_HARD_LIMIT}；请减少因变量、因素组合或拆分组"),
            details={"task_count": expanded_task_count, "hard_limit": SPLIT_TASK_HARD_LIMIT},
        ))
    elif expanded_task_count > SPLIT_TASK_WARNING_THRESHOLD:
        issues.append(ValidationIssue(
            code="large_expanded_task_plan", severity=IssueSeverity.WARNING, field="split_by",
            message=f"当前计划将生成 {expanded_task_count} 个分析任务，执行和报告生成可能较慢",
            details={"task_count": expanded_task_count, "warning_threshold": SPLIT_TASK_WARNING_THRESHOLD},
        ))

    if plan.split_by and not split_projection_blocked:
        assigned_indices: set = set()
        for _labels, subset in groups:
            assigned_indices.update(subset.index.tolist())
        excluded_rows = int(len(frame) - len(assigned_indices))
        if excluded_rows:
            issues.append(ValidationIssue(
                code="unassigned_split_rows_excluded",
                severity=IssueSeverity.WARNING,
                field="split_by",
                message=f"有 {excluded_rows} 行未落入任何自定义拆分组，将不参与本次计算",
                details={"excluded_rows": excluded_rows, "total_rows": int(len(frame))},
            ))

        dual_role_columns = sorted(set(plan.split_by) & set(plan.fixed_factors))
        if dual_role_columns:
            if plan.factor_combinations_enabled:
                factor_sets = [
                    list(items)
                    for order in range(
                        int(plan.factor_combination_min_order or 1),
                        int(plan.factor_combination_max_order or 1) + 1,
                    )
                    for items in combinations(plan.fixed_factors, order)
                ]
            else:
                factor_sets = [list(plan.fixed_factors)]
            if spec.dependent_mode == "none":
                dependent_sets = [[]]
            elif spec.dependent_mode == "joint":
                dependent_sets = [list(plan.dependent_variables)]
            else:
                dependent_sets = [[item] for item in plan.dependent_variables]
            invalid_groups: list[dict] = []
            for labels, raw_subset in groups:
                for dependent_set in dependent_sets:
                    for factor_set in factor_sets:
                        checked = [column for column in dual_role_columns if column in factor_set]
                        if not checked:
                            continue
                        required = list(dict.fromkeys(
                            dependent_set + factor_set + plan.covariates + plan.random_factors +
                            plan.random_slopes +
                            ([plan.subject_id] if plan.subject_id else []) +
                            ([plan.repeated_factor] if plan.repeated_factor else [])
                        ))
                        complete = raw_subset.dropna(subset=required) if required else raw_subset
                        for column in checked:
                            level_count = int(complete[column].nunique(dropna=True))
                            if level_count < 2:
                                invalid_groups.append({
                                    "group": dict(labels),
                                    "factor": column,
                                    "levels": level_count,
                                    "rows": int(len(complete)),
                                    "factor_set": factor_set,
                                    "dependent_set": dependent_set,
                                })
            if invalid_groups:
                issues.append(ValidationIssue(
                    code="split_factor_insufficient_levels",
                    field="split_by",
                    message=(
                        "拆分列兼作分类因素时，每个最终分析子集必须保留至少两个有效因素水平；"
                        f"当前有 {len(invalid_groups)} 个任务不满足要求"
                    ),
                    details={"tasks": invalid_groups[:100], "total_invalid_tasks": len(invalid_groups)},
                ))
        small_groups = {
            ", ".join(f"{column}={label}" for column, label in labels.items()): int(len(subset))
            for labels, subset in groups if len(subset) < minimum_complete
        }
        if small_groups:
            issues.append(ValidationIssue(code="small_split_groups", severity=IssueSeverity.WARNING, field="split_by", message=f"部分拆分子集少于建议的 {minimum_complete} 行，将在合并结果中记录失败或不稳定警告", details={"groups": small_groups}))

    issues.extend(_validate_method_specific_data(plan, frame))

    if spec.status.value == "experimental":
        issues.append(ValidationIssue(code="experimental_method", severity=IssueSeverity.WARNING, field="method", message=f"{spec.label_zh} 当前为实验性方法：{spec.notes or '复杂设计需人工复核'}"))
    return ValidationReport(issues=issues)


def _levels_as_text(series: pd.Series) -> list[str]:
    return [str(item) for item in pd.unique(series.dropna())]


def _parse_dunnett_control_spec(value: str) -> tuple[dict[str, str], str | None]:
    """解析统一或按因素指定的 Dunnett 对照水平。"""
    raw = str(value or "").strip()
    if not raw:
        return {}, None
    normalized = raw.replace("；", ";").replace("，", ",").replace("\n", ";")
    parts = [item.strip() for chunk in normalized.split(";") for item in chunk.split(",") if item.strip()]
    mappings: dict[str, str] = {}
    for item in parts:
        separator = "=" if "=" in item else (":" if ":" in item else ("：" if "：" in item else ""))
        if not separator:
            continue
        factor, level = (piece.strip() for piece in item.split(separator, 1))
        if factor and level:
            mappings[factor] = level
    return (mappings, None) if mappings else ({}, raw)


def _requested_text(plan: "AnalysisPlan", name: str) -> str:
    value = plan.method_parameters.get(name, "")
    return str(value).strip() if value is not None else ""


def _validate_requested_level(
    issues: list[ValidationIssue], *, field: str, requested: str, levels: list[str], label: str
) -> None:
    if requested and requested not in levels:
        issues.append(ValidationIssue(
            code="unknown_requested_level", field=field,
            message=f"{label} {requested!r} 不在当前数据水平中，可选值为: {levels}",
            details={"requested": requested, "available_levels": levels},
        ))


def _validate_method_specific_data(plan: "AnalysisPlan", frame: pd.DataFrame) -> list[ValidationIssue]:
    """校验只有结合真实数据才能判断的方法细节。"""
    issues: list[ValidationIssue] = []
    method = plan.method

    outcome_success_methods = {
        "logistic_regression", "two_proportion_ztest", "k_proportion_chi_square",
        "cochran_mantel_haenszel", "breslow_day", "cochran_armitage_trend",
    }
    factor_success_methods = {"exact_binomial_test", "one_sample_proportion_ztest"}
    if method in outcome_success_methods and plan.dependent_variables:
        outcome = plan.dependent_variables[0]
        _validate_requested_level(
            issues, field="method_parameters.success_level",
            requested=_requested_text(plan, "success_level"),
            levels=_levels_as_text(frame[outcome]), label="成功水平",
        )
    elif method in factor_success_methods and plan.fixed_factors:
        factor = plan.fixed_factors[0]
        _validate_requested_level(
            issues, field="method_parameters.success_level",
            requested=_requested_text(plan, "success_level"),
            levels=_levels_as_text(frame[factor]), label="成功水平",
        )
    elif method == "cochran_q_test":
        requested = _requested_text(plan, "success_level")
        variable_levels = {column: _levels_as_text(frame[column]) for column in plan.dependent_variables}
        if requested:
            missing_from = [column for column, levels in variable_levels.items() if requested not in levels]
            if missing_from:
                issues.append(ValidationIssue(
                    code="success_level_missing_in_paired_variables", field="method_parameters.success_level",
                    message=f"成功水平 {requested!r} 未出现在这些配对变量中: {missing_from}",
                    details={"columns": missing_from, "requested": requested},
                ))
        level_sets = {column: set(levels) for column, levels in variable_levels.items()}
        if level_sets and len({frozenset(levels) for levels in level_sets.values()}) > 1:
            issues.append(ValidationIssue(
                code="paired_category_mismatch", field="dependent_variables",
                message="Cochran Q 的所有配对变量必须使用相同的两个分类水平",
                details={"levels": {column: sorted(levels) for column, levels in level_sets.items()}},
            ))
        if len(plan.dependent_variables) >= 3 and all(len(levels) == 2 for levels in level_sets.values()):
            complete = frame[plan.dependent_variables].dropna()
            if not complete.empty:
                success_text = requested or next(iter(variable_levels.values()))[-1]
                matrix = np.column_stack([
                    (complete[column].astype(str).to_numpy() == success_text).astype(int)
                    for column in plan.dependent_variables
                ])
                if not bool(np.any(np.any(matrix != matrix[:, [0]], axis=1))):
                    issues.append(ValidationIssue(
                        code="no_cochran_q_variation", field="dependent_variables",
                        message="所有对象在各条件下的二元结果完全一致，Cochran Q 统计量无法定义；请检查数据或改用描述性比例汇总",
                    ))

    if method in {"cochran_mantel_haenszel", "breslow_day"} and len(plan.fixed_factors) >= 2:
        exposure, strata = plan.fixed_factors[:2]
        exposure_levels = _levels_as_text(frame[exposure])
        strata_levels = _levels_as_text(frame[strata])
        if len(exposure_levels) != 2:
            issues.append(ValidationIssue(
                code="binary_exposure_required", field=exposure,
                message=f"{get_method(method).label_zh} 要求第一个分类因素 {exposure!r} 恰好有 2 个水平，当前为 {len(exposure_levels)}",
                details={"levels": exposure_levels},
            ))
        if len(strata_levels) < 2:
            issues.append(ValidationIssue(
                code="multiple_strata_required", field=strata,
                message=f"分层因素 {strata!r} 至少需要 2 个有效水平",
                details={"levels": strata_levels},
            ))
        _validate_requested_level(
            issues, field="method_parameters.exposed_level",
            requested=_requested_text(plan, "exposed_level"), levels=exposure_levels, label="暴露水平",
        )
        if plan.dependent_variables and len(exposure_levels) == 2:
            outcome = plan.dependent_variables[0]
            invalid_strata: list[str] = []
            for level, subset in frame[[outcome, exposure, strata]].dropna().groupby(strata, observed=True):
                if subset[outcome].nunique() != 2 or subset[exposure].nunique() != 2:
                    invalid_strata.append(str(level))
            if invalid_strata:
                issues.append(ValidationIssue(
                    code="invalid_stratified_2x2", field=strata,
                    message=f"这些分层不能形成完整 2×2 表: {invalid_strata}",
                    details={"invalid_strata": invalid_strata},
                ))

    if method == "multinomial_logistic_regression" and plan.dependent_variables:
        outcome = plan.dependent_variables[0]
        _validate_requested_level(
            issues, field="method_parameters.reference_level",
            requested=_requested_text(plan, "reference_level"),
            levels=_levels_as_text(frame[outcome]), label="参考类别",
        )

    if method in {"cochran_armitage_trend", "ordinal_logistic_regression"}:
        ordered_column = plan.fixed_factors[0] if method == "cochran_armitage_trend" else plan.dependent_variables[0]
        observed = _levels_as_text(frame[ordered_column])
        order_text = _requested_text(plan, "level_order")
        if order_text:
            requested_order = [item.strip() for item in order_text.split(",") if item.strip()]
            if len(requested_order) != len(set(requested_order)) or set(requested_order) != set(observed):
                issues.append(ValidationIssue(
                    code="invalid_level_order", field="method_parameters.level_order",
                    message=f"有序水平必须完整且不重复地覆盖当前类别: {observed}",
                    details={"requested_order": requested_order, "available_levels": observed},
                ))
        if method == "cochran_armitage_trend":
            scores_text = _requested_text(plan, "scores")
            if scores_text:
                try:
                    scores = [float(item.strip()) for item in scores_text.split(",") if item.strip()]
                except ValueError:
                    scores = []
                    issues.append(ValidationIssue(
                        code="invalid_trend_scores", field="method_parameters.scores",
                        message="趋势得分必须是用英文逗号分隔的有限数值",
                    ))
                if scores:
                    if len(scores) != len(observed):
                        issues.append(ValidationIssue(
                            code="trend_score_length", field="method_parameters.scores",
                            message=f"趋势得分数量应为 {len(observed)}，当前为 {len(scores)}",
                        ))
                    elif not all(math.isfinite(item) for item in scores) or len(set(scores)) < 2:
                        issues.append(ValidationIssue(
                            code="invalid_trend_scores", field="method_parameters.scores",
                            message="趋势得分必须为有限数值，且至少包含两个不同取值",
                        ))

    if method in {"mcnemar_test", "bowker_symmetry", "stuart_maxwell", "cohen_kappa"} and len(plan.dependent_variables) >= 2:
        first, second = plan.dependent_variables[:2]
        first_levels = set(_levels_as_text(frame[first]))
        second_levels = set(_levels_as_text(frame[second]))
        if first_levels != second_levels:
            issues.append(ValidationIssue(
                code="paired_category_mismatch", field="dependent_variables",
                message=f"配对分类变量必须使用相同类别集合；{first!r}={sorted(first_levels)}，{second!r}={sorted(second_levels)}",
                details={"first_levels": sorted(first_levels), "second_levels": sorted(second_levels)},
            ))
        elif method == "stuart_maxwell":
            clean = frame[[first, second]].dropna()
            categories = list(dict.fromkeys(
                clean[first].tolist() + clean[second].tolist()
            ))
            table = pd.crosstab(clean[first], clean[second]).reindex(
                index=categories, columns=categories, fill_value=0
            ).to_numpy(dtype=float)
            if bool(plan.method_parameters.get("shift_zeros", False)) and table.size and table.min() == 0:
                table[table == 0] = 0.5
            if table.sum() > 0 and table.shape[0] >= 3:
                probabilities = table / table.sum()
                row = probabilities.sum(axis=1)[:-1]
                column = probabilities.sum(axis=0)[:-1]
                core = probabilities[:-1, :-1]
                difference = column - row
                method_name = str(plan.method_parameters.get("homogeneity_method", "stuart_maxwell"))
                covariance = -(core + core.T)
                diagonal = row + column - 2 * np.diag(core)
                if method_name == "bhapkar":
                    covariance -= np.outer(difference, difference)
                    diagonal -= difference ** 2
                np.fill_diagonal(covariance, diagonal)
                if np.linalg.matrix_rank(covariance) < covariance.shape[0]:
                    issues.append(ValidationIssue(
                        code="singular_marginal_homogeneity_covariance",
                        field="dependent_variables",
                        message="Stuart–Maxwell/Bhapkar 检验的边际差协方差矩阵不可逆；请增加有效配对观测或合并稀疏类别",
                        details={"complete_pairs": int(len(clean)), "categories": [str(item) for item in categories]},
                    ))

    if method in {"twoway_anova", "threeway_anova", "mixed_anova", "oneway_manova", "twoway_manova", "threeway_manova"} and plan.fixed_factors:
        factors = list(plan.fixed_factors)
        if method == "mixed_anova" and plan.repeated_factor:
            factors = [*plan.fixed_factors, plan.repeated_factor]
        if len(factors) >= 2:
            clean = frame[factors].dropna()
            levels = [list(pd.unique(clean[column])) for column in factors]
            observed_counts = clean.groupby(factors, observed=False).size()
            empty_cells: list[dict[str, str]] = []
            singleton_cells: list[dict[str, str]] = []
            for combination in product(*levels):
                count = int(observed_counts.get(combination, 0))
                label = {factor: str(value) for factor, value in zip(factors, combination)}
                if count == 0:
                    empty_cells.append(label)
                elif count == 1:
                    singleton_cells.append(label)
            if empty_cells:
                issues.append(ValidationIssue(
                    code="empty_factorial_cells", field="fixed_factors",
                    message=f"因素组合中存在 {len(empty_cells)} 个空单元，完整交互模型无法稳定估计",
                    details={"empty_cells": empty_cells[:50]},
                ))
            if singleton_cells:
                issues.append(ValidationIssue(
                    code="singleton_factorial_cells", field="fixed_factors", severity=IssueSeverity.WARNING,
                    message=f"因素组合中有 {len(singleton_cells)} 个单元仅 1 条观测，误差估计可能不稳定",
                    details={"singleton_cells": singleton_cells[:50]},
                ))

    if method in {"linear_regression", "logistic_regression", "multinomial_logistic_regression", "ordinal_logistic_regression", "ancova"} and plan.dependent_variables:
        required = list(dict.fromkeys(plan.dependent_variables[:1] + plan.fixed_factors + plan.covariates))
        complete = frame[required].dropna()
        parameter_count = 1 + len(plan.covariates)
        for factor in plan.fixed_factors:
            parameter_count += max(0, int(complete[factor].nunique()) - 1)
        outcome_multiplier = 1
        if method == "multinomial_logistic_regression":
            outcome_multiplier = max(1, int(complete[plan.dependent_variables[0]].nunique()) - 1)
        estimated_parameters = parameter_count * outcome_multiplier
        if len(complete) <= estimated_parameters:
            issues.append(ValidationIssue(
                code="model_overparameterized", field="fixed_factors",
                message=f"完整案例 {len(complete)} 行不足以估计约 {estimated_parameters} 个模型参数；请减少预测变量或增加样本",
                details={"complete_cases": len(complete), "estimated_parameters": estimated_parameters},
            ))
        elif len(complete) < max(10, estimated_parameters * 5):
            issues.append(ValidationIssue(
                code="low_cases_per_parameter", field="fixed_factors", severity=IssueSeverity.WARNING,
                message=f"完整案例相对模型参数较少（约 {len(complete)}/{estimated_parameters}），估计可能不稳定",
                details={"complete_cases": len(complete), "estimated_parameters": estimated_parameters},
            ))

    if method == "logistic_regression" and plan.dependent_variables:
        outcome = plan.dependent_variables[0]
        for factor in plan.fixed_factors:
            table = pd.crosstab(frame[factor], frame[outcome])
            if table.shape[1] == 2 and (table == 0).any(axis=1).any():
                issues.append(ValidationIssue(
                    code="possible_complete_separation", field=factor, severity=IssueSeverity.WARNING,
                    message=f"分类预测量 {factor!r} 的部分水平只出现一种结局，可能导致完全或准完全分离",
                ))

    if method in {"oneway_manova", "twoway_manova", "threeway_manova"} and len(plan.dependent_variables) >= 2:
        required = [*plan.dependent_variables, *plan.fixed_factors]
        complete = frame[required].copy()
        for outcome in plan.dependent_variables:
            complete[outcome] = pd.to_numeric(complete[outcome], errors="coerce")
        complete = complete.dropna()
        matrix = complete[plan.dependent_variables]
        p_outcomes = len(plan.dependent_variables)
        if not matrix.empty and np.linalg.matrix_rank(matrix.to_numpy() - matrix.mean().to_numpy()) < p_outcomes:
            issues.append(ValidationIssue(
                code="rank_deficient_manova_outcomes", field="dependent_variables",
                message="多个因变量之间存在完全线性依赖，MANOVA 响应矩阵秩不足；请删除重复或线性组合变量",
            ))
        if not matrix.empty:
            corr = matrix.corr().abs().to_numpy(copy=True)
            np.fill_diagonal(corr, 0.0)
            max_corr = float(np.nanmax(corr)) if corr.size else 0.0
            if max_corr >= 0.98:
                issues.append(ValidationIssue(
                    code="extreme_manova_outcome_correlation", field="dependent_variables", severity=IssueSeverity.WARNING,
                    message=f"因变量最大绝对相关达到 {max_corr:.3f}，存在严重冗余或数值不稳定风险",
                    details={"max_abs_correlation": max_corr},
                ))
        if plan.fixed_factors and not complete.empty:
            cells = int(complete.groupby(plan.fixed_factors, observed=False).ngroups)
            residual_df = int(len(complete) - cells)
            if residual_df < p_outcomes:
                issues.append(ValidationIssue(
                    code="insufficient_manova_error_df", field="fixed_factors",
                    message=f"完整析因模型残差自由度约 {residual_df}，小于因变量数 {p_outcomes}，多元误差矩阵无法稳定估计",
                    details={"complete_cases": len(complete), "observed_cells": cells, "residual_df": residual_df, "outcomes": p_outcomes},
                ))
            elif residual_df < 2 * p_outcomes:
                issues.append(ValidationIssue(
                    code="low_manova_error_df", field="fixed_factors", severity=IssueSeverity.WARNING,
                    message=f"MANOVA 残差自由度约 {residual_df}，相对 {p_outcomes} 个因变量偏少，近似检验和协方差诊断可能不稳定",
                    details={"residual_df": residual_df, "outcomes": p_outcomes},
                ))

    posthoc_methods = plan.method_parameters.get("posthoc_methods", [])
    if isinstance(posthoc_methods, str):
        posthoc_methods = [posthoc_methods]
    posthoc_methods = [str(item).lower() for item in posthoc_methods]
    if "dunnett" in posthoc_methods:
        control = str(plan.method_parameters.get("control_group", "")).strip()
        if not control:
            issues.append(ValidationIssue(
                code="dunnett_control_required", field="method_parameters.control_group",
                message="选择 Dunnett 事后比较时必须指定对照水平",
            ))
        elif plan.fixed_factors:
            mappings, shared = _parse_dunnett_control_spec(control)
            available = {factor: _levels_as_text(frame[factor]) for factor in plan.fixed_factors}
            if mappings:
                missing_factors = [factor for factor in plan.fixed_factors if factor not in mappings]
                invalid = {
                    factor: mappings[factor]
                    for factor in plan.fixed_factors
                    if factor in mappings and mappings[factor] not in available[factor]
                }
                if missing_factors:
                    issues.append(ValidationIssue(
                        code="dunnett_factor_control_missing", field="method_parameters.control_group",
                        message=f"按因素指定 Dunnett 对照时，以下因素缺少对照水平: {missing_factors}",
                        details={"available_levels": available, "parsed_controls": mappings},
                    ))
                if invalid:
                    issues.append(ValidationIssue(
                        code="dunnett_control_not_found", field="method_parameters.control_group",
                        message=f"部分 Dunnett 对照水平未出现在对应因素中: {invalid}",
                        details={"available_levels": available, "parsed_controls": mappings},
                    ))
            elif shared is not None:
                missing = [factor for factor in plan.fixed_factors if shared not in available[factor]]
                matches = [factor for factor in plan.fixed_factors if shared in available[factor]]
                if missing:
                    issues.append(ValidationIssue(
                        code="dunnett_control_not_found", field="method_parameters.control_group",
                        message=(f"统一对照水平 {shared!r} 未出现在因素 {missing} 中；"
                                 "请改用按因素写法，例如 处理=CK;品种=对照品种。"),
                        details={"available_levels": available, "matched_factors": matches},
                    ))
                elif len(matches) > 1:
                    issues.append(ValidationIssue(
                        code="shared_dunnett_control", field="method_parameters.control_group", severity=IssueSeverity.WARNING,
                        message=f"统一对照值 {shared!r} 将同时用于多个因素 {matches}；请确认这些因素确实共享同名对照水平。",
                    ))

    return issues


def _minimum_complete_cases(method: str, predictor_count: int) -> int:
    if method in {"logistic_regression", "multinomial_logistic_regression", "ordinal_logistic_regression"}:
        return max(20, 5 * (predictor_count + 1))
    if method in {"linear_regression", "ancova", "linear_mixed_model", "mixed_anova"}:
        return max(8, 3 * (predictor_count + 2))
    if method in {"pearson_correlation", "spearman_correlation", "kendall_correlation"}:
        return 5
    if method in {"repeated_measures_anova", "friedman_test", "mixed_anova"}:
        return 6
    if method in {
        "chi_square_independence", "fisher_exact", "chi_square_goodness_of_fit", "mcnemar_test",
        "exact_binomial_test", "one_sample_proportion_ztest", "two_proportion_ztest",
        "k_proportion_chi_square", "barnard_exact", "boschloo_exact", "cochran_q_test",
        "bowker_symmetry", "stuart_maxwell", "cochran_mantel_haenszel", "breslow_day",
        "cohen_kappa", "fleiss_kappa", "cochran_armitage_trend",
    }:
        return 4
    return 3
