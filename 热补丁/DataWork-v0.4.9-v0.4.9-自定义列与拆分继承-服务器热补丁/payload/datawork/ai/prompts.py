"""AI Prompt 模板 — 各步骤的结构化 Prompt。

所有 Prompt 必须要求 JSON 输出，且包含规则引擎的约束。
"""

from __future__ import annotations

import json
from pydantic import BaseModel, Field


# ─── Pydantic Schema: AI 输出结构 ───

class VariableRoleSuggestion(BaseModel):
    """AI 对单列的角色建议。"""
    column: str
    suggested_role: str = Field(description="id/between/within/time/covariate/dependent/derived/ignore")
    confidence: float = Field(ge=0, le=1)
    reasoning: str = ""


class VariableRoleResponse(BaseModel):
    """AI 变量角色推断的完整响应。"""
    variables: list[VariableRoleSuggestion]
    notes: list[str] = []             # 额外观察或警告
    questions: list[str] = []          # 需要用户确认的问题
    wide_format_hint: str = ""         # 宽格式检测
    derived_hints: list[str] = []      # 派生变量关系


class MethodRecommendation(BaseModel):
    """AI 方法推荐。"""
    method_name: str
    label_zh: str
    confidence: float
    formula: str
    reasoning: list[str]
    assumptions: list[str] = []
    posthoc_plan: str = ""
    alternatives: list[dict[str, str]] = []  # [{method, when}]
    limitations: list[str] = []
    questions: list[str] = []


class MethodRecommendationResponse(BaseModel):
    """AI 方法推荐的完整响应。"""
    primary: MethodRecommendation
    alternatives: list[MethodRecommendation] = []
    notes: list[str] = []


class ResearchGoalStructured(BaseModel):
    """AI 解析的研究目标。"""
    goal_key: str = Field(description="compare_groups/test_interaction/endpoint_only/control_baseline/change_amplitude/trajectory/cross_sectional_times/correlation/multiple_dvs/custom")
    goal_label_zh: str
    explanation: str
    suggested_methods: list[str] = []


# ─── Prompt 模板 ───

def variable_inference_prompt(columns_info: list[dict], n_rows: int, warnings: list[str]) -> list[dict]:
    """
    生成变量角色推断的 Prompt。

    columns_info: [{name, dtype, n_unique, missing_rate, sample_values, rules_inferred_role}]
    """
    system = """你是一位实验统计设计专家。根据数据列信息，推断每个列的变量角色。

角色定义：
- id: 实验单元/被试的唯一标识（如编号、ID、被试号）
- between: 组间因素（如性别、教学方法、品种、处理）
- within: 组内因素或重复测量因素（如时间点、条件）
- time: 时间变量（如年份、日期、时期）
- covariate: 连续协变量（如基线值、前测成绩）
- dependent: 连续因变量（需要分析的结果指标）
- derived: 派生变量（由其他列计算而来，如总分 = 数学 + 语文）
- ignore: 应排除的列（全空、无意义、自由文本）

注意事项：
1. 宽格式时间列（如 "7d脱叶率", "14d脱叶率", "21d脱叶率"）通常应当转为长格式
2. 含"%"/"率"/"percent"的列可能是因变量，但需要先转为数值
3. 总分 = 子变量之和的派生关系须明确指出
4. 置信度低于 0.5 的建议需要提出确认问题

规则引擎的初步推断已包含在内，请在其基础上修正或增强。"""

    user_lines = [
        f"数据总行数: {n_rows}",
        f"数据预览:",
    ]
    for ci in columns_info:
        user_lines.append(
            f"  - {ci['name']}: dtype={ci['dtype']}, unique={ci['n_unique']}, "
            f"missing={ci['missing_rate']:.1%}, "
            f"sample={ci.get('sample_values', [])[:5]}, "
            f"rules_role={ci.get('rules_inferred_role', '?')}"
        )

    if warnings:
        user_lines.append(f"\n警告: {warnings}")

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_lines)},
    ]


def method_recommendation_prompt(
    design_summary: dict,
    research_goal: str,
    candidates: list[dict],
) -> list[dict]:
    """
    生成方法推荐的 Prompt。

    design_summary: {n_between_factors, n_within_factors, n_dependent_vars, has_covariate, has_repeated_measures, has_time, ...}
    research_goal: 用户选择的研究目标（中文）
    candidates: 规则引擎筛选的候选方法 [{method_name, label_zh, confidence, reasoning}]
    """
    system = """你是一位统计方法学专家。根据实验设计特征和研究目标，从候选方法中推荐最佳方案。

要求：
1. 必须从候选方法列表中选择，不能推荐规则引擎未允许的方法
2. 如果候选方法都不完全适合，可以建议调整变量角色后重新选择
3. 推荐理由必须结合研究目标和数据特征
4. 必须列出该方法的前提假设和局限性
5. 每个推荐需说明"可以回答的问题"和"不能回答的问题"
6. 备选方案必须指出适用场景"""

    user_lines = [
        f"## 实验设计特征",
        f"组间因素数: {design_summary.get('n_between_factors', 0)}",
        f"组内因素数: {design_summary.get('n_within_factors', 0)}",
        f"因变量数: {design_summary.get('n_dependent_vars', 1)}",
        f"有协变量: {design_summary.get('has_covariate', False)}",
        f"有重复测量: {design_summary.get('has_repeated_measures', False)}",
        f"有时间变量: {design_summary.get('has_time_variable', False)}",
        f"有派生变量: {design_summary.get('has_derived_variable', False)}",
        f"",
        f"## 研究目标",
        f"{research_goal}",
        f"",
        f"## 规则引擎候选方法 (只能从中选择)",
    ]
    for c in candidates:
        user_lines.append(
            f"  - {c['method_name']} ({c['label_zh']}): 规则置信度 {c.get('confidence', 0):.0%}"
        )
        if c.get('reasoning'):
            for r in c['reasoning']:
                user_lines.append(f"      {r}")

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_lines)},
    ]


def report_generation_prompt(
    result_json: str,
    style: str = "apa",
    lang: str = "zh",
) -> list[dict]:
    """
    根据统计结果 JSON 生成规范化报告摘要的 Prompt。

    result_json: canonical_result.json 的完整内容（字符串）
    style: "apa" | "cn"
    lang: "zh" | "en"
    """
    system_en = """You are a senior academic editor specializing in quantitative research.
Based on the provided statistical results JSON, write a concise research summary
following APA 7th edition standards.

IMPORTANT RULES:
1. NEVER invent or alter any F, p, eta-squared, confidence interval, or mean values.
   Use EXACTLY the numbers from the JSON.
2. When interaction is significant, interpret simple effects BEFORE main effects.
3. When interaction is NOT significant, interpret main effects directly.
4. Use "non-significant" not "no difference" for p > .05.
5. Only claim "significant" when p < alpha (default .05).
6. Report effect sizes alongside p values.
7. Do NOT use causal language for observational data.

Structure:
1. Study Design (1-2 sentences)
2. Key Findings (3-5 bullet points using exact statistics)
3. Interpretation (1 paragraph)
4. Limitations (1-2 sentences)"""

    system_zh = """你是一位量化研究学术编辑。基于提供的统计结果 JSON，撰写一份规范的研究摘要。
遵循 GB/T 标准格式。

重要规则：
1. 绝不编造或修改任何 F、p、η²、置信区间或均值。必须严格使用 JSON 中的数值。
2. 交互显著时，优先解读简单效应，再附带报告主效应。
3. 交互不显著时，直接解读主效应。
4. p > 0.05 时使用"无统计学意义"，而非"无差异"。
5. 仅当 p < alpha（默认 0.05）时使用"显著"。
6. 效应量必须与 p 值同时报告。
7. 观察性数据禁止使用因果表述。

结构：
1. 研究设计（1-2 句）
2. 主要发现（3-5 条，含具体统计量）
3. 解释（1 段）
4. 局限（1-2 句）
5. 报告约束：只描述统计事实，不做因果推论"""

    system = system_zh if lang == "zh" else system_en

    user = f"以下是一次统计分析的结果 JSON：\n\n```json\n{result_json}\n```"

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def research_goal_prompt(description: str, design_summary: dict) -> list[dict]:
    """
    将自然语言研究目标，结构化为预定义类型。

    description: 用户的自然语言描述
    """
    goal_options = [
        ("compare_groups", "比较多个处理是否存在差异"),
        ("test_interaction", "判断两个因素是否交互"),
        ("endpoint_only", "研究某个最终时间点的表现"),
        ("control_baseline", "控制基线后比较最终结果 (ANCOVA)"),
        ("change_amplitude", "比较不同处理的变化幅度"),
        ("trajectory", "比较随时间的变化轨迹"),
        ("cross_sectional_times", "分别考察不同时间节点"),
        ("correlation", "分析变量之间的关系"),
        ("multiple_dvs", "分析多个相关指标 (MANOVA)"),
        ("custom", "自定义/其他"),
    ]

    system = f"""你是实验设计分析助手。将用户的自然语言研究目标映射到以下预定义类别之一：

{json.dumps([{'key': g[0], 'label': g[1]} for g in goal_options], ensure_ascii=False, indent=2)}

设计特征: {json.dumps(design_summary, ensure_ascii=False)}

选择最匹配的目标，并给出解释和建议的分析方法。"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": description},
    ]


def role_explanation_prompt(
    variable_roles: dict[str, str],
    column_details: list[dict],
    n_rows: int,
) -> list[dict]:
    """
    生成对当前变量角色分配的自然语言解释。
    告诉用户：这个分组方案在研究什么、每个角色的含义、有什么注意事项。
    """
    role_labels = {
        "between": "组间因素（实验操纵的自变量）",
        "label": "标签/分组列（用于分组观察的描述性标签）",
        "dependent": "因变量（需要分析的结果指标）",
        "within": "组内因素（重复测量条件）",
        "time": "时间变量",
        "covariate": "协变量（需要控制的连续变量）",
        "id": "实验单元 ID",
        "ignore": "忽略",
    }

    role_summary = []
    for role in ["between", "label", "dependent", "within", "time", "covariate", "id"]:
        cols = [k for k, v in variable_roles.items() if v == role]
        if cols:
            role_summary.append(f"- {role_labels.get(role, role)}: {', '.join(cols)}")

    col_info = []
    for cd in column_details:
        col_info.append(
            f"  {cd['name']}: {cd['dtype']}, {cd['n_unique']} 个水平"
            f"{', 示例: ' + str(cd.get('sample', [])[:3]) if cd.get('sample') else ''}"
        )

    system = """你是一位实验设计与统计分析专家。用户刚完成了变量角色分配。
请用通俗易懂的中文，分以下三部分做简短解释（共 200-300 字）：

1. 📋 **当前分组方案**：这个方案把数据分成了哪些角色？每组是什么含义？
2. 🔬 **能研究什么问题**：基于这个分组，可以回答哪些科学问题？
3. ⚠️ **注意事项**：有什么需要特别注意的地方？（如标签列 vs 因素的区别、是否有遗漏的重要变量等）

要求：简洁、有洞察力、让非统计专业的实验人员也能理解。"""

    user = f"""数据概况: {n_rows} 行观测

变量角色分配:
{chr(10).join(role_summary)}

列详情:
{chr(10).join(col_info)}"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def method_explanation_prompt(
    method_name: str,
    method_label: str,
    formula: str,
    research_goal: str,
    variable_roles: dict[str, str],
    design_summary: dict,
) -> list[dict]:
    """
    生成对所选分析方法的自然语言解释。
    告诉用户：这个方法做什么、为什么选它、研究什么效应、会输出什么结果。
    """
    between = [k for k, v in variable_roles.items() if v == "between"]
    dependent = [k for k, v in variable_roles.items() if v == "dependent"]
    labels = [k for k, v in variable_roles.items() if v == "label"]

    system = """你是一位统计方法学专家。用户选定了一种分析方法。
请用通俗易懂的中文，分以下四部分做简短解释（共 200-350 字）：

1. 🎯 **这个方法做什么**：一句话解释这个方法的核心逻辑
2. 📐 **研究什么效应**：具体研究哪个（些）效应的显著性？交互还是主效应？
3. 📊 **会输出什么**：用户会看到什么结果？（F 检验表、交互图、事后比较等）
4. 💡 **为什么选它**：相比于其他可选方法，为什么这个是合适的？

要求：避免公式和术语堆砌。用"比较 A 组和 B 组在 XX 上的差异"这样的语言。"""

    user = f"""## 实验设计
- 组间因素: {between}
- 因变量: {dependent}
- 标签列: {labels if labels else '(无)'}
- 重复测量: {design_summary.get('has_repeated_measures', False)}
- 协变量: {design_summary.get('has_covariate', False)}

## 研究目标
{research_goal}

## 选定方法
- 方法名: {method_label}
- 公式: {formula}"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def analysis_preview_prompt(
    variable_roles: dict[str, str],
    column_details: list[dict],
    n_rows: int,
) -> list[dict]:
    """生成分析方案预览的 Prompt — AI 读取角色分组，给出不同分析方式的预期结果对比。"""
    between = [k for k, v in variable_roles.items() if v == "between"]
    dependent = [k for k, v in variable_roles.items() if v == "dependent"]
    within = [k for k, v in variable_roles.items() if v == "within"]
    time_col = [k for k, v in variable_roles.items() if v == "time"]
    label_cols = [k for k, v in variable_roles.items() if v == "label"]

    col_summary = []
    for cd in column_details:
        role = variable_roles.get(cd["name"], "?")
        role_label = {"between": "因素", "label": "标签", "dependent": "因变量",
                      "within": "组内", "time": "时间", "covariate": "协变量"}.get(role, role)
        col_summary.append(f"  {cd['name']}: {role_label}, {cd['n_unique']} 个水平")

    system = """你是一位资深统计顾问。用户完成了变量角色分组。请根据当前设计，
用通俗易懂的语言，分以下三部分给出分析方案预览（共 300-500 字）：

1. 📋 **当前设计解读**：这是一个什么实验设计？有几个因素、几个因变量？
2. 🔬 **分析方法预览**：针对可行的分析方法，分别说明：
   - 用方法A会研究什么效应，预期会看到什么样的结果
   - 用方法B会研究什么效应，与A有何不同
   - 如果有交互作用怎么看，没有交互怎么看
3. 💡 **建议**：根据当前数据特征，给出首选方案

注意：你是给出"预期会看到什么"，不是真的跑分析。"""

    user = f"""数据规模: {n_rows} 行
变量角色:
- 组间因素: {between if between else '(无)'}
- 因变量: {dependent if dependent else '(无)'}
- 组内/重复: {within if within else '(无)'}
- 时间: {time_col if time_col else '(无)'}
- 标签: {label_cols if label_cols else '(无)'}
列详情:
{chr(10).join(col_summary)}"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def formal_report_prompt(result_json: str, lang: str = "zh") -> list[dict]:
    """生成正式规范化统计报告（APA/GB 格式）的 Prompt。"""
    system_zh = """你是一位量化研究学术编辑。基于统计结果 JSON，生成完整规范化报告。

## 摘要
1-2 句话概括研究目的和主要发现。

## 研究设计
实验设计类型、因素水平、因变量、样本量。

## 统计方法
分析方法及选择理由，前提假设检验结果。

## 结果
按规范报告所有统计量：
- 先报告交互效应
- 交互显著优先报告简单效应
- 交互不显著分别报告主效应
- 事后多重比较
- 效应量(p值+η²p)
- p>0.05用"无统计学意义"

## 结论与局限

严格使用JSON数值，不编造。禁止因果表述。"""

    system = system_zh if lang == "zh" else system_zh

    user = f"结果 JSON:\n\n```json\n{result_json}\n```"

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
