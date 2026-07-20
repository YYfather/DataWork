"""统一分析计划。

所有界面只负责构造 AnalysisPlan；方法角色要求由 method_registry 描述，
统计执行由 application 层统一验证和分派。
"""
from __future__ import annotations

from enum import Enum
from itertools import combinations
from math import comb
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator

from .method_registry import canonical_method_name, get_method


class MissingPolicy(str, Enum):
    LISTWISE = "listwise"


class SplitGroupRule(BaseModel):
    """一个用户命名的拆分组；类别组使用 values，数值组使用上下界。"""

    label: str
    values: list[str] = Field(default_factory=list)
    lower: float | None = None
    upper: float | None = None
    include_lower: bool = True
    include_upper: bool = False

    @field_validator("label")
    @classmethod
    def _clean_label(cls, value: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("拆分组名称不能为空")
        return cleaned

    @field_validator("values")
    @classmethod
    def _clean_values(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("同一拆分组中不能重复选择类别值")
        return cleaned


class SplitRule(BaseModel):
    """专业模式下对一个拆分列的显式分组规则。"""

    column: str
    kind: Literal["categorical", "numeric"]
    groups: list[SplitGroupRule]

    @field_validator("column")
    @classmethod
    def _clean_column(cls, value: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("拆分规则必须指定列")
        return cleaned

    @model_validator(mode="after")
    def _validate_groups(self) -> "SplitRule":
        if not self.groups:
            raise ValueError("自定义拆分规则至少需要一个组")
        if len(self.groups) > 100:
            raise ValueError("单个拆分列最多允许 100 个自定义组")
        labels = [group.label for group in self.groups]
        if len(labels) != len(set(labels)):
            raise ValueError("同一拆分规则中的组名称不能重复")
        if self.kind == "categorical":
            assigned: set[str] = set()
            for group in self.groups:
                if not group.values:
                    raise ValueError(f"类别组“{group.label}”至少需要选择一个值")
                overlap = assigned & set(group.values)
                if overlap:
                    raise ValueError(f"类别值 {sorted(overlap)} 不能同时属于多个拆分组")
                assigned.update(group.values)
            return self
        intervals: list[tuple[float, float, bool, bool, str]] = []
        for group in self.groups:
            if group.values:
                raise ValueError("数值区间规则不能同时设置类别值")
            lower = float("-inf") if group.lower is None else group.lower
            upper = float("inf") if group.upper is None else group.upper
            if lower >= upper:
                raise ValueError(f"数值组“{group.label}”的下界必须小于上界")
            intervals.append((lower, upper, group.include_lower, group.include_upper, group.label))
        intervals.sort(key=lambda item: (item[0], item[1]))
        for left, right in zip(intervals, intervals[1:]):
            overlaps = right[0] < left[1] or (right[0] == left[1] and left[3] and right[2])
            if overlaps:
                raise ValueError(f"数值组“{left[4]}”与“{right[4]}”区间重叠")
        return self


class AnalysisPlan(BaseModel):
    interface_mode: Literal["concise", "professional"] | None = None
    dependent_variables: list[str] = Field(default_factory=list)
    fixed_factors: list[str] = Field(default_factory=list)
    random_factors: list[str] = Field(default_factory=list)
    random_slopes: list[str] = Field(default_factory=list)
    covariates: list[str] = Field(default_factory=list)
    subject_id: str | None = None
    repeated_factor: str | None = None
    split_by: list[str] = Field(default_factory=list)
    split_rules: list[SplitRule] = Field(default_factory=list)
    method: str
    alpha: float = 0.05
    ss_type: Literal[1, 2, 3] = 3
    equal_var: bool | None = None
    posthoc_method: str = "tukey"
    missing_policy: MissingPolicy = MissingPolicy.LISTWISE
    research_goal: str = ""
    test_value: float = 0.0
    alternative: Literal["two-sided", "less", "greater"] = "two-sided"
    expected_proportions: list[float] = Field(default_factory=list)
    method_parameters: dict[str, Any] = Field(default_factory=dict)
    factor_combinations_enabled: bool = False
    factor_combination_order: int | None = None
    factor_combination_min_order: int | None = None
    factor_combination_max_order: int | None = None
    factor_combination_labels: dict[str, str] = Field(default_factory=dict)
    cross_model_p_adjust: Literal["none", "bonferroni", "holm", "fdr_bh"] | None = None
    combination_p_adjust: Literal["none", "bonferroni", "holm", "fdr_bh"] = "holm"
    estimate_marginal_means: bool = False
    emm_factors: list[str] = Field(default_factory=list)
    contrast_correction: Literal["none", "bonferroni", "holm", "fdr_bh"] = "holm"
    diagnostic_plots: bool = True
    calibration_enabled: bool = False
    calibration_method: Literal["zscore", "robust_zscore", "baseline_center"] = "zscore"
    calibration_columns: list[str] = Field(default_factory=list)
    calibration_baseline_column: str | None = None
    calibration_baseline_value: str | None = None

    @field_validator("dependent_variables", "fixed_factors", "random_factors", "random_slopes", "covariates", "split_by", "emm_factors", "calibration_columns")
    @classmethod
    def _unique_columns(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("同一角色中不能重复选择列")
        return cleaned

    @field_validator("subject_id", "repeated_factor", "calibration_baseline_column", "calibration_baseline_value")
    @classmethod
    def _clean_optional_column(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("factor_combination_labels")
    @classmethod
    def _clean_factor_combination_labels(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for raw_key, raw_label in value.items():
            key = str(raw_key).strip()
            label = str(raw_label).strip()
            if not key or not label:
                continue
            if len(label) > 120:
                raise ValueError("因素组合名称不能超过 120 个字符")
            cleaned[key] = label
        return cleaned

    @field_validator("alpha")
    @classmethod
    def _valid_alpha(cls, value: float) -> float:
        if not 0 < value < 1:
            raise ValueError("alpha 必须位于 0 和 1 之间")
        return value

    @field_validator("expected_proportions")
    @classmethod
    def _valid_expected_proportions(cls, value: list[float]) -> list[float]:
        values = [float(item) for item in value]
        if values and (any(item <= 0 for item in values) or abs(sum(values) - 1) > 1e-6):
            raise ValueError("期望比例必须全部大于 0 且总和为 1")
        return values

    @model_validator(mode="after")
    def _validate_roles_and_method(self) -> "AnalysisPlan":
        # 前端显式声明简洁模式时，服务端再次应用默认预设并丢弃专业参数。
        # interface_mode=None 保留旧 API/已保存计划的兼容行为。
        if self.interface_mode == "concise":
            self.alpha = 0.05
            self.ss_type = 3
            self.method_parameters = {}
            self.factor_combinations_enabled = False
            self.factor_combination_order = None
            self.factor_combination_min_order = None
            self.factor_combination_max_order = None
            self.factor_combination_labels = {}
            self.split_rules = []
            self.estimate_marginal_means = False
            self.emm_factors = []
            self.contrast_correction = "holm"
            self.diagnostic_plots = False
            self.calibration_enabled = False
            self.calibration_columns = []
            self.calibration_baseline_column = None
            self.calibration_baseline_value = None
        # 旧版本把 1/2/3 因素 ANOVA 或 MANOVA 放在统一方法中。
        # 新版本按保存阶数迁移到固定方法，避免方法范围与阶数参数双重控制。
        if self.method in {"manova", "factorial_anova"}:
            legacy_parameters = dict(self.method_parameters or {})
            try:
                legacy_order = int(legacy_parameters.get("factor_model_order", 0) or 0)
            except (TypeError, ValueError):
                legacy_order = 0
            if legacy_order not in {1, 2, 3}:
                legacy_order = min(max(len(self.fixed_factors), 1), 3)
            migration = (
                {1: "oneway_manova", 2: "twoway_manova", 3: "threeway_manova"}
                if self.method == "manova"
                else {1: "oneway_anova", 2: "twoway_anova", 3: "threeway_anova"}
            )
            self.method = migration[legacy_order]
            legacy_parameters.pop("factor_model_order", None)
            self.method_parameters = legacy_parameters
        self.method = canonical_method_name(self.method)
        # ``combination_p_adjust`` 是旧版字段名。实际上该校正覆盖一次批量
        # 执行中的全部模型任务（多因变量、因素组合和数据拆分），因此使用
        # 更准确的 cross_model_p_adjust 作为规范字段，同时保留双向兼容。
        if self.cross_model_p_adjust is None:
            self.cross_model_p_adjust = self.combination_p_adjust
        else:
            self.combination_p_adjust = self.cross_model_p_adjust
        rule_columns = [rule.column for rule in self.split_rules]
        if len(rule_columns) != len(set(rule_columns)):
            raise ValueError("同一拆分列只能配置一条自定义分组规则")
        self.split_by = list(dict.fromkeys([*self.split_by, *rule_columns]))
        spec = get_method(self.method)
        if not spec.is_runnable:
            raise ValueError(f"{spec.label_zh} 尚未实现，分析未执行。{spec.notes}")

        # 兼容 v0.4.4 及更早计划中的单选事后检验字段。
        raw_parameters = dict(self.method_parameters or {})
        if "posthoc_method" in raw_parameters and "posthoc_methods" not in raw_parameters:
            raw_parameters["posthoc_methods"] = [raw_parameters.pop("posthoc_method")]
        self.method_parameters = self._normalize_method_parameters(spec.parameters, raw_parameters)
        if len(self.dependent_variables) < spec.min_dependent_vars:
            raise ValueError(f"{spec.label_zh} 至少需要 {spec.min_dependent_vars} 个因变量")
        if spec.max_dependent_vars is not None and len(self.dependent_variables) > spec.max_dependent_vars:
            if spec.dependent_mode != "single" or not spec.supports_batch:
                raise ValueError(f"{spec.label_zh} 最多支持 {spec.max_dependent_vars} 个因变量")
        if self.factor_combinations_enabled:
            if spec.max_fixed_factors == 0:
                raise ValueError(f"{spec.label_zh} 不使用分类因素，不能启用因素组合实验")
            explicit_highest_order = self.factor_combination_order is not None
            minimum_required = 1 if explicit_highest_order else spec.min_fixed_factors
            if len(self.fixed_factors) < minimum_required:
                raise ValueError(f"因素组合候选池至少需要 {minimum_required} 个分类因素")
            maximum_default = spec.max_fixed_factors if spec.max_fixed_factors is not None else len(self.fixed_factors)
            overflow = spec.max_fixed_factors is not None and len(self.fixed_factors) > spec.max_fixed_factors
            default_order = min(len(self.fixed_factors), maximum_default)
            if explicit_highest_order:
                minimum_order = 1
                maximum_order = int(self.factor_combination_order)
            else:
                minimum_order = (
                    self.factor_combination_min_order if self.factor_combination_min_order is not None
                    else (default_order if overflow else max(1, spec.min_fixed_factors))
                )
                maximum_order = (
                    self.factor_combination_max_order if self.factor_combination_max_order is not None else default_order
                )
            if not explicit_highest_order and minimum_order < spec.min_fixed_factors:
                raise ValueError(f"组合最小阶数不能小于 {spec.label_zh} 要求的 {spec.min_fixed_factors}")
            if maximum_order < 1:
                raise ValueError("计算阶数必须至少为 1")
            if spec.max_fixed_factors is not None and maximum_order > spec.max_fixed_factors:
                raise ValueError(f"组合最大阶数不能大于 {spec.label_zh} 允许的 {spec.max_fixed_factors}")
            if minimum_order > maximum_order:
                raise ValueError("因素组合最小阶数不能大于最大阶数")
            if maximum_order > len(self.fixed_factors):
                raise ValueError("因素组合阶数不能超过已选候选因素数量")
            combination_count = sum(comb(len(self.fixed_factors), order) for order in range(minimum_order, maximum_order + 1))
            if combination_count > 1000:
                raise ValueError(f"当前分类因素设置会生成 {combination_count} 个组合，超过安全上限 1000；请减少候选因素或缩小组合阶数")
            self.factor_combination_min_order = minimum_order
            self.factor_combination_max_order = maximum_order
            self.factor_combination_order = maximum_order
            valid_combinations = [
                " × ".join(items)
                for order in range(minimum_order, maximum_order + 1)
                for items in combinations(self.fixed_factors, order)
            ]
            unknown_labels = sorted(set(self.factor_combination_labels) - set(valid_combinations))
            if unknown_labels:
                raise ValueError(f"组合名称包含当前计划不存在的因素组合: {unknown_labels}")
            self.factor_combination_labels = {
                key: label for key, label in self.factor_combination_labels.items()
                if label != key
            }
            final_labels = [self.factor_combination_labels.get(key, key) for key in valid_combinations]
            if len(final_labels) != len(set(final_labels)):
                raise ValueError("因素组合名称不能重复，也不能与其他组合的默认名称相同")
        else:
            self._check_count("固定因素", len(self.fixed_factors), spec.min_fixed_factors, spec.max_fixed_factors)
            self.factor_combination_min_order = None
            self.factor_combination_max_order = None
            self.factor_combination_order = None
            self.factor_combination_labels = {}
        if self.calibration_enabled:
            if self.interface_mode == "concise":
                raise ValueError("简洁模式不能启用校正配置")
            if not self.calibration_columns:
                self.calibration_columns = list(dict.fromkeys([*self.dependent_variables, *self.covariates]))
            if not self.calibration_columns:
                raise ValueError("启用校正后至少需要一个数值校正列")
            if self.calibration_method == "baseline_center":
                if not self.calibration_baseline_column or self.calibration_baseline_value is None:
                    raise ValueError("基线对齐校正必须指定基准列和基准值")
        else:
            self.calibration_columns = []
            self.calibration_baseline_column = None
            self.calibration_baseline_value = None
        if spec.max_covariates == 0 and self.covariates:
            raise ValueError(f"{spec.label_zh} 不会使用协变量 {self.covariates}")
        self._check_count("协变量", len(self.covariates), spec.min_covariates, spec.max_covariates)
        if spec.max_random_factors == 0 and self.random_factors:
            raise ValueError(f"{spec.label_zh} 不会使用随机因素 {self.random_factors}")
        self._check_count("随机因素", len(self.random_factors), spec.min_random_factors, spec.max_random_factors)
        self._check_count("随机斜率", len(self.random_slopes), spec.min_random_slopes, spec.max_random_slopes)
        if self.random_slopes:
            allowed_slopes = set(self.fixed_factors) | set(self.covariates) | ({self.repeated_factor} if self.repeated_factor else set())
            invalid_slopes = sorted(set(self.random_slopes) - allowed_slopes)
            if invalid_slopes:
                raise ValueError(f"随机斜率必须同时作为固定预测量或重复因素进入模型: {invalid_slopes}")
        if self.estimate_marginal_means:
            if not spec.supports_emm:
                raise ValueError(f"{spec.label_zh} 当前不支持模型边际均值")
            if self.emm_factors:
                allowed_emm = set(self.fixed_factors) | ({self.repeated_factor} if self.repeated_factor else set())
                invalid_emm = sorted(set(self.emm_factors) - allowed_emm)
                if invalid_emm:
                    raise ValueError(f"EMM 因素必须来自当前分类因素或重复因素: {invalid_emm}")
            elif self.fixed_factors:
                self.emm_factors = list(self.fixed_factors)
            elif self.repeated_factor:
                self.emm_factors = [self.repeated_factor]
        else:
            self.emm_factors = []
        if spec.requires_any_predictor and not (self.fixed_factors or self.covariates):
            raise ValueError(f"{spec.label_zh} 至少需要一个固定因素或连续协变量作为预测变量")
        if spec.requires_subject_id and not self.subject_id:
            raise ValueError(f"{spec.label_zh} 需要选择受试者/样本 ID")
        if not spec.requires_subject_id and self.subject_id:
            raise ValueError(f"{spec.label_zh} 不使用受试者 ID；请清除该角色")
        if spec.requires_repeated_factor and not self.repeated_factor:
            raise ValueError(f"{spec.label_zh} 需要选择重复/时间因素")
        if not spec.requires_repeated_factor and self.repeated_factor:
            raise ValueError(f"{spec.label_zh} 不使用重复/时间因素；请清除该角色")
        if self.split_by and not spec.supports_batch:
            raise ValueError(f"{spec.label_zh} 当前不支持批量拆分分析")

        role_sets = {
            "因变量": set(self.dependent_variables),
            "固定因素": set(self.fixed_factors),
            "随机因素": set(self.random_factors),
            "协变量": set(self.covariates),
            "拆分列": set(self.split_by),
            "受试者 ID": {self.subject_id} if self.subject_id else set(),
            "重复因素": {self.repeated_factor} if self.repeated_factor else set(),
        }
        names = list(role_sets)
        for index, left_name in enumerate(names):
            for right_name in names[index + 1:]:
                overlap = role_sets[left_name] & role_sets[right_name]
                if overlap:
                    if "拆分列" in {left_name, right_name}:
                        raise ValueError(f"拆分列 {sorted(overlap)} 不能同时进入模型")
                    raise ValueError(f"列 {sorted(overlap)} 不能同时作为{left_name}和{right_name}")
        return self

    @staticmethod
    def _normalize_method_parameters(parameter_specs: tuple, raw: dict[str, Any]) -> dict[str, Any]:
        allowed = {item.key: item for item in parameter_specs}
        unknown = sorted(set(raw) - set(allowed))
        if unknown:
            raise ValueError(f"当前统计方法不支持这些高级参数: {unknown}")
        normalized: dict[str, Any] = {}
        for key, spec in allowed.items():
            value = raw.get(key, spec.default)
            if spec.kind == "boolean":
                if isinstance(value, str):
                    value = value.strip().lower() in {"1", "true", "yes", "on"}
                value = bool(value)
            elif spec.kind == "integer":
                value = int(value)
            elif spec.kind == "number":
                value = float(value)
            elif spec.kind == "number_list":
                if isinstance(value, str):
                    value = [float(item.strip()) for item in value.split(",") if item.strip()]
                else:
                    value = [float(item) for item in (value or [])]
            elif spec.kind == "multi_select":
                if isinstance(value, str):
                    value = [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
                else:
                    value = [str(item).strip() for item in (value or []) if str(item).strip()]
                value = list(dict.fromkeys(value))
                if "none" in value and len(value) > 1:
                    value = [item for item in value if item != "none"]
                if "auto" in value and len(value) > 1:
                    value = [item for item in value if item != "auto"]
                if not value:
                    value = list(spec.default) if isinstance(spec.default, (list, tuple)) else [str(spec.default)]
            else:
                value = str(value)
            if spec.options:
                allowed_options = {option[0] for option in spec.options}
                invalid = [item for item in value if item not in allowed_options] if spec.kind == "multi_select" else ([] if str(value) in allowed_options else [value])
                if invalid:
                    raise ValueError(f"参数 {spec.label_zh} 的值 {invalid!r} 不在允许范围内")
            if spec.kind in {"integer", "number"}:
                numeric = float(value)
                if spec.minimum is not None and numeric < spec.minimum:
                    raise ValueError(f"参数 {spec.label_zh} 不能小于 {spec.minimum}")
                if spec.maximum is not None and numeric > spec.maximum:
                    raise ValueError(f"参数 {spec.label_zh} 不能大于 {spec.maximum}")
            normalized[key] = value
        return normalized

    @staticmethod
    def _check_count(label: str, selected: int, minimum: int, maximum: int | None) -> None:
        if selected < minimum:
            raise ValueError(f"至少需要 {minimum} 个{label}")
        if maximum is not None and selected > maximum:
            raise ValueError(f"最多允许 {maximum} 个{label}")

    @property
    def is_batch(self) -> bool:
        spec = get_method(self.method)
        multiple_outcomes = spec.dependent_mode == "single" and len(self.dependent_variables) > 1
        return bool(self.split_by or multiple_outcomes or self.factor_combinations_enabled)

    @property
    def all_columns(self) -> list[str]:
        columns = self.dependent_variables + self.fixed_factors + self.random_factors + self.random_slopes + self.covariates + self.split_by + self.emm_factors + self.calibration_columns
        if self.subject_id:
            columns.append(self.subject_id)
        if self.repeated_factor:
            columns.append(self.repeated_factor)
        if self.calibration_baseline_column:
            columns.append(self.calibration_baseline_column)
        return list(dict.fromkeys(columns))

    def validate_dataframe(self, df: pd.DataFrame) -> None:
        from .validation import validate_plan_dataframe
        validate_plan_dataframe(self, df).raise_for_errors()
