"""分析执行前检查。"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, ValidationError

from datawork.core.errors import IssueSeverity, ValidationIssue
from datawork.core.method_registry import get_method
from datawork.core.plan import AnalysisPlan
from datawork.core.splitting import SPLIT_TASK_HARD_LIMIT, SPLIT_TASK_WARNING_THRESHOLD, build_split_groups, projected_split_group_count
from datawork.core.validation import validate_plan_dataframe
from datawork.core.task_expansion import factor_tasks, outcome_tasks
from datawork.application.analysis_service import AnalysisService


class PreflightReport(BaseModel):
    ready: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    method: dict[str, Any] = Field(default_factory=dict)
    selections: dict[str, Any] = Field(default_factory=dict)
    data_summary: dict[str, Any] = Field(default_factory=dict)
    batch_summary: dict[str, Any] = Field(default_factory=dict)
    pairing_summary: dict[str, Any] = Field(default_factory=dict)
    task_hierarchy: dict[str, Any] = Field(default_factory=dict)
    design_review: dict[str, Any] = Field(default_factory=dict)


class PreflightService:
    def inspect(self, frame: pd.DataFrame, raw_plan: dict[str, Any]) -> PreflightReport:
        issues: list[ValidationIssue] = []
        method_name = str(raw_plan.get("method") or "").strip()
        if method_name in {"manova", "factorial_anova"}:
            legacy_parameters = raw_plan.get("method_parameters") if isinstance(raw_plan.get("method_parameters"), dict) else {}
            try:
                legacy_order = int(legacy_parameters.get("factor_model_order", 0) or 0)
            except (TypeError, ValueError):
                legacy_order = 0
            factor_count = len(_clean_list(raw_plan.get("fixed_factors")))
            if legacy_order not in {1, 2, 3}:
                legacy_order = min(max(factor_count, 1), 3)
            migration = (
                {1: "oneway_manova", 2: "twoway_manova", 3: "threeway_manova"}
                if method_name == "manova"
                else {1: "oneway_anova", 2: "twoway_anova", 3: "threeway_anova"}
            )
            method_name = migration[legacy_order]
            raw_plan = {**raw_plan, "method": method_name, "method_parameters": {key: value for key, value in legacy_parameters.items() if key != "factor_model_order"}}
        spec = None
        if not method_name:
            issues.append(_missing("method", "请选择统计方法"))
        else:
            try:
                spec = get_method(method_name)
            except ValueError:
                issues.append(ValidationIssue(code="unknown_method", field="method", message=f"无法识别统计方法: {method_name}"))

        split_rules = raw_plan.get("split_rules") if isinstance(raw_plan.get("split_rules"), list) else []
        rule_columns = [str(rule.get("column") or "").strip() for rule in split_rules if isinstance(rule, dict)]
        normalized = {
            **raw_plan,
            "dependent_variables": _clean_list(raw_plan.get("dependent_variables")),
            "fixed_factors": _clean_list(raw_plan.get("fixed_factors")),
            "covariates": _clean_list(raw_plan.get("covariates")),
            "random_factors": _clean_list(raw_plan.get("random_factors")),
            "random_slopes": _clean_list(raw_plan.get("random_slopes")),
            "emm_factors": _clean_list(raw_plan.get("emm_factors")),
            "split_by": list(dict.fromkeys([*_clean_list(raw_plan.get("split_by")), *[item for item in rule_columns if item]])),
            "split_rules": split_rules,
            "derived_columns": raw_plan.get("derived_columns") if isinstance(raw_plan.get("derived_columns"), list) else [],
            "pairing": raw_plan.get("pairing") if isinstance(raw_plan.get("pairing"), dict) else None,
            "dependent_variable_groups": raw_plan.get("dependent_variable_groups") if isinstance(raw_plan.get("dependent_variable_groups"), list) else [],
            "subject_id": _clean_scalar(raw_plan.get("subject_id")),
            "repeated_factor": _clean_scalar(raw_plan.get("repeated_factor")),
            "method_parameters": raw_plan.get("method_parameters") if isinstance(raw_plan.get("method_parameters"), dict) else {},
            "factor_combinations_enabled": bool(raw_plan.get("factor_combinations_enabled", False)),
            "factor_combination_min_order": raw_plan.get("factor_combination_min_order"),
            "factor_combination_max_order": raw_plan.get("factor_combination_max_order"),
            "factor_combination_labels": raw_plan.get("factor_combination_labels", {}),
            "cross_model_p_adjust": raw_plan.get("cross_model_p_adjust"),
            "combination_p_adjust": raw_plan.get("combination_p_adjust", "holm"),
            "estimate_marginal_means": bool(raw_plan.get("estimate_marginal_means", False)),
            "contrast_correction": raw_plan.get("contrast_correction", "holm"),
            "diagnostic_plots": bool(raw_plan.get("diagnostic_plots", True)),
        }
        # 在进入 Pydantic 模型前给出可定位的缺失项与角色冲突。
        if spec is not None:
            if len(normalized["dependent_variables"]) < spec.min_dependent_vars:
                issues.append(_missing("dependent_variables", f"{spec.label_zh} 至少需要 {spec.min_dependent_vars} 个因变量"))
            if len(normalized["fixed_factors"]) < spec.min_fixed_factors:
                count_word = "恰好" if spec.max_fixed_factors == spec.min_fixed_factors else "至少"
                issues.append(_missing("fixed_factors", f"{spec.label_zh} {count_word}需要 {spec.min_fixed_factors} 个固定/分类因素"))
            if len(normalized["covariates"]) < spec.min_covariates:
                issues.append(_missing("covariates", f"{spec.label_zh} 至少需要 {spec.min_covariates} 个协变量"))
            if len(normalized["random_factors"]) < spec.min_random_factors:
                issues.append(_missing("random_factors", f"{spec.label_zh} 至少需要 {spec.min_random_factors} 个随机分组因素"))
            if len(normalized["random_slopes"]) < spec.min_random_slopes:
                issues.append(_missing("random_slopes", f"{spec.label_zh} 至少需要 {spec.min_random_slopes} 个随机斜率"))
            if spec.requires_subject_id and not normalized["subject_id"]:
                issues.append(_missing("subject_id", f"{spec.label_zh} 需要受试者/样本 ID"))
            if spec.requires_repeated_factor and not normalized["repeated_factor"]:
                issues.append(_missing("repeated_factor", f"{spec.label_zh} 需要重复/时间因素"))
            if method_name in {"multifactor_anova", "multifactor_manova"}:
                try:
                    model_order = int(normalized["method_parameters"].get("factor_model_order", 4))
                except (TypeError, ValueError):
                    model_order = 0
                if model_order not in range(4, 9):
                    issues.append(ValidationIssue(
                        code="invalid_factor_model_order", field="method_parameters",
                        message="多因素模型阶数必须是 4–8 之间的整数。",
                        details={"factor_model_order": model_order},
                    ))
                elif len(normalized["fixed_factors"]) != model_order:
                    issues.append(ValidationIssue(
                        code="factor_order_mismatch", field="fixed_factors",
                        message=f"当前模型阶数为 {model_order}，必须恰好选择 {model_order} 个分类因素；当前选择了 {len(normalized['fixed_factors'])} 个。",
                        details={"factor_model_order": model_order, "selected_factor_count": len(normalized["fixed_factors"])},
                    ))
        role_sets = {
            "dependent_variables": set(normalized["dependent_variables"]),
            "fixed_factors": set(normalized["fixed_factors"]),
            "covariates": set(normalized["covariates"]),
            "random_factors": set(normalized["random_factors"]),
            "split_by": set(normalized["split_by"]),
            "subject_id": {normalized["subject_id"]} if normalized["subject_id"] else set(),
            "repeated_factor": {normalized["repeated_factor"]} if normalized["repeated_factor"] else set(),
        }
        names = list(role_sets)
        for index, left in enumerate(names):
            for right in names[index + 1:]:
                overlap = sorted(role_sets[left] & role_sets[right])
                if overlap:
                    if {left, right} == {"fixed_factors", "split_by"} and normalized.get("interface_mode") == "professional":
                        continue
                    issues.append(ValidationIssue(code="overlapping_roles", field="split_by" if "split_by" in {left, right} else right, message=f"这些列被重复分配到冲突角色: {overlap}", details={"columns": overlap, "roles": [left, right]}))

        plan: AnalysisPlan | None = None
        if spec is not None and not any(issue.severity == IssueSeverity.ERROR for issue in issues):
            try:
                plan = AnalysisPlan.model_validate(normalized)
            except ValidationError as exc:
                for item in exc.errors():
                    location = list(item.get("loc") or [])
                    field = str(location[0]) if location else None
                    issues.append(ValidationIssue(code="invalid_plan_value", field=field, message=str(item.get("msg") or "分析计划配置无效"), details={"location": location}))
        inspection_frame = frame
        transformation_log: list[dict[str, Any]] = []
        if plan is not None:
            try:
                inspection_frame, transformation_log, transformation_warnings = AnalysisService.prepare_frame(frame, plan)
                for message in transformation_warnings:
                    issues.append(ValidationIssue(
                        code="transformation_invalid_values",
                        severity=IssueSeverity.WARNING,
                        field="pairing" if plan.pairing else "derived_columns",
                        message=message,
                    ))
                issues.extend(validate_plan_dataframe(plan, inspection_frame).issues)
            except (ValueError, RuntimeError) as exc:
                issues.append(ValidationIssue(
                    code="invalid_transformation",
                    field="pairing" if plan.pairing else "derived_columns",
                    message=str(exc),
                ))
                plan = None

        batch_summary = self._batch_summary(inspection_frame, plan, issues) if plan and plan.is_batch else {
            "enabled": False, "dimensions": [], "group_count": 0,
            "ready_group_count": 0, "problem_group_count": 0, "groups": [],
        }
        method_payload: dict[str, Any] = {}
        if spec is not None:
            method_payload = {
                "name": spec.name, "label_zh": spec.label_zh, "category": spec.category,
                "purpose": spec.purpose, "variable_relationship": spec.variable_relationship,
                "supports_batch": spec.supports_batch, "supports_emm": spec.supports_emm,
                "supports_diagnostic_plots": spec.supports_diagnostic_plots, "status": spec.status.value,
            }
        selected_columns = list(dict.fromkeys(
            normalized["dependent_variables"] + normalized["fixed_factors"] + normalized["covariates"] +
            normalized["random_factors"] + normalized["random_slopes"] + normalized["emm_factors"] + normalized["split_by"] +
            ([normalized["subject_id"]] if normalized["subject_id"] else []) +
            ([normalized["repeated_factor"]] if normalized["repeated_factor"] else [])
        ))
        design_review = _build_design_review(inspection_frame, plan, issues)
        pairing_summary = _build_pairing_summary(plan, transformation_log)
        task_hierarchy = _build_task_hierarchy(plan, batch_summary)
        return PreflightReport(
            ready=not any(issue.severity == IssueSeverity.ERROR for issue in issues),
            issues=issues, method=method_payload,
            selections={key: normalized.get(key) for key in ["interface_mode", "dependent_variables", "dependent_variable_groups", "fixed_factors", "covariates", "random_factors", "random_slopes", "subject_id", "repeated_factor", "split_by", "split_rules", "derived_columns", "pairing", "alpha", "ss_type", "test_value", "method_parameters", "factor_combinations_enabled", "factor_combination_order", "factor_combination_min_order", "factor_combination_max_order", "factor_combination_labels", "cross_model_p_adjust", "combination_p_adjust", "estimate_marginal_means", "emm_factors", "contrast_correction", "diagnostic_plots", "calibration_enabled", "calibration_method", "calibration_columns", "calibration_baseline_column", "calibration_baseline_value"]},
            data_summary={
                "rows": int(inspection_frame.shape[0]), "columns": int(inspection_frame.shape[1]),
                "complete_rows_for_plan": int(inspection_frame[selected_columns].dropna().shape[0]) if selected_columns and all(column in inspection_frame.columns for column in selected_columns) else int(len(inspection_frame)),
            },
            batch_summary=batch_summary,
            pairing_summary=pairing_summary,
            task_hierarchy=task_hierarchy,
            design_review=design_review,
        )

    @staticmethod
    def _batch_summary(frame: pd.DataFrame, plan: AnalysisPlan, issues: list[ValidationIssue]) -> dict[str, Any]:
        spec = get_method(plan.method)
        dependent_tasks = outcome_tasks(plan)
        factor_sets = factor_tasks(plan)
        projected_split_count = projected_split_group_count(frame, plan)
        if projected_split_count > SPLIT_TASK_HARD_LIMIT:
            return {
                "enabled": True, "split_by": plan.split_by,
                "factor_combinations_enabled": plan.factor_combinations_enabled,
                "factor_combination_count": len(factor_sets),
                "outcome_group_count": len(dependent_tasks),
                "split_group_count": projected_split_count,
                "factor_model_count": len(factor_sets),
                "p_adjust": plan.cross_model_p_adjust or plan.combination_p_adjust,
                "dimensions": plan.split_by, "group_count": projected_split_count,
                "ready_group_count": 0, "problem_group_count": projected_split_count,
                "skipped_group_count": 0,
                "expanded_task_count": len(dependent_tasks) * len(factor_sets) * projected_split_count,
                "groups": [],
            }
        group_items = build_split_groups(frame, plan, include_empty=True)
        expanded_task_count = len(dependent_tasks) * len(factor_sets) * len(group_items)
        issue_codes = {issue.code for issue in issues}
        if expanded_task_count > SPLIT_TASK_HARD_LIMIT and "expanded_task_limit_exceeded" not in issue_codes:
            issues.append(ValidationIssue(
                code="expanded_task_limit_exceeded", field="split_by",
                message=(f"当前计划会生成 {expanded_task_count} 个分析任务，超过安全上限 "
                         f"{SPLIT_TASK_HARD_LIMIT}；请减少因变量、因素组合或拆分组"),
                details={"task_count": expanded_task_count, "hard_limit": SPLIT_TASK_HARD_LIMIT},
            ))
        elif expanded_task_count > SPLIT_TASK_WARNING_THRESHOLD and "large_expanded_task_plan" not in issue_codes:
            issues.append(ValidationIssue(
                code="large_expanded_task_plan", severity=IssueSeverity.WARNING, field="split_by",
                message=f"当前计划将生成 {expanded_task_count} 个分析任务，执行和报告生成可能较慢",
                details={"task_count": expanded_task_count, "warning_threshold": SPLIT_TASK_WARNING_THRESHOLD},
            ))
        groups = []
        ready_count = 0
        task_id = 0
        for outcome_task in dependent_tasks:
            dependent_set = list(outcome_task.variables)
            for factor_set in factor_sets:
                for labels, raw_subset in group_items:
                    task_id += 1
                    labels = dict(labels)
                    if outcome_task.name and plan.dependent_variable_groups:
                        labels = {
                            "dependent_group": outcome_task.name,
                            "dependent_variables": " | ".join(dependent_set),
                            **labels,
                        }
                    elif spec.dependent_mode == "single" and len(dependent_tasks) > 1:
                        labels = {"dependent_variable": dependent_set[0], **labels}
                    if plan.factor_combinations_enabled:
                        canonical_combination = " × ".join(factor_set)
                        labels = {
                            "task_id": task_id,
                            "factor_combination": plan.factor_combination_labels.get(
                                canonical_combination, canonical_combination
                            ),
                            "combination_order": len(factor_set),
                            **labels,
                        }
                        if plan.factor_combination_labels:
                            labels["factor_columns"] = canonical_combination
                    if raw_subset.empty:
                        groups.append({
                            "key": labels, "rows": 0, "ready": False, "skipped": True,
                            "reasons": ["该拆分组合没有数据，已跳过"], "warnings": [],
                        })
                        continue
                    required = list(dict.fromkeys(dependent_set + factor_set + plan.covariates + plan.random_factors + plan.random_slopes + ([plan.subject_id] if plan.subject_id else []) + ([plan.repeated_factor] if plan.repeated_factor else [])))
                    subset = raw_subset.dropna(subset=required) if required else raw_subset
                    sub_plan = AnalysisService._build_combination_subplan(
                        plan, list(dependent_set), list(factor_set)
                    )
                    task_report = validate_plan_dataframe(sub_plan, subset)
                    reasons = [item.message for item in task_report.issues if item.severity == IssueSeverity.ERROR]
                    warnings = [item.message for item in task_report.issues if item.severity == IssueSeverity.WARNING]
                    ready = not reasons
                    ready_count += int(ready)
                    groups.append({
                        "key": labels, "rows": int(len(subset)), "ready": ready,
                        "reasons": reasons, "warnings": warnings,
                    })
        skipped_count = sum(bool(item.get("skipped")) for item in groups)
        problem_count = len(groups) - ready_count - skipped_count
        if problem_count:
            severity = IssueSeverity.ERROR if ready_count == 0 else IssueSeverity.WARNING
            message = (f"全部 {problem_count} 个批量任务均无法执行，请调整变量或拆分条件" if ready_count == 0
                       else f"{problem_count} 个批量任务可能无法完成，将在合并结果中保留失败原因")
            issues.append(ValidationIssue(code="batch_groups_not_ready", field="split_by", severity=severity, message=message, details={"problem_group_count": problem_count, "ready_group_count": ready_count}))
        dimensions = (
            ["factor_combination", "combination_order"]
            + (["factor_columns"] if plan.factor_combinations_enabled and plan.factor_combination_labels else [])
            if plan.factor_combinations_enabled else []
        )
        if plan.dependent_variable_groups:
            dimensions += ["dependent_group", "dependent_variables"]
        elif spec.dependent_mode == "single" and len(dependent_tasks) > 1:
            dimensions += ["dependent_variable"]
        dimensions += plan.split_by
        return {
            "enabled": True,
            "split_by": plan.split_by,
            "factor_combinations_enabled": plan.factor_combinations_enabled,
            "factor_combination_count": len(factor_sets),
            "outcome_group_count": len(dependent_tasks),
            "factor_model_count": len(factor_sets),
            "split_group_count": len(group_items),
            "p_adjust": plan.cross_model_p_adjust or plan.combination_p_adjust,
            "dimensions": dimensions,
            "group_count": len(groups),
            "ready_group_count": ready_count,
            "problem_group_count": problem_count,
            "skipped_group_count": skipped_count,
            "expanded_task_count": expanded_task_count,
            "groups": groups[:200],
        }


def _build_pairing_summary(
    plan: AnalysisPlan | None,
    transformation_log: list[dict[str, Any]],
) -> dict[str, Any]:
    if plan is None or plan.pairing is None:
        return {"enabled": False}
    audit = next(
        (item for item in transformation_log if item.get("operation") == "pairing"),
        None,
    )
    if audit is None:
        return {
            "enabled": True,
            "status": "blocked",
            "group_column": plan.pairing.group_column,
        }
    split_relationships = []
    match_columns = set(plan.pairing.match_columns)
    for column in plan.split_by:
        if column == plan.pairing.group_column:
            relationship = "配对分组并拆分"
            detail = "配对分组列；配对后按处理水平拆分"
        elif column in match_columns:
            relationship = "参与匹配并拆分"
            detail = "先作为标签参与配对，再按同一标签拆分"
        else:
            relationship = "仅配对后拆分"
            detail = "与公式无关；配对完成后作用于整个分析任务"
        split_relationships.append({
            "column": column,
            "relationship": relationship,
            "detail": detail,
            "recommend_add_to_match": False,
        })
    return {
        "enabled": True,
        "status": "ready",
        **audit,
        "split_relationships": split_relationships,
    }


def _build_task_hierarchy(
    plan: AnalysisPlan | None,
    batch_summary: dict[str, Any],
) -> dict[str, Any]:
    if plan is None:
        return {"enabled": False, "task_count": 0}
    outcomes = [
        {
            "name": task.name or (task.variables[0] if len(task.variables) == 1 else "全部联合因变量"),
            "dependent_variables": list(task.variables),
        }
        for task in outcome_tasks(plan)
    ]
    factors = [
        {
            "name": plan.factor_combination_labels.get(" × ".join(items), " × ".join(items)),
            "fixed_factors": items,
        }
        for items in factor_tasks(plan)
    ]
    return {
        "enabled": True,
        "outcome_groups": outcomes,
        "factor_models": factors,
        "split_dimensions": list(plan.split_by),
        "task_count": int(batch_summary.get("expanded_task_count") or 1),
        "tasks": [item.get("key", {}) for item in batch_summary.get("groups", [])],
    }


def _build_design_review(
    frame: pd.DataFrame, plan: AnalysisPlan | None, issues: list[ValidationIssue]
) -> dict[str, Any]:
    """生成可直接展示且不依赖外部 AI 的统计设计审查。"""
    if plan is None:
        return {
            "status": "blocked", "headline": "分析计划尚未完整",
            "summary": "完成统计方法和变量角色后，系统会检查重复、平衡性、样本量与模型可估计性。",
            "metrics": [], "strengths": [], "risks": ["当前无法建立完整设计矩阵。"],
            "actions": ["先补齐标记为必须补充的变量和参数。"], "engine": "待确定",
        }
    required = list(dict.fromkeys(plan.all_columns))
    complete = frame[required].dropna() if required else frame.copy()
    metrics: list[dict[str, Any]] = [
        {"label": "总行数", "value": int(len(frame)), "status": "info"},
        {"label": "计划完整案例", "value": int(len(complete)), "status": "good" if len(complete) >= 10 else "warning"},
    ]
    strengths: list[str] = []
    risks: list[str] = []
    actions: list[str] = []
    engine = get_method(plan.method).label_zh

    if plan.fixed_factors and not complete.empty:
        counts = complete.groupby(plan.fixed_factors, observed=False).size()
        if len(counts):
            minimum, maximum = int(counts.min()), int(counts.max())
            ratio = float(minimum / maximum) if maximum else 0.0
            metrics.extend([
                {"label": "观察设计单元", "value": int(len(counts)), "status": "info"},
                {"label": "最小单元重复", "value": minimum, "status": "good" if minimum >= 3 else "warning"},
                {"label": "单元平衡比", "value": round(ratio, 3), "status": "good" if ratio >= 0.8 else "warning"},
            ])
            if minimum >= 2:
                strengths.append(f"每个已观察因素组合至少有 {minimum} 条完整观测，可估计残差。")
            else:
                risks.append("至少一个因素组合只有单个观测，误差和交互估计容易不稳定。")
                actions.append("优先补充单元重复，或降低模型阶数并明确无法估计的交互。")
            if ratio < 0.8:
                risks.append(f"设计单元不平衡（最小/最大={ratio:.2f}），原始边际均值不应替代模型 EMM。")
                actions.append("保留 Type III/Sum 对比，并使用模型估计边际均值开展比较。")
            else:
                strengths.append("因素组合样本量整体较平衡。")

    if plan.method in {"oneway_manova", "twoway_manova", "threeway_manova"} and len(plan.dependent_variables) >= 2 and not complete.empty:
        p = len(plan.dependent_variables)
        cells = int(complete.groupby(plan.fixed_factors, observed=False).ngroups) if plan.fixed_factors else 1
        residual_df = int(len(complete) - cells)
        matrix = complete[plan.dependent_variables].apply(pd.to_numeric, errors="coerce")
        corr = matrix.corr().abs().to_numpy(copy=True)
        np.fill_diagonal(corr, 0.0)
        max_corr = float(np.nanmax(corr)) if corr.size else 0.0
        metrics.extend([
            {"label": "联合因变量数", "value": p, "status": "info"},
            {"label": "近似残差自由度", "value": residual_df, "status": "good" if residual_df >= 2 * p else "warning"},
            {"label": "最大因变量相关", "value": round(max_corr, 3), "status": "warning" if max_corr >= 0.9 else "good"},
        ])
        engine = f"{len(plan.fixed_factors)} 因素完整析因 MANOVA"
        if residual_df < p:
            risks.append("残差自由度少于因变量数，多元误差矩阵可能奇异。")
            actions.append("增加单元重复、减少因变量或降低因素/交互复杂度。")
        elif residual_df < 2 * p:
            risks.append("多元模型自由度储备偏低，Box's M 与近似 F 可能不稳定。")
        else:
            strengths.append("残差自由度能够覆盖联合因变量维度。")
        if max_corr >= 0.9:
            risks.append("部分因变量高度相关，可能重复表达同一信息。")
            actions.append("检查相关矩阵、测量定义与条件数，必要时删减冗余指标或先降维。")
        actions.append("先解释 Pillai/Wilks 等联合效应，再查看经校正的单变量跟进和事后比较。")

    if plan.subject_id and plan.repeated_factor and not complete.empty:
        counts = complete.groupby(plan.subject_id, observed=True)[plan.repeated_factor].nunique()
        expected = int(complete[plan.repeated_factor].nunique())
        incomplete = int((counts < expected).sum())
        metrics.extend([
            {"label": "对象数", "value": int(complete[plan.subject_id].nunique()), "status": "info"},
            {"label": "重复水平", "value": expected, "status": "info"},
            {"label": "缺失重复对象", "value": incomplete, "status": "warning" if incomplete else "good"},
        ])
        if plan.method == "mixed_anova":
            mode = str(plan.method_parameters.get("analysis_mode", "auto"))
            if mode == "mixedlm" or incomplete or len(plan.fixed_factors) > 1:
                engine = "线性混合效应模型（对象随机截距）"
                strengths.append("MixedLM 路径可利用不平衡或部分缺失的可用观测，而不要求删除整个对象。")
            else:
                engine = "经典平衡混合 ANOVA（自动条件满足时）" if mode == "auto" else "经典平衡混合 ANOVA"
            if incomplete:
                risks.append(f"有 {incomplete} 个对象缺少重复水平；经典 ANOVA 不适用。")
                actions.append("使用自动/MixedLM 模式，并说明缺失机制与随机效应结构。")

    posthoc_methods = plan.method_parameters.get("posthoc_methods", [])
    if isinstance(posthoc_methods, str):
        posthoc_methods = [posthoc_methods]
    posthoc_methods = [str(item).lower() for item in posthoc_methods]
    if posthoc_methods:
        metrics.append({"label": "事后比较", "value": ", ".join(posthoc_methods), "status": "warning" if set(posthoc_methods) & {"duncan", "lsd"} else "good"})
        if set(posthoc_methods) & {"duncan", "lsd"}:
            risks.append("已选择 Duncan/LSD 宽松多重比较，第一类错误控制弱于 Tukey/Holm。")
            actions.append("正式报告建议同时给出 Tukey 或 Holm 结果，并说明选择宽松检验的预设依据。")
        if "dunnett" in posthoc_methods:
            actions.append("确认对照水平唯一；Dunnett 只比较处理组与对照组，不生成完整字母分组。")

    error_count = sum(item.severity == IssueSeverity.ERROR for item in issues)
    warning_count = sum(item.severity == IssueSeverity.WARNING for item in issues)
    issue_risks = [item.message for item in issues if item.severity == IssueSeverity.ERROR][:5]
    risks = list(dict.fromkeys([*issue_risks, *risks]))
    if error_count:
        status, headline = "blocked", "设计审查未通过，当前不应运行"
    elif warning_count or risks:
        status, headline = "attention", "模型可运行，但需要重点复核设计风险"
    else:
        status, headline = "ready", "设计结构与所选方法基本匹配"
    if not strengths:
        strengths.append("变量角色和方法参数已进入统一预检流程。")
    if not actions:
        actions.append("运行后结合诊断、效应量和研究设计解释结果，不仅依据 p 值。")
    return {
        "status": status, "headline": headline,
        "summary": f"预计使用：{engine}。发现 {error_count} 个阻断项和 {warning_count} 个提醒。",
        "engine": engine, "metrics": metrics,
        "strengths": list(dict.fromkeys(strengths))[:6],
        "risks": risks[:8], "actions": list(dict.fromkeys(actions))[:8],
    }


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _clean_scalar(value: Any) -> str | None:
    cleaned = str(value).strip() if value is not None else ""
    return cleaned or None


def _missing(field: str, message: str) -> ValidationIssue:
    return ValidationIssue(code="missing_selection", field=field, message=message)
