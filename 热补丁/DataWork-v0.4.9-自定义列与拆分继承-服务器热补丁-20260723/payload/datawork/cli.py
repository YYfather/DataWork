"""CLI 交互式向导 — Typer + Rich 实现六步数据分析工作流 (含 AI)。"""

from __future__ import annotations

import sys
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm

from .io.reader import read_file, clean_dataframe, auto_clean_percentage
from .io.profiler import profile_dataframe, DataProfile
from .engine.result import StatisticalResult
from .ai.provider import create_provider, LLMProvider
from .ai.guard import guard_ai_output
from .design.infer import ai_enhance_roles
from .application.analysis_service import AnalysisService, ExecutionContext
from .application.dataset_service import DatasetService
from .application.batch_export_service import GenericBatchExportService
from .application.preflight_service import PreflightService
from .application.report_service import ReportService
from .core.plan import AnalysisPlan
from .core.method_registry import get_method, list_methods

app = typer.Typer(help="通用实验统计分析与报告 CLI")
console = Console()


# ─── 主命令 ───

@app.command()
def run(
    file: str = typer.Argument(..., help="数据文件路径 (.csv/.xlsx/.xls)"),
    sheet: Optional[str] = typer.Option(None, "--sheet", "-s", help="工作表名 (xlsx)"),
    output: str = typer.Option("output", "--output", "-o", help="报告输出目录"),
    no_ai: bool = typer.Option(False, "--no-ai", help="禁用 AI 辅助，使用纯规则引擎"),
):
    """
    交互式数据分析向导。

    六步流程: 数据画像 → 变量分组 → 研究目标 → 方法选择 → 执行分析 → 生成报告
    AI 辅助: 变量角色推断 / 方法推荐 / 报告增强
    """
    file_path = Path(file)
    if not file_path.exists():
        console.print(f"[red]❌ 文件不存在: {file}[/red]")
        raise typer.Exit(1)

    # AI 初始化
    ai: Optional[LLMProvider] = None
    if not no_ai:
        ai = create_provider()
        if ai:
            console.print(f"[dim]AI: {ai.config.kind.value} / {ai.config.model} 已就绪[/dim]")
        else:
            console.print("[dim]AI: 未检测到 API Key，使用纯规则引擎模式[/dim]")

    # ═══════════════ 步骤 1: 数据画像 ═══════════════
    _step_banner(1, "数据画像")
    dataset_service = DatasetService()
    loaded = dataset_service.load_path(file_path, sheet=sheet)
    if len(loaded.sheet_names) > 1 and sheet is None:
        console.print(f"[yellow][!] 检测到 {len(loaded.sheet_names)} 个工作表: {loaded.sheet_names}[/yellow]")
        chosen = Prompt.ask(
            "  选择工作表",
            choices=loaded.sheet_names,
            default=loaded.sheet_names[0],
        )
        loaded = dataset_service.load_path(file_path, sheet=chosen)

    df = loaded.frame
    sheet_name = loaded.selected_sheet
    pct_cols = loaded.profile.percent_columns_found
    profile = loaded.profile
    _print_profile(profile)

    # ═══════════════ 步骤 2: 变量分组 (AI 增强) ═══════════════
    _step_banner(2, "变量角色确认")

    # AI 复核角色
    if ai:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      console=console) as progress:
            task = progress.add_task("[cyan]AI 复核变量角色中...", total=None)
            try:
                ai_roles = asyncio.run(ai_enhance_roles(profile, ai))
                progress.update(task, description="[green]✓ AI 复核完成[/green]")
            except Exception as e:
                ai_roles = None
                progress.update(task, description=f"[yellow]AI 复核失败: {e}，使用规则推断[/yellow]")

        if ai_roles and ai_roles.notes:
            for note in ai_roles.notes:
                if "[规则引擎]" not in note:
                    console.print(f"  [dim cyan]AI: {note}[/dim cyan]")
    else:
        ai_roles = None

    _print_role_table(profile)

    if Confirm.ask("\n  [bold]确认以上变量角色?[/bold]", default=True):
        roles = {c.name: c.inferred_role for c in profile.columns}
    else:
        roles = _interactive_role_edit(profile)

    id_col = _find_first_role(profile, roles, "id")
    between_cols = _find_all_role(profile, roles, "between")
    within_cols = _find_all_role(profile, roles, "within")
    time_col = _find_first_role(profile, roles, "time")
    covariate_cols = _find_all_role(profile, roles, "covariate")
    dependent_cols = _find_all_role(profile, roles, "dependent")

    if not dependent_cols:
        numeric_cols = [c.name for c in profile.columns
                       if c.inferred_role == "dependent" or ("float" in c.dtype)]
        if numeric_cols:
            console.print("\n[yellow]⚠ 未明确标记因变量[/yellow]")
            chosen = Prompt.ask(
                "  请选择因变量 (逗号分隔多选)",
                default=", ".join(numeric_cols[:2]),
            )
            dependent_cols = [c.strip() for c in chosen.split(",") if c.strip() in df.columns]

    console.print(f"\n  [green]ID:[/green] {id_col or '(无)'}")
    console.print(f"  [green]组间因素:[/green] {between_cols or '(无)'}")
    time_str = time_col or "(无)"
    console.print(f"  [green]组内/时间:[/green] {within_cols or '(无, 时间: ' + time_str + ')'}")
    console.print(f"  [green]协变量:[/green] {covariate_cols or '(无)'}")
    console.print(f"  [green]因变量:[/green] {dependent_cols}")

    # ═══════════════ 步骤 3: 研究目标 ═══════════════
    _step_banner(3, "研究目标")

    goals = {
        "1": ("比较多个处理是否存在差异", "compare_groups"),
        "2": ("判断两个因素是否交互", "test_interaction"),
        "3": ("研究某个最终时间点的表现", "endpoint_only"),
        "4": ("控制基线后比较最终结果 (ANCOVA)", "control_baseline"),
        "5": ("比较不同处理的变化幅度", "change_amplitude"),
        "6": ("比较随时间的变化轨迹", "trajectory"),
        "7": ("分别考察不同时间节点", "cross_sectional_times"),
        "8": ("分析变量之间的关系", "correlation"),
        "9": ("分析多个相关指标 (MANOVA)", "multiple_dvs"),
        "C": ("自定义描述", "custom"),
    }

    goal_table = Table(title="研究目标选项")
    goal_table.add_column("序号", style="cyan")
    goal_table.add_column("目标")
    for k, (label, _) in goals.items():
        goal_table.add_row(f"[{k}]", label)
    console.print(goal_table)

    # AI 推荐目标
    if ai:
        design_summary = {
            "n_between_factors": len(between_cols),
            "n_within_factors": len(within_cols) + (1 if time_col else 0),
            "n_dependent_vars": len(dependent_cols),
            "has_covariate": len(covariate_cols) > 0,
            "has_repeated_measures": (time_col is not None or len(within_cols) > 0),
        }
        ai_hint = _ai_goal_hint(ai, design_summary)
        if ai_hint:
            console.print(f"\n  [dim cyan]AI 建议: {ai_hint}[/dim cyan]")

    goal_choice = Prompt.ask("  请选择", choices=list(goals.keys()), default="2")
    research_goal = goals[goal_choice][0]

    # ═══════════════ 步骤 4: 方法选择 (AI 增强) ═══════════════
    _step_banner(4, "分析方法")

    from .rules.decision_tree import recommend_methods, DesignSignature, ResearchGoal

    rg_key = goals[goal_choice][1]
    rg_enum = ResearchGoal(rg_key)

    sig = DesignSignature(
        n_between_factors=len(between_cols),
        n_within_factors=len(within_cols) + (1 if time_col else 0),
        n_dependent_vars=len(dependent_cols),
        has_covariate=len(covariate_cols) > 0,
        has_repeated_measures=(time_col is not None or len(within_cols) > 0),
        has_time_variable=(time_col is not None),
        dv_is_continuous=True,
    )
    candidates = recommend_methods(sig, rg_enum)

    if not candidates:
        console.print("[red]❌ 未找到匹配的分析方法。[/red]")
        raise typer.Exit(1)

    # AI 在候选方法中排序和解释
    if ai:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      console=console) as progress:
            task = progress.add_task("[cyan]AI 分析推荐方案中...", total=None)
            try:
                ai_rec = _ai_method_rank(ai, design_summary, research_goal, candidates)
                if ai_rec:
                    progress.update(task, description="[green]✓ AI 推荐完成[/green]")
                    console.print(f"\n  [bold cyan]AI 首选推荐: {ai_rec}[/bold cyan]")
                else:
                    progress.update(task, description="[dim]AI 推荐: 使用规则引擎[/dim]")
            except Exception:
                progress.update(task, description="[dim]AI 推荐超时，使用规则引擎[/dim]")

    method_table = Table(title=f"[AI] 推荐分析方法 (共 {len(candidates)} 个候选)")
    method_table.add_column("排名", style="cyan")
    method_table.add_column("方法")
    method_table.add_column("置信度")
    method_table.add_column("理由")
    for i, c in enumerate(candidates[:5], 1):
        icon = "★" if i == 1 else "  "
        method_table.add_row(
            f"{icon} [{i}]", c.label_zh,
            f"{c.confidence:.0%}",
            c.reasoning[0] if c.reasoning else "",
        )
    console.print(method_table)

    runnable = list_methods(runnable_only=True)
    usable = {}
    for spec in runnable:
        ndv = len(dependent_cols)
        nff = len(between_cols)
        ncov = len(covariate_cols)
        dv_ok = ndv >= spec.min_dependent_vars
        factor_ok = nff >= spec.min_fixed_factors
        covariate_ok = ncov >= spec.min_covariates
        repeated_ok = (not spec.requires_subject_id or bool(id_col)) and (not spec.requires_repeated_factor or bool(time_col))
        # 交互式旧向导目前没有单独的随机因素角色编辑器；避免把 ID 私自当作随机因素。
        random_ok = spec.min_random_factors == 0
        if dv_ok and factor_ok and covariate_ok and repeated_ok and random_ok:
            usable[spec.name] = spec

    if not usable:
        console.print("[red]当前变量角色无法构造任何已实现的分析计划。请返回并调整变量角色。[/red]")
        raise typer.Exit(1)

    method_table2 = Table(title="可执行方法（未实现方法不会进入此表）")
    method_table2.add_column("代码", style="cyan")
    method_table2.add_column("方法")
    method_table2.add_column("状态")
    method_table2.add_column("通常用途")
    method_table2.add_column("变量作用关系")
    for name, spec in usable.items():
        method_table2.add_row(name, spec.label_zh, spec.status.value, spec.purpose, spec.variable_relationship)
    console.print(method_table2)

    recommended_default = next(
        (candidate.method_name for candidate in candidates if candidate.method_name in usable),
        next(iter(usable)),
    )
    chosen_method = Prompt.ask(
        "  请选择分析方法",
        choices=list(usable),
        default=recommended_default,
    )

    # ═══════════════ 步骤 5: 执行分析 ═══════════════
    _step_banner(5, "执行分析")
    result: Optional[StatisticalResult] = None

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as progress:
        task = progress.add_task("[cyan]分析中...", total=None)
        try:
            spec = get_method(chosen_method)
            if spec.dependent_mode == "none":
                selected_dvs = []
            elif spec.dependent_mode == "joint":
                selected_dvs = dependent_cols[: spec.max_dependent_vars or len(dependent_cols)]
            else:
                # 交互式 CLI 一次执行一个结果变量；多变量批量请使用 datawork batch。
                selected_dvs = dependent_cols[:1]

            if spec.max_fixed_factors == 0:
                selected_factors = []
            elif spec.max_fixed_factors is None:
                selected_factors = between_cols
            else:
                selected_factors = between_cols[:spec.max_fixed_factors]

            if spec.max_covariates == 0:
                selected_covariates = []
            elif spec.max_covariates is None:
                selected_covariates = covariate_cols
            else:
                selected_covariates = covariate_cols[:spec.max_covariates]

            plan = AnalysisPlan(
                dependent_variables=selected_dvs,
                fixed_factors=selected_factors,
                covariates=selected_covariates,
                subject_id=id_col if spec.requires_subject_id else None,
                repeated_factor=time_col if spec.requires_repeated_factor else None,
                method=chosen_method,
                ss_type=3,
                research_goal=rg_key,
            )
            analysis = AnalysisService().execute(
                df,
                plan,
                context=ExecutionContext(
                    dataset_fingerprint=loaded.fingerprint,
                    source_filename=loaded.source_filename,
                    sheet_name=loaded.selected_sheet,
                    cleaning_log=loaded.cleaning_payload(),
                ),
            ).result
            if not isinstance(analysis, StatisticalResult):
                raise RuntimeError("CLI 当前仅执行单次分析，不应返回批量结果")
            result = analysis
        except Exception as e:
            progress.stop()
            console.print(f"[red]❌ 分析未执行: {e}[/red]")
            raise typer.Exit(1)

        progress.update(task, description="[green]✓ 分析完成[/green]")

    _print_result_summary(result)

    # ═══════════════ 步骤 6: 报告生成 (AI 增强) ═══════════════
    _step_banner(6, "生成报告")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(output) / f"analysis_{ts}"

    # 先保存基础报告和 JSON
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as progress:
        task = progress.add_task("[cyan]生成报告中...", total=None)
        bundle = ReportService().generate(result, out_dir,
                                          title=f"统计分析报告 — {file_path.stem}")
        report_path = out_dir / "statistical_report.md"
        progress.update(task, description="[green]✓ 报告完成[/green]")

    # AI 增强报告
    ai_report_path = None
    if ai:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      console=console) as progress:
            task = progress.add_task("[cyan]AI 生成报告摘要中...", total=None)
            try:
                ai_report_path = asyncio.run(_ai_enhance_report(
                    ai, result, out_dir, file_path.stem
                ))
                if ai_report_path:
                    progress.update(task, description="[green]✓ AI 报告摘要完成[/green]")
                else:
                    progress.update(task, description="[dim]AI 报告跳过[/dim]")
            except Exception as e:
                progress.update(task, description=f"[yellow]AI 报告失败: {e}[/yellow]")

    # 输出汇总
    files_info = (
        f"[report] 报告: {report_path}\n"
        f"[data] 数据: {out_dir / 'results.xlsx'}\n"
        f"[json] JSON: {out_dir / 'canonical_result.json'}"
    )
    if ai_report_path:
        files_info += f"\n[ai] AI 摘要: {ai_report_path}"

    console.print(Panel.fit(
        f"[bold green]✅ 分析完成！[/bold green]\n\n{files_info}",
        title="输出文件",
    ))

    # 清理
    if ai:
        asyncio.run(ai.close())


# ─── Helper Commands ───

@app.command()
def profile(
    file: str = typer.Argument(..., help="数据文件"),
    sheet: Optional[str] = typer.Option(None, "--sheet", "-s"),
    no_ai: bool = typer.Option(False, "--no-ai"),
):
    """仅跑数据画像（不执行分析）。"""
    file_path = Path(file)
    sheets = read_file(file_path, sheet_name=sheet)
    for sn, df in sheets.items():
        df = clean_dataframe(df)
        df, _ = auto_clean_percentage(df)
        p = profile_dataframe(df, file_path.name, sn)
        _print_profile(p)
        _print_role_table(p)


def _parse_cli_parameters(items: list[str] | None) -> dict[str, object]:
    """解析 --parameter key=value；类型最终由 AnalysisPlan 按方法元数据校验。"""
    parsed: dict[str, object] = {}
    for item in items or []:
        if "=" not in item:
            raise typer.BadParameter(f"高级参数必须使用 key=value 形式: {item}")
        key, raw = item.split("=", 1)
        key = key.strip()
        raw = raw.strip()
        if not key:
            raise typer.BadParameter("高级参数键不能为空")
        parsed[key] = raw
    return parsed


@app.command("batch")
def batch(
    file: str = typer.Argument(..., help="数据文件路径"),
    dependent: Optional[list[str]] = typer.Option(None, "--dependent", "--dv", help="因变量/分析变量列名，可重复"),
    factor: Optional[list[str]] = typer.Option(None, "--factor", "-f", help="分类固定因素或组合候选因素，可重复"),
    factor_combinations: bool = typer.Option(False, "--factor-combinations", help="将所选分类因素作为候选池，按组合阶数建立多个模型"),
    min_factor_order: Optional[int] = typer.Option(None, "--min-factor-order", help="因素组合最小阶数"),
    max_factor_order: Optional[int] = typer.Option(None, "--max-factor-order", help="因素组合最大阶数"),
    p_adjust: str = typer.Option("holm", "--p-adjust", help="跨组合校正: none/bonferroni/holm/fdr_bh"),
    parameter: Optional[list[str]] = typer.Option(None, "--parameter", "-P", help="方法高级参数 key=value，可重复"),
    covariate: Optional[list[str]] = typer.Option(None, "--covariate", "-c", help="连续预测量/协变量，可重复"),
    random_factor: Optional[list[str]] = typer.Option(None, "--random-factor", help="随机分组因素，可重复"),
    random_slope: Optional[list[str]] = typer.Option(None, "--random-slope", help="随机斜率列，可重复；须同时作为固定预测量或重复因素"),
    estimate_marginal_means: bool = typer.Option(False, "--emm/--no-emm", help="计算估计边际均值与对比"),
    emm_factor: Optional[list[str]] = typer.Option(None, "--emm-factor", help="EMM 目标分类因素，可重复"),
    contrast_correction: str = typer.Option("holm", "--contrast-correction", help="EMM/两两对比校正: none/bonferroni/holm/fdr_bh"),
    diagnostic_plots: bool = typer.Option(True, "--diagnostic-plots/--no-diagnostic-plots", help="生成结构化模型诊断图"),
    subject_id: Optional[str] = typer.Option(None, "--subject-id", help="受试者或样本 ID 列"),
    repeated_factor: Optional[str] = typer.Option(None, "--repeated-factor", help="重复/时间因素列"),
    split: Optional[list[str]] = typer.Option(None, "--split", help="批量拆分列名，可重复"),
    method: str = typer.Option("twoway_anova", "--method", "-m", help="注册表中的统计方法"),
    output: str = typer.Option("DataWork_合并批量结果.xlsx", "--output", "-o", help="输出 XLSX 路径"),
    sheet: Optional[str] = typer.Option(None, "--sheet", "-s", help="工作表名"),
    alpha: float = typer.Option(0.05, "--alpha", help="显著性水平"),
    ss_type: int = typer.Option(3, "--ss-type", help="平方和类型 1/2/3"),
    test_value: float = typer.Option(0.0, "--test-value", help="单样本 t 检验参考值"),
    expected_proportion: Optional[list[float]] = typer.Option(None, "--expected-proportion", help="卡方拟合优度的期望比例，可重复且总和为 1"),
    percentage_scale: str = typer.Option("percent_points", "--percentage-scale", help="percent_points 或 proportion"),
):
    """按用户指定列执行通用批量分析，并导出一个合并结果表。"""
    source = Path(file).expanduser().resolve()
    if not source.exists():
        console.print(f"[red]❌ 文件不存在: {source}[/red]")
        raise typer.Exit(1)

    plan_data = {
        "dependent_variables": dependent or [],
        "fixed_factors": factor or [],
        "covariates": covariate or [],
        "random_factors": random_factor or [],
        "random_slopes": random_slope or [],
        "estimate_marginal_means": estimate_marginal_means,
        "emm_factors": emm_factor or [],
        "contrast_correction": contrast_correction,
        "diagnostic_plots": diagnostic_plots,
        "subject_id": subject_id,
        "repeated_factor": repeated_factor,
        "split_by": split or [],
        "method": method,
        "alpha": alpha,
        "ss_type": ss_type,
        "test_value": test_value,
        "expected_proportions": expected_proportion or [],
        "method_parameters": _parse_cli_parameters(parameter),
        "factor_combinations_enabled": factor_combinations,
        "factor_combination_min_order": min_factor_order,
        "factor_combination_max_order": max_factor_order,
        "combination_p_adjust": p_adjust,
    }
    console.print(Panel.fit(
        "[bold]分析目的[/bold]：按用户选择的拆分列重复执行同一统计方法，不假设任何固定列名或业务语义。\n"
        "[bold]预期效果[/bold]：每个批次产生一行合并汇总；失败批次保留错误原因，最终导出单个 XLSX。",
        title="通用批量分析",
    ))
    try:
        loaded = DatasetService().load_path(source, sheet=sheet, percentage_scale=percentage_scale)
        preflight = PreflightService().inspect(loaded.frame, plan_data)
        for issue in preflight.issues:
            style = "red" if issue.severity.value == "error" else "yellow"
            console.print(f"[{style}]{issue.severity.value.upper()}: {issue.message}[/{style}]")
        if not preflight.ready:
            raise typer.Exit(1)

        plan = AnalysisPlan.model_validate(plan_data)
        execution = AnalysisService().execute(
            loaded.frame,
            plan,
            context=ExecutionContext(
                dataset_fingerprint=loaded.fingerprint,
                source_filename=loaded.source_filename,
                sheet_name=loaded.selected_sheet,
                cleaning_log=loaded.cleaning_payload(),
            ),
        )
        if not hasattr(execution.result, "summary_df"):
            console.print("[red]❌ 当前计划没有生成批量结果[/red]")
            raise typer.Exit(1)
        target = GenericBatchExportService().export_xlsx(execution.result, Path(output))
        console.print(Panel.fit(
            f"[bold green]✅ 批量分析完成[/bold green]\n"
            f"批次数: {len(execution.result.results)}\n输出: {target}",
            title="输出文件",
        ))
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]❌ 批量分析失败: {exc}[/red]")
        raise typer.Exit(1) from exc


# ─── AI 辅助函数 ───

def _ai_goal_hint(ai: LLMProvider, design_summary: dict) -> str:
    """AI 快速提示研究目标建议。"""
    # 简化：基于规则的快速建议
    hints = []
    if design_summary.get("has_repeated_measures"):
        hints.append("检测到重复测量结构，建议选择 [6] 轨迹 或 [7] 各时间点")
    if design_summary.get("has_covariate"):
        hints.append("检测到协变量，建议选择 [4] ANCOVA")
    if design_summary.get("n_between_factors", 0) >= 2:
        hints.append("有多因素设计，可关注 [2] 交互作用")
    return " | ".join(hints) if hints else ""


def _ai_method_rank(
    ai: LLMProvider,
    design_summary: dict,
    research_goal: str,
    candidates,
) -> Optional[str]:
    """AI 在候选方法中选择最佳方案（简化为同步推荐）。"""
    if not candidates:
        return None
    top = candidates[0]
    return f"{top.label_zh} (置信度 {top.confidence:.0%}) — {top.reasoning[0] if top.reasoning else ''}"


async def _ai_enhance_report(
    ai: LLMProvider,
    result: StatisticalResult,
    out_dir: Path,
    title: str,
) -> Optional[Path]:
    """AI 增强报告：基于结果 JSON 生成自然语言摘要。"""
    from .ai.prompts import report_generation_prompt

    result_json = result.model_dump_json(indent=2, ensure_ascii=False)

    # 截断过长的 JSON（控制 token 消耗）
    if len(result_json) > 8000:
        result_json = result_json[:8000] + '\n... (truncated)'

    messages = report_generation_prompt(result_json, style="apa", lang="zh")

    try:
        response = await ai.generate_text(messages, temperature=0.4, max_tokens=2000)
    except Exception:
        return None

    if response.error or not response.content:
        return None

    # Guard: 检查 AI 输出是否合规
    guard_result = guard_ai_output(
        response.content,
        result_json=result_json,
        method_type="",
        design_has_repeated_measures=bool(result.design.within_factors),
        research_goal=result.method.research_question,
    )

    ai_text = response.content
    if guard_result["violations"]:
        ai_text = (
            f"[Guard: 检测到 {len(guard_result['violations'])} 处违规，"
            f"以下为原始 AI 输出，请人工审核]\n\n{ai_text}"
        )

    # 保存 AI 报告
    ai_path = out_dir / "ai_report_summary.md"
    ai_path.write_text(
        f"# AI 生成报告摘要\n\n"
        f"> 模型: {ai.config.model} | Token: {response.usage}\n\n"
        f"{ai_text}\n\n"
        f"---\n"
        f"*此摘要由 AI 根据统计结果 JSON 自动生成。所有统计数值来自统计引擎。*",
        encoding="utf-8",
    )

    # 打印 AI 摘要
    console.print(Panel(
        ai_text[:1200] + ("..." if len(ai_text) > 1200 else ""),
        title="AI 报告摘要",
        border_style="blue",
    ))

    return ai_path


# ─── 内部辅助函数 ───

def _step_banner(n: int, title: str):
    console.print(f"\n{'─' * 55}")
    console.print(f"  [bold cyan]步骤 {n}/6: {title}[/bold cyan]")
    console.print(f"{'─' * 55}")


def _print_profile(profile: DataProfile):
    console.print(f"\n  [bold]文件:[/bold] {profile.file_name}  "
                  f"[bold]工作表:[/bold] {profile.sheet_name}  "
                  f"[bold]尺寸:[/bold] {profile.n_rows} 行 × {profile.n_cols} 列")
    console.print(f"  [bold]总缺失率:[/bold] {profile.total_missing_rate:.1%}  "
                  f"[bold]重复行:[/bold] {profile.n_duplicate_rows}")
    if profile.percent_columns_found:
        console.print(f"  [yellow]⚠ 含 '%' 列 (已自动转数值): {profile.percent_columns_found}[/yellow]")

    table = Table(title="列画像")
    for h in ["列名", "类型", "唯一值", "缺失率", "推断角色", "备注"]:
        table.add_column(h, style="cyan" if h == "列名" else "")
    for col in profile.columns:
        role_color = {
            "id": "yellow", "between": "green", "within": "blue",
            "covariate": "magenta", "dependent": "bold cyan", "time": "blue",
            "ignore": "dim",
        }.get(col.inferred_role, "white")
        table.add_row(col.name, col.dtype, str(col.n_unique),
                      f"{col.missing_rate:.1%}",
                      f"[{role_color}]{col.inferred_role}[/{role_color}]",
                      col.note or "")
    console.print(table)
    if profile.wide_to_long_hint:
        console.print(f"\n[yellow][wide] {profile.wide_to_long_hint}[/yellow]")


def _print_role_table(profile: DataProfile):
    role_order = ["id", "between", "within", "time", "covariate", "dependent", "ignore"]
    role_labels = {
        "id": "ID/实验单元", "between": "组间因素", "within": "组内/重复",
        "time": "时间变量", "covariate": "协变量",
        "dependent": "因变量 (DV)", "ignore": "建议忽略",
    }
    role_table = Table(title="[AI] AI 推断的变量角色")
    role_table.add_column("角色", style="cyan")
    role_table.add_column("列", style="green")
    role_table.add_column("置信度")
    for role in role_order:
        cols = [c for c in profile.columns if c.inferred_role == role]
        if cols:
            role_table.add_row(
                role_labels.get(role, role),
                ", ".join(c.name for c in cols),
                f"{(sum(c.role_confidence for c in cols) / len(cols)):.0%}",
            )
    console.print(role_table)


def _interactive_role_edit(profile: DataProfile) -> dict:
    roles = {}
    for c in profile.columns:
        valid = ["id", "between", "within", "time", "covariate", "dependent", "ignore"]
        choice = Prompt.ask(
            f"  列 '[cyan]{c.name}[/cyan]' ({c.dtype}, {c.n_unique} levels) → 角色",
            choices=valid, default=c.inferred_role,
        )
        roles[c.name] = choice
    return roles


def _find_first_role(profile, roles, role):
    for c in profile.columns:
        if roles.get(c.name) == role:
            return c.name
    return None


def _find_all_role(profile, roles, role):
    return [c.name for c in profile.columns if roles.get(c.name) == role]


def _print_result_summary(result: StatisticalResult):
    console.print("\n[bold][result] 结果摘要:[/bold]\n")
    if result.omnibus_tests:
        table = Table(title="总体检验")
        for h in ["效应", "F", "p", "η²p", "显著"]:
            table.add_column(h)
        for ot in result.omnibus_tests:
            sig = "[bold green]✓[/bold green]" if ot.is_significant else ""
            table.add_row(ot.effect, f"{ot.f_value:.2f}", _fmt_p_short(ot.p_value),
                          f"{ot.eta_sq_p:.4f}", sig)
        console.print(table)
    if result.contrasts:
        console.print(f"\n[bold]事后比较 ({result.contrasts[0].correction}):[/bold]")
        for ct in result.contrasts[:10]:
            sig = "[bold green]*[/bold green]" if ct.significant else " "
            console.print(f"  {sig} {ct.contrast}: diff={ct.estimate:.4f}, p_adj={_fmt_p_short(ct.p_adjusted)}")
    if result.simple_effects:
        console.print(f"\n[bold]简单效应:[/bold]")
        for se in result.simple_effects:
            sig = "[bold green]*[/bold green]" if se.is_significant else " "
            console.print(f"  {sig} {se.effect}: F={se.f_value:.2f}, p={_fmt_p_short(se.p_value)}")
    if result.report_constraints:
        console.print(f"\n[bold yellow]⚠ 报告约束:[/bold yellow]")
        for rc in result.report_constraints:
            console.print(f"  {rc}")


def _fmt_p_short(p: float) -> str:
    if p < 0.001: return "<.001"
    elif p < 0.01: return f"{p:.3f}"
    elif p < 0.05: return f"{p:.3f}"
    else: return f"{p:.3f}"


def main():
    app()


if __name__ == "__main__":
    app()
