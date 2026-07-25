"""分析路径决策树 — 根据数据结构和研究目标推荐统计方法。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ResearchGoal(Enum):
    """研究目标枚举 — 对应 CLI 步骤 3 的 12 个选项。"""
    COMPARE_GROUPS = "compare_groups"                    # 1. 比较多个处理是否存在差异
    TEST_INTERACTION = "test_interaction"                # 2. 判断两个因素是否交互
    ENDPOINT_ONLY = "endpoint_only"                      # 3. 研究某个最终时间点的表现
    CONTROL_BASELINE = "control_baseline"                # 4. 控制基线后比较最终结果 (ANCOVA)
    CHANGE_AMPLITUDE = "change_amplitude"                # 5. 比较不同处理的变化幅度
    TRAJECTORY = "trajectory"                            # 6. 比较随时间的变化轨迹
    CROSS_SECTIONAL_TIMES = "cross_sectional_times"      # 7. 分别考察不同时间节点
    CORRELATION = "correlation"                          # 8. 分析变量之间的关系
    MULTIPLE_DVS = "multiple_dvs"                        # 9. 分析多个相关指标 (MANOVA)
    PREDICTION = "prediction"                            # 10. 建立预测模型
    CATEGORICAL_OUTCOME = "categorical_outcome"          # 11. 分析比例/计数/等级/二分类结果
    CUSTOM = "custom"                                    # C. 自定义描述


@dataclass
class MethodCandidate:
    """候选分析方法。"""
    method_name: str           # 内部名称
    label_zh: str              # 中文名称
    formula_template: str      # 公式模板
    confidence: float          # 0-1
    reasoning: list[str]       # 推荐理由
    prerequisites: list[str]   # 前提条件
    limitations: list[str]     # 不能回答的问题
    posthoc_plan: str = ""     # 后续比较方案
    alternatives: list[dict] = field(default_factory=list)  # 备选方案


@dataclass
class DesignSignature:
    """实验设计特征签名 — 用于匹配方法。"""
    n_between_factors: int = 0        # 组间因素数
    n_within_factors: int = 0         # 组内因素数
    n_dependent_vars: int = 1         # 因变量数
    has_covariate: bool = False       # 是否有协变量
    has_repeated_measures: bool = False  # 是否有重复测量
    has_random_effects: bool = False  # 是否有随机效应
    has_time_variable: bool = False   # 是否有时间变量
    dv_is_continuous: bool = True     # 因变量是否连续
    dv_is_binary: bool = False        # 因变量是否二分类
    dv_is_count: bool = False         # 因变量是否计数
    dv_is_ordinal: bool = False       # 因变量是否有序
    has_derived_variable: bool = False  # 是否有派生变量
    n_time_points: int = 0            # 时间点数（若有）


def recommend_methods(
    signature: DesignSignature,
    research_goal: ResearchGoal,
) -> list[MethodCandidate]:
    """
    根据设计特征 + 研究目标，返回排序后的候选方法列表。

    这是整个决策树的核心函数。
    """
    candidates: list[MethodCandidate] = []

    # --- 连续因变量 ---
    if signature.dv_is_continuous:

        # 1-factor designs
        if signature.n_between_factors == 1 and signature.n_within_factors == 0:
            candidates.append(MethodCandidate(
                method_name="oneway_anova",
                label_zh="单因素方差分析",
                formula_template="{dv} ~ {factor}",
                confidence=0.9,
                reasoning=["1个组间因素 → 单因素 ANOVA 是标准选择"],
                prerequisites=["因变量连续", "方差齐性 (Levene)", "各组正态性"],
                limitations=["不能处理组内重复测量"],
                posthoc_plan="Tukey HSD 或 Dunnett (有对照组时)",
                alternatives=[
                    {"method": "Welch ANOVA", "when": "Levene 检验显著 (方差不齐)"},
                    {"method": "Kruskal-Wallis", "when": "严重非正态或小样本"},
                ],
            ))

        # 2-factor between-subjects
        elif signature.n_between_factors == 2 and signature.n_within_factors == 0:
            candidates.append(MethodCandidate(
                method_name="twoway_anova",
                label_zh="双因素方差分析",
                formula_template="{dv} ~ {factor_a} * {factor_b}",
                confidence=0.85,
                reasoning=["2个组间因素 → 双因素 ANOVA 可检验交互作用"],
                prerequisites=["因变量连续", "方差齐性", "各组正态性"],
                limitations=["不能处理重复测量"],
                posthoc_plan="交互显著→简单效应; 交互不显著+主效应显著→Tukey HSD",
            ))

        # 3-factor between-subjects
        elif signature.n_between_factors >= 3 and signature.n_within_factors == 0:
            candidates.append(MethodCandidate(
                method_name="threeway_anova",
                label_zh="三因素方差分析",
                formula_template="{dv} ~ {factor_a} * {factor_b} * {factor_c}",
                confidence=0.75,
                reasoning=["3个组间因素 → 三因素 ANOVA，注意三阶交互的复杂度"],
                prerequisites=["因变量连续", "方差齐性", "各组正态性", "足够样本量"],
                limitations=["三阶交互显著时解释困难"],
                posthoc_plan="三阶交互显著→简单简单效应; 否则退回到二阶交互/主效应",
            ))

        # Between + Within (mixed/mixed-design)
        if signature.n_between_factors >= 1 and signature.n_within_factors >= 1:
            candidates.append(MethodCandidate(
                method_name="mixed_anova",
                label_zh="混合方差分析",
                formula_template="{dv} ~ {between} * {within} + Error({id}/{within})",
                confidence=0.85,
                reasoning=["组间+组内因素 → 混合设计"],
                prerequisites=["球形假设 (Mauchly)", "各组正态性"],
                limitations=["不满足球形假设时需 GG/HF 校正"],
                posthoc_plan="交互显著→简单效应; 否则→主效应事后比较",
            ))

        # ANCOVA: has covariate
        if signature.has_covariate and signature.n_between_factors >= 1:
            candidates.append(MethodCandidate(
                method_name="ancova",
                label_zh="协方差分析 (ANCOVA)",
                formula_template="{dv} ~ {covariate} + {factor}",
                confidence=0.85,
                reasoning=["有连续协变量 → ANCOVA 可控制基线差异"],
                prerequisites=["回归斜率同质性 (协变量×因素交互不显著)"],
                limitations=["斜率不平行时不能使用"],
                posthoc_plan="基于修正均值的成对比较",
                alternatives=[
                    {"method": "变化量 ANOVA", "when": "不关心协变量调整，只关心差值"},
                ],
            ))

        # Repeated measures (within only)
        if signature.has_repeated_measures and signature.n_between_factors == 0:
            candidates.append(MethodCandidate(
                method_name="repeated_measures_anova",
                label_zh="重复测量方差分析",
                formula_template="{dv} ~ {time} + Error({id}/{time})",
                confidence=0.8,
                reasoning=["同一被试多次测量 → 重复测量 ANOVA"],
                prerequisites=["球形假设 (Mauchly)", "各时间点正态性"],
                limitations=["不满足球形时需 GG/HF 校正", "不能处理缺失数据"],
                posthoc_plan="时间点成对比较 (Bonferroni/Holm)",
            ))

        # Linear Mixed Model (complex with random effects or repeated)
        if signature.has_repeated_measures or signature.has_random_effects:
            candidates.append(MethodCandidate(
                method_name="linear_mixed_model",
                label_zh="线性混合效应模型 (LMM)",
                formula_template="{dv} ~ {fixed_effects} + (1|{random_effect})",
                confidence=0.9 if signature.has_random_effects else 0.7,
                reasoning=[
                    "有随机效应/重复测量 → LMM 可灵活建模",
                    "可处理不平衡数据和缺失值",
                    "不需要严格的球形假设",
                ],
                prerequisites=["残差近似正态", "随机效应结构合理"],
                limitations=["需要指定正确的随机效应结构"],
                posthoc_plan="emmeans 估算边际均值 + 多重比较校正",
                alternatives=[
                    {"method": "GEE", "when": "关注总体平均效应，不需要个体随机效应"},
                ],
            ))

        # MANOVA
        if signature.n_dependent_vars >= 2:
            manova_order = min(max(signature.n_between_factors, 1), 3)
            manova_name = {1: "oneway_manova", 2: "twoway_manova", 3: "threeway_manova"}[manova_order]
            manova_label = {1: "单因素多元方差分析 (MANOVA)", 2: "双因素多元方差分析 (MANOVA)", 3: "三因素多元方差分析 (MANOVA)"}[manova_order]
            candidates.append(MethodCandidate(
                method_name=manova_name,
                label_zh=manova_label,
                formula_template="{dv1} + {dv2} ~ {factor}",
                confidence=0.8 if not signature.has_derived_variable else 0.5,
                reasoning=["多个相关因变量 → MANOVA 控制整体错误率" if not signature.has_derived_variable
                           else "检测到派生变量关系，MANOVA 中不应同时包含总分和子变量"],
                prerequisites=["多元正态性", "方差-协方差矩阵齐性 (Box's M)"],
                limitations=["不能包含派生变量和子变量同时"],  # R3
                posthoc_plan="显著后分因变量做单变量 ANOVA → 事后比较",
            ))

        # Gain score / change
        if research_goal == ResearchGoal.CHANGE_AMPLITUDE:
            candidates.append(MethodCandidate(
                method_name="gain_score_anova",
                label_zh="变化量 (Gain Score) 方差分析",
                formula_template="(post - pre) ~ {factor}",
                confidence=0.8,
                reasoning=["研究目标为'变化幅度' → 对差值做 ANOVA 是直接且简洁的方案"],
                prerequisites=["变化量近似正态", "各组方差齐性"],
                limitations=["不能区分基线效应 (用 ANCOVA 更精确)"],
                posthoc_plan="Tukey HSD 比较各组变化量",
                alternatives=[
                    {"method": "ANCOVA", "when": "需要控制基线差异获得更精确估计"},
                ],
            ))

        # 横截面分时点
        if research_goal == ResearchGoal.CROSS_SECTIONAL_TIMES:
            candidates.append(MethodCandidate(
                method_name="cross_sectional_anova",
                label_zh="分时点横截面分析",
                formula_template="每个时间点独立运行 ANOVA: {dv}_t ~ {factor}",
                confidence=0.8,
                reasoning=["只关注各时间节点的表现，不关心动态变化"],
                prerequisites=["每次独立 ANOVA 的前提条件"],
                limitations=["不能证明动态变化 (R2)", "需要校正多重比较"],
                posthoc_plan="每时点内事后比较 + 整体 Bonferroni 校正",
            ))

    # --- 非连续因变量 ---
    if signature.dv_is_binary:
        candidates.append(MethodCandidate(
            method_name="logistic_regression",
            label_zh="Logistic 回归",
            formula_template="{dv} ~ {factor}",
            confidence=0.9,
            reasoning=["二分类因变量 → Logistic 回归"],
            prerequisites=["观测独立性", "线性关系 (logit)"],
            limitations=["不能直接给出均值差"],
        ))

    if signature.dv_is_count:
        candidates.append(MethodCandidate(
            method_name="poisson_regression",
            label_zh="Poisson 回归",
            formula_template="log({dv}) ~ {factor}",
            confidence=0.85,
            reasoning=["计数因变量 → Poisson 回归"],
            prerequisites=["等离散假设"],
            limitations=["过离散时需切换到负二项回归"],
            alternatives=[
                {"method": "负二项回归", "when": "过离散 (方差 > 均值)"},
            ],
        ))

    if signature.dv_is_ordinal:
        candidates.append(MethodCandidate(
            method_name="ordinal_logistic",
            label_zh="有序 Logistic 回归",
            formula_template="{dv} ~ {factor}",
            confidence=0.85,
            reasoning=["有序等级因变量 → 有序 Logistic 回归"],
            prerequisites=["比例优势假设"],
            limitations=["比例优势假设不满足时需用多分类 Logistic"],
        ))

    # --- 相关性 ---
    if research_goal == ResearchGoal.CORRELATION:
        candidates.append(MethodCandidate(
            method_name="correlation",
            label_zh="相关分析",
            formula_template="cor({var1}, {var2})",
            confidence=0.9,
            reasoning=["研究变量间关系 → Pearson/Spearman 相关"],
            prerequisites=["双变量线性关系 (Pearson)"],
            limitations=["相关≠因果", "离群值敏感"],
        ))

    # --- 按置信度排序 ---
    candidates.sort(key=lambda c: c.confidence, reverse=True)

    # --- 按研究目标针对性地调整置信度 ---
    for c in candidates:
        if research_goal == ResearchGoal.TEST_INTERACTION:
            if "交互" in c.label_zh:
                c.confidence = min(c.confidence + 0.1, 1.0)
        elif research_goal == ResearchGoal.CONTROL_BASELINE:
            if c.method_name == "ancova":
                c.confidence = min(c.confidence + 0.1, 1.0)
        elif research_goal == ResearchGoal.TRAJECTORY:
            if c.method_name in ("mixed_anova", "linear_mixed_model", "repeated_measures_anova"):
                c.confidence = min(c.confidence + 0.1, 1.0)

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates
