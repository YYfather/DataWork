"""统一统计分析执行服务。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests
from pydantic import BaseModel, Field

from datawork.application.executors import get_executor
from datawork.core.errors import DataWorkError, ErrorCode
from datawork.core.formula import apply_derived_columns
from datawork.core.method_registry import get_method
from datawork.core.pairing import apply_pairing
from datawork.core.plan import AnalysisPlan
from datawork.core.splitting import build_split_groups
from datawork.core.task_expansion import factor_tasks, outcome_task_labels, outcome_tasks
from datawork.core.provenance import (
    DatasetFingerprint,
    ReproducibilityMetadata,
    canonical_json_hash,
    dataframe_hash,
)
from datawork.core.validation import ValidationReport, validate_plan_dataframe
from datawork.engine.batch import BatchAnalysisResult, BatchResult, _build_batch_summary
from datawork.engine.result import StatisticalResult


class ExecutionContext(BaseModel):
    run_id: str = ""
    dataset_fingerprint: DatasetFingerprint | None = None
    source_filename: str = ""
    sheet_name: str = ""
    cleaning_log: list[dict[str, Any]] = Field(default_factory=list)
    random_seed: int | None = None
    extra_parameters: dict[str, Any] = Field(default_factory=dict)


@dataclass
class AnalysisExecution:
    run_id: str
    plan: AnalysisPlan
    result: StatisticalResult | BatchAnalysisResult
    validation: ValidationReport
    provenance: ReproducibilityMetadata
    warnings: list[str] = field(default_factory=list)


class AnalysisService:
    """严格验证并执行分析计划；绝不静默切换统计方法。"""

    def run(
        self,
        df: pd.DataFrame,
        plan: AnalysisPlan,
    ) -> StatisticalResult | BatchAnalysisResult:
        """兼容 0.2 的直接结果入口。"""
        return self.execute(df, plan).result

    def execute(
        self,
        df: pd.DataFrame,
        plan: AnalysisPlan,
        *,
        context: ExecutionContext | None = None,
    ) -> AnalysisExecution:
        execution_frame, transformation_log, transformation_warnings = self.prepare_frame(df, plan)
        validation = validate_plan_dataframe(plan, execution_frame)
        validation.raise_for_errors()
        spec = get_method(plan.method)
        if not spec.is_runnable:
            raise DataWorkError(
                ErrorCode.METHOD_UNAVAILABLE,
                f"{spec.label_zh} 尚未实现，分析未执行。{spec.notes}",
                status_code=422,
            )

        context = context or ExecutionContext()
        run_id = context.run_id or uuid4().hex
        fingerprint = context.dataset_fingerprint or DatasetFingerprint(
            source_sha256=dataframe_hash(df),
            cleaned_sha256=dataframe_hash(execution_frame),
            source_size_bytes=0,
            n_rows=int(execution_frame.shape[0]),
            n_columns=int(execution_frame.shape[1]),
            source_filename=context.source_filename,
            sheet_name=context.sheet_name,
        )
        provenance = ReproducibilityMetadata(
            run_id=run_id,
            plan_sha256=canonical_json_hash(plan),
            dataset=fingerprint,
            cleaning_log=[*context.cleaning_log, *transformation_log],
            parameters={
                **plan.model_dump(mode="json"),
                **context.extra_parameters,
            },
            random_seed=context.random_seed,
        )

        try:
            if plan.is_batch:
                if not spec.supports_batch:
                    raise DataWorkError(
                        ErrorCode.INVALID_PLAN,
                        f"{spec.label_zh} 当前不支持批量拆分",
                    )
                result: StatisticalResult | BatchAnalysisResult = self._execute_batch(
                    df=execution_frame,
                    plan=plan,
                )
            else:
                executor = get_executor(spec.executor)
                result = executor(execution_frame, plan)
        except DataWorkError:
            raise
        except (ValueError, RuntimeError) as exc:
            raise DataWorkError(
                ErrorCode.EXECUTION_FAILED,
                str(exc),
                status_code=422,
                details={"method": plan.method, "run_id": run_id},
            ) from exc

        warning_messages = list(dict.fromkeys([
            *transformation_warnings,
            *[issue.message for issue in validation.warnings],
        ]))
        if isinstance(result, StatisticalResult):
            result.analysis_id = run_id
            result.warnings = list(dict.fromkeys(result.warnings + warning_messages))
            result.provenance = {
                **result.provenance,
                "reproducibility": provenance.model_dump(mode="json"),
            }

        return AnalysisExecution(
            run_id=run_id,
            plan=plan,
            result=result,
            validation=validation,
            provenance=provenance,
            warnings=warning_messages,
        )

    @classmethod
    def prepare_frame(
        cls,
        df: pd.DataFrame,
        plan: AnalysisPlan,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]], list[str]]:
        """按唯一顺序应用配对、普通派生列与校正。"""
        paired, pairing_log, pairing_warnings = apply_pairing(df, plan)
        derived, derived_log, derived_warnings = apply_derived_columns(paired, plan.derived_columns)
        # 自定义列预览覆盖完整数据，但正式计划中的质量计数只针对至少进入
        # 一个拆分子任务的行。自定义列本身不能作为拆分列，因此可以安全地
        # 在配对后的处理侧列上确定分析范围，而不会形成依赖环。
        if plan.derived_columns and plan.split_by:
            assigned_indices: set[Any] = set()
            for _labels, subset in build_split_groups(paired, plan):
                assigned_indices.update(subset.index.tolist())
            if assigned_indices:
                scoped = paired.loc[paired.index.isin(assigned_indices)]
                _scoped_frame, derived_log, derived_warnings = apply_derived_columns(
                    scoped, plan.derived_columns
                )
            else:
                derived_warnings = []
                derived_log = [
                    {**item, "missing_result_count": 0, "invalid_operation_count": 0}
                    for item in derived_log
                ]
        calibrated, calibration_log = cls._apply_calibration(derived, plan)
        transformation_log = [
            *([pairing_log] if pairing_log is not None else []),
            *derived_log,
            *calibration_log,
        ]
        warnings = list(dict.fromkeys([*pairing_warnings, *derived_warnings]))
        return calibrated, transformation_log, warnings

    @staticmethod
    def _apply_calibration(df: pd.DataFrame, plan: AnalysisPlan) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        """按专业计划显式校正数值列，并把操作写入可复现清理日志。"""
        if not plan.calibration_enabled:
            return df, []
        calibrated = df.copy()
        columns = list(plan.calibration_columns)
        for column in columns:
            if column not in calibrated.columns:
                raise DataWorkError(ErrorCode.INVALID_PLAN, f"校正列不存在: {column}")
            numeric = pd.to_numeric(calibrated[column], errors="coerce")
            if numeric.notna().sum() != calibrated[column].notna().sum():
                raise DataWorkError(ErrorCode.INVALID_PLAN, f"校正列必须是数值列: {column}")
            if plan.calibration_method == "zscore":
                center = float(numeric.mean())
                scale = float(numeric.std(ddof=1))
                if not np.isfinite(scale) or scale <= 0:
                    raise DataWorkError(ErrorCode.INVALID_PLAN, f"校正列 {column} 没有可用的标准差")
                calibrated[column] = (numeric - center) / scale
            elif plan.calibration_method == "robust_zscore":
                center = float(numeric.median())
                mad = float((numeric - center).abs().median())
                scale = 1.4826 * mad
                if not np.isfinite(scale) or scale <= 0:
                    raise DataWorkError(ErrorCode.INVALID_PLAN, f"校正列 {column} 没有可用的稳健尺度")
                calibrated[column] = (numeric - center) / scale
            else:
                baseline_column = str(plan.calibration_baseline_column)
                if baseline_column not in calibrated.columns:
                    raise DataWorkError(ErrorCode.INVALID_PLAN, f"基准列不存在: {baseline_column}")
                mask = calibrated[baseline_column].astype(str) == str(plan.calibration_baseline_value)
                if not mask.any():
                    raise DataWorkError(
                        ErrorCode.INVALID_PLAN,
                        f"基准列 {baseline_column} 中未找到基准值 {plan.calibration_baseline_value}",
                    )
                center = float(numeric.loc[mask].mean())
                if not np.isfinite(center):
                    raise DataWorkError(ErrorCode.INVALID_PLAN, f"校正列 {column} 的基准均值不可用")
                calibrated[column] = numeric - center
        return calibrated, [{
            "operation": "calibration",
            "method": plan.calibration_method,
            "columns": columns,
            "baseline_column": plan.calibration_baseline_column,
            "baseline_value": plan.calibration_baseline_value,
            "purpose": "消除系统偏差、对齐基准特征空间并降低极值引起的预测偏移",
        }]

    @staticmethod
    def _execute_batch(
        *,
        df: pd.DataFrame,
        plan: AnalysisPlan,
    ) -> BatchAnalysisResult:
        """展开因变量、分类因素组合与拆分列，并执行同一注册方法。

        分类因素组合仅使用用户选中的候选因素，不根据列名、关键词或领域语义推断。
        """
        spec = get_method(plan.method)
        results: list[BatchResult] = []

        dependent_tasks = outcome_tasks(plan)
        factor_sets = factor_tasks(plan)

        group_items = build_split_groups(df, plan)

        label_outcome = len(dependent_tasks) > 1
        task_index = 0
        for outcome_task in dependent_tasks:
            dependent_set = list(outcome_task.variables)
            for factor_set in factor_sets:
                for group_info, raw_subset in group_items:
                    task_index += 1
                    info = dict(group_info)
                    info = {
                        **outcome_task_labels(
                            outcome_task,
                            include_single=label_outcome,
                            include_joint_all=spec.dependent_mode == "joint",
                        ),
                        **info,
                    }
                    if plan.factor_combinations_enabled:
                        canonical_combination = " × ".join(factor_set)
                        info = {
                            "task_id": task_index,
                            "factor_combination": plan.factor_combination_labels.get(
                                canonical_combination, canonical_combination
                            ),
                            "combination_order": len(factor_set),
                            **info,
                        }
                        if plan.factor_combination_labels:
                            info["factor_columns"] = canonical_combination
                    else:
                        info = {"task_id": task_index, **info}

                    sub_plan = AnalysisService._build_combination_subplan(plan, dependent_set, factor_set)
                    required = sub_plan.all_columns
                    subset = raw_subset.dropna(subset=required).copy() if required else raw_subset.copy()
                    key_string = ", ".join(f"{name}={value}" for name, value in info.items()) or plan.method
                    try:
                        if subset.empty:
                            raise ValueError("当前任务没有完整案例")
                        subset_validation = validate_plan_dataframe(sub_plan, subset)
                        subset_validation.raise_for_errors()
                        executor = get_executor(get_method(sub_plan.method).executor)
                        statistical_result = executor(subset, sub_plan)
                        records = AnalysisService._result_records(statistical_result)
                        legacy_tests = [{
                            "effect": item.get("effect", item.get("term", item.get("metric", ""))),
                            "statistic_name": item.get("statistic_name", ""),
                            "statistic_value": item.get("statistic_value"),
                            "p": item.get("p_value"),
                            "effect_size_name": item.get("effect_size_name", ""),
                            "effect_size_value": item.get("effect_size_value"),
                            "significant": item.get("significant", False),
                        } for item in records if item.get("result_type") in {"test", "coefficient"}]
                        results.append(BatchResult(
                            subset_key=key_string, subset_info=info, n_rows=int(len(subset)),
                            omnibus_tests=legacy_tests, records=records, result=statistical_result,
                        ))
                    except Exception as exc:
                        results.append(BatchResult(
                            subset_key=key_string, subset_info=info, n_rows=int(len(subset)),
                            omnibus_tests=[], records=[], error=str(exc)[:500],
                        ))

        summary_split_columns: list[str] = []
        if plan.factor_combinations_enabled:
            summary_split_columns += ["task_id", "factor_combination", "combination_order"]
            if plan.factor_combination_labels:
                summary_split_columns += ["factor_columns"]
        if plan.dependent_task_mode == "manual_groups":
            summary_split_columns += ["dependent_group", "dependent_variables"]
        elif plan.dependent_task_mode == "combinations":
            summary_split_columns += [
                "dependent_combination",
                "dependent_columns",
                "dependent_combination_size",
            ]
            if plan.dependent_combination_labels:
                summary_split_columns += ["dependent_combination_columns"]
        else:
            summary_split_columns += (["dependent_variable"] if label_outcome else [])
            summary_split_columns += (["dependent_variables"] if spec.dependent_mode == "joint" and plan.dependent_variables else [])
        summary_split_columns += plan.split_by
        summary = _build_batch_summary(results, summary_split_columns)
        summary = AnalysisService._adjust_batch_pvalues(
            summary, str(plan.cross_model_p_adjust or plan.combination_p_adjust), plan.alpha
        )
        overview = AnalysisService._build_batch_overview(
            summary,
            summary_split_columns,
            str(plan.cross_model_p_adjust or plan.combination_p_adjust),
        )
        return BatchAnalysisResult(
            split_cols=summary_split_columns, method=plan.method,
            dv_col=", ".join(plan.dependent_variables), factor_cols=plan.fixed_factors,
            results=results, summary_df=summary, overview_df=overview,
            settings=plan.model_dump(mode="json"),
        )

    @staticmethod
    def _build_combination_subplan(
        plan: AnalysisPlan,
        dependent_set: list[str],
        factor_set: list[str],
    ) -> AnalysisPlan:
        """为 1..k 阶组合选择匹配的 ANOVA/MANOVA 执行器。"""
        method = plan.method
        order = len(factor_set)
        anova_family = {"oneway_anova", "twoway_anova", "threeway_anova", "multifactor_anova"}
        manova_family = {"oneway_manova", "twoway_manova", "threeway_manova", "multifactor_manova"}
        if method in anova_family:
            method = {1: "oneway_anova", 2: "twoway_anova", 3: "threeway_anova"}.get(order, "multifactor_anova")
        elif method in manova_family:
            method = {1: "oneway_manova", 2: "twoway_manova", 3: "threeway_manova"}.get(order, "multifactor_manova")

        target_spec = get_method(method)
        allowed_parameters = {item.key for item in target_spec.parameters}
        parameters = {
            key: value for key, value in plan.method_parameters.items()
            if key in allowed_parameters
        }
        if method in {"multifactor_anova", "multifactor_manova"}:
            parameters["factor_model_order"] = order

        payload = plan.model_dump(mode="json")
        payload.update({
            "interface_mode": "professional" if plan.interface_mode == "professional" else None,
            "method": method,
            "dependent_variables": dependent_set,
            "fixed_factors": factor_set,
            "method_parameters": parameters,
            "split_by": [],
            "split_rules": [],
            "factor_combinations_enabled": False,
            "factor_combination_order": None,
            "factor_combination_min_order": None,
            "factor_combination_max_order": None,
            "emm_factors": [name for name in plan.emm_factors if name in factor_set or name == plan.repeated_factor],
            "calibration_enabled": False,
            "pairing": None,
            "dependent_variable_groups": [],
            "dependent_task_mode": "joint_all",
            "dependent_combination_min_size": None,
            "dependent_combination_max_size": None,
            "dependent_combination_labels": {},
            "derived_columns": [],
            "calibration_columns": [],
            "calibration_baseline_column": None,
            "calibration_baseline_value": None,
        })
        return AnalysisPlan.model_validate(payload)

    @staticmethod
    def _build_batch_overview(
        frame: pd.DataFrame,
        split_columns: list[str],
        adjustment_method: str = "holm",
    ) -> pd.DataFrame:
        """为页面和 Excel 生成结论优先的批次总览。"""
        if frame.empty:
            return frame.copy()
        # ``task_id`` is created for every batch task, including ordinary split-only
        # batches.  Keep it in the overview so downstream reports can join each
        # inferential row back to the exact task instead of guessing from labels.
        metadata = [
            column
            for column in dict.fromkeys(["task_id", *split_columns, "n"])
            if column in frame.columns
        ]
        result_type = frame.get("result_type", pd.Series("", index=frame.index)).fillna("").astype(str)
        numeric_p = pd.to_numeric(
            frame.get("p_value", pd.Series(np.nan, index=frame.index)), errors="coerce"
        )
        inferential_test = result_type.eq("test") & numeric_p.notna() & np.isfinite(numeric_p)
        # 批次总览只承载能进行显著性判断的主要/总体检验。EMM、对比、
        # 字母分组和描述行属于后续解释层，不能混进跨任务校正家族；没有
        # 推断 p 的占位记录也不能被包装成“不显著”。失败任务仍单列保留。
        selected = frame.loc[inferential_test | result_type.eq("error")].copy()
        columns = metadata + [
            "result_type", "effect", "statistic_name", "statistic_value", "df_num", "df_den",
            "p_value", "significant", "p_adjusted_across_tasks", "significant_adjusted", "error",
        ]
        selected = selected[[column for column in columns if column in selected.columns]].copy()
        selected["status"] = np.where(selected.get("result_type", "").eq("error"), "failed", "completed")
        selected["raw_conclusion"] = np.where(
            selected["status"].eq("failed"),
            "执行失败",
            np.where(
                selected.get(
                    "significant", pd.Series(False, index=selected.index, dtype=bool)
                ).fillna(False),
                "原始显著",
                "原始不显著",
            ),
        )
        if adjustment_method == "none":
            # 没有执行跨任务校正时，只存在原始判断。不要制造一个与原始 p
            # 相同的“校正后 p”，也不要把原始显著包装为“未校正后显著”。
            selected["conclusion"] = selected["raw_conclusion"]
            selected = selected.drop(
                columns=["p_adjusted_across_tasks", "significant_adjusted"],
                errors="ignore",
            )
        elif "significant_adjusted" in selected.columns:
            selected["conclusion"] = np.where(
                selected["status"].eq("failed"),
                "执行失败",
                np.where(
                    selected["significant_adjusted"].fillna(False),
                    "校正后显著",
                    "校正后不显著",
                ),
            )
        else:
            selected["conclusion"] = np.where(selected["status"].eq("failed"), "执行失败", "已完成")
        return selected.reset_index(drop=True)

    @staticmethod
    def _adjust_batch_pvalues(frame: pd.DataFrame, method: str, alpha: float) -> pd.DataFrame:
        """对同一次多模型执行中的主要/总体检验按统计量类型分族校正。

        MANOVA 同一效应可能同时输出 Pillai、Wilks 等替代判据；它们是同一
        多元假设的不同统计量，不能与彼此及普通 F 检验混成一个校正家族。
        因此跨模型校正在 ``statistic_name`` 内分别执行，模型系数、EMM、
        事后比较和字母分组不纳入该层校正。这里的模型任务既可能来自因素
        组合，也可能来自多个因变量或数据拆分；彼此独立启动的历史运行不会
        被事后拼成一个假设族。
        """
        result = frame.copy()
        result["p_adjust_method"] = method
        result["p_adjust_family"] = ""
        result["p_adjusted_across_tasks"] = np.nan
        result["significant_adjusted"] = pd.Series(
            [None] * len(result), index=result.index, dtype=object
        )
        if "p_value" not in result.columns:
            return result
        numeric = pd.to_numeric(result["p_value"], errors="coerce")
        test_mask = numeric.notna() & result.get(
            "result_type", pd.Series(index=result.index, dtype=object)
        ).eq("test")
        if not test_mask.any():
            return result
        if method == "none":
            return result

        statistic_names = result.get(
            "statistic_name", pd.Series("test", index=result.index, dtype=object)
        ).fillna("test").astype(str)
        for family, indices in result.loc[test_mask].groupby(statistic_names[test_mask], sort=True).groups.items():
            family_index = pd.Index(indices)
            family_p = numeric.loc[family_index].to_numpy(dtype=float)
            adjusted = multipletests(family_p, alpha=alpha, method=method)[1]
            result.loc[family_index, "p_adjust_family"] = str(family)
            result.loc[family_index, "p_adjusted_across_tasks"] = adjusted
            result.loc[family_index, "significant_adjusted"] = adjusted < alpha
        return result

    @staticmethod
    def _result_records(result: StatisticalResult) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for test in result.primary_tests:
            records.append({
                "result_type": "test", "effect": test.effect,
                "statistic_name": test.statistic_name, "statistic_value": test.statistic_value,
                "df_num": test.df_num, "df_den": test.df_den, "p_value": test.p_value,
                "effect_size_name": test.effect_size_name, "effect_size_value": test.effect_size_value,
                "ci_lower": test.ci_lower, "ci_upper": test.ci_upper,
                "significant": test.is_significant, "detail": test.detail,
            })
        for test in result.omnibus_tests:
            is_multivariate = bool(test.statistic_name and test.statistic_value is not None)
            records.append({
                "result_type": "test", "effect": test.effect,
                "statistic_name": test.statistic_name or "F",
                "statistic_value": test.statistic_value if is_multivariate else test.f_value,
                "approx_f": test.f_value if is_multivariate else None,
                "df_num": test.df_num, "df_den": test.df_den,
                "p_value": test.p_value,
                "effect_size_name": "" if is_multivariate else "partial eta squared",
                "effect_size_value": None if is_multivariate else test.eta_sq_p,
                "significant": test.is_significant,
                "adjustments": "; ".join(
                    f"{item.correction}: df=({item.df_num:.4g},{item.df_den:.4g}), p={item.p_value:.6g}"
                    for item in test.adjustments
                ),
            })
        for coefficient in result.coefficients:
            records.append({
                "result_type": "coefficient", "term": coefficient.term,
                "statistic_name": coefficient.statistic_name, "statistic_value": coefficient.statistic_value,
                "estimate": coefficient.estimate, "se": coefficient.se, "p_value": coefficient.p_value,
                "ci_lower": coefficient.ci_lower, "ci_upper": coefficient.ci_upper,
                "transformed_name": coefficient.transformed_name, "transformed_value": coefficient.transformed_value,
                "significant": coefficient.significant,
            })
        for marginal in result.estimated_marginal_means:
            records.append({
                "result_type": "emm", "effect": marginal.group, "estimate": marginal.mean, "se": marginal.se,
                "ci_lower": marginal.ci_lower, "ci_upper": marginal.ci_upper, "df_num": marginal.df,
                "detail": marginal.source,
            })
        for contrast in result.contrasts:
            records.append({
                "result_type": "contrast", "effect": contrast.contrast, "statistic_name": contrast.statistic_name,
                "statistic_value": contrast.t_value, "estimate": contrast.estimate, "se": contrast.se,
                "p_value": contrast.p_adjusted, "p_raw": contrast.p_value, "ci_lower": contrast.ci_lower,
                "ci_upper": contrast.ci_upper, "significant": contrast.significant,
                "detail": f"校正={contrast.correction}",
            })
        for item in result.significance_letters:
            records.append({
                "result_type": "letter_group", "outcome": item.outcome, "factor": item.factor,
                "context": item.context, "method": item.method, "effect": item.group,
                "estimate": item.mean, "letters": item.letters,
                "detail": "; ".join(f"{key}={value}" for key, value in item.levels.items()),
            })
        for metric in result.fit_statistics:
            records.append({"result_type": "fit", "metric": metric.name, "value": metric.value, "detail": metric.detail})
        if not records:
            for row in result.descriptive_stats:
                records.append({"result_type": "descriptive", **row})
        if result.warnings and records:
            records[0]["warnings"] = "；".join(result.warnings)
        return records

    @staticmethod
    def serialize_result(result: StatisticalResult | BatchAnalysisResult) -> dict[str, Any]:
        if isinstance(result, StatisticalResult):
            return {"kind": "single", "result": result.model_dump(mode="json")}
        summary = None
        if result.summary_df is not None:
            summary = result.summary_df.where(pd.notna(result.summary_df), None).to_dict(orient="records")
        overview = None
        if result.overview_df is not None:
            overview = result.overview_df.where(pd.notna(result.overview_df), None).to_dict(orient="records")
        serialized_results = []
        for item in result.results:
            serialized_results.append({
                "subset_key": item.subset_key,
                "subset_info": item.subset_info,
                "n_rows": item.n_rows,
                "omnibus_tests": item.omnibus_tests,
                "records": item.records,
                "error": item.error,
                "result": item.result.model_dump(mode="json") if item.result is not None else None,
            })
        return {
            "kind": "batch",
            "result": {
                "split_cols": result.split_cols,
                "method": result.method,
                "dv_col": result.dv_col,
                "factor_cols": result.factor_cols,
                "results": serialized_results,
                "summary": summary,
                "overview": overview,
                "settings": result.settings,
            },
        }

    @classmethod
    def serialize_execution(cls, execution: AnalysisExecution) -> dict[str, Any]:
        payload = cls.serialize_result(execution.result)
        payload.update({
            "run_id": execution.run_id,
            "plan": execution.plan.model_dump(mode="json"),
            "validation": execution.validation.model_dump(mode="json"),
            "provenance": execution.provenance.model_dump(mode="json"),
            "warnings": execution.warnings,
        })
        return payload
