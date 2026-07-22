"""固化约束规则 — 硬编码禁止行为，AI 和报告均不可违反。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RuleLevel(str, Enum):
    HARD = "hard"       # 硬约束，必须遵守
    SOFT = "soft"       # 软建议，提醒用户


@dataclass
class Rule:
    id: str
    level: RuleLevel
    category: str       # "design" / "execution" / "report" / "ai"
    description: str
    check: str          # 人性化的检查条件描述
    violation_msg: str  # 违规时的消息


# --- 十大固化规则 ---

RULES: list[Rule] = [
    # R1: 重复测量规则
    Rule(
        id="R1",
        level=RuleLevel.HARD,
        category="design",
        description="同一 ID 在多个时间点重复测量 + 研究问题含变化/提高/趋势 → 必须使用混合模型",
        check="检测到重复测量结构 & 研究目标含 '变化/轨迹/幅度/趋势' → 禁止分时点独立 ANOVA",
        violation_msg="同一被试重复测量，不能通过分时点独立 ANOVA 并比较 p 值来证明变化。"
                       "请使用重复测量 ANOVA 或线性混合效应模型。",
    ),

    # R2: 横截面规则
    Rule(
        id="R2",
        level=RuleLevel.HARD,
        category="report",
        description="横截面分析（分时点独立 ANOVA）报告中禁止使用纵向词汇",
        check="方法为分时点独立分析 → 报告禁止 '提高/下降/进步/退步/变化幅度/趋势'",
        violation_msg="横截面分析不能使用动态词汇。请替换为：'在T2节点，A组得分显著高于B组'。",
    ),

    # R3: 派生变量规则
    Rule(
        id="R3",
        level=RuleLevel.HARD,
        category="design",
        description="派生变量不能与子变量同时进入 MANOVA",
        check="检测到 总分=数学+语文 等派生关系 → MANOVA 中只含子变量，总分单独分析",
        violation_msg="'总分' 是 '数学' + '语文' 的线性组合，三者不能同时进入 MANOVA。"
                       "请在 MANOVA 中仅放入子变量；总分作为独立派生分析。",
    ),

    # R4: 交互作用规则
    Rule(
        id="R4",
        level=RuleLevel.HARD,
        category="execution",
        description="交互显著时必须优先解释简单效应/条件效应",
        check="交互 p < 0.05 → 主效应解读标记为'边际效应'，优先展示简单效应分析",
        violation_msg="交互作用显著时，主效应只是跨水平的平均值。"
                       "请优先报告简单效应分析结果，再附带报告主效应。",
    ),

    # R5: ANOVA 显著后才能做事后比较
    Rule(
        id="R5",
        level=RuleLevel.HARD,
        category="execution",
        description="事后多重比较必须在 ANOVA 整体显著后进行",
        check="ANOVA omnibus p > 0.05 → 不做事后比较",
        violation_msg="ANOVA 整体不显著，事后比较没有统计意义。",
    ),

    # R6: 方差齐性必须在 ANOVA 前
    Rule(
        id="R6",
        level=RuleLevel.HARD,
        category="execution",
        description="ANOVA 前必须执行方差齐性检验",
        check="执行 ANOVA 前务必先运行 Levene / Bartlett 检验",
        violation_msg="方差分析前未进行方差齐性检验。请先检验。",
    ),

    # R7: ANCOVA 回归斜率同质性
    Rule(
        id="R7",
        level=RuleLevel.HARD,
        category="execution",
        description="ANCOVA 前必须检验回归斜率同质性",
        check="ANCOVA 模型中包含交互项 '因素×协变量' → 交互必须不显著(p>.05)",
        violation_msg="回归斜率不平行 (交互显著)，不满足 ANCOVA 前提。"
                       "请考虑分层分析或改用其他方法。",
    ),

    # R8: 简单效应必须使用合并误差项
    Rule(
        id="R8",
        level=RuleLevel.HARD,
        category="execution",
        description="简单效应分析必须使用全局 ANOVA 模型的合并误差项",
        check="简单效应不可通过独立 t 检验实现 → 必须使用合并 MS_error 和 df_error",
        violation_msg="简单效应分析不能使用拆分后独立 t 检验。"
                       "必须使用完整模型的合并误差项 (pooled error term)。",
    ),

    # R9: AI 不能计算统计数值
    Rule(
        id="R9",
        level=RuleLevel.HARD,
        category="ai",
        description="AI 不能自行产生任何 F/p/η²/Cohen's d/CI 数值",
        check="AI 输出中检测到可能的统计数值 → 拦截并警告",
        violation_msg="AI 生成的内容含疑似编造的统计数值。"
                       "所有统计数值必须由统计引擎产生。",
    ),

    # R10: AI 不能更换已确认方案
    Rule(
        id="R10",
        level=RuleLevel.HARD,
        category="ai",
        description="AI 不能因为看到显著结果而事后更换分析方法",
        check="分析方法在用户确认后锁定 → AI 不能建议'既然 p<.05, 不如改用...'",
        violation_msg="分析方法已在步骤 4 由您确认，不能因见到显著结果而更改。",
    ),
]


def get_hard_rules() -> list[Rule]:
    return [r for r in RULES if r.level == RuleLevel.HARD]


def get_soft_rules() -> list[Rule]:
    return [r for r in RULES if r.level == RuleLevel.SOFT]


def get_rules_by_category(category: str) -> list[Rule]:
    return [r for r in RULES if r.category == category]


def validate_design_against_rules(
    has_repeated_measures: bool,
    has_derived_variables: bool,
    has_time_variable: bool,
    research_goal: str,
    proposed_method: str,
) -> list[str]:
    """根据实验设计和研究目标，返回所有违规。"""
    violations: list[str] = []

    # R1: 重复测量 + 变化类目标 → 不能用分时点独立方法
    if has_repeated_measures:
        dynamic_keywords = ["变化", "轨迹", "幅度", "趋势", "提高", "下降", "进步", "增长"]
        if any(kw in research_goal for kw in dynamic_keywords):
            if "分时点" in proposed_method or proposed_method in ["twoway_anova", "oneway_anova"]:
                violations.append(f"[R1] {RULES[0].violation_msg}")

    return violations


def check_report_for_violations(
    report_text: str,
    method_type: str,  # "cross_sectional" | "longitudinal" | "ancova" etc.
) -> list[str]:
    """检查生成的报告是否违反约束。"""
    violations: list[str] = []

    # R2: 横截面分析不能有纵向词汇
    if method_type == "cross_sectional":
        forbidden_words = ["提高", "下降", "进步", "退步", "变化幅度", "趋势向好",
                          "显著提升", "明显改善", "随时间增长"]
        for word in forbidden_words:
            if word in report_text:
                violations.append(f"[R2] 横截面分析中使用了纵向词汇 '{word}'。"
                                  f"{RULES[1].violation_msg}")

    return violations
