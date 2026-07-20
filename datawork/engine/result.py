"""统一统计结果 Schema (Pydantic) — 所有引擎输出的唯一格式。"""

from __future__ import annotations

from typing import Optional, Any
from pydantic import BaseModel, Field

from datawork.core.roles import VariableRole


class VariableInfo(BaseModel):
    """单个变量的信息。"""
    name: str
    dtype: str
    role: VariableRole
    levels: Optional[list[str]] = None      # 类别变量的水平
    n_unique: int = 0
    missing_rate: float = 0.0
    confidence: float = 1.0                 # AI 推断置信度


class DesignInfo(BaseModel):
    """实验设计描述。"""
    variables: list[VariableInfo] = Field(default_factory=list)
    n_subjects: int = 0
    n_observations: int = 0
    between_factors: list[str] = Field(default_factory=list)          # 列名
    within_factors: list[str] = Field(default_factory=list)
    covariates: list[str] = Field(default_factory=list)
    dependent_vars: list[str] = Field(default_factory=list)
    id_column: Optional[str] = None
    time_column: Optional[str] = None


class DiagnosticResult(BaseModel):
    """单项诊断结果。"""
    test_name: str                           # Shapiro-Wilk, Levene, etc.
    statistic: float
    p_value: float
    passed: bool                             # p > 0.05 ?
    detail: str = ""


class AdjustedTestResult(BaseModel):
    """球形性或其他自由度校正后的总体检验。"""
    correction: str
    df_num: float
    df_den: float
    p_value: float
    is_significant: bool


class SphericityResult(BaseModel):
    """重复测量设计的球形性诊断。"""
    test_name: str = "Mauchly 球形性检验"
    statistic: float
    chi_square: float
    df: float
    p_value: float
    epsilon_gg: float
    epsilon_hf: float
    passed: bool
    detail: str = ""


class DiagnosticPlot(BaseModel):
    """前端和报告均可消费的结构化诊断图。"""
    kind: str
    title: str
    x_label: str = ""
    y_label: str = ""
    series: list[dict[str, Any]] = Field(default_factory=list)
    reference_lines: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class OmnibusTest(BaseModel):
    """总体检验结果（ANOVA/MANOVA 表中一行）。"""
    effect: str                              # "品种", "种植模式", "品种×种植模式"
    statistic_name: str = ""                # MANOVA: Wilks/Pillai/Hotelling–Lawley/Roy
    statistic_value: Optional[float] = None  # 多元统计量本身；普通 ANOVA 留空
    ss_type: int = 3
    df_num: float                            # 分子 df
    df_den: float                            # 分母 df
    f_value: float                           # MANOVA 中为近似 F
    p_value: float
    eta_sq: float                            # η²
    eta_sq_p: float                          # 偏 η²
    omega_sq: float = 0.0                    # ω²
    is_significant: bool
    significance_level: float = 0.05
    adjustments: list[AdjustedTestResult] = Field(default_factory=list)




class UnivariateFollowUpResult(BaseModel):
    """MANOVA 显著后的单变量跟进 ANOVA 结果。"""
    outcome: str
    effect: str
    ss_type: int = 3
    df_num: float
    df_den: float
    f_value: float
    p_value: float
    p_adjusted: float
    sum_sq: Optional[float] = None
    mean_sq: Optional[float] = None
    eta_sq_p: float = 0.0
    significant: bool
    correction: str = "holm"
    interpretation: str = ""


class ContrastResult(BaseModel):
    """单次成对比较。"""
    contrast: str                            # "H76 - L76"
    estimate: float                          # 均值差
    se: float = 0
    t_value: float = 0
    p_value: float
    p_adjusted: float
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    df: float = 0
    significant: bool
    correction: str = "tukey"               # tukey / bonferroni / holm / none
    statistic_name: str = "t"


class EMMeans(BaseModel):
    """模型估计边际均值。"""
    group: str
    mean: float
    se: float
    ci_lower: float
    ci_upper: float
    levels: dict[str, str] = Field(default_factory=dict)
    df: Optional[float] = None
    source: str = "model"


class SignificanceLetterGroup(BaseModel):
    """显著性紧凑字母分组的一行。"""
    outcome: str = ""
    factor: str
    context: str = ""
    method: str
    group: str
    mean: float
    letters: str
    levels: dict[str, str] = Field(default_factory=dict)


class EffectSize(BaseModel):
    """效应量。"""
    measure: str                             # "cohens_d", "eta_sq", "eta_sq_p", "omega_sq"
    value: float
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    interpretation: str = ""                 # "小效应" / "中效应" / "大效应"




class PrimaryTestResult(BaseModel):
    """适用于 t/U/H/χ²/r/z 等任意主要检验的通用结果。"""
    effect: str
    statistic_name: str
    statistic_value: float
    p_value: Optional[float] = None
    df_num: Optional[float] = None
    df_den: Optional[float] = None
    effect_size_name: str = ""
    effect_size_value: Optional[float] = None
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    is_significant: Optional[bool] = None
    significance_level: float = 0.05
    detail: str = ""


class CoefficientResult(BaseModel):
    """回归或混合模型中的单个参数估计。"""
    term: str
    estimate: float
    se: float
    statistic_name: str = "t"
    statistic_value: float
    p_value: float
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    transformed_name: str = ""
    transformed_value: Optional[float] = None
    significant: bool = False


class FitStatistic(BaseModel):
    """模型拟合优度或方差组成。"""
    name: str
    value: float
    detail: str = ""


class MethodInfo(BaseModel):
    """分析方法的元信息。"""
    name: str                                # "two_way_anova"
    label_zh: str                            # "双因素方差分析"
    formula: str                             # "脱叶率 ~ 品种 * 种植模式"
    software: str = "statsmodels"
    research_question: str = ""
    reasoning: list[str] = Field(default_factory=list)                # 推荐理由
    alternatives: list[dict[str, str]] = Field(default_factory=list)  # 备选方案
    assumptions: list[str] = Field(default_factory=list)
    report_constraints: list[str] = Field(default_factory=list)       # 报告必须遵守的边界


class SimpleEffectResult(BaseModel):
    """简单效应分析的一行结果。"""
    fixed_factor: str                        # 固定哪个因素
    fixed_level: str                         # 固定在哪个水平
    effect: str                              # 检验的效应
    df_num: float
    df_den: float
    f_value: float
    p_value: float
    p_adjusted: Optional[float] = None
    correction: str = "none"
    is_significant: bool


class StatisticalResult(BaseModel):
    """统一统计分析结果 — 所有引擎的最终输出。"""

    analysis_id: str = ""
    design: DesignInfo = Field(default_factory=DesignInfo)
    method: MethodInfo = Field(default_factory=MethodInfo)
    data_snapshot: dict[str, Any] = Field(default_factory=dict)

    # 假设诊断
    diagnostics: list[DiagnosticResult] = Field(default_factory=list)
    sphericity: Optional[SphericityResult] = None
    diagnostic_plots: list[DiagnosticPlot] = Field(default_factory=list)

    # 通用主要检验（t/U/H/χ²/r/z 等）
    primary_tests: list[PrimaryTestResult] = Field(default_factory=list)

    # 总体模型检验（传统 ANOVA 兼容字段）
    omnibus_tests: list[OmnibusTest] = Field(default_factory=list)

    # 回归/混合模型参数与拟合统计
    coefficients: list[CoefficientResult] = Field(default_factory=list)
    fit_statistics: list[FitStatistic] = Field(default_factory=list)

    # 估计边际均值
    estimated_marginal_means: list[EMMeans] = Field(default_factory=list)

    # MANOVA 显著后的单变量跟进
    follow_up_tests: list[UnivariateFollowUpResult] = Field(default_factory=list)

    # 成对比较
    contrasts: list[ContrastResult] = Field(default_factory=list)

    # 显著性紧凑字母分组（CLD）
    significance_letters: list[SignificanceLetterGroup] = Field(default_factory=list)

    # 简单效应
    simple_effects: list[SimpleEffectResult] = Field(default_factory=list)

    # 效应量
    effect_sizes: list[EffectSize] = Field(default_factory=list)

    # 风险点
    warnings: list[str] = Field(default_factory=list)
    report_constraints: list[str] = Field(default_factory=list)

    # 可复现溯源
    provenance: dict[str, Any] = Field(default_factory=dict)

    # 描述统计快照 (均值±SD)
    descriptive_stats: list[dict[str, Any]] = Field(default_factory=list)


class MultiDVResult(BaseModel):
    """多因变量分析汇总 — 同一方法对多个 DVs 的批量结果。"""

    dv_results: list[StatisticalResult] = Field(default_factory=list)
    method_name: str = ""
    method_label: str = ""
    factor_cols: list[str] = Field(default_factory=list)

    @property
    def omnibus_summary(self) -> list[dict[str, Any]]:
        """提取所有 DV 的 omnibus 检验汇总表。"""
        rows = []
        for r in self.dv_results:
            dv_name = r.method.research_question or r.analysis_id.split("_")[-1] if r.analysis_id else "?"
            for ot in r.omnibus_tests:
                rows.append({
                    "dv": dv_name,
                    "effect": ot.effect,
                    "F": round(ot.f_value, 3),
                    "df_num": ot.df_num,
                    "df_den": ot.df_den,
                    "p": ot.p_value,
                    "eta_sq_p": round(ot.eta_sq_p, 4),
                    "significant": ot.is_significant,
                })
        return rows
