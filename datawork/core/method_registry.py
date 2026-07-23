"""统计方法注册表与面向用户的方法说明。

界面、CLI、API、预检与 AI 助手均从此处读取同一份能力元数据，避免出现
“界面能选但后端不会算”或不同页面解释不一致的问题。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Literal


class MethodStatus(str, Enum):
    IMPLEMENTED = "implemented"
    EXPERIMENTAL = "experimental"
    UNAVAILABLE = "unavailable"


DependentMode = Literal["none", "single", "joint"]
ParameterKind = Literal["boolean", "integer", "number", "select", "multi_select", "text", "number_list"]


@dataclass(frozen=True)
class ParameterSpec:
    key: str
    label_zh: str
    kind: ParameterKind
    default: object
    description: str
    options: tuple[tuple[str, str], ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    advanced: bool = True
    simple_description: str = ""
    recommended_options: tuple[str, ...] = ()
    recommendation_note: str = ""
    option_help: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class VariableRequirement:
    role: str
    label_zh: str
    count: str
    description: str


@dataclass(frozen=True)
class MethodSpec:
    name: str
    label_zh: str
    category: str
    status: MethodStatus
    purpose: str
    variable_relationship: str
    variable_requirements: tuple[VariableRequirement, ...]
    output_metrics: tuple[str, ...]
    assumptions: tuple[str, ...] = ()
    typical_uses: tuple[str, ...] = ()
    min_dependent_vars: int = 1
    max_dependent_vars: int | None = 1
    dependent_mode: DependentMode = "single"
    min_fixed_factors: int = 0
    max_fixed_factors: int | None = 0
    min_covariates: int = 0
    max_covariates: int | None = 0
    min_random_factors: int = 0
    max_random_factors: int | None = 0
    min_random_slopes: int = 0
    max_random_slopes: int | None = 0
    requires_subject_id: bool = False
    requires_repeated_factor: bool = False
    exact_factor_levels: int | None = None
    requires_any_predictor: bool = False
    supports_batch: bool = True
    supports_emm: bool = False
    supports_diagnostic_plots: bool = False
    executor: str | None = None
    parameters: tuple[ParameterSpec, ...] = ()
    notes: str = ""
    visible: bool = True

    @property
    def is_runnable(self) -> bool:
        return self.status in {MethodStatus.IMPLEMENTED, MethodStatus.EXPERIMENTAL}


DV1 = VariableRequirement("dependent_variables", "因变量", "1 个", "需要被比较、解释或预测的数值变量。")
DV2 = VariableRequirement("dependent_variables", "配对变量", "2 个", "同一对象上的两个数值测量，或需要计算关联的两个数值变量。")
GROUP2 = VariableRequirement("fixed_factors", "分组因素", "1 个，恰好 2 个水平", "把样本分成两个相互独立的组。")
GROUPK = VariableRequirement("fixed_factors", "分组因素", "1 个，至少 2 个水平", "把样本分成多个独立组。")
FACTOR2 = VariableRequirement("fixed_factors", "固定因素", "2 个", "两个分类自变量共同作用于一个数值结果。")
FACTOR3 = VariableRequirement("fixed_factors", "固定因素", "3 个", "三个分类自变量及其交互共同作用于一个数值结果。")
COV1 = VariableRequirement("covariates", "连续自变量/协变量", "至少 1 个", "用于解释、预测或校正因变量的连续变量。")
SUBJECT = VariableRequirement("subject_id", "受试者/样本 ID", "1 个", "标识同一对象的重复观测。")
REPEATED = VariableRequirement("repeated_factor", "重复/时间因素", "1 个", "标识同一对象在不同时间或条件下的观测。")
RANDOM = VariableRequirement("random_factors", "随机分组因素", "1 个", "标识地块、受试者、年份或地点等相关观测群组。")
CAT2 = VariableRequirement("fixed_factors", "分类变量", "2 个", "用于建立列联表并检验两个分类变量是否独立。")
CAT1 = VariableRequirement("fixed_factors", "分类变量", "1 个", "提供各类别的观察频数。")
BINARY_DV = VariableRequirement("dependent_variables", "二元结局", "1 个，恰好 2 个水平", "成功/失败、阳性/阴性等二分类结果。")
PAIR_CAT = VariableRequirement("dependent_variables", "配对分类变量", "2 个", "同一对象在两个时间或条件下的分类结果。")
PAIR_BINARY_K = VariableRequirement("dependent_variables", "配对二元变量", "至少 3 个", "同一对象在三个及以上条件下的二元结果。")

ALT_PARAM = ParameterSpec(
    "alternative", "备择假设", "select", "two-sided", "双侧或单侧检验。",
    options=(("two-sided", "双侧"), ("less", "小于"), ("greater", "大于")),
)
SUCCESS_LEVEL_PARAM = ParameterSpec("success_level", "成功水平", "text", "", "留空时使用数据中最后出现的水平；正式分析建议明确指定。")
NULL_PROP_PARAM = ParameterSpec("null_proportion", "原假设比例", "number", 0.5, "待检验的理论成功比例。", minimum=0.000001, maximum=0.999999, step=0.01)
EXACT_GRID_PARAM = ParameterSpec("grid_points", "精确检验网格点", "integer", 32, "Barnard/Boschloo 数值积分网格，越大越精细但更慢。", minimum=8, maximum=1024, step=8)

POSTHOC_OPTIONS = (
    ("auto", "自动：齐性时 Tukey，不齐时 Games–Howell"),
    ("tukey", "Tukey–Kramer HSD（推荐）"),
    ("holm", "Holm"),
    ("bonferroni", "Bonferroni"),
    ("sidak", "Šidák"),
    ("fdr_bh", "Benjamini–Hochberg FDR"),
    ("scheffe", "Scheffé（保守，可用于任意对比）"),
    ("duncan", "Duncan 多重极差（宽松）"),
    ("lsd", "Fisher protected LSD（未校正，宽松）"),
    ("dunnett", "Dunnett：处理组与对照组"),
    ("games_howell", "Games–Howell（方差不齐）"),
    ("none", "不执行事后比较"),
)

MODEL_POSTHOC_OPTIONS = tuple(
    item for item in POSTHOC_OPTIONS if item[0] not in {"auto", "games_howell"}
)

POSTHOC_MULTI_DESCRIPTION = (
    "可单选或多选；每种方法独立生成成对比较和显著性字母分组。"
    "Tukey 适合全部两两比较并较好控制家族错误率；Duncan 更宽松、较易检出差异，"
    "建议仅作为农业领域兼容或探索性结果；Games–Howell 适合方差不齐；"
    "Dunnett 只比较处理组与对照组，因此不生成完整字母分组。"
)

POSTHOC_OPTION_HELP = (
    ("auto", "推荐。先检查方差齐性：齐时使用 Tukey，不齐时使用 Games–Howell。"),
    ("tukey", "常规全组两两比较的首选，较好控制整体误报风险。"),
    ("games_howell", "适合方差不齐或各组样本量差异明显的两两比较。"),
    ("duncan", "农业研究中常见但较宽松，更容易出现假阳性，建议作为补充结果。"),
    ("dunnett", "只将各处理组与指定对照比较，需填写对照水平。"),
    ("holm", "逐步校正，通常比 Bonferroni 更有检验效能。"),
    ("bonferroni", "简单且保守，比较数量多时可能不易检出差异。"),
    ("sidak", "与 Bonferroni 类似，在比较近似独立时略少保守。"),
    ("fdr_bh", "控制发现中的预期假阳性比例，适合探索性筛选。"),
    ("scheffe", "非常保守，但可保护更广泛的线性对比。"),
    ("lsd", "总体检验显著后进行未充分校正的比较，误报风险较高。"),
    ("none", "只报告总体检验，不判断具体哪些组不同。"),
)

_METHODS: dict[str, MethodSpec] = {
    "descriptive_statistics": MethodSpec(
        name="descriptive_statistics", label_zh="描述统计", category="描述与数据概览",
        status=MethodStatus.IMPLEMENTED, executor="descriptive_statistics",
        purpose="概括一个或多个数值变量的中心位置、离散程度、分布形态和缺失情况。",
        variable_relationship="不检验因果或组间差异；直接对所选数值变量进行汇总。",
        variable_requirements=(VariableRequirement("dependent_variables", "数值变量", "1 个或多个", "需要概括的数据列。"),),
        output_metrics=("样本量", "均值", "标准差", "中位数", "四分位数", "最小值/最大值", "偏度", "峰度"),
        assumptions=("不要求正态分布；均值和标准差对异常值敏感。",),
        typical_uses=("分析前数据概览", "报告基线特征", "批量汇总多个指标"),
        min_dependent_vars=1, max_dependent_vars=None, dependent_mode="single",
        max_fixed_factors=0,
    ),
    "one_sample_ttest": MethodSpec(
        name="one_sample_ttest", label_zh="单样本 t 检验", category="均值比较（参数）",
        status=MethodStatus.IMPLEMENTED, executor="one_sample_ttest",
        purpose="检验一个样本的总体均值是否不同于指定参考值。",
        variable_relationship="一个数值因变量的均值与用户设定的参考值进行比较。",
        variable_requirements=(DV1, VariableRequirement("test_value", "参考值", "1 个数值", "默认 0，可在高级参数中修改。")),
        output_metrics=("t 值", "自由度", "p 值", "均值差", "置信区间", "Cohen's d"),
        assumptions=("观测独立", "因变量近似正态，或样本量足够大"),
        typical_uses=("检测指标是否偏离标准值", "检测变化量是否显著偏离 0"),
        min_fixed_factors=0, max_fixed_factors=0,
    ),
    "welch_ttest": MethodSpec(
        name="welch_ttest", label_zh="Welch 独立样本 t 检验", category="均值比较（参数）",
        status=MethodStatus.IMPLEMENTED, executor="welch_ttest",
        purpose="比较两个独立组的均值，允许两组方差和样本量不同。",
        variable_relationship="一个二水平分类因素作用于一个连续因变量，检验两个组的均值是否不同。",
        variable_requirements=(DV1, GROUP2),
        output_metrics=("t 值", "Welch 自由度", "p 值", "均值差及置信区间", "Cohen's d", "Hedges' g"),
        assumptions=("两组观测相互独立", "组内分布近似正态或样本量足够"),
        typical_uses=("处理组与对照组比较", "两个品种或方案的均值比较"),
        min_fixed_factors=1, max_fixed_factors=1, exact_factor_levels=2,
        notes="通常优先于 Student t 检验，因为不强制方差齐性。",
    ),
    "independent_ttest": MethodSpec(
        name="independent_ttest", label_zh="Student 独立样本 t 检验", category="均值比较（参数）",
        status=MethodStatus.IMPLEMENTED, executor="independent_ttest",
        purpose="在接受方差齐性假设时比较两个独立组的均值。",
        variable_relationship="一个二水平分类因素作用于一个连续因变量。",
        variable_requirements=(DV1, GROUP2),
        output_metrics=("t 值", "自由度", "p 值", "均值差及置信区间", "Cohen's d"),
        assumptions=("观测独立", "组内近似正态", "两组方差齐"),
        typical_uses=("经典两组均值比较",),
        min_fixed_factors=1, max_fixed_factors=1, exact_factor_levels=2,
        notes="若 Levene 检验提示方差不齐，应改用 Welch t 检验。",
    ),
    "paired_ttest": MethodSpec(
        name="paired_ttest", label_zh="配对样本 t 检验", category="均值比较（参数）",
        status=MethodStatus.IMPLEMENTED, executor="paired_ttest",
        purpose="比较同一对象的两次测量或一一匹配样本的平均差值。",
        variable_relationship="两个配对数值变量相减，检验配对差值的均值是否为 0。",
        variable_requirements=(DV2,),
        output_metrics=("t 值", "自由度", "p 值", "平均差", "配对 Cohen's d"),
        assumptions=("配对关系正确", "配对差值近似正态"),
        typical_uses=("处理前后比较", "同一地块两个时期比较"),
        min_dependent_vars=2, max_dependent_vars=2, dependent_mode="joint",
        max_fixed_factors=0, supports_batch=True,
    ),
    "mann_whitney_u": MethodSpec(
        name="mann_whitney_u", label_zh="Mann–Whitney U 检验", category="非参数比较",
        status=MethodStatus.IMPLEMENTED, executor="mann_whitney_u",
        purpose="比较两个独立组的分布位置，适用于明显偏态、等级数据或异常值较多的情况。",
        variable_relationship="一个二水平分类因素把一个数值或有序变量分成两个独立组。",
        variable_requirements=(DV1, GROUP2),
        output_metrics=("U 统计量", "p 值", "秩双列相关效应量", "各组中位数"),
        assumptions=("组间独立", "若解释为中位数差异，两组分布形状应近似"),
        typical_uses=("两个独立组的非正态数据比较", "等级评分比较"),
        min_fixed_factors=1, max_fixed_factors=1, exact_factor_levels=2,
    ),
    "wilcoxon_signed_rank": MethodSpec(
        name="wilcoxon_signed_rank", label_zh="Wilcoxon 符号秩检验", category="非参数比较",
        status=MethodStatus.IMPLEMENTED, executor="wilcoxon_signed_rank",
        purpose="比较两个配对测量的分布位置，不要求配对差值正态。",
        variable_relationship="对同一对象的两个数值变量计算配对差值并按绝对差排序。",
        variable_requirements=(DV2,),
        output_metrics=("W 统计量", "p 值", "秩双列相关效应量", "配对差值中位数"),
        assumptions=("配对关系正确", "差值分布大致对称时解释更清晰"),
        typical_uses=("小样本前后比较", "配对等级数据比较"),
        min_dependent_vars=2, max_dependent_vars=2, dependent_mode="joint", max_fixed_factors=0,
    ),
    "oneway_anova": MethodSpec(
        name="oneway_anova", label_zh="单因素方差分析", category="方差分析",
        status=MethodStatus.IMPLEMENTED, executor="oneway_anova", supports_emm=True, supports_diagnostic_plots=True,
        purpose="比较三个或更多独立组的均值是否相同。",
        variable_relationship="一个分类因素作用于一个连续因变量。",
        variable_requirements=(DV1, GROUPK),
        output_metrics=("F 值", "自由度", "p 值", "η²/ω²", "Tukey 事后比较"),
        assumptions=("观测独立", "组内近似正态", "方差齐性"),
        typical_uses=("多个处理水平比较", "多个品种均值比较"),
        min_fixed_factors=1, max_fixed_factors=1,
        parameters=(
            ParameterSpec("posthoc_methods", "事后比较", "multi_select", ["auto"], POSTHOC_MULTI_DESCRIPTION + " 自动模式根据 Levene 检验在 Tukey 与 Games–Howell 间选择。", options=POSTHOC_OPTIONS, advanced=False, simple_description="总体差异显著后，进一步判断哪些组不同。普通用户保留‘自动’即可。", recommended_options=("auto", "tukey", "games_howell", "duncan", "dunnett", "none"), recommendation_note="推荐自动：方差齐时使用 Tukey，方差不齐时使用 Games–Howell。", option_help=POSTHOC_OPTION_HELP),
            ParameterSpec("control_group", "Dunnett 对照组", "text", "", "仅选择 Dunnett 时必填，需与数据中的因素水平完全一致。", advanced=False, simple_description="选择 Dunnett 后填写对照水平，例如 CK。"),
            ParameterSpec("random_seed", "Dunnett 随机种子", "integer", 2026, "SciPy Dunnett 数值积分的可复现随机种子。", minimum=0, maximum=2147483647, step=1),
        ),
        notes="Duncan 与 LSD 为宽松方法，默认不推荐；方差不齐时优先 Welch ANOVA + Games–Howell。",
    ),
    "welch_anova": MethodSpec(
        name="welch_anova", label_zh="Welch 单因素方差分析", category="方差分析",
        status=MethodStatus.IMPLEMENTED, executor="welch_anova", supports_emm=True, supports_diagnostic_plots=True,
        purpose="在方差不齐时比较多个独立组的均值。",
        variable_relationship="一个分类因素作用于一个连续因变量，并允许组间方差不同。",
        variable_requirements=(DV1, GROUPK),
        output_metrics=("Welch F 值", "近似自由度", "p 值", "Games–Howell 事后比较"),
        assumptions=("观测独立", "组内分布近似正态"),
        typical_uses=("方差不齐或样本量不平衡的多组比较",),
        min_fixed_factors=1, max_fixed_factors=1,
        parameters=(ParameterSpec("posthoc_methods", "事后比较", "multi_select", ["auto"], "Welch ANOVA 仅允许自动/Games–Howell/不比较。", options=(("auto", "自动（Games–Howell）"), ("games_howell", "Games–Howell"), ("none", "不执行")), advanced=False, simple_description="总体差异显著后比较具体组别。Welch 分析通常使用 Games–Howell。", recommended_options=("auto", "games_howell", "none"), recommendation_note="推荐自动：直接使用适合方差不齐的 Games–Howell。", option_help=POSTHOC_OPTION_HELP),),
    ),
    "kruskal_wallis": MethodSpec(
        name="kruskal_wallis", label_zh="Kruskal–Wallis H 检验", category="非参数比较",
        status=MethodStatus.IMPLEMENTED, executor="kruskal_wallis",
        purpose="比较三个或更多独立组的分布位置，是单因素 ANOVA 的非参数替代。",
        variable_relationship="一个多水平分类因素把一个数值或有序变量分成多个独立组。",
        variable_requirements=(DV1, GROUPK),
        output_metrics=("H 统计量", "自由度", "p 值", "ε² 效应量", "Dunn 两两比较（全局秩、并列修正、Holm 校正）"),
        assumptions=("组间独立", "若解释为中位数差异，各组分布形状应近似"),
        typical_uses=("偏态或等级数据的多组比较",),
        min_fixed_factors=1, max_fixed_factors=1,
    ),
    "twoway_anova": MethodSpec(
        name="twoway_anova", label_zh="双因素方差分析", category="方差分析",
        status=MethodStatus.IMPLEMENTED, executor="twoway_anova", supports_emm=True, supports_diagnostic_plots=True,
        purpose="同时检验两个分类因素的主效应及二者的交互效应。",
        variable_relationship="因素 A 与因素 B 分别及共同作用于一个连续因变量。",
        variable_requirements=(DV1, FACTOR2),
        output_metrics=("两个主效应", "交互效应", "F 值", "p 值", "偏 η²", "简单效应/事后比较"),
        assumptions=("观测独立", "残差近似正态", "方差齐性", "模型结构正确"),
        typical_uses=("品种×处理", "年份×地点", "方法×剂量"),
        min_fixed_factors=2, max_fixed_factors=2,
        parameters=(
            ParameterSpec("posthoc_methods", "显著主效应事后比较（可多选）", "multi_select", ["tukey"], POSTHOC_MULTI_DESCRIPTION + " 交互不显著时，对显著主效应的模型估计边际均值进行比较。", options=MODEL_POSTHOC_OPTIONS, advanced=False, simple_description="总体或简单效应显著后，进一步比较各水平。普通用户通常选择 Tukey。", recommended_options=("tukey", "duncan", "dunnett", "none"), recommendation_note="推荐 Tukey：适合全部两两比较，并控制整体误报风险。", option_help=POSTHOC_OPTION_HELP),
            ParameterSpec("control_group", "Dunnett 对照组", "text", "", "仅选择 Dunnett 时填写；对每个主效应按对应因素水平识别。", advanced=False, simple_description="只在选择 Dunnett 时填写；内容必须与数据中的水平一致。"),
            ParameterSpec("simple_effect_correction", "简单效应多重校正", "select", "holm", "交互显著后，对全部条件简单效应统一校正。", options=(("holm", "Holm（推荐）"), ("bonferroni", "Bonferroni"), ("sidak", "Šidák"), ("fdr_bh", "FDR-BH"), ("none", "不校正"))),
        ),
    ),
    "threeway_anova": MethodSpec(
        name="threeway_anova", label_zh="三因素方差分析", category="方差分析",
        status=MethodStatus.IMPLEMENTED, executor="threeway_anova", supports_emm=True, supports_diagnostic_plots=True,
        purpose="检验三个分类因素的主效应、两两交互和三阶交互。",
        variable_relationship="三个分类因素共同作用于一个连续因变量。",
        variable_requirements=(DV1, FACTOR3),
        output_metrics=("主效应", "二阶与三阶交互", "F 值", "p 值", "偏 η²"),
        assumptions=("观测独立", "残差近似正态", "方差齐性", "每个组合有足够重复"),
        typical_uses=("多因素田间试验",),
        min_fixed_factors=3, max_fixed_factors=3,
        parameters=(
            ParameterSpec("posthoc_methods", "主效应事后比较（可多选）", "multi_select", ["tukey"], POSTHOC_MULTI_DESCRIPTION + " 仅对未卷入显著交互的显著主效应执行模型 EMM 比较。", options=MODEL_POSTHOC_OPTIONS, advanced=False, simple_description="总体或简单效应显著后，进一步比较各水平。普通用户通常选择 Tukey。", recommended_options=("tukey", "duncan", "dunnett", "none"), recommendation_note="推荐 Tukey：适合全部两两比较，并控制整体误报风险。", option_help=POSTHOC_OPTION_HELP),
            ParameterSpec("control_group", "Dunnett 对照组", "text", "", "可填写统一水平 CK，或按因素填写 处理=CK;品种=对照品种。", advanced=False, simple_description="只在选择 Dunnett 时填写；多因素可写 处理=CK;品种=对照品种。"),
            ParameterSpec("simple_effect_correction", "简单效应多重校正", "select", "holm", "显著交互后，对全部条件简单效应统一校正。", options=(("holm", "Holm（推荐）"), ("bonferroni", "Bonferroni"), ("sidak", "Šidák"), ("fdr_bh", "FDR-BH"), ("none", "不校正"))),
        ),
        notes="显著交互将自动转入校正后的条件简单效应；复杂三阶交互仍需结合图形和专业判断复核。Duncan/LSD 仅作探索性兼容选项。",
    ),
    "ancova": MethodSpec(
        name="ancova", label_zh="协方差分析（ANCOVA）", category="方差分析与校正",
        status=MethodStatus.IMPLEMENTED, executor="ancova", supports_emm=True, supports_diagnostic_plots=True,
        purpose="在控制一个或多个连续协变量后，比较分类组别的调整后均值。",
        variable_relationship="分类因素作用于连续因变量，同时用连续协变量校正基线或其他混杂差异。",
        variable_requirements=(DV1, GROUPK, COV1),
        output_metrics=("调整后因素效应", "协变量效应", "F 值", "p 值", "偏 η²", "回归斜率同质性提示"),
        assumptions=("线性关系", "组内回归斜率近似一致", "残差正态与方差齐", "协变量测量可靠"),
        typical_uses=("控制基线值后的处理比较", "控制环境协变量后的品种比较"),
        min_fixed_factors=1, max_fixed_factors=2, min_covariates=1, max_covariates=None,
    ),
    "pearson_correlation": MethodSpec(
        name="pearson_correlation", label_zh="Pearson 相关", category="相关分析",
        status=MethodStatus.IMPLEMENTED, executor="pearson_correlation",
        purpose="衡量两个连续变量之间线性关系的方向和强度。",
        variable_relationship="两个数值变量相互关联；不区分因变量和自变量，也不代表因果。",
        variable_requirements=(DV2,),
        output_metrics=("Pearson r", "p 值", "r 的置信区间", "有效样本量"),
        assumptions=("关系近似线性", "无严重异常值", "推断时变量近似二元正态"),
        typical_uses=("性状间线性相关", "环境指标与表型指标相关"),
        min_dependent_vars=2, max_dependent_vars=2, dependent_mode="joint", max_fixed_factors=0,
    ),
    "spearman_correlation": MethodSpec(
        name="spearman_correlation", label_zh="Spearman 秩相关", category="相关分析",
        status=MethodStatus.IMPLEMENTED, executor="spearman_correlation",
        purpose="衡量两个变量之间单调关系的方向和强度，对偏态和异常值更稳健。",
        variable_relationship="将两个变量转为秩后计算关联，不要求线性。",
        variable_requirements=(DV2,),
        output_metrics=("Spearman ρ", "p 值", "有效样本量"),
        assumptions=("观测成对独立", "关系大体单调"),
        typical_uses=("等级数据相关", "非线性但单调的性状关系"),
        min_dependent_vars=2, max_dependent_vars=2, dependent_mode="joint", max_fixed_factors=0,
    ),
    "kendall_correlation": MethodSpec(
        name="kendall_correlation", label_zh="Kendall τ 相关", category="相关分析",
        status=MethodStatus.IMPLEMENTED, executor="kendall_correlation",
        purpose="基于一致对和不一致对衡量两个有序变量的关联，适合小样本或大量并列秩。",
        variable_relationship="比较两个变量中样本排序的一致程度。",
        variable_requirements=(DV2,),
        output_metrics=("Kendall τ", "p 值", "有效样本量"),
        assumptions=("观测成对独立",),
        typical_uses=("小样本等级相关", "大量相同等级值的相关分析"),
        min_dependent_vars=2, max_dependent_vars=2, dependent_mode="joint", max_fixed_factors=0,
    ),
    "linear_regression": MethodSpec(
        name="linear_regression", label_zh="线性回归（简单/多元）", category="回归分析",
        status=MethodStatus.IMPLEMENTED, executor="linear_regression", supports_emm=True, supports_diagnostic_plots=True,
        purpose="估计一个或多个自变量对连续因变量的线性关联，并进行预测或效应调整。",
        variable_relationship="连续协变量和/或分类固定因素共同解释一个连续因变量。",
        variable_requirements=(DV1, VariableRequirement("covariates/fixed_factors", "预测变量", "至少 1 个", "连续变量放入协变量，分类变量放入固定因素。")),
        output_metrics=("回归系数", "标准误", "t 值与 p 值", "置信区间", "R²/调整 R²", "整体 F 检验"),
        assumptions=("线性关系", "残差独立", "同方差", "残差近似正态", "无严重多重共线性"),
        typical_uses=("连续性状预测", "控制多个解释变量", "剂量反应的线性部分"),
        min_fixed_factors=0, max_fixed_factors=None, min_covariates=0, max_covariates=None,
        requires_any_predictor=True,
    ),
    "logistic_regression": MethodSpec(
        name="logistic_regression", label_zh="二元 Logistic 回归", category="回归分析",
        status=MethodStatus.IMPLEMENTED, executor="logistic_regression",
        purpose="分析连续或分类自变量与二元结局发生概率之间的关系。",
        variable_relationship="连续协变量和/或分类固定因素作用于一个只有两个水平的结局变量。",
        variable_requirements=(VariableRequirement("dependent_variables", "二元因变量", "1 个，恰好 2 个水平", "例如 0/1、成功/失败。"), VariableRequirement("covariates/fixed_factors", "预测变量", "至少 1 个", "连续预测量放协变量，分类预测量放固定因素。")),
        output_metrics=("回归系数", "优势比 OR", "置信区间", "Wald z 与 p 值", "AIC", "伪 R²"),
        assumptions=("观测独立", "连续预测量与 logit 近似线性", "无完全分离", "无严重共线性"),
        typical_uses=("发病/不发病", "存活/死亡", "是否达标"),
        min_fixed_factors=0, max_fixed_factors=None, min_covariates=0, max_covariates=None,
        requires_any_predictor=True,
        parameters=(SUCCESS_LEVEL_PARAM,
                    ParameterSpec("max_iterations", "最大迭代次数", "integer", 200, "IRLS 优化最大迭代次数。", minimum=25, maximum=5000, step=25),
                    ParameterSpec("covariance_type", "协方差估计", "select", "nonrobust", "默认模型协方差或异方差稳健协方差。", options=(("nonrobust", "默认"), ("HC0", "HC0 稳健"), ("HC1", "HC1 稳健"), ("HC2", "HC2 稳健"), ("HC3", "HC3 稳健")))),
    ),
    "chi_square_independence": MethodSpec(
        name="chi_square_independence", label_zh="卡方独立性检验", category="分类数据",
        status=MethodStatus.IMPLEMENTED, executor="chi_square_independence",
        purpose="检验两个分类变量是否相互独立。",
        variable_relationship="分类变量 A 与分类变量 B 组成列联表，比较观察频数与独立假设下的期望频数。",
        variable_requirements=(CAT2,),
        output_metrics=("χ²", "自由度", "p 值", "Cramér's V", "期望频数"),
        assumptions=("每个观测只进入一个单元格", "期望频数不应大量过小"),
        typical_uses=("处理与发生率的关联", "类别性状之间的关联"),
        min_dependent_vars=0, max_dependent_vars=0, dependent_mode="none",
        min_fixed_factors=2, max_fixed_factors=2,
        parameters=(
            ParameterSpec("continuity_correction", "连续性校正", "select", "auto", "2×2 表默认自动使用 Yates 校正。", options=(("auto", "自动"), ("on", "始终使用"), ("off", "不使用"))),
            ParameterSpec("power_divergence", "统计量类型", "select", "pearson", "选择 Pearson χ² 或 Cressie–Read 幂散度族。", options=(("pearson", "Pearson χ²"), ("log-likelihood", "似然比 G²"), ("freeman-tukey", "Freeman–Tukey"), ("mod-log-likelihood", "修正似然比"), ("neyman", "Neyman"), ("cressie-read", "Cressie–Read"))),
            ParameterSpec("p_value_method", "p 值计算方式", "select", "asymptotic", "渐近卡方、置换或 Monte Carlo。重抽样方式仅支持 Pearson 且不能同时使用连续性校正。", options=(("asymptotic", "渐近卡方"), ("permutation", "置换检验"), ("monte_carlo", "Monte Carlo"))),
            ParameterSpec("n_resamples", "重抽样次数", "integer", 9999, "置换或 Monte Carlo 的抽样次数。", minimum=99, maximum=1000000, step=100),
            ParameterSpec("random_seed", "随机种子", "integer", 2026, "保证重抽样结果可复现。", minimum=0, maximum=2147483647, step=1),
        ),
    ),
    "fisher_exact": MethodSpec(
        name="fisher_exact", label_zh="Fisher 精确检验（2×2）", category="分类数据",
        status=MethodStatus.IMPLEMENTED, executor="fisher_exact",
        purpose="在小样本或期望频数较低时检验两个二元分类变量是否关联。",
        variable_relationship="两个二水平分类变量组成 2×2 列联表。",
        variable_requirements=(VariableRequirement("fixed_factors", "二元分类变量", "2 个，各 2 个水平", "形成 2×2 表。"),),
        output_metrics=("优势比", "精确 p 值", "2×2 频数表"),
        assumptions=("观测独立", "固定边际下进行精确推断"),
        typical_uses=("小样本发生率比较", "稀有事件关联"),
        min_dependent_vars=0, max_dependent_vars=0, dependent_mode="none",
        min_fixed_factors=2, max_fixed_factors=2, exact_factor_levels=2,
        parameters=(ALT_PARAM,),
    ),
    "chi_square_goodness_of_fit": MethodSpec(
        name="chi_square_goodness_of_fit", label_zh="卡方拟合优度检验", category="分类数据",
        status=MethodStatus.IMPLEMENTED, executor="chi_square_goodness_of_fit",
        purpose="检验一个分类变量的观察频数是否符合指定比例；未提供比例时默认各类别等比例。",
        variable_relationship="一个分类变量的实际类别频数与理论期望频数比较。",
        variable_requirements=(CAT1,),
        output_metrics=("χ²", "自由度", "p 值", "观察/期望频数", "Cohen's w"),
        assumptions=("类别互斥", "期望频数不能过小", "期望比例之和为 1"),
        typical_uses=("分离比检验", "类别比例是否均匀", "理论分布拟合"),
        min_dependent_vars=0, max_dependent_vars=0, dependent_mode="none",
        min_fixed_factors=1, max_fixed_factors=1,
    ),
    "mcnemar_test": MethodSpec(
        name="mcnemar_test", label_zh="McNemar 配对分类检验", category="分类数据",
        status=MethodStatus.IMPLEMENTED, executor="mcnemar_test",
        purpose="比较同一对象在两个条件或两个时间点上的二元结局比例是否变化。",
        variable_relationship="两个配对二元变量构成 2×2 配对表，重点比较不一致配对。",
        variable_requirements=(VariableRequirement("dependent_variables", "配对二元变量", "2 个，各 2 个水平", "例如干预前/后是否阳性。"),),
        output_metrics=("McNemar 统计量", "p 值", "配对 2×2 表", "不一致对数量"),
        assumptions=("同一行代表同一对象", "对象之间独立"),
        typical_uses=("前后阳性率变化", "两个分类器在同一样本上的差异"),
        min_dependent_vars=2, max_dependent_vars=2, dependent_mode="joint", max_fixed_factors=0,
        parameters=(
            ParameterSpec("mcnemar_mode", "计算方式", "select", "auto", "自动在小样本精确检验与渐近卡方之间切换。", options=(("auto", "自动"), ("exact", "精确二项"), ("asymptotic", "渐近卡方"))),
            ParameterSpec("exact_threshold", "精确检验阈值", "integer", 25, "不一致配对数低于该值时自动使用精确检验。", minimum=1, maximum=10000, step=1),
            ParameterSpec("continuity_correction", "连续性校正", "boolean", True, "渐近 McNemar 检验是否使用连续性校正。"),
        ),
    ),
    "exact_binomial_test": MethodSpec(
        name="exact_binomial_test", label_zh="精确二项检验", category="分类数据与比例",
        status=MethodStatus.IMPLEMENTED, executor="exact_binomial_test",
        purpose="检验一个二元分类变量的成功比例是否等于指定理论比例，适合小样本。",
        variable_relationship="一个二元分类变量的观察成功次数与理论二项分布进行比较。",
        variable_requirements=(VariableRequirement("fixed_factors", "二元分类变量", "1 个，2 个水平", "选择需要检验比例的分类列。"),),
        output_metrics=("成功次数/总数", "观察比例", "精确 p 值", "精确置信区间", "比例差"),
        assumptions=("独立伯努利观测", "成功概率在观测间相同"),
        typical_uses=("发生率是否达到目标", "孟德尔分离比例中的二分类情形", "小样本阳性率检验"),
        min_dependent_vars=0, max_dependent_vars=0, dependent_mode="none",
        min_fixed_factors=1, max_fixed_factors=1, exact_factor_levels=2,
        parameters=(SUCCESS_LEVEL_PARAM, NULL_PROP_PARAM, ALT_PARAM,
                    ParameterSpec("ci_method", "比例置信区间", "select", "exact", "二项比例置信区间算法。", options=(("exact", "Clopper–Pearson 精确区间"), ("wilson", "Wilson 区间")))),
    ),
    "one_sample_proportion_ztest": MethodSpec(
        name="one_sample_proportion_ztest", label_zh="单样本比例 z 检验", category="分类数据与比例",
        status=MethodStatus.IMPLEMENTED, executor="one_sample_proportion_ztest",
        purpose="用正态近似检验一个二元变量的总体比例是否等于指定值。",
        variable_relationship="一个二元分类变量的成功比例与理论比例比较。",
        variable_requirements=(VariableRequirement("fixed_factors", "二元分类变量", "1 个，2 个水平", "样本量应足够使成功与失败期望数不太小。"),),
        output_metrics=("z 值", "p 值", "观察比例", "比例差", "近似置信区间"),
        assumptions=("观测独立", "正态近似条件满足"),
        typical_uses=("大样本达标率检验",),
        min_dependent_vars=0, max_dependent_vars=0, dependent_mode="none",
        min_fixed_factors=1, max_fixed_factors=1, exact_factor_levels=2,
        parameters=(SUCCESS_LEVEL_PARAM, NULL_PROP_PARAM, ALT_PARAM),
        notes="成功或失败计数较小时应优先使用精确二项检验。",
    ),
    "two_proportion_ztest": MethodSpec(
        name="two_proportion_ztest", label_zh="两独立比例 z 检验", category="分类数据与比例",
        status=MethodStatus.IMPLEMENTED, executor="two_proportion_ztest",
        purpose="比较两个独立组的二元结局发生比例。",
        variable_relationship="一个二水平分组因素作用于一个二元结局，比较两个组的成功率。",
        variable_requirements=(BINARY_DV, GROUP2),
        output_metrics=("z 值", "p 值", "两组比例", "风险差", "风险比", "优势比"),
        assumptions=("组间独立", "各组成功与失败计数足以支持正态近似"),
        typical_uses=("两个处理的发生率比较", "两组阳性率比较"),
        min_dependent_vars=1, max_dependent_vars=1, dependent_mode="single",
        min_fixed_factors=1, max_fixed_factors=1, exact_factor_levels=2,
        parameters=(SUCCESS_LEVEL_PARAM, ALT_PARAM),
        notes="稀疏 2×2 表应改用 Fisher、Barnard 或 Boschloo 精确检验。",
    ),
    "k_proportion_chi_square": MethodSpec(
        name="k_proportion_chi_square", label_zh="多组比例卡方检验", category="分类数据与比例",
        status=MethodStatus.IMPLEMENTED, executor="k_proportion_chi_square",
        purpose="比较两个或更多独立组的二元结局比例是否一致。",
        variable_relationship="一个多水平分组因素作用于一个二元结局，检验各组成功率是否相同。",
        variable_requirements=(BINARY_DV, GROUPK),
        output_metrics=("χ²", "自由度", "p 值", "各组比例", "Cohen's w"),
        assumptions=("组间独立", "期望频数满足卡方近似"),
        typical_uses=("多个处理的发生率比较", "多个地区的达标率比较"),
        min_dependent_vars=1, max_dependent_vars=1, dependent_mode="single",
        min_fixed_factors=1, max_fixed_factors=1,
        parameters=(SUCCESS_LEVEL_PARAM,
                    ParameterSpec("pairwise_posthoc", "执行两两比例比较", "boolean", True, "总体检验后，对各组进行两两比例 z 检验。"),
                    ParameterSpec("pairwise_p_adjust", "两两比较校正", "select", "holm", "多重比较 p 值校正。", options=(("holm", "Holm"), ("bonferroni", "Bonferroni"), ("fdr_bh", "FDR-BH"), ("none", "不校正")))),
    ),
    "barnard_exact": MethodSpec(
        name="barnard_exact", label_zh="Barnard 无条件精确检验（2×2）", category="分类数据与比例",
        status=MethodStatus.IMPLEMENTED, executor="barnard_exact",
        purpose="在两个独立二元变量形成的 2×2 表中检验关联，通常比 Fisher 更有检验效能。",
        variable_relationship="两个二水平分类变量形成 2×2 表，使用无条件精确推断。",
        variable_requirements=(VariableRequirement("fixed_factors", "二元分类变量", "2 个，各 2 个水平", "形成 2×2 表。"),),
        output_metrics=("Barnard 统计量", "精确 p 值", "优势比及置信区间"),
        assumptions=("观测独立",), typical_uses=("小样本 2×2 发生率比较",),
        min_dependent_vars=0, max_dependent_vars=0, dependent_mode="none",
        min_fixed_factors=2, max_fixed_factors=2, exact_factor_levels=2,
        parameters=(ALT_PARAM, ParameterSpec("pooled", "合并方差", "boolean", True, "Wald 统计量是否使用合并方差。"), EXACT_GRID_PARAM),
    ),
    "boschloo_exact": MethodSpec(
        name="boschloo_exact", label_zh="Boschloo 精确检验（2×2）", category="分类数据与比例",
        status=MethodStatus.IMPLEMENTED, executor="boschloo_exact",
        purpose="对 2×2 列联表执行比 Fisher 更有检验效能的无条件精确检验。",
        variable_relationship="两个二水平分类变量形成 2×2 表，以 Fisher p 值为检验统计量。",
        variable_requirements=(VariableRequirement("fixed_factors", "二元分类变量", "2 个，各 2 个水平", "形成 2×2 表。"),),
        output_metrics=("Boschloo 统计量", "精确 p 值", "优势比及置信区间"),
        assumptions=("观测独立",), typical_uses=("小样本 2×2 发生率比较",),
        min_dependent_vars=0, max_dependent_vars=0, dependent_mode="none",
        min_fixed_factors=2, max_fixed_factors=2, exact_factor_levels=2,
        parameters=(ALT_PARAM, EXACT_GRID_PARAM),
    ),
    "cochran_q_test": MethodSpec(
        name="cochran_q_test", label_zh="Cochran Q 配对比例检验", category="分类数据与比例",
        status=MethodStatus.IMPLEMENTED, executor="cochran_q_test",
        purpose="比较同一对象在三个或更多条件下的二元结局比例。",
        variable_relationship="三个及以上配对二元变量共同描述同一对象在不同条件下的结果。",
        variable_requirements=(PAIR_BINARY_K,),
        output_metrics=("Q 统计量", "自由度", "p 值", "各条件成功率", "Kendall's W"),
        assumptions=("同一行对应同一对象", "对象之间独立", "各变量均为二元"),
        typical_uses=("三个以上分类器比较", "多个时间点阳性率比较"),
        min_dependent_vars=3, max_dependent_vars=None, dependent_mode="joint", max_fixed_factors=0,
        parameters=(SUCCESS_LEVEL_PARAM,),
    ),
    "bowker_symmetry": MethodSpec(
        name="bowker_symmetry", label_zh="Bowker 多分类对称性检验", category="分类数据与比例",
        status=MethodStatus.IMPLEMENTED, executor="bowker_symmetry",
        purpose="检验两个配对多分类测量的联合分布是否关于主对角线对称，是 McNemar 的多分类扩展。",
        variable_relationship="同一对象的两个多分类结果形成方形配对列联表。",
        variable_requirements=(PAIR_CAT,),
        output_metrics=("χ²", "自由度", "p 值", "配对方形列联表"),
        assumptions=("同一行代表同一对象", "两个变量使用相同类别集合", "样本量足以支持卡方近似"),
        typical_uses=("前后多分类状态变化", "两个分类器的多类别差异"),
        min_dependent_vars=2, max_dependent_vars=2, dependent_mode="joint", max_fixed_factors=0,
        parameters=(ParameterSpec("shift_zeros", "零单元格校正", "boolean", False, "若启用，零单元格存在时对所有单元格加 0.5。"),),
    ),
    "stuart_maxwell": MethodSpec(
        name="stuart_maxwell", label_zh="Stuart–Maxwell/Bhapkar 边际同质性检验", category="分类数据与比例",
        status=MethodStatus.IMPLEMENTED, executor="stuart_maxwell",
        purpose="检验两个配对多分类测量的边际类别分布是否相同。",
        variable_relationship="比较同一对象两个多分类测量的行边际与列边际。",
        variable_requirements=(PAIR_CAT,),
        output_metrics=("χ²", "自由度", "p 值", "配对方形列联表"),
        assumptions=("同一行代表同一对象", "两个变量使用相同类别集合"),
        typical_uses=("多分类前后分布变化",),
        min_dependent_vars=2, max_dependent_vars=2, dependent_mode="joint", max_fixed_factors=0,
        parameters=(
            ParameterSpec("homogeneity_method", "边际同质性算法", "select", "stuart_maxwell", "选择 Stuart–Maxwell 或 Bhapkar 协方差估计。", options=(("stuart_maxwell", "Stuart–Maxwell"), ("bhapkar", "Bhapkar"))),
            ParameterSpec("shift_zeros", "零单元格校正", "boolean", False, "若启用，零单元格存在时对所有单元格加 0.5。"),
        ),
    ),
    "cochran_mantel_haenszel": MethodSpec(
        name="cochran_mantel_haenszel", label_zh="Cochran–Mantel–Haenszel 分层检验", category="分类数据与比例",
        status=MethodStatus.IMPLEMENTED, executor="cochran_mantel_haenszel",
        purpose="在控制一个分层变量后，检验二元暴露与二元结局的共同关联并估计合并优势比。",
        variable_relationship="第一个分类因素作为二元暴露，第二个分类因素作为分层变量，共同作用于二元结局。",
        variable_requirements=(BINARY_DV, VariableRequirement("fixed_factors", "暴露与分层", "2 个", "第 1 个须为二元暴露；第 2 个为至少 2 水平的分层变量。")),
        output_metrics=("CMH χ²", "p 值", "合并优势比", "置信区间", "合并风险比"),
        assumptions=("各层独立", "层内为 2×2 表", "层间优势比具有可合并意义"),
        typical_uses=("控制中心/年份/区组后的 2×2 关联",),
        min_dependent_vars=1, max_dependent_vars=1, dependent_mode="single",
        min_fixed_factors=2, max_fixed_factors=2,
        parameters=(SUCCESS_LEVEL_PARAM, ParameterSpec("exposed_level", "暴露水平", "text", "", "留空时使用暴露因素最后出现的水平。"), ParameterSpec("continuity_correction", "连续性校正", "boolean", False, "CMH 检验连续性校正。"), ParameterSpec("shift_zeros", "零单元格校正", "boolean", False, "分层表有零单元格时加 0.5。")),
    ),
    "breslow_day": MethodSpec(
        name="breslow_day", label_zh="Breslow–Day 比值比同质性检验", category="分类数据与比例",
        status=MethodStatus.IMPLEMENTED, executor="breslow_day",
        purpose="检验多个分层 2×2 表的优势比是否相同，判断 CMH 合并优势比是否合理。",
        variable_relationship="第一个分类因素作为二元暴露，第二个分类因素作为分层变量，检验暴露—结局关联是否随层变化。",
        variable_requirements=(BINARY_DV, VariableRequirement("fixed_factors", "暴露与分层", "2 个", "第 1 个须为二元暴露；第 2 个为分层变量。")),
        output_metrics=("Breslow–Day χ²", "自由度", "p 值", "分层 2×2 表"),
        assumptions=("各层独立", "层内为 2×2 表"),
        typical_uses=("检验分层效应修饰", "CMH 前的同质性检查"),
        min_dependent_vars=1, max_dependent_vars=1, dependent_mode="single",
        min_fixed_factors=2, max_fixed_factors=2,
        parameters=(SUCCESS_LEVEL_PARAM, ParameterSpec("exposed_level", "暴露水平", "text", "", "留空时使用暴露因素最后出现的水平。"), ParameterSpec("tarone_adjust", "Tarone 校正", "boolean", False, "使用 Tarone 调整的 Breslow–Day 检验。"), ParameterSpec("shift_zeros", "零单元格校正", "boolean", False, "分层表有零单元格时加 0.5。")),
    ),
    "cohen_kappa": MethodSpec(
        name="cohen_kappa", label_zh="Cohen's kappa 一致性检验", category="分类一致性",
        status=MethodStatus.IMPLEMENTED, executor="cohen_kappa",
        purpose="衡量两个分类测量或两个评分者对同一批对象的超偶然一致性。",
        variable_relationship="两个配对分类变量共同描述同一对象的类别，比较观察一致性与偶然一致性。",
        variable_requirements=(PAIR_CAT,),
        output_metrics=("Cohen's kappa", "标准误", "z 与 p 值", "置信区间", "配对列联表"),
        assumptions=("同一行对应同一对象", "两个变量使用可对齐的类别集合", "对象之间独立"),
        typical_uses=("两名评价者一致性", "两个分类器结果一致性", "前后分类稳定性"),
        min_dependent_vars=2, max_dependent_vars=2, dependent_mode="joint", max_fixed_factors=0,
        parameters=(ParameterSpec("weights", "权重方式", "select", "none", "名义类别使用不加权；有序类别可选线性或二次加权。", options=(("none", "不加权"), ("linear", "线性加权"), ("quadratic", "二次加权"))),),
    ),
    "fleiss_kappa": MethodSpec(
        name="fleiss_kappa", label_zh="Fleiss/Randolph 多评分者 kappa", category="分类一致性",
        status=MethodStatus.IMPLEMENTED, executor="fleiss_kappa",
        purpose="衡量三个及以上评分者对同一批对象进行分类时的一致性。",
        variable_relationship="每个所选分类变量代表一名评分者，各列共同作用于同一对象的一致性评价。",
        variable_requirements=(VariableRequirement("dependent_variables", "评分者分类变量", "至少 3 个", "每列代表一个评分者或分类器，每行代表同一对象。"),),
        output_metrics=("Fleiss 或 Randolph kappa", "评分者数量", "对象数量", "类别集合"),
        assumptions=("各列评价同一批对象", "缺失行按完整案例处理", "类别编码可对齐"),
        typical_uses=("多专家评级", "多个分类器一致性", "多观察者分类记录"),
        min_dependent_vars=3, max_dependent_vars=None, dependent_mode="joint", max_fixed_factors=0,
        parameters=(ParameterSpec("kappa_method", "kappa 定义", "select", "fleiss", "Fleiss 使用样本边际；Randolph 使用自由边际。", options=(("fleiss", "Fleiss 固定边际"), ("randolph", "Randolph 自由边际"))),),
    ),
    "cochran_armitage_trend": MethodSpec(
        name="cochran_armitage_trend", label_zh="Cochran–Armitage 比例趋势检验", category="分类数据与比例",
        status=MethodStatus.IMPLEMENTED, executor="cochran_armitage_trend",
        purpose="检验二元结局比例是否随一个有序分类因素呈线性趋势。",
        variable_relationship="一个有序多水平分类因素作用于一个二元结局，利用预先指定的水平顺序和得分检验比例趋势。",
        variable_requirements=(BINARY_DV, VariableRequirement("fixed_factors", "有序分类因素", "1 个，至少 3 个水平", "必须确认从低到高的水平顺序。")),
        output_metrics=("趋势 z 值", "p 值", "各水平比例", "首末水平比例差"),
        assumptions=("组间观测独立", "结局为二元", "水平顺序和趋势得分在分析前确定"),
        typical_uses=("剂量—反应趋势", "等级递增下发生率趋势", "有序暴露水平与阳性率"),
        min_dependent_vars=1, max_dependent_vars=1, dependent_mode="single", min_fixed_factors=1, max_fixed_factors=1,
        parameters=(SUCCESS_LEVEL_PARAM,
                    ParameterSpec("level_order", "有序水平顺序", "text", "", "按从低到高用英文逗号分隔；留空使用数据出现顺序。"),
                    ParameterSpec("scores", "趋势得分", "text", "", "用英文逗号分隔；留空使用 0,1,2,… 等距得分。"), ALT_PARAM),
    ),
    "multinomial_logistic_regression": MethodSpec(
        name="multinomial_logistic_regression", label_zh="多项 Logistic 回归", category="分类回归",
        status=MethodStatus.IMPLEMENTED, executor="multinomial_logistic_regression",
        purpose="分析连续或分类预测变量与三个及以上无序类别结局之间的关系。",
        variable_relationship="分类固定因素和连续协变量共同作用于一个无序多分类因变量。",
        variable_requirements=(VariableRequirement("dependent_variables", "无序多分类因变量", "1 个，至少 3 个水平", "类别没有自然顺序。"), VariableRequirement("covariates/fixed_factors", "预测变量", "至少 1 个", "分类预测量放固定因素，连续预测量放协变量。")),
        output_metrics=("整体似然比检验", "各类别相对风险比", "系数及置信区间", "AIC/BIC", "伪 R²"),
        assumptions=("观测独立", "无完全分离", "无严重多重共线性", "类别应无自然顺序"),
        typical_uses=("多类别状态预测", "品级/类型等无序结局"),
        min_dependent_vars=1, max_dependent_vars=1, dependent_mode="single",
        min_fixed_factors=0, max_fixed_factors=None, min_covariates=0, max_covariates=None, requires_any_predictor=True,
        parameters=(ParameterSpec("reference_level", "参考类别", "text", "", "留空使用数据中第一个类别；填写后该类别作为比较基准。"),
                    ParameterSpec("max_iterations", "最大迭代次数", "integer", 200, "优化器最大迭代次数。", minimum=50, maximum=5000, step=50),),
    ),
    "ordinal_logistic_regression": MethodSpec(
        name="ordinal_logistic_regression", label_zh="有序 Logistic/Probit 回归", category="分类回归",
        status=MethodStatus.IMPLEMENTED, executor="ordinal_logistic_regression",
        purpose="分析预测变量如何影响具有自然顺序的三个及以上类别结局。",
        variable_relationship="分类固定因素和连续协变量共同作用于一个有序多分类因变量。",
        variable_requirements=(VariableRequirement("dependent_variables", "有序多分类因变量", "1 个，至少 3 个水平", "必须在高级参数中确认水平顺序。"), VariableRequirement("covariates/fixed_factors", "预测变量", "至少 1 个", "分类预测量放固定因素，连续预测量放协变量。")),
        output_metrics=("整体似然比检验", "比例优势比", "系数及置信区间", "阈值参数", "AIC/BIC", "伪 R²"),
        assumptions=("观测独立", "给定类别顺序正确", "比例优势/平行线假设需复核"),
        typical_uses=("轻/中/重等级", "低/中/高评分", "有序质量等级"),
        min_dependent_vars=1, max_dependent_vars=1, dependent_mode="single",
        min_fixed_factors=0, max_fixed_factors=None, min_covariates=0, max_covariates=None, requires_any_predictor=True,
        parameters=(
            ParameterSpec("level_order", "类别顺序", "text", "", "按从低到高用英文逗号分隔；留空使用数据出现顺序。"),
            ParameterSpec("link", "链接函数", "select", "logit", "有序模型链接函数。", options=(("logit", "Logit"), ("probit", "Probit"), ("cloglog", "Complementary log-log"), ("loglog", "Log-log"), ("cauchit", "Cauchit"))),
            ParameterSpec("max_iterations", "最大迭代次数", "integer", 200, "优化器最大迭代次数。", minimum=50, maximum=5000, step=50),
        ),
    ),
    "repeated_measures_anova": MethodSpec(
        name="repeated_measures_anova", label_zh="单因素重复测量 ANOVA", category="重复测量与层级数据",
        status=MethodStatus.IMPLEMENTED, executor="repeated_measures_anova", supports_emm=True, supports_diagnostic_plots=True,
        purpose="比较同一对象在三个或更多时间/条件下的均值，并建模对象内相关性。",
        variable_relationship="重复/时间因素作用于连续因变量，受试者 ID 连接同一对象的多次观测。",
        variable_requirements=(DV1, SUBJECT, REPEATED),
        output_metrics=("重复因素 F 值", "自由度", "p 值", "偏 η²（近似）"),
        assumptions=("长表结构", "每个对象每个水平一条观测", "完整且平衡的对象内设计", "球形性"),
        typical_uses=("多时期连续指标", "同一对象多条件测量"),
        min_fixed_factors=0, max_fixed_factors=0, requires_subject_id=True, requires_repeated_factor=True,
        parameters=(
            ParameterSpec("sphericity_correction", "球形性校正", "select", "auto", "auto 在 Mauchly 检验显著时优先提示 GG/HF 校正。", options=(("auto", "自动"), ("none", "不校正"), ("greenhouse_geisser", "Greenhouse–Geisser"), ("huynh_feldt", "Huynh–Feldt"))),
            ParameterSpec("pairwise_correction", "重复水平两两比较校正", "select", "holm", "重复水平成对比较的多重校正。", options=(("holm", "Holm"), ("bonferroni", "Bonferroni"), ("fdr_bh", "FDR-BH"), ("none", "不校正"))),
        ),
        notes="要求完整对象内数据；已提供 Mauchly 球形性检验以及 Greenhouse–Geisser/Huynh–Feldt 校正。",
    ),
    "friedman_test": MethodSpec(
        name="friedman_test", label_zh="Friedman 重复测量秩检验", category="重复测量与层级数据",
        status=MethodStatus.IMPLEMENTED, executor="friedman_test",
        purpose="比较同一对象在三个或更多条件下的分布位置，是重复测量 ANOVA 的非参数替代。",
        variable_relationship="重复因素作用于一个数值或有序结果，受试者 ID 标识配对区组。",
        variable_requirements=(DV1, SUBJECT, REPEATED),
        output_metrics=("χ² 近似统计量", "自由度", "p 值", "Kendall's W"),
        assumptions=("同一对象在各条件均有观测", "对象之间独立"),
        typical_uses=("非正态的多时间点比较", "重复等级评分"),
        min_fixed_factors=0, max_fixed_factors=0, requires_subject_id=True, requires_repeated_factor=True,
    ),
    "linear_mixed_model": MethodSpec(
        name="linear_mixed_model", label_zh="线性混合效应模型", category="重复测量与层级数据",
        status=MethodStatus.IMPLEMENTED, executor="linear_mixed_model", supports_emm=True, supports_diagnostic_plots=True,
        purpose="在存在地块、对象、年份或地点内相关性时，同时估计固定效应和随机组间变异。",
        variable_relationship="连续/分类固定预测量作用于连续因变量，随机分组因素吸收群组内相关性。",
        variable_requirements=(DV1, VariableRequirement("covariates/fixed_factors", "固定预测量", "至少 1 个", "连续预测量作为协变量，分类预测量作为固定因素。"), RANDOM),
        output_metrics=("固定效应系数", "标准误与 p 值", "随机效应方差与协方差", "残差方差", "ML 下的 AIC/BIC"),
        assumptions=("条件线性", "随机效应与残差近似正态", "分组数量和每组观测充分"),
        typical_uses=("多地点/多年份试验", "重复测量", "区组或地块嵌套数据"),
        min_fixed_factors=0, max_fixed_factors=None, min_covariates=0, max_covariates=None,
        min_random_factors=1, max_random_factors=1, min_random_slopes=0, max_random_slopes=2, requires_any_predictor=True,
        parameters=(
            ParameterSpec("reml", "REML 估计", "boolean", True, "默认使用 REML；模型比较时可切换为最大似然 ML。"),
            ParameterSpec("optimizer", "优化器", "select", "lbfgs", "混合模型数值优化器。", options=(("lbfgs", "L-BFGS"), ("bfgs", "BFGS"), ("cg", "共轭梯度"), ("powell", "Powell"))),
            ParameterSpec("max_iterations", "最大迭代次数", "integer", 500, "优化器最大迭代次数。", minimum=50, maximum=5000, step=50),
        ),
        notes="支持一个随机分组因素、随机截距和最多两个随机斜率；复杂交叉随机效应仍需专门建模。",
    ),
    "oneway_manova": MethodSpec(
        name="oneway_manova", label_zh="单因素多元方差分析（MANOVA）", category="多变量分析",
        status=MethodStatus.IMPLEMENTED, executor="oneway_manova", supports_emm=True,
        purpose="检验一个分类因素是否影响一组相关连续因变量的联合响应。",
        variable_relationship="一个分类因素进入联合响应模型，只检验该因素的多元总体效应。",
        variable_requirements=(
            VariableRequirement("dependent_variables", "联合连续因变量", "至少 2 个", "多个因变量会作为一个联合响应向量进入同一个 MANOVA，而不是分别运行多个 ANOVA。"),
            VariableRequirement("fixed_factors", "对象间分类因素", "恰好 1 个", "方法已经固定模型因素数；继续选择额外因素时，需确认后按同阶组合分别执行。"),
        ),
        output_metrics=("Pillai/Wilks/Hotelling–Lawley/Roy", "近似 F 与 p 值", "Box's M", "Mardia 残差诊断", "相关矩阵与共线风险", "单变量 Type I/II/III 跟进", "事后比较与字母分组"),
        assumptions=("观测独立", "设计单元内近似多元正态", "方差-协方差矩阵相近", "因变量不过度共线", "完整模型可估计"),
        typical_uses=("不同处理对多个相关性状的联合影响",),
        min_dependent_vars=2, max_dependent_vars=None, dependent_mode="joint",
        min_fixed_factors=1, max_fixed_factors=1, supports_batch=True,
        parameters=(
            ParameterSpec("multivariate_test", "输出多元统计量", "select", "pillai", "输出全部四种统计量或只输出预先指定的一种。", options=(("all", "全部四种"), ("pillai", "Pillai 轨迹"), ("wilks", "Wilks' Lambda"), ("hotelling_lawley", "Hotelling–Lawley"), ("roy", "Roy 最大根")), advanced=True, simple_description="默认只显示较稳健的 Pillai 轨迹；专业用户可展开查看全部四种统计量。", recommendation_note="推荐 Pillai：对协方差假设偏离通常更稳健。"),
            ParameterSpec("primary_multivariate_test", "主要多元判据", "select", "pillai", "决定是否启动显著效应的单变量跟进；默认 Pillai 更稳健。", options=(("pillai", "Pillai 轨迹（推荐）"), ("wilks", "Wilks' Lambda"), ("hotelling_lawley", "Hotelling–Lawley"), ("roy", "Roy 最大根"))),
            ParameterSpec("covariance_test", "Box's M 协方差齐性检验", "boolean", True, "按完整因素组合检查方差-协方差矩阵相近性。"),
            ParameterSpec("box_m_alpha", "Box's M 判定阈值", "number", 0.001, "Box's M 对非正态和大样本敏感，默认使用更严格的 0.001；该阈值不改变主分析 α。", minimum=0.000001, maximum=0.1, step=0.001),
            ParameterSpec("normality_test", "Mardia 多元正态近似诊断", "boolean", True, "基于完整析因模型残差进行多元偏度与峰度近似诊断。"),
            ParameterSpec("correlation_diagnostics", "相关与冗余诊断", "boolean", True, "输出完整模型残差相关矩阵的 Bartlett 探索性检验、原始因变量相关矩阵和标准化条件数。"),
            ParameterSpec("follow_up_mode", "单变量跟进范围", "select", "significant", "仅对主要多元判据显著的效应跟进，或对所有效应跟进。", options=(("significant", "仅多元显著效应"), ("all", "全部效应"), ("none", "不执行"))),
            ParameterSpec("follow_up_ss_type", "单变量跟进平方和类型", "select", "3", "不平衡析因设计通常使用 Type III；平衡且无高阶交互时可按方案选择。", options=(("1", "Type I"), ("2", "Type II"), ("3", "Type III（默认）"))),
            ParameterSpec("follow_up_correction", "跨因变量/效应校正", "select", "holm", "对全部单变量跟进检验统一校正。", options=(("holm", "Holm"), ("bonferroni", "Bonferroni"), ("sidak", "Šidák"), ("fdr_bh", "FDR-BH"), ("none", "不校正"))),
            ParameterSpec("posthoc_methods", "跟进比较方法（可多选）", "multi_select", ["tukey"], POSTHOC_MULTI_DESCRIPTION + " 无显著交互时比较显著主效应；存在显著交互时改为条件简单效应内比较。", options=MODEL_POSTHOC_OPTIONS, advanced=False, simple_description="总体或简单效应显著后，进一步比较各水平。普通用户通常选择 Tukey。", recommended_options=("tukey", "duncan", "dunnett", "none"), recommendation_note="推荐 Tukey：适合全部两两比较，并控制整体误报风险。", option_help=POSTHOC_OPTION_HELP),
            ParameterSpec("simple_effect_correction", "简单效应多重校正", "select", "holm", "显著交互后的条件简单效应统一校正。", options=(("holm", "Holm（推荐）"), ("bonferroni", "Bonferroni"), ("sidak", "Šidák"), ("fdr_bh", "FDR-BH"), ("none", "不校正"))),
            ParameterSpec("posthoc_scope", "事后比较分支", "select", "significance_gated", "默认仅在单变量主效应或简单效应显著后比较；R 复现模式按交互是否显著选择边际比较或双向条件内比较，并执行该分支的全部预设比较。", options=(("significance_gated", "仅显著效应后比较（默认）"), ("branch_all", "按交互分支完整比较（R 复现）")), advanced=True),
            ParameterSpec("control_group", "Dunnett 对照组", "text", "", "可填写统一水平 CK，或按因素填写 处理=CK;品种=对照品种。", advanced=False, simple_description="只在选择 Dunnett 时填写；多因素可写 处理=CK;品种=对照品种。"),
        ),
        notes="固定为单因素 MANOVA。选择多个候选因素时，经确认后分别运行每个单因素模型，不会把它们同时放入一个模型。",
    ),
    "twoway_manova": MethodSpec(
        name="twoway_manova", label_zh="双因素多元方差分析（MANOVA）", category="多变量分析",
        status=MethodStatus.IMPLEMENTED, executor="twoway_manova", supports_emm=True,
        purpose="同时检验两个分类因素的多元主效应及二者的多元交互效应。",
        variable_relationship="两个分类因素以完整析因形式进入联合响应模型，检验 A、B 和 A×B。",
        variable_requirements=(
            VariableRequirement("dependent_variables", "联合连续因变量", "至少 2 个", "多个因变量会作为一个联合响应向量进入同一个 MANOVA，而不是分别运行多个 ANOVA。"),
            VariableRequirement("fixed_factors", "对象间分类因素", "恰好 2 个", "方法已经固定模型因素数；继续选择额外因素时，需确认后按同阶组合分别执行。"),
        ),
        output_metrics=("Pillai/Wilks/Hotelling–Lawley/Roy", "近似 F 与 p 值", "Box's M", "Mardia 残差诊断", "相关矩阵与共线风险", "单变量 Type I/II/III 跟进", "事后比较与字母分组"),
        assumptions=("观测独立", "设计单元内近似多元正态", "方差-协方差矩阵相近", "因变量不过度共线", "完整模型可估计"),
        typical_uses=("处理×品种对多个相关性状的联合影响",),
        min_dependent_vars=2, max_dependent_vars=None, dependent_mode="joint",
        min_fixed_factors=2, max_fixed_factors=2, supports_batch=True,
        parameters=(
            ParameterSpec("multivariate_test", "输出多元统计量", "select", "pillai", "输出全部四种统计量或只输出预先指定的一种。", options=(("all", "全部四种"), ("pillai", "Pillai 轨迹"), ("wilks", "Wilks' Lambda"), ("hotelling_lawley", "Hotelling–Lawley"), ("roy", "Roy 最大根")), advanced=True, simple_description="默认只显示较稳健的 Pillai 轨迹；专业用户可展开查看全部四种统计量。", recommendation_note="推荐 Pillai：对协方差假设偏离通常更稳健。"),
            ParameterSpec("primary_multivariate_test", "主要多元判据", "select", "pillai", "决定是否启动显著效应的单变量跟进；默认 Pillai 更稳健。", options=(("pillai", "Pillai 轨迹（推荐）"), ("wilks", "Wilks' Lambda"), ("hotelling_lawley", "Hotelling–Lawley"), ("roy", "Roy 最大根"))),
            ParameterSpec("covariance_test", "Box's M 协方差齐性检验", "boolean", True, "按完整因素组合检查方差-协方差矩阵相近性。"),
            ParameterSpec("box_m_alpha", "Box's M 判定阈值", "number", 0.001, "Box's M 对非正态和大样本敏感，默认使用更严格的 0.001；该阈值不改变主分析 α。", minimum=0.000001, maximum=0.1, step=0.001),
            ParameterSpec("normality_test", "Mardia 多元正态近似诊断", "boolean", True, "基于完整析因模型残差进行多元偏度与峰度近似诊断。"),
            ParameterSpec("correlation_diagnostics", "相关与冗余诊断", "boolean", True, "输出完整模型残差相关矩阵的 Bartlett 探索性检验、原始因变量相关矩阵和标准化条件数。"),
            ParameterSpec("follow_up_mode", "单变量跟进范围", "select", "significant", "仅对主要多元判据显著的效应跟进，或对所有效应跟进。", options=(("significant", "仅多元显著效应"), ("all", "全部效应"), ("none", "不执行"))),
            ParameterSpec("follow_up_ss_type", "单变量跟进平方和类型", "select", "3", "不平衡析因设计通常使用 Type III；平衡且无高阶交互时可按方案选择。", options=(("1", "Type I"), ("2", "Type II"), ("3", "Type III（默认）"))),
            ParameterSpec("follow_up_correction", "跨因变量/效应校正", "select", "holm", "对全部单变量跟进检验统一校正。", options=(("holm", "Holm"), ("bonferroni", "Bonferroni"), ("sidak", "Šidák"), ("fdr_bh", "FDR-BH"), ("none", "不校正"))),
            ParameterSpec("posthoc_methods", "跟进比较方法（可多选）", "multi_select", ["tukey"], POSTHOC_MULTI_DESCRIPTION + " 无显著交互时比较显著主效应；存在显著交互时改为条件简单效应内比较。", options=MODEL_POSTHOC_OPTIONS, advanced=False, simple_description="总体或简单效应显著后，进一步比较各水平。普通用户通常选择 Tukey。", recommended_options=("tukey", "duncan", "dunnett", "none"), recommendation_note="推荐 Tukey：适合全部两两比较，并控制整体误报风险。", option_help=POSTHOC_OPTION_HELP),
            ParameterSpec("simple_effect_correction", "简单效应多重校正", "select", "holm", "显著交互后的条件简单效应统一校正。", options=(("holm", "Holm（推荐）"), ("bonferroni", "Bonferroni"), ("sidak", "Šidák"), ("fdr_bh", "FDR-BH"), ("none", "不校正"))),
            ParameterSpec("posthoc_scope", "事后比较分支", "select", "significance_gated", "默认仅在单变量主效应或简单效应显著后比较；R 复现模式按交互是否显著选择边际比较或双向条件内比较，并执行该分支的全部预设比较。", options=(("significance_gated", "仅显著效应后比较（默认）"), ("branch_all", "按交互分支完整比较（R 复现）")), advanced=True),
            ParameterSpec("control_group", "Dunnett 对照组", "text", "", "可填写统一水平 CK，或按因素填写 处理=CK;品种=对照品种。", advanced=False, simple_description="只在选择 Dunnett 时填写；多因素可写 处理=CK;品种=对照品种。"),
        ),
        notes="固定为双因素 MANOVA。选择三个或更多候选因素时，经确认后按 C(n,2) 运行全部双因素组合。",
    ),
    "threeway_manova": MethodSpec(
        name="threeway_manova", label_zh="三因素多元方差分析（MANOVA）", category="多变量分析",
        status=MethodStatus.IMPLEMENTED, executor="threeway_manova", supports_emm=True,
        purpose="检验三个分类因素的多元主效应、两两交互及三因素交互。",
        variable_relationship="三个分类因素以完整析因形式进入联合响应模型，检验主效应、两两交互和 A×B×C。",
        variable_requirements=(
            VariableRequirement("dependent_variables", "联合连续因变量", "至少 2 个", "多个因变量会作为一个联合响应向量进入同一个 MANOVA，而不是分别运行多个 ANOVA。"),
            VariableRequirement("fixed_factors", "对象间分类因素", "恰好 3 个", "方法已经固定模型因素数；继续选择额外因素时，需确认后按同阶组合分别执行。"),
        ),
        output_metrics=("Pillai/Wilks/Hotelling–Lawley/Roy", "近似 F 与 p 值", "Box's M", "Mardia 残差诊断", "相关矩阵与共线风险", "单变量 Type I/II/III 跟进", "事后比较与字母分组"),
        assumptions=("观测独立", "设计单元内近似多元正态", "方差-协方差矩阵相近", "因变量不过度共线", "完整模型可估计"),
        typical_uses=("处理×品种×环境对多个相关性状的联合影响",),
        min_dependent_vars=2, max_dependent_vars=None, dependent_mode="joint",
        min_fixed_factors=3, max_fixed_factors=3, supports_batch=True,
        parameters=(
            ParameterSpec("multivariate_test", "输出多元统计量", "select", "pillai", "输出全部四种统计量或只输出预先指定的一种。", options=(("all", "全部四种"), ("pillai", "Pillai 轨迹"), ("wilks", "Wilks' Lambda"), ("hotelling_lawley", "Hotelling–Lawley"), ("roy", "Roy 最大根")), advanced=True, simple_description="默认只显示较稳健的 Pillai 轨迹；专业用户可展开查看全部四种统计量。", recommendation_note="推荐 Pillai：对协方差假设偏离通常更稳健。"),
            ParameterSpec("primary_multivariate_test", "主要多元判据", "select", "pillai", "决定是否启动显著效应的单变量跟进；默认 Pillai 更稳健。", options=(("pillai", "Pillai 轨迹（推荐）"), ("wilks", "Wilks' Lambda"), ("hotelling_lawley", "Hotelling–Lawley"), ("roy", "Roy 最大根"))),
            ParameterSpec("covariance_test", "Box's M 协方差齐性检验", "boolean", True, "按完整因素组合检查方差-协方差矩阵相近性。"),
            ParameterSpec("box_m_alpha", "Box's M 判定阈值", "number", 0.001, "Box's M 对非正态和大样本敏感，默认使用更严格的 0.001；该阈值不改变主分析 α。", minimum=0.000001, maximum=0.1, step=0.001),
            ParameterSpec("normality_test", "Mardia 多元正态近似诊断", "boolean", True, "基于完整析因模型残差进行多元偏度与峰度近似诊断。"),
            ParameterSpec("correlation_diagnostics", "相关与冗余诊断", "boolean", True, "输出完整模型残差相关矩阵的 Bartlett 探索性检验、原始因变量相关矩阵和标准化条件数。"),
            ParameterSpec("follow_up_mode", "单变量跟进范围", "select", "significant", "仅对主要多元判据显著的效应跟进，或对所有效应跟进。", options=(("significant", "仅多元显著效应"), ("all", "全部效应"), ("none", "不执行"))),
            ParameterSpec("follow_up_ss_type", "单变量跟进平方和类型", "select", "3", "不平衡析因设计通常使用 Type III；平衡且无高阶交互时可按方案选择。", options=(("1", "Type I"), ("2", "Type II"), ("3", "Type III（默认）"))),
            ParameterSpec("follow_up_correction", "跨因变量/效应校正", "select", "holm", "对全部单变量跟进检验统一校正。", options=(("holm", "Holm"), ("bonferroni", "Bonferroni"), ("sidak", "Šidák"), ("fdr_bh", "FDR-BH"), ("none", "不校正"))),
            ParameterSpec("posthoc_methods", "跟进比较方法（可多选）", "multi_select", ["tukey"], POSTHOC_MULTI_DESCRIPTION + " 无显著交互时比较显著主效应；存在显著交互时改为条件简单效应内比较。", options=MODEL_POSTHOC_OPTIONS, advanced=False, simple_description="总体或简单效应显著后，进一步比较各水平。普通用户通常选择 Tukey。", recommended_options=("tukey", "duncan", "dunnett", "none"), recommendation_note="推荐 Tukey：适合全部两两比较，并控制整体误报风险。", option_help=POSTHOC_OPTION_HELP),
            ParameterSpec("simple_effect_correction", "简单效应多重校正", "select", "holm", "显著交互后的条件简单效应统一校正。", options=(("holm", "Holm（推荐）"), ("bonferroni", "Bonferroni"), ("sidak", "Šidák"), ("fdr_bh", "FDR-BH"), ("none", "不校正"))),
            ParameterSpec("posthoc_scope", "事后比较分支", "select", "significance_gated", "默认仅在单变量主效应或简单效应显著后比较；R 复现模式按交互是否显著选择边际比较或双向条件内比较，并执行该分支的全部预设比较。", options=(("significance_gated", "仅显著效应后比较（默认）"), ("branch_all", "按交互分支完整比较（R 复现）")), advanced=True),
            ParameterSpec("control_group", "Dunnett 对照组", "text", "", "可填写统一水平 CK，或按因素填写 处理=CK;品种=对照品种。", advanced=False, simple_description="只在选择 Dunnett 时填写；多因素可写 处理=CK;品种=对照品种。"),
        ),
        notes="固定为三因素 MANOVA。选择四个或更多候选因素时，经确认后按 C(n,3) 运行全部三因素组合。",
    ),
    "manova": MethodSpec(
        name="manova", label_zh="旧版统一 MANOVA（兼容）", category="多变量分析",
        status=MethodStatus.IMPLEMENTED, executor=None, supports_emm=True,
        purpose="仅用于读取 v0.4.6 及更早保存的统一 MANOVA 计划。",
        variable_relationship="载入时会按原计划的因素阶数迁移到单因素、双因素或三因素 MANOVA。",
        variable_requirements=(VariableRequirement("dependent_variables", "联合连续因变量", "至少 2 个", "旧版兼容入口。"), VariableRequirement("fixed_factors", "对象间分类因素", "1–3 个", "旧版兼容入口。")),
        output_metrics=("旧版兼容迁移",), min_dependent_vars=2, max_dependent_vars=None, dependent_mode="joint",
        min_fixed_factors=1, max_fixed_factors=3, supports_batch=True, parameters=(),
        notes="该入口不在新建分析的方法列表中显示。", visible=False,
    ),
    "mixed_anova": MethodSpec(
        name="mixed_anova", label_zh="自适应混合设计分析", category="重复测量与层级数据",
        status=MethodStatus.IMPLEMENTED, executor="mixed_anova", supports_emm=True, supports_diagnostic_plots=True,
        purpose="分析一至两个对象间因素与一个对象内重复因素，并根据数据完整性自动选择经典混合 ANOVA 或线性混合效应模型。",
        variable_relationship="对象间因素、重复因素及其完整交互共同作用于连续因变量；对象 ID 作为配对结构或随机截距。",
        variable_requirements=(DV1, SUBJECT, REPEATED, VariableRequirement("fixed_factors", "对象间因素", "1–2 个", "完整平衡单因素设计可用经典方法；不平衡、缺失或双对象间因素自动进入 MixedLM。")),
        output_metrics=("经典 F/GG/HF 校正或 MixedLM Wald χ²", "固定效应系数", "随机截距方差", "边际均值与多重比较", "残差诊断", "AIC/BIC"),
        assumptions=("每个对象的对象间因素水平固定", "对象之间独立", "条件残差与随机效应近似正态", "经典模式额外要求完整、平衡与球形性"),
        typical_uses=("处理组×时间", "品种×生育时期", "处理×品种×时间", "存在部分缺测的纵向试验"),
        min_fixed_factors=1, max_fixed_factors=2, requires_subject_id=True, requires_repeated_factor=True,
        supports_batch=True,
        parameters=(
            ParameterSpec("analysis_mode", "分析引擎", "select", "auto", "自动模式在完整平衡单因素设计中使用经典混合 ANOVA，其余情况使用 MixedLM。", options=(("auto", "自动选择（推荐）"), ("classical", "强制经典平衡混合 ANOVA"), ("mixedlm", "强制线性混合效应模型"))),
            ParameterSpec("sphericity_correction", "经典模式球形性校正", "select", "auto", "仅经典模式使用。", options=(("auto", "自动"), ("none", "不校正"), ("greenhouse_geisser", "Greenhouse–Geisser"), ("huynh_feldt", "Huynh–Feldt"))),
            ParameterSpec("posthoc_methods", "边际均值多重比较（可多选）", "multi_select", ["tukey"], POSTHOC_MULTI_DESCRIPTION + " MixedLM 使用模型边际均值；经典模式仍保留配对结构比较。", options=MODEL_POSTHOC_OPTIONS, option_help=POSTHOC_OPTION_HELP),
            ParameterSpec("control_group", "Dunnett 对照组", "text", "", "选择 Dunnett 时填写唯一对照水平。", advanced=False, simple_description="只在选择 Dunnett 时填写，例如 CK。"),
            ParameterSpec("emm_scope", "MixedLM 边际均值范围", "select", "cells", "控制输出重复因素、对象间因素或完整组合的 EMM。", options=(("cells", "完整因素组合"), ("within", "重复因素边际均值"), ("between", "对象间因素边际均值"))),
            ParameterSpec("reml", "MixedLM 使用 REML", "boolean", False, "固定效应比较默认 ML；最终估计可切换 REML。"),
            ParameterSpec("optimizer", "MixedLM 优化器", "select", "auto", "自动依次尝试 L-BFGS、Powell、CG。", options=(("auto", "自动尝试"), ("lbfgs", "L-BFGS"), ("powell", "Powell"), ("cg", "共轭梯度"))),
            ParameterSpec("max_iterations", "最大迭代次数", "integer", 500, "混合模型优化器最大迭代次数。", minimum=50, maximum=5000, step=50),
            ParameterSpec("random_slope_repeated", "重复因素随机斜率", "boolean", False, "复杂数据可启用，但可能增加奇异拟合或不收敛风险。"),
            ParameterSpec("pairwise_correction", "经典模式两两比较校正", "select", "holm", "仅经典路径使用。", options=(("holm", "Holm"), ("bonferroni", "Bonferroni"), ("sidak", "Šidák"), ("fdr_bh", "FDR-BH"), ("none", "不校正"))),
        ),
        notes="自动路径不会把 MixedLM 的 Wald χ² 伪装成经典 F 检验；结果会明确记录所用引擎、选择原因与收敛状态。",
    ),
}

_MULTIFACTOR_ORDER = ParameterSpec(
    "factor_model_order",
    "模型因素阶数",
    "select",
    "4",
    "控制进入同一个完整析因模型的分类因素数量；必须与实际选择的因素数完全一致。",
    options=tuple((str(order), f"{order} 因素") for order in range(4, 9)),
    advanced=False,
    simple_description="选择 4–8 阶完整析因模型；阶数就是同时进入模型的分类因素数量。",
    recommended_options=("4", "5", "6", "7", "8"),
    recommendation_note="阶数越高，交互项和所需样本量呈指数增长；只选择研究设计预先规定的阶数。",
    option_help=tuple(
        (str(order), f"同时拟合 {order} 个分类因素及其全部交互；完整模型最多包含 {2 ** order - 1} 个效应。")
        for order in range(4, 9)
    ),
)

_METHODS["multifactor_anova"] = MethodSpec(
    name="multifactor_anova", label_zh="多因素方差分析（4–8 因素）", category="方差分析",
    status=MethodStatus.IMPLEMENTED, executor="multifactor_anova", supports_emm=True, supports_diagnostic_plots=True,
    purpose="检验 4–8 个分类因素对一个连续因变量的主效应及全部阶次交互作用。",
    variable_relationship="所选阶数个分类因素同时进入一个完整析因模型，而不是拆成多个低阶模型。",
    variable_requirements=(
        DV1,
        VariableRequirement("fixed_factors", "分类因素", "由阶数控制，恰好 4–8 个", "阶数必须与选择的因素数量一致；模型包含全部主效应和最高至所选阶数的交互。"),
    ),
    output_metrics=("全部主效应与交互效应", "Type I/II/III F 检验", "p 值", "偏 η²/ω²", "残差与方差齐性诊断", "可估计性检查"),
    assumptions=("观测独立", "完整析因设计可估计", "残差近似正态", "设计单元方差近似相等", "因素组合内有足够重复"),
    typical_uses=("四因素及以上完整析因试验", "多环境×多处理×品种试验"),
    min_fixed_factors=4, max_fixed_factors=8,
    parameters=(_MULTIFACTOR_ORDER,),
    notes="仅用于 4–8 因素完整模型。系统会检查设计矩阵秩和残差自由度；高阶模型通常需要大量完整单元与重复观测。",
)

_METHODS["multifactor_manova"] = MethodSpec(
    name="multifactor_manova", label_zh="多因素多元方差分析（4–8 因素 MANOVA）", category="多变量分析",
    status=MethodStatus.IMPLEMENTED, executor="multifactor_manova", supports_emm=True,
    purpose="检验 4–8 个分类因素是否影响一组相关连续因变量的联合响应。",
    variable_relationship="多个连续因变量作为联合响应，所选阶数个分类因素以完整析因形式同时进入 MANOVA。",
    variable_requirements=(
        VariableRequirement("dependent_variables", "联合连续因变量", "至少 2 个", "多个因变量共同进入一个联合响应模型。"),
        VariableRequirement("fixed_factors", "对象间分类因素", "由阶数控制，恰好 4–8 个", "模型检验全部主效应以及最高至所选阶数的多元交互。"),
    ),
    output_metrics=_METHODS["threeway_manova"].output_metrics,
    assumptions=_METHODS["threeway_manova"].assumptions,
    typical_uses=("四因素及以上对多个相关性状的联合影响",),
    min_dependent_vars=2, max_dependent_vars=None, dependent_mode="joint",
    min_fixed_factors=4, max_fixed_factors=8,
    parameters=(
        _MULTIFACTOR_ORDER,
        *(
            replace(parameter, advanced=True)
            if parameter.key == "control_group"
            else parameter
            for parameter in _METHODS["threeway_manova"].parameters
        ),
    ),
    notes="仅用于 4–8 因素完整 MANOVA。高阶交互数量按 2^k−1 增长；系统不会把不可估计模型静默降级。",
)

_ALIASES = {"ttest": "welch_ttest"}


def canonical_method_name(name: str) -> str:
    return _ALIASES.get(name, name)


def get_method(name: str) -> MethodSpec:
    canonical = canonical_method_name(name)
    try:
        return _METHODS[canonical]
    except KeyError as exc:
        raise ValueError(f"未知统计方法: {name}") from exc


def list_methods(*, runnable_only: bool = False) -> list[MethodSpec]:
    methods = [method for method in _METHODS.values() if method.visible]
    if runnable_only:
        methods = [method for method in methods if method.is_runnable]
    return methods
