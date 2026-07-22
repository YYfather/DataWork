"""Streamlit 图形界面 — 六步数据分析向导。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from datetime import datetime
import streamlit as st
import pandas as pd

from datawork.io.profiler import profile_dataframe

# 设置页面
st.set_page_config(
    page_title="DataWork — 实验统计分析平台",
    page_icon="📊",
    layout="wide",
)

# 导入引擎模块
from datawork.engine.ttest import independent_ttest
from datawork.engine.oneway_anova import oneway_anova
from datawork.engine.twoway_anova import twoway_anova, threeway_anova
from datawork.engine.result import StatisticalResult
from datawork.rules.decision_tree import recommend_methods, DesignSignature, ResearchGoal
from datawork.rules.constraints import get_hard_rules
from datawork.ai.provider import create_provider, is_ai_available
from datawork.application.analysis_service import AnalysisService
from datawork.application.dataset_service import DatasetService
from datawork.application.report_service import ReportService
from datawork.core.plan import AnalysisPlan
from datawork.core.method_registry import get_method, list_methods

# ─── 会话状态初始化 ───

if "step" not in st.session_state:
    st.session_state.step = 1
if "df" not in st.session_state:
    st.session_state.df = None
if "profile" not in st.session_state:
    st.session_state.profile = None
if "variable_roles" not in st.session_state:
    st.session_state.variable_roles = {}
if "research_goal" not in st.session_state:
    st.session_state.research_goal = None
if "chosen_method" not in st.session_state:
    st.session_state.chosen_method = None
if "result" not in st.session_state:
    st.session_state.result = None
if "batch_result" not in st.session_state:
    st.session_state.batch_result = None
if "factor_cols" not in st.session_state:
    st.session_state.factor_cols = []
if "report_dir" not in st.session_state:
    st.session_state.report_dir = None
if "ai_available" not in st.session_state:
    st.session_state.ai_available = is_ai_available()


# ─── 侧边栏进度 ───

with st.sidebar:
    st.title("📊 DataWork")
    st.caption("通用实验统计分析平台")

    step_names = ["上传数据", "变量角色", "AI分析预览", "分析方法", "执行分析", "查看报告"]
    for i, name in enumerate(step_names, 1):
        icon = "✅" if i < st.session_state.step else ("▶️" if i == st.session_state.step else "⬜")
        st.write(f"{icon} 步骤 {i}: {name}")

    st.divider()
    st.caption(f"AI: {'已就绪 (DeepSeek)' if st.session_state.ai_available else '未配置'}")
    st.caption(f"规则: {len(get_hard_rules())} 条固化规则")


# ─── 步骤 1: 上传数据 ───

if st.session_state.step == 1:
    st.header("步骤 1: 上传数据")
    st.markdown("支持 CSV / Excel (.xlsx/.xls) 文件，自动检测多工作表。")

    uploaded = st.file_uploader(
        "拖拽或选择数据文件",
        type=["csv", "xlsx", "xls"],
        help="支持 CSV、Excel 文件",
    )

    if uploaded is not None:
        try:
            dataset_service = DatasetService()
            initial = dataset_service.load_bytes(uploaded.getvalue(), uploaded.name)
            if len(initial.sheet_names) > 1:
                sheet_name = st.selectbox("选择工作表", initial.sheet_names)
                loaded = dataset_service.load_bytes(
                    uploaded.getvalue(), uploaded.name, sheet=sheet_name
                )
            else:
                loaded = initial
                sheet_name = loaded.selected_sheet

            df = loaded.frame
            pct_cols = loaded.profile.percent_columns_found
            st.session_state.df = df
            st.session_state.profile = loaded.profile
            st.session_state.dataset_fingerprint = loaded.fingerprint.model_dump(mode="json")
            st.session_state.cleaning_log = loaded.cleaning_payload()

            # 显示画像
            profile = st.session_state.profile
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("行数", profile.n_rows)
            c2.metric("列数", profile.n_cols)
            c3.metric("缺失率", f"{profile.total_missing_rate:.1%}")
            c4.metric("重复行", profile.n_duplicate_rows)

            if profile.percent_columns_found:
                st.warning(f"含 '%' 列已自动转为数值: {profile.percent_columns_found}")

            # 列画像表
            st.subheader("列画像")
            rows = []
            for col in profile.columns:
                rows.append({
                    "列名": col.name,
                    "类型": col.dtype,
                    "唯一值": col.n_unique,
                    "缺失率": f"{col.missing_rate:.1%}",
                    "推断角色": col.inferred_role,
                    "备注": col.note or "",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            if profile.wide_to_long_hint:
                st.info(profile.wide_to_long_hint)

            st.success("数据读取完成！点击下方进入下一步。")
            if st.button("下一步 → 变量角色", type="primary", use_container_width=True):
                st.session_state.step = 2
                st.rerun()

        except Exception as e:
            st.error(f"读取文件出错: {e}")


# ─── 步骤 2: 变量角色 ───

elif st.session_state.step == 2:
    st.header("步骤 2: 确认变量角色")
    st.markdown("修改每个列的分析角色。**标签列**可用于分组/筛选。默认不会自动填充疑似合并单元格，以免覆盖真实缺失值。")

    profile = st.session_state.profile
    df = st.session_state.df

    # 合并单元格提示
    label_candidates = [c for c in profile.columns if c.inferred_role == "label"]
    if label_candidates:
        st.info(f"🔖 检测到 {len(label_candidates)} 个可能的标签列: {', '.join(c.name for c in label_candidates)}。"
                f"标签列不含因素关键词但中等基数，可用于分组观察。")

    roles = {}
    cols = st.columns(2)
    for i, col in enumerate(profile.columns):
        c = cols[i % 2]
        with c:
            options = ["between", "label", "dependent", "within", "time", "covariate", "id", "ignore"]
            labels = {
                "between": "组间因素", "label": "标签/分组",
                "dependent": "因变量 (DV)",
                "within": "组内/重复", "time": "时间变量",
                "covariate": "协变量", "id": "ID", "ignore": "忽略",
            }
            default_role = col.inferred_role
            if default_role not in options:
                default_role = "ignore"
            choice = st.selectbox(
                f"{col.name} ({col.dtype}, {col.n_unique} levels)",
                options=options,
                index=options.index(default_role),
                format_func=lambda x, l=labels: l.get(x, x),
                key=f"role_{col.name}",
            )
            roles[col.name] = choice

    st.session_state.variable_roles = roles

    # 汇总
    st.divider()
    st.subheader("角色汇总")
    summary = {}
    for name, role in roles.items():
        summary.setdefault(role, []).append(name)
    for role, cols_list in summary.items():
        label = {
            "between": "组间因素", "label": "标签/分组", "dependent": "因变量",
            "within": "组内", "time": "时间", "covariate": "协变量",
            "id": "ID", "ignore": "忽略",
        }.get(role, role)
        st.write(f"**{label}**: {', '.join(cols_list)}")

    # 衍生变量
    st.divider()
    st.subheader("🧮 衍生变量 (可选)")
    st.caption("定义从现有列计算的新变量，如: (7d脱叶率 + 14d脱叶率) / 2")
    
    if "derived_vars" not in st.session_state:
        st.session_state.derived_vars = []
    
    c1, c2, c3 = st.columns([3, 3, 1])
    with c1:
        new_name = st.text_input("新变量名", key="dv_name", placeholder="如: 平均脱叶率")
    with c2:
        formula = st.text_input("公式", key="dv_formula", placeholder="如: (7d脱叶率 + 14d脱叶率 + 21d脱叶率) / 3")
    with c3:
        if st.button("添加", key="dv_add") and new_name and formula:
            try:
                from datawork.engine.batch import derive_variable
                df = st.session_state.df
                df = derive_variable(df, new_name, formula)
                st.session_state.df = df
                st.session_state.profile = profile_dataframe(df, "data.csv", "sheet")
                if "derived_vars" not in st.session_state:
                    st.session_state.derived_vars = []
                st.session_state.derived_vars.append({"name": new_name, "formula": formula})
                st.success(f"已添加: {new_name} = {formula}")
                st.rerun()
            except Exception as e:
                st.error(f"公式错误: {e}")
    
    if st.session_state.derived_vars:
        st.write("已定义的衍生变量:")
        for dv in st.session_state.derived_vars:
            st.caption(f"  • {dv['name']} = {dv['formula']}")

    # AI 解释按钮
    if st.session_state.ai_available:
        st.divider()
        if st.button("🤖 AI 解释这个分组方案", use_container_width=True):
            with st.spinner("AI 分析中..."):
                async def _explain_roles():
                    from datawork.ai.prompts import role_explanation_prompt
                    p = create_provider()
                    cols_info = [{
                        "name": c.name, "dtype": c.dtype, "n_unique": c.n_unique,
                        "sample": c.unique_values[:3],
                    } for c in profile.columns]
                    msgs = role_explanation_prompt(roles, cols_info, profile.n_rows)
                    resp = await p.generate_text(msgs, temperature=0.5, max_tokens=500)
                    await p.close()
                    return resp

                resp = asyncio.run(_explain_roles())
                if resp.content:
                    st.info(resp.content)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← 返回上一步"):
            st.session_state.step = 1
            st.rerun()
    with c2:
        if st.button("下一步 → AI 分析预览", type="primary", use_container_width=True):
            st.session_state.step = 3
            st.rerun()


# ─── 步骤 3: AI 分析预览 ───

elif st.session_state.step == 3:
    st.header("步骤 3: AI 分析预览")
    st.markdown("AI 根据当前变量角色分组，预览不同分析方法会研究什么效应、预期看到什么结果。")

    profile = st.session_state.profile
    roles = st.session_state.variable_roles

    # Auto-trigger AI preview
    if "ai_preview_done" not in st.session_state:
        st.session_state.ai_preview_done = False
        st.session_state.ai_preview_text = ""

    if st.session_state.ai_available:
        if st.button("🤖 AI 分析方案预览", type="primary", use_container_width=True):
            with st.spinner("AI 分析中..."):
                async def _preview():
                    from datawork.ai.prompts import analysis_preview_prompt
                    p = create_provider()
                    cols_info = [{
                        "name": c.name, "dtype": c.dtype, "n_unique": c.n_unique,
                    } for c in profile.columns]
                    msgs = analysis_preview_prompt(roles, cols_info, profile.n_rows)
                    resp = await p.generate_text(msgs, temperature=0.5, max_tokens=600)
                    await p.close()
                    return resp

                resp = asyncio.run(_preview())
                if resp.content:
                    st.session_state.ai_preview_text = resp.content
                    st.session_state.ai_preview_done = True
                    st.rerun()

        if st.session_state.ai_preview_done:
            st.success(st.session_state.ai_preview_text)
    else:
        st.info("AI 未配置，可直接进入下一步选择方法。")

    goal_options = {
        "compare_groups": "比较多个处理是否存在差异",
        "test_interaction": "判断两个或多个因素是否交互",
        "endpoint_only": "研究最终时间点表现",
        "control_baseline": "控制基线后比较最终结果（ANCOVA）",
        "change_amplitude": "比较变化幅度",
        "trajectory": "比较随时间的变化轨迹",
        "cross_sectional_times": "分别考察不同时间节点",
        "correlation": "分析变量之间的关系",
        "multiple_dvs": "联合分析多个相关指标（MANOVA）",
    }
    current_goal = st.session_state.research_goal or "test_interaction"
    selected_goal = st.selectbox(
        "研究目标",
        options=list(goal_options),
        format_func=lambda key: goal_options[key],
        index=list(goal_options).index(current_goal) if current_goal in goal_options else 1,
    )
    st.session_state.research_goal = selected_goal
    st.session_state.research_goal_label = goal_options[selected_goal]

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← 返回上一步"):
            st.session_state.ai_preview_done = False
            st.session_state.ai_preview_text = ""
            st.session_state.step = 2
            st.rerun()
    with c2:
        if st.button("下一步 → 选择分析方法", type="primary", use_container_width=True):
            st.session_state.ai_preview_done = False
            st.session_state.ai_preview_text = ""
            st.session_state.step = 4
            st.rerun()


# ─── 步骤 4: 分析方法 ───

elif st.session_state.step == 4:
    st.header("步骤 4: 建立分析计划")

    roles = st.session_state.variable_roles
    between_cols = [k for k, v in roles.items() if v == "between"]
    within_cols = [k for k, v in roles.items() if v == "within"]
    time_col = next((k for k, v in roles.items() if v == "time"), None)
    cov_cols = [k for k, v in roles.items() if v == "covariate"]
    dep_cols = [k for k, v in roles.items() if v == "dependent"]
    id_col = next((k for k, v in roles.items() if v == "id"), None)

    sig = DesignSignature(
        n_between_factors=len(between_cols),
        n_within_factors=len(within_cols) + (1 if time_col else 0),
        n_dependent_vars=len(dep_cols),
        has_covariate=bool(cov_cols),
        has_repeated_measures=bool(time_col or within_cols),
        has_time_variable=bool(time_col),
        dv_is_continuous=True,
    )
    candidates = recommend_methods(sig, ResearchGoal(st.session_state.research_goal))

    st.subheader("规则引擎建议")
    if candidates:
        for i, candidate in enumerate(candidates[:4]):
            try:
                status = get_method(candidate.method_name).status.value
            except ValueError:
                status = "unavailable"
            icon = "✅" if status in {"implemented", "experimental"} else "⛔"
            st.write(f"{icon} **{candidate.label_zh}** · {candidate.confidence:.0%} · {status}")
            if candidate.reasoning:
                st.caption(candidate.reasoning[0])
    else:
        st.warning("当前数据结构没有匹配的推荐方法。")

    runnable = {item.name: item for item in list_methods(runnable_only=True)}
    default_method = next(
        (candidate.method_name for candidate in candidates if candidate.method_name in runnable),
        "twoway_anova" if len(between_cols) >= 2 else "oneway_anova",
    )
    if default_method not in runnable:
        default_method = next(iter(runnable))

    chosen = st.selectbox(
        "统计方法",
        options=list(runnable),
        format_func=lambda name: (
            runnable[name].label_zh
            + ("（实验性）" if runnable[name].status.value == "experimental" else "")
        ),
        index=list(runnable).index(default_method),
    )
    spec = runnable[chosen]
    st.session_state.chosen_method = chosen
    if spec.notes:
        st.caption(spec.notes)

    if chosen in {"oneway_manova", "twoway_manova", "threeway_manova", "manova", "paired_ttest"}:
        selected_dvs = st.multiselect(
            "因变量",
            options=dep_cols or list(st.session_state.df.columns),
            default=(dep_cols or list(st.session_state.df.columns))[:spec.min_dependent_vars],
        )
    else:
        dv_options = dep_cols or list(st.session_state.df.select_dtypes(include="number").columns)
        selected_dvs = [st.selectbox("因变量", options=dv_options)] if dv_options else []
    st.session_state.dv_cols = selected_dvs
    st.session_state.dv_col = selected_dvs[0] if selected_dvs else None

    if spec.max_fixed_factors == 0:
        selected_factors = []
    else:
        selected_factors = st.multiselect(
            "固定因素",
            options=between_cols or list(st.session_state.df.columns),
            default=(between_cols or [])[:spec.min_fixed_factors],
            max_selections=spec.max_fixed_factors,
            help=f"该方法需要 {spec.min_fixed_factors}"
                 + (f"–{spec.max_fixed_factors}" if spec.max_fixed_factors != spec.min_fixed_factors else "")
                 + " 个固定因素。",
        )
    st.session_state.factor_cols = selected_factors

    ss_type = 3
    if chosen in {"twoway_anova", "threeway_anova"}:
        ss_type = st.selectbox(
            "平方和类型",
            options=[1, 2, 3],
            index=2,
            format_func=lambda value: f"Type {value}" + ("（Sum 对比编码）" if value == 3 else ""),
        )
    st.session_state.ss_type = ss_type
    st.info(
        f"计划：**{spec.label_zh}**；因变量：**{', '.join(selected_dvs) or '未选择'}**；"
        f"固定因素：**{' × '.join(selected_factors) or '无'}**"
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← 返回上一步"):
            st.session_state.step = 3
            st.rerun()
    with c2:
        if st.button("下一步 → 执行分析", type="primary", use_container_width=True):
            try:
                AnalysisPlan(
                    dependent_variables=selected_dvs,
                    fixed_factors=selected_factors,
                    covariates=cov_cols,
                    subject_id=id_col,
                    method=chosen,
                    ss_type=ss_type,
                    research_goal=st.session_state.research_goal,
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                st.session_state.step = 5
                st.rerun()


# ─── 步骤 5: 执行分析 ───

elif st.session_state.step == 5:
    st.header("步骤 5: 执行分析")

    df = st.session_state.df
    method = st.session_state.chosen_method
    factor_cols = list(st.session_state.factor_cols)
    dv_cols = list(st.session_state.get("dv_cols", []))
    roles = st.session_state.variable_roles
    cov_cols = [k for k, v in roles.items() if v == "covariate"]
    time_col = next((k for k, v in roles.items() if v == "time"), None)
    within_cols = [k for k, v in roles.items() if v == "within"]
    id_col = next((k for k, v in roles.items() if v == "id"), None)
    spec = get_method(method)

    st.subheader("分析模式")
    batch_mode = st.checkbox(
        "批量分析：按列拆分后分别分析",
        value=False,
        disabled=not spec.supports_batch,
    )
    all_split_candidates = [
        column for column, role in roles.items()
        if role in {"between", "label", "time"}
        and column not in factor_cols
        and column not in dv_cols
    ]
    split_cols = st.multiselect(
        "拆分列",
        options=all_split_candidates,
        disabled=not batch_mode,
        help="拆分列不会同时进入统计模型。",
    ) if batch_mode else []

    if st.button("🚀 开始分析", type="primary", use_container_width=True):
        st.session_state.result = None
        st.session_state.batch_result = None
        with st.spinner("分析中..."):
            try:
                plan = AnalysisPlan(
                    dependent_variables=dv_cols,
                    fixed_factors=factor_cols,
                    covariates=cov_cols,
                    subject_id=id_col,
                    repeated_factor=time_col or (within_cols[0] if within_cols else None),
                    split_by=split_cols,
                    method=method,
                    alpha=0.05,
                    ss_type=st.session_state.get("ss_type", 3),
                    research_goal=st.session_state.research_goal,
                )
                analysis = AnalysisService().run(df, plan)
                if isinstance(analysis, StatisticalResult):
                    st.session_state.result = analysis
                else:
                    st.session_state.batch_result = analysis
                st.success("分析完成。")
            except Exception as exc:
                st.error(f"分析未执行: {exc}")

    result = st.session_state.get("result")
    batch_result = st.session_state.get("batch_result")

    if result is not None:
        st.subheader("总体检验")
        rows = [
            {
                "效应": test.effect,
                "SS 类型": test.ss_type,
                "F": round(test.f_value, 4),
                "df₁": test.df_num,
                "df₂": round(test.df_den, 3),
                "p": test.p_value,
                "η²p": test.eta_sq_p,
                "显著": "✅" if test.is_significant else "",
            }
            for test in result.omnibus_tests
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        for warning in result.warnings:
            st.warning(warning)

    if batch_result is not None:
        st.subheader("批量分析汇总")
        if batch_result.summary_df is not None:
            st.dataframe(batch_result.summary_df, use_container_width=True)
        with st.expander("查看子集状态"):
            for item in batch_result.results:
                st.caption(
                    f"{'⚠️' if item.error else '✅'} {item.subset_key} · n={item.n_rows}"
                    + (f" · {item.error}" if item.error else "")
                )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← 返回上一步"):
            st.session_state.step = 4
            st.rerun()
    with c2:
        if result is not None or batch_result is not None:
            if st.button("下一步 → 查看报告", type="primary", use_container_width=True):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                if result is not None:
                    out_dir = Path("output") / f"analysis_{ts}"
                    ReportService().generate(result, out_dir, title="统计分析报告")
                else:
                    out_dir = Path("output") / f"batch_{ts}"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    if batch_result.summary_df is not None:
                        batch_result.summary_df.to_excel(out_dir / "batch_summary.xlsx", index=False)
                st.session_state.report_dir = out_dir
                st.session_state.step = 6
                st.rerun()


# ─── 步骤 6: 查看报告 ───

elif st.session_state.step == 6:
    st.header("步骤 6: 查看报告")

    out_dir = st.session_state.report_dir
    result = st.session_state.result
    batch_result = st.session_state.get("batch_result")

    if not (out_dir and out_dir.exists()):
        st.error("报告目录不存在，请返回上一步。")
    else:
        # Auto AI formal report
        if st.session_state.ai_available and "ai_formal_report" not in st.session_state:
            with st.spinner("🤖 AI 正在撰写规范化报告..."):
                async def _gen_formal():
                    from datawork.ai.prompts import formal_report_prompt
                    from datawork.ai.guard import guard_ai_output
                    p = create_provider()
                    rj = result.model_dump_json(indent=2, ensure_ascii=False)[:6000] if result else "{}"
                    msgs = formal_report_prompt(rj, lang="zh")
                    resp = await p.generate_text(msgs, temperature=0.3, max_tokens=1500)
                    g = guard_ai_output(resp.content, result_json=rj) if result else {"passed":True,"violations":[]}
                    await p.close()
                    return resp, g
                try:
                    resp, guard = asyncio.run(_gen_formal())
                    st.session_state.ai_formal_report = resp.content
                    st.session_state.ai_formal_guard = guard
                except Exception as e:
                    st.session_state.ai_formal_report = f"AI 报告生成失败: {e}"
                    st.session_state.ai_formal_guard = {"passed":True,"violations":[]}
            st.rerun()

        tab1, tab2, tab3 = st.tabs(["📝 AI 规范报告", "📊 统计报告", "📥 下载"])

        with tab1:
            if st.session_state.get("ai_formal_report"):
                guard = st.session_state.get("ai_formal_guard", {})
                st.caption(f"Guard: {'✅ 通过' if guard.get('passed') else '⚠️ ' + str(guard.get('violations', []))}")
                st.markdown(st.session_state.ai_formal_report)
            else:
                md_path = out_dir / "statistical_report.md"
                if md_path.exists():
                    st.markdown(md_path.read_text(encoding="utf-8"))

        with tab2:
            # 显示描述统计
            if result.descriptive_stats:
                st.subheader("描述统计")
                st.dataframe(pd.DataFrame(result.descriptive_stats), use_container_width=True)

            # 显示诊断
            if result.diagnostics:
                st.subheader("假设检验")
                diag_rows = []
                for d in result.diagnostics:
                    diag_rows.append({
                        "检验": d.test_name,
                        "统计量": f"{d.statistic:.4f}" if d.statistic is not None else "N/A",
                        "p": f"{d.p_value:.4f}" if d.p_value is not None else "N/A",
                        "通过": "✅" if d.passed else "❌",
                    })
                st.dataframe(pd.DataFrame(diag_rows), use_container_width=True)

        with tab3:
            st.json(result.model_dump(exclude={"descriptive_stats", "diagnostics"}))
            st.caption("完整的 canonical_result.json")

        # 下载按钮
        st.divider()
        cols = st.columns(3)
        with cols[0]:
            md_path = out_dir / "statistical_report.md"
            if md_path.exists():
                st.download_button(
                    "📥 下载报告 (MD)",
                    md_path.read_bytes(),
                    "statistical_report.md",
                    "text/markdown",
                )
        with cols[1]:
            xlsx_path = out_dir / "results.xlsx"
            if xlsx_path.exists():
                st.download_button(
                    "📥 下载结果 (Excel)",
                    xlsx_path.read_bytes(),
                    "results.xlsx",
                )
        with cols[2]:
            json_path = out_dir / "canonical_result.json"
            if json_path.exists():
                st.download_button(
                    "📥 下载 JSON",
                    json_path.read_bytes(),
                    "canonical_result.json",
                    "application/json",
                )

        # AI 报告（可选）
        if st.session_state.ai_available:
            st.divider()
            st.subheader("🤖 AI 报告摘要")
            if st.button("生成 AI 摘要"):
                with st.spinner("AI 生成中..."):
                    async def _ai_report():
                        from datawork.ai.prompts import report_generation_prompt
                        from datawork.ai.guard import guard_ai_output
                        p = create_provider()
                        rj = result.model_dump_json(indent=2, ensure_ascii=False)[:6000]
                        msgs = report_generation_prompt(rj, lang="zh")
                        resp = await p.generate_text(msgs, temperature=0.4, max_tokens=1000)
                        guard = guard_ai_output(resp.content, result_json=rj)
                        await p.close()
                        return resp, guard

                    resp, guard = asyncio.run(_ai_report())
                    st.caption(f"Guard: {'✅ 通过' if guard['passed'] else '⚠️ ' + str(guard['violations'])}")
                    st.caption(f"费用: ${resp.cost_usd:.6f}")
                    st.markdown(resp.content)

    c1, _ = st.columns(2)
    with c1:
        if st.button("← 返回上一步"):
            st.session_state.step = 5
            st.rerun()

    # 重新开始
    st.divider()
    if st.button("🔄 开始新分析"):
        for k in list(st.session_state.keys()):
            if k != "ai_available":
                del st.session_state[k]
        st.session_state.step = 1
        st.rerun()
