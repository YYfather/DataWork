"""报告生成 — 基于统一结果 JSON + Jinja2 模板。"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json

from jinja2 import Environment, PackageLoader, select_autoescape

from ..engine.result import StatisticalResult
from ..engine.batch import BatchAnalysisResult


# ─── Jinja2 环境 ───

_env = Environment(
    loader=PackageLoader("datawork.report", "templates"),
    autoescape=select_autoescape(),
)


def _format_p(p: float | None) -> str:
    """格式化 p 值。"""
    if p is None:
        return "N/A"
    if p < 0.001:
        return "< 0.001"
    return f"{p:.3f}"


def _format_f(f: float) -> str:
    return f"{f:.2f}"


_env.filters["format_p"] = _format_p
_env.filters["format_f"] = _format_f


# ─── 主入口 ───

def generate_report(
    result: StatisticalResult,
    output_dir: str | Path,
    title: str = "统计分析报告",
    lang: str = "zh",
) -> Path:
    """
    将 StatisticalResult 渲染为 Markdown 报告，并导出辅助文件。

    Returns:
        生成的 MD 文件路径。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 选择模板
    template_name = f"report_{lang}.md.j2"
    template = _env.get_template(template_name)

    # 先渲染结构化诊断图，Markdown 再引用相对路径。
    plot_files = _render_diagnostic_plots(result, output_dir / "plots")
    md_content = template.render(
        result=result,
        plot_files=plot_files,
        title=title,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    # 写入 MD
    md_path = output_dir / "statistical_report.md"
    md_path.write_text(md_content, encoding="utf-8")

    # 保存 canonical JSON
    json_path = output_dir / "canonical_result.json"
    json_path.write_text(
        result.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # 保存结果表为 Excel
    _export_excel(result, output_dir / "results.xlsx")

    # 保存可复现信息
    _save_reproducibility(result, output_dir)

    return md_path


def generate_batch_report(
    result: BatchAnalysisResult,
    output_dir: str | Path,
    title: str = "规范化批量分析报告",
    lang: str = "zh",
) -> Path:
    """将批量结果聚合为与单次报告同名、同入口的标准报告包。"""
    if lang != "zh":
        raise ValueError("批量标准报告当前仅支持中文")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    overview = _frame_records(result.overview_df)
    summary = _frame_records(result.summary_df)
    tasks = []
    for index, item in enumerate(result.results, start=1):
        tasks.append({
            "task_id": item.subset_info.get("task_id", index),
            "subset_key": item.subset_key,
            "subset_info": item.subset_info,
            "n_rows": item.n_rows,
            "status": "failed" if item.error else "completed",
            "error": item.error,
            "records": item.records,
            "result": item.result.model_dump(mode="json") if item.result is not None else None,
        })
    canonical = {
        "schema_version": "datawork.standard-report.v1",
        "kind": "batch",
        "method": result.method,
        "dependent_variables": [item.strip() for item in result.dv_col.split(",") if item.strip()],
        "fixed_factors": result.factor_cols,
        "dimensions": result.split_cols,
        "settings": result.settings,
        "overview": overview,
        "summary": summary,
        "tasks": tasks,
    }
    (output_dir / "canonical_result.json").write_text(
        json.dumps(canonical, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 复用统一批量工作簿组件，文件名与单次报告包保持一致。
    from datawork.application.batch_export_service import GenericBatchExportService
    GenericBatchExportService().export_xlsx(result, output_dir / "results.xlsx")

    completed = sum(not item.error for item in result.results)
    failed = len(result.results) - completed
    adjustment_method = str(
        result.settings.get("cross_model_p_adjust")
        or result.settings.get("combination_p_adjust")
        or "holm"
    )
    significant = len({
        row.get("task_id") for row in overview
        if (
            row.get("significant") is True
            if adjustment_method == "none"
            else row.get("significant_adjusted") is True
        )
    })
    significance_summary_label = (
        "按原始 p 判断显著任务" if adjustment_method == "none"
        else "跨任务校正后显著任务"
    )
    lines = [
        f"# {title}", "", f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "",
        "## 一、研究设计", "",
        f"- **分析方法**：{result.method}",
        f"- **因变量**：{result.dv_col or '—'}",
        f"- **分类因素候选池**：{'、'.join(result.factor_cols) or '—'}",
        f"- **批量维度**：{'、'.join(result.split_cols) or '—'}", "",
        "## 二、规范化结果摘要", "",
        f"- 全部任务：{len(result.results)}",
        f"- 成功任务：{completed}",
        f"- 失败任务：{failed}",
        f"- 跨模型判断方法：{'不校正' if adjustment_method == 'none' else adjustment_method}",
        f"- {significance_summary_label}：{significant}", "",
        "## 三、核心推断结果", "",
    ]
    columns = [
        "task_id", "dependent_combination", "dependent_columns",
        "dependent_combination_size", "dependent_group", "dependent_variables",
        "factor_combination", "factor_columns", "combination_order", "dependent_variable",
        "effect", "statistic_name", "statistic_value", "p_value",
        "raw_conclusion",
        *([] if adjustment_method == "none" else ["p_adjusted_across_tasks", "conclusion"]),
        "status", "error",
    ]
    present = [column for column in columns if any(column in row for row in overview)]
    if overview and present:
        lines.extend([
            "| " + " | ".join(present) + " |",
            "| " + " | ".join("---" for _ in present) + " |",
        ])
        for row in overview:
            lines.append("| " + " | ".join(_markdown_value(row.get(column)) for column in present) + " |")
    else:
        lines.append("暂无可展示的核心推断结果。")
    lines.extend(["", "## 四、失败、警告与中间态", ""])
    issues = []
    for item in result.results:
        if item.error:
            issues.append(f"- {item.subset_key}：执行失败；{item.error}")
        elif item.result is not None:
            issues.extend(f"- {item.subset_key}：{warning}" for warning in item.result.warnings)
    lines.extend(issues or ["所有任务均未记录失败或警告。"])
    correction_boundary = (
        "- 本次未执行跨任务校正；报告只使用原始 p 与原始显著性，不生成‘校正后’结论。"
        if adjustment_method == "none"
        else "- 正式跨任务结论使用校正后的 p 值；原始显著性同时保留，用于识别校正前后变化。"
    )
    lines.extend([
        "", "## 五、解释边界", "",
        correction_boundary,
        "- 批量任务共享字段定义；单个任务的完整过程数据保存在 canonical_result.json 与 results.xlsx 中。",
        "- 统计显著性不等于实际重要性，应结合效应大小、区间估计和研究设计解释。",
        "", "## 六、可复现信息", "",
        "- 完整规范结果：`canonical_result.json`",
        "- 标准化工作簿：`results.xlsx`",
        "- 分析设置保存在规范结果与工作簿的“分析设置”页。", "",
    ])
    md_path = output_dir / "statistical_report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def _frame_records(frame) -> list[dict]:
    if frame is None:
        return []
    return frame.where(frame.notna(), None).to_dict(orient="records")


def _markdown_value(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _export_excel(result: StatisticalResult, path: Path) -> None:
    """导出结果到 Excel。"""
    import pandas as pd

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        # 描述统计
        if result.descriptive_stats:
            pd.DataFrame(result.descriptive_stats).to_excel(
                writer, sheet_name="描述统计", index=False)

        # 通用主要检验
        if result.primary_tests:
            rows = []
            for test in result.primary_tests:
                rows.append({
                    "效应/关系": test.effect,
                    "统计量名称": test.statistic_name,
                    "统计量": test.statistic_value,
                    "df1": test.df_num,
                    "df2": test.df_den,
                    "p": test.p_value,
                    "效应量名称": test.effect_size_name,
                    "效应量": test.effect_size_value,
                    "CI下限": test.ci_lower,
                    "CI上限": test.ci_upper,
                    "显著": "未检验" if test.is_significant is None else ("是" if test.is_significant else "否"),
                    "说明": test.detail,
                })
            pd.DataFrame(rows).to_excel(writer, sheet_name="主要检验", index=False)

        # 总体检验
        if result.omnibus_tests:
            rows = []
            for ot in result.omnibus_tests:
                rows.append({
                    "效应": ot.effect,
                    "多元统计量": ot.statistic_name or "",
                    "统计量值": ot.statistic_value,
                    "F/近似F": ot.f_value,
                    "分子df": ot.df_num,
                    "分母df": ot.df_den,
                    "p": ot.p_value,
                    "η²p": None if ot.statistic_name else ot.eta_sq_p,
                    "ω²": None if ot.statistic_name else ot.omega_sq,
                    "显著": "是" if ot.is_significant else "否",
                    "校正结果": "; ".join(
                        f"{item.correction}: df=({item.df_num:.4g},{item.df_den:.4g}), p={item.p_value:.6g}"
                        for item in ot.adjustments
                    ),
                })
            pd.DataFrame(rows).to_excel(writer, sheet_name="总体检验", index=False)

        # MANOVA 单变量跟进
        if result.follow_up_tests:
            pd.DataFrame([item.model_dump() for item in result.follow_up_tests]).rename(columns={
                "outcome": "因变量", "effect": "效应", "ss_type": "平方和类型",
                "df_num": "分子df", "df_den": "分母df", "f_value": "F",
                "p_value": "原始p", "p_adjusted": "校正p", "eta_sq_p": "偏η²",
                "significant": "显著", "correction": "校正方法", "interpretation": "解释",
            }).to_excel(writer, sheet_name="MANOVA单变量跟进", index=False)

        # 模型系数
        if result.coefficients:
            rows = []
            for coef in result.coefficients:
                rows.append({
                    "项": coef.term,
                    "估计值": coef.estimate,
                    "标准误": coef.se,
                    "统计量名称": coef.statistic_name,
                    "统计量": coef.statistic_value,
                    "p": coef.p_value,
                    "CI下限": coef.ci_lower,
                    "CI上限": coef.ci_upper,
                    "变换指标": coef.transformed_name,
                    "变换值": coef.transformed_value,
                    "显著": "是" if coef.significant else "否",
                })
            pd.DataFrame(rows).to_excel(writer, sheet_name="模型系数", index=False)

        # 拟合统计
        if result.fit_statistics:
            pd.DataFrame([item.model_dump() for item in result.fit_statistics]).to_excel(
                writer, sheet_name="拟合统计", index=False
            )

        # 事后比较
        if result.contrasts:
            rows = []
            for ct in result.contrasts:
                rows.append({
                    "比较": ct.contrast,
                    "均值差": ct.estimate,
                    "SE": ct.se,
                    "统计量名称": ct.statistic_name,
                    "统计量": ct.t_value,
                    "p(原始)": ct.p_value,
                    "p(校正)": ct.p_adjusted,
                    "CI下限": ct.ci_lower,
                    "CI上限": ct.ci_upper,
                    "自由度": ct.df,
                    "显著": "是" if ct.significant else "否",
                    "校正方法": ct.correction,
                })
            pd.DataFrame(rows).to_excel(writer, sheet_name="事后比较", index=False)

        # 显著性字母分组（Compact Letter Display）
        if result.significance_letters:
            rows = []
            for item in result.significance_letters:
                rows.append({
                    "因变量": item.outcome,
                    "因素": item.factor,
                    "条件": item.context,
                    "事后方法": item.method,
                    "水平": item.group,
                    "均值或EMM": item.mean,
                    "显著性字母": item.letters,
                    "因素水平": "; ".join(f"{key}={value}" for key, value in item.levels.items()),
                })
            pd.DataFrame(rows).to_excel(writer, sheet_name="显著性字母分组", index=False)

        # 估计边际均值
        if result.estimated_marginal_means:
            pd.DataFrame([item.model_dump() for item in result.estimated_marginal_means]).to_excel(
                writer, sheet_name="估计边际均值", index=False
            )

        # 球形性
        if result.sphericity:
            pd.DataFrame([result.sphericity.model_dump()]).to_excel(
                writer, sheet_name="球形性", index=False
            )

        # 简单效应
        if result.simple_effects:
            rows = []
            for se in result.simple_effects:
                rows.append({
                    "固定因素": se.fixed_factor,
                    "固定水平": se.fixed_level,
                    "效应": se.effect,
                    "F": se.f_value,
                    "df_num": se.df_num,
                    "df_den": se.df_den,
                    "p": se.p_value,
                    "校正后 p": se.p_adjusted,
                    "校正方法": se.correction,
                    "显著": "是" if se.is_significant else "否",
                })
            pd.DataFrame(rows).to_excel(writer, sheet_name="简单效应", index=False)

        # 效应量
        if result.effect_sizes:
            pd.DataFrame([es.model_dump() for es in result.effect_sizes]).to_excel(
                writer, sheet_name="效应量", index=False)

        # 诊断
        if result.diagnostics:
            rows = []
            for d in result.diagnostics:
                rows.append({
                    "检验": d.test_name,
                    "统计量": d.statistic,
                    "p": d.p_value,
                    "通过": "是" if d.passed else "否",
                    "说明": d.detail,
                })
            pd.DataFrame(rows).to_excel(writer, sheet_name="诊断", index=False)

        if result.diagnostic_plots:
            pd.DataFrame([
                {"图类型": item.kind, "标题": item.title, "X轴": item.x_label, "Y轴": item.y_label, "说明": "；".join(item.notes)}
                for item in result.diagnostic_plots
            ]).to_excel(writer, sheet_name="诊断图索引", index=False)


def _render_diagnostic_plots(result: StatisticalResult, directory: Path) -> list[dict[str, str]]:
    if not result.diagnostic_plots:
        return []
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    import numpy as np

    preferred_fonts = [
        "Noto Sans CJK SC", "Noto Sans CJK JP", "Microsoft YaHei", "PingFang SC", "SimHei",
        "WenQuanYi Micro Hei", "Arial Unicode MS", "DejaVu Sans",
    ]
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    selected_font = next((font for font in preferred_fonts if font in available_fonts), "DejaVu Sans")
    plt.rcParams["font.family"] = [selected_font]
    plt.rcParams["axes.unicode_minus"] = False

    directory.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, str]] = []
    for index, plot in enumerate(result.diagnostic_plots, start=1):
        fig, ax = plt.subplots(figsize=(7.2, 4.6))
        for series in plot.series:
            x_values = list(series.get("x", []))
            y_values = np.asarray(series.get("y", []), dtype=float)
            numeric_x = all(isinstance(value, (int, float, np.number)) for value in x_values)
            x_plot = np.asarray(x_values, dtype=float) if numeric_x else np.arange(len(x_values), dtype=float)
            label = str(series.get("name", ""))
            error = series.get("error")
            if plot.kind in {"line", "point"}:
                if error is not None:
                    ax.errorbar(x_plot, y_values, yerr=np.asarray(error, dtype=float), marker="o", label=label or None, capsize=3)
                elif plot.kind == "line":
                    ax.plot(x_plot, y_values, marker="o", label=label or None)
                else:
                    ax.scatter(x_plot, y_values, label=label or None)
            else:
                ax.scatter(x_plot, y_values, label=label or None, s=24)
            if not numeric_x:
                ax.set_xticks(x_plot)
                ax.set_xticklabels([str(value) for value in x_values], rotation=30, ha="right")
        for line in plot.reference_lines:
            axis = line.get("axis")
            if axis == "y":
                ax.axhline(float(line.get("value", 0.0)), linestyle="--")
            elif axis == "x":
                ax.axvline(float(line.get("value", 0.0)), linestyle="--")
            elif axis == "xy":
                xmin, xmax = ax.get_xlim()
                xs = np.asarray([xmin, xmax])
                ax.plot(xs, float(line.get("intercept", 0.0)) + float(line.get("slope", 1.0)) * xs, linestyle="--")
        ax.set_title(plot.title)
        ax.set_xlabel(plot.x_label)
        ax.set_ylabel(plot.y_label)
        if any(series.get("name") for series in plot.series):
            ax.legend()
        ax.grid(True, alpha=0.2)
        fig.tight_layout()
        filename = f"diagnostic_{index:02d}.png"
        path = directory / filename
        fig.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(fig)
        files.append({"title": plot.title, "path": f"plots/{filename}"})
    return files


def _save_reproducibility(result: StatisticalResult, output_dir: Path) -> None:
    """保存可复现信息，包含运行环境、数据指纹和完整分析参数。"""
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    reproducibility = result.provenance.get("reproducibility", {})
    analysis_plan = {
        "analysis_id": result.analysis_id,
        "method": result.method.model_dump(mode="json"),
        "design": result.design.model_dump(mode="json"),
        "parameters": reproducibility.get("parameters", {}),
        "plan_sha256": reproducibility.get("plan_sha256", ""),
    }
    (repro_dir / "analysis_plan.json").write_text(
        json.dumps(analysis_plan, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (repro_dir / "provenance.json").write_text(
        json.dumps(result.provenance, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    environment = reproducibility.get("environment", {})
    lines = [
        f"analysis_id={result.analysis_id}",
        f"python={environment.get('python_version', '')}",
        f"platform={environment.get('operating_system', '')} {environment.get('operating_system_release', '')}",
        f"machine={environment.get('machine', '')}",
    ]
    for package, package_version in sorted(environment.get("packages", {}).items()):
        lines.append(f"{package}={package_version}")
    (repro_dir / "environment.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
