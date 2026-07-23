from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "frontend/src/App.vue").read_text(encoding="utf-8")
STYLE = (ROOT / "frontend/src/style.css").read_text(encoding="utf-8")
PREFLIGHT = (ROOT / "frontend/src/components/PreflightDialog.vue").read_text(encoding="utf-8")
ASSISTANT = (ROOT / "frontend/src/components/AIAssistantPanel.vue").read_text(encoding="utf-8")
AI_RESULT_REPORT = (ROOT / "frontend/src/components/AIResultReportPanel.vue").read_text(encoding="utf-8")
PAIRING = (ROOT / "frontend/src/components/PairingEditor.vue").read_text(encoding="utf-8")
OUTCOME_GROUPS = (ROOT / "frontend/src/components/OutcomeGroupEditor.vue").read_text(encoding="utf-8")
RELEASE_NOTICE = (ROOT / "frontend/src/components/ReleaseNoticeDialog.vue").read_text(encoding="utf-8")


def test_unbounded_method_roles_are_not_hidden():
    assert "maximum === null" in APP
    assert "showDependentRole" in APP
    assert "workspaceShowDependentRole" in APP
    assert "(currentMethod?.max_dependent_vars ?? 0) !== 0" not in APP
    assert "(workspaceCurrentMethod?.max_dependent_vars ?? 0) !== 0" not in APP


def test_long_operations_have_busy_guards_and_waiting_overlay():
    assert "<LoadingOverlay" in APP
    assert "interactionBusy" in APP
    assert "正在执行统计分析" in APP
    assert "正在生成报告" in APP
    assert "operation-spinner" in STYLE
    assert "prefers-reduced-motion" in STYLE


def test_errors_and_preflight_are_actionable():
    assert "<ErrorNotice" in APP
    assert "locatePreflightField" in APP
    assert "preflight-focus" in STYLE
    assert "逐项验证变量角色" in PREFLIGHT
    assert "group.warnings" in PREFLIGHT


def test_cross_model_correction_and_repeat_runs_require_visible_confirmation():
    assert "cross_model_p_adjust: combinationPAdjust.value" in APP
    assert "cross_model_p_adjust: workspaceCombinationPAdjust.value" in APP
    assert "简洁模式与专业模式使用同一统计内核和同一选项" in APP
    assert "简洁模式与专业模式均可设置" in APP
    assert ':prior-run-count="preflightPriorRunCount"' in APP
    assert "prior_run_count" in APP
    assert "多模型运行确认" in PREFLIGHT
    assert "重复运行提醒" in PREFLIGHT
    assert "历史运行不会被自动拼接成同一个校正家族" in PREFLIGHT
    assert "确认并运行 ${taskCount.value} 个任务" in PREFLIGHT
    assert ".cross-model-correction-panel" in STYLE
    assert ".preflight-section.repeat-run-alert" in STYLE
    assert "判断 p 与原始 p 完全相同" in APP
    assert "按原始 p 显著" in (ROOT / "frontend/src/components/AnalysisResultView.vue").read_text(encoding="utf-8")


def test_cross_model_correction_mismatch_blocks_stale_backend_results():
    assert "function guardPreflightCorrection" in APP
    assert "function assertExecutionCorrection" in APP
    assert "correction_setting_mismatch" in APP
    assert "旧后端进程仍在运行" in APP
    assert "assertExecutionCorrection(execution, plan)" in APP
    assert "assertExecutionCorrection(payload.result_json, workspacePlanJson(selected))" in APP
    assert "cross_model_p_adjust: '跨模型多重校正'" in PREFLIGHT


def test_professional_combination_names_are_editable_and_traceable():
    assert "factor_combination_labels" in APP
    assert "编辑组合名称（可选）" in APP
    assert "组合名称（可编辑）" in APP
    assert "自定义拆分组合名称" in APP
    assert "serializeFactorCombinationLabels('instant')" in APP
    assert "serializeFactorCombinationLabels('workspace')" in APP
    assert ".combination-name-editor" in STYLE


def test_normative_result_relies_on_the_single_global_assistant_entry():
    assert "后续分析与具体差异" in AI_RESULT_REPORT
    assert "ordered_comparisons" in AI_RESULT_REPORT
    assert "在小助手中提问" not in AI_RESULT_REPORT
    assert "emit('ask')" not in AI_RESULT_REPORT
    assert '@ask="openResultQuestion"' not in APP
    assert "function openResultQuestion" not in APP
    assert "询问显著性、效应量、组别关系或结论边界" in ASSISTANT
    assert ".result-free-question" not in STYLE


def test_ai_and_guidance_requests_ignore_stale_responses():
    assert "requestId" in ASSISTANT
    guidance = (ROOT / "frontend/src/components/AnalysisGuidanceCard.vue").read_text(encoding="utf-8")
    assert "requestId" in guidance
    assert "assistant-loading" in ASSISTANT


def test_ai_assistant_is_a_contextual_non_blocking_sidebar():
    assert "assistant-side-panel" in ASSISTANT
    assert "当前工作流信息" in ASSISTANT
    assert 'class="assistant-welcome-card"' not in ASSISTANT
    assert "快捷提问" in ASSISTANT
    assert "activeTab" not in ASSISTANT
    assert "minimized" in ASSISTANT
    assert "expanded" in ASSISTANT
    assert "startDrag" in ASSISTANT
    assert "startResize" in ASSISTANT
    assert "assistant-corner-resize" in ASSISTANT
    assert "dockedBottom" not in ASSISTANT
    assert "toggleBottomDock" not in ASSISTANT
    assert "停靠到底部" not in ASSISTANT
    assert "assistant-chat-composer" in ASSISTANT
    assert "toggleExpanded" in ASSISTANT
    assert "mobileMode.value || minimized.value || expanded.value" in ASSISTANT
    assert "'assistant-open': aiAssistantOpen" not in APP
    assert ".assistant-side-layer" in STYLE
    assert ".assistant-side-panel" in STYLE
    assert ".assistant-drawer.assistant-side-panel.expanded" in STYLE
    assert "bottom:22px" in STYLE
    assert "pointer-events: none" in STYLE
    assert ".assistant-message-list" in STYLE


def test_ai_assistant_has_workflow_presets_user_controlled_context_and_markdown_chat():
    assert "assistantNavigationKey" not in APP
    assert "assistantLaunchMode" not in APP
    assert "assistantLaunchQuestion" not in APP
    assert "function askHelp" not in APP
    assert "workflow_step: currentHelpStep.value" in APP
    assert "result_available" in APP
    assert "询问 AI：" not in APP
    assert "在小助手中提问" not in AI_RESULT_REPORT
    assert "PRESETS" in ASSISTANT
    assert "sendPreset" in ASSISTANT
    preset_body = re.search(
        r"async function sendPreset\(preset: PresetPrompt\) \{(?P<body>.*?)\n\}",
        ASSISTANT,
        re.DOTALL,
    )
    assert preset_body
    assert "selectedContext.value" not in preset_body.group("body")
    assert "await sendQuestion(preset.prompt)" in preset_body.group("body")
    assert "selectedContext" in ASSISTANT
    assert "数据画像" in ASSISTANT
    assert "分析计划" in ASSISTANT
    assert "当前结果" in ASSISTANT
    assert "当前分析结果" in ASSISTANT
    assert "结果时间" in ASSISTANT
    assert "resultTimestampLabel" in ASSISTANT
    assert "instantResultCompletedAt.value = new Date().toISOString()" in APP
    assert "workspaceRun.value?.completed_at || workspaceRun.value?.started_at" in APP
    assert ':result-timestamp="assistantResultTimestamp"' in APP
    assert "规范化证据（默认）" in ASSISTANT
    assert "完整结果与诊断" in ASSISTANT
    assert "组别排序（A &gt; B &gt; C）" in ASSISTANT
    assert "include_ordering: includeOrdering.value" in ASSISTANT
    assert "AI 生成的文字报告" in ASSISTANT
    assert "本回答依据" in ASSISTANT
    assert "result_context_id" in ASSISTANT
    assert ':ai-report="assistantAIReport"' in APP
    assert "messages.value = []" in ASSISTANT
    assert "response.value = null" not in ASSISTANT
    assert "liveContextItems" in ASSISTANT
    assert "['模式'" in ASSISTANT
    assert "['方法'" in ASSISTANT
    assert "['因变量'" in ASSISTANT
    assert "['因素'" in ASSISTANT
    assert "['拆分列'" in ASSISTANT
    assert "['结果状态'" in ASSISTANT
    assert "data: true" in ASSISTANT
    assert "plan: false" in ASSISTANT
    assert "result: false" in ASSISTANT
    assert "aiReport: false" in ASSISTANT
    assert "setDefaultContexts" not in ASSISTANT
    assert "'/api/ai/ask'" in ASSISTANT
    assert "answer_markdown" in ASSISTANT
    assert "renderMarkdown" in ASSISTANT
    assert 'class="assistant-welcome-card"' not in ASSISTANT
    assert "<h3>核心发现</h3>" not in ASSISTANT
    assert "原始数据行默认不发送" in ASSISTANT
    assert "Enter 发送，Shift + Enter 换行" in ASSISTANT


def test_page_has_an_accessible_automatic_back_to_top_control():
    assert "showBackToTop" in APP
    assert "window.scrollY > 360" in APP
    assert "scrollToTop" in APP
    assert "prefers-reduced-motion: reduce" in APP
    assert 'aria-label="回到页面顶部"' in APP
    assert ".back-to-top" in STYLE


def test_method_change_resets_roles_and_reapplies_method_specific_suggestions():
    assert '@change="selectWorkspaceDataset(workspaceDatasetId)"' not in APP
    assert "restoreSuggestedRoles('instant')" in APP
    assert "restoreSuggestedRoles('workspace')" in APP
    assert "切换方法会重置变量角色" in APP
    assert "workspaceRun.value = null" in APP


def test_direct_method_or_factor_changes_invalidate_mode_scoped_results_and_reports():
    assert "invalidateInstantResult('分析方法已经改变" in APP
    assert "invalidateWorkspaceResult('分析方法已经改变" in APP
    assert "instantBuiltinReport.value = null" in APP
    assert "instantAIReport.value = null" in APP
    assert "workspaceBuiltinReport.value = null" in APP
    assert "workspaceAIReport.value = null" in APP
    assert "mode.value === 'instant'\n  ? result.value" in APP
    assert "mode.value === 'instant'\n    ? Boolean(result.value)" in APP


def test_order_control_is_limited_to_new_four_through_eight_factor_methods():
    assert "析因阶数（方法选择）" not in APP
    assert "factor_model_order" in APP
    assert "multifactor_anova" in APP
    assert "multifactor_manova" in APP
    assert "configuredMultiFactorOrder" in APP
    assert "hasFactorOrderControl" not in APP
    assert "exactFactorCount" in APP


def test_high_order_instant_analysis_exposes_professional_combinations_and_split():
    assert "HIGH_ORDER_FACTORIAL_METHODS" in APP
    assert "instantFactorCombinationsAllowed" in APP
    assert 'v-if="instantFactorCombinationsAllowed && showFixedRole' in APP
    assert "计算阶数（最高阶 k）" in APP
    assert "自动生成从 1 阶到 k 阶的全部数学组合" in APP
    assert "showInstantSplitRole" in APP
    assert 'v-if="showInstantSplitRole">批量拆分' in APP
    assert "showInstantSplitRuleEditor" in APP
    assert "按每个实际值自动拆分（原方式）" in APP
    assert "自定义分组" in APP
    assert "split_rules: serializeInstantSplitRules()" in APP


def test_professional_derived_columns_and_dual_role_split_are_exposed():
    assert "import DerivedColumnEditor" in APP
    assert "derived_columns: professional ? derivedColumns.value : []" in APP
    assert "split_rules: workspaceExpertMode.value ? serializeWorkspaceSplitRules() : []" in APP
    assert "同时作为分类因素时，每组至少需要两个原始水平" in APP
    for label in ("数据准备与拆分", "模型与检验", "比较与结果", "批量任务"):
        assert label in APP


def test_workspace_save_is_blocked_until_required_roles_are_selected():
    assert "workspaceMissingSelections" in APP
    assert "还需选择" in APP
    assert ":disabled=\"!canCreateWorkspacePlan || workspaceLoading\"" in APP


def test_joint_dependent_variables_and_factor_overflow_require_explicit_confirmation():
    assert "联合因变量（至少" in APP
    assert "ensureMinimumDependentSelection" in APP
    assert "openFactorOverflowPrompt" in APP
    assert "确认并启用组合实验" in APP
    assert "这是重复的排列组合分析" in APP
    assert "combinationCount(projectedCount, 1, maximum)" in APP
    assert "factor-overflow-dialog" in STYLE


def test_release_interaction_polish_keeps_state_transparent_and_keyboard_accessible():
    assert "workflow-strip" in APP
    assert "resultInvalidatedReason" in APP
    assert "workspaceResultInvalidatedReason" in APP
    assert "恢复推荐选择" in APP
    assert "parameter-toolbar" in APP
    assert "恢复默认" in APP
    assert "combination-list" in APP
    assert "handleGlobalKeydown" in APP
    assert "event.key !== 'Escape'" in APP
    assert "DATAWORK {{ releaseVersionLabel }}" in APP
    assert ".workflow-strip" in STYLE
    assert ".state-notice.stale" in STYLE


def test_default_interface_is_simplified_but_expert_controls_remain_available():
    result_view = (ROOT / "frontend/src/components/AnalysisResultView.vue").read_text(encoding="utf-8")
    assert "简洁模式" in APP
    assert "专业模式" in APP
    assert "instantCommonParameters" in APP
    assert "instantAdvancedParameters" in APP
    assert "推荐设置" in APP
    assert "默认仅显示核心结论" in APP
    assert "查看详细结果" in result_view
    assert "结果 Excel" in APP
    assert "/api/instant/reports" in APP


def test_completed_workflow_can_restart_and_reselect_the_same_file():
    assert "startNewInstantAnalysis" in APP
    assert "开始新分析" in APP
    assert "prepareFileReselection" in APP
    assert '@click="prepareFileReselection"' in APP
    assert "selectedMethod.value = DEFAULT_INSTANT_METHOD" in APP
    assert "instantExpertMode.value = false" in APP
    assert "alpha.value = 0.05" in APP
    assert "ssType.value = 3" in APP
    assert "methodParameters.value = defaultMethodParameters(defaultMethod)" in APP
    assert "setInstantExpertMode" in APP
    assert "setWorkspaceExpertMode" in APP
    assert "旧结果已隐藏" in APP


def test_batch_results_use_overview_and_per_batch_pages_with_settings_last():
    result_view = (ROOT / "frontend/src/components/AnalysisResultView.vue").read_text(encoding="utf-8")
    assert "结果总览" in result_view
    assert "逐批查看" in result_view
    assert "selectedTaskIndex" in result_view
    assert "上一批" in result_view and "下一批" in result_view
    assert "分析设置与参数" in result_view
    assert 'watch(() => props.execution' in result_view
    assert ".batch-page-tabs" in STYLE
    assert ".batch-task-switcher" in STYLE


def test_ordinary_user_parameters_have_recommendations_and_low_frequency_options_stay_hidden():
    assert "commonParameterOptions" in APP
    assert "parameterHelp" in APP
    assert "recommendation_note" in APP
    assert "更多低频选项可在专业模式中选择" in APP
    assert "commonParameterIsRelevant" in APP
    assert "parameter.key === 'control_group'" in APP
    assert "recommended_options" in APP


def test_nullable_inference_is_not_rendered_as_not_significant():
    result_view = (ROOT / "frontend/src/components/AnalysisResultView.vue").read_text(encoding="utf-8")
    assert "未提供推断检验" in result_view
    assert "significanceLabel" in result_view
    assert "includes('manova')" in result_view


def test_every_mode_can_open_each_batch_and_result_tables_are_collapsible():
    result_view = (ROOT / "frontend/src/components/AnalysisResultView.vue").read_text(encoding="utf-8")
    assert '<button type="button" :class="{ active: batchPage === \'detail\' }" @click="batchPage = \'detail\'">逐批查看</button>' in result_view
    assert 'v-if="professional" type="button" :class="{ active: batchPage === \'detail\' }"' not in result_view
    assert "batchSummary.value.filter" in result_view
    assert "isBatchInferenceRow(row)" in result_view
    assert "String(row?.result_type ?? '') === 'test'" in result_view
    assert "pValue !== null" in result_view
    assert "因素水平估计、两两比较和字母分组" in result_view
    assert "String(row.task_id ?? '') === String(selectedTaskId.value ?? '')" in result_view
    assert "result-table-disclosure" in result_view
    assert "可折叠" in result_view
    assert "report-table-disclosure" in AI_RESULT_REPORT
    assert "表格默认折叠" in AI_RESULT_REPORT


def test_common_parameter_choices_show_plain_language_option_help():
    source = (ROOT / "frontend/src/App.vue").read_text(encoding="utf-8")
    assert "optionHelp(parameter, option.value)" in source
    assert "choice-help" in source
    registry = (ROOT / "datawork/core/method_registry.py").read_text(encoding="utf-8")
    assert "POSTHOC_OPTION_HELP" in registry
    assert "常规全组两两比较的首选" in registry


def test_ai_normative_report_is_additional_and_independently_downloadable():
    assert "AIResultReportPanel" in APP
    assert "/api/ai/report/result" in APP
    assert "生成 AI 文字总结" in APP
    assert "use_ai: false" in APP
    assert "use_ai: true" in APP
    assert "analysis_context: buildAIReportContext(target, execution)" in APP
    assert ':builtin-payload="instantBuiltinReport"' in APP
    assert ':ai-payload="instantAIReport"' in APP
    assert "下载当前页 Markdown" in AI_RESULT_REPORT
    assert "本地排序与规范表" in AI_RESULT_REPORT
    assert "AI 文字总结" in AI_RESULT_REPORT
    assert "本地页只显示确定性排序和三张规范表" in AI_RESULT_REPORT
    assert "内置规范报告（原文）" not in AI_RESULT_REPORT
    assert "AI 未应用（规范回退）" not in AI_RESULT_REPORT
    assert "AI 文字总结已通过守卫并应用" in AI_RESULT_REPORT
    assert "report-evidence-strip" in AI_RESULT_REPORT
    assert "已并入表2" in AI_RESULT_REPORT
    assert "结构化证据" in AI_RESULT_REPORT
    assert "report-control-disclosure" in AI_RESULT_REPORT
    assert "activePage === 'builtin' && comparisonSequences.length" in AI_RESULT_REPORT
    assert "activePage === 'builtin' && report.tables?.length" in AI_RESULT_REPORT
    assert "本页只显示优化后的文字" in AI_RESULT_REPORT
    assert "固定可视高度" in AI_RESULT_REPORT
    assert "整体滚动查看" in AI_RESULT_REPORT
    assert 'class="comparison-sequence-list scrollable"' in AI_RESULT_REPORT
    assert "primaryComparisonSequences" not in AI_RESULT_REPORT
    assert "overflowComparisonSequences" not in AI_RESULT_REPORT
    assert "comparison-sequence-more" not in AI_RESULT_REPORT
    assert "显著性字母层级优先" in AI_RESULT_REPORT
    assert "comparison-sequence-list" in AI_RESULT_REPORT
    assert "comparison-sequence-flow" in AI_RESULT_REPORT
    assert "组别序列化结论" in AI_RESULT_REPORT
    assert "下一页：AI 文字总结" in AI_RESULT_REPORT
    assert "当前：AI 文字总结" in AI_RESULT_REPORT
    assert "描述性统计" in AI_RESULT_REPORT
    assert "report.tables" in AI_RESULT_REPORT
    assert "aiLoading" in AI_RESULT_REPORT
    assert "排序与表格不会交给 AI 改写" in AI_RESULT_REPORT
    assert 'class="report-content-disclosure"' in AI_RESULT_REPORT
    assert 'class="comparison-sequence-disclosure"' in AI_RESULT_REPORT
    assert "批量总结默认折叠" in AI_RESULT_REPORT
    assert "AI 文字总结已经生成" in AI_RESULT_REPORT
    assert "展开其余" in AI_RESULT_REPORT
    assert "ai-report-points" in AI_RESULT_REPORT
    assert "internalReportTerms" in AI_RESULT_REPORT
    assert "全部项目位于同一列表中" in AI_RESULT_REPORT
    assert "AI 文字未应用" in AI_RESULT_REPORT
    assert "重新生成 AI 文字总结" in AI_RESULT_REPORT
    assert "activePage.value = 'ai'" in AI_RESULT_REPORT
    assert ':ai-error="aiReportErrors.instant"' in APP
    assert '@generate-ai="generateAIResultReport(\'instant\')"' in APP
    assert "prepareResultReports" in APP
    assert "void prepareResultReports('instant', result.value)" in APP
    assert "void prepareResultReports('workspace', payload.result_json)" in APP
    assert "background: true" in APP
    assert "automaticAIReportAllowed" in APP
    assert "aiStatus.value?.configuration_source === 'personal'" in APP
    assert "aiStatus.value?.owner_authenticated" in APP
    assert "builtinReportLoading" in APP
    assert "if (loading) activePage.value = 'builtin'" in AI_RESULT_REPORT
    assert "AI 总结 · 守卫删减" in AI_RESULT_REPORT
    assert "guard_filtered" in AI_RESULT_REPORT
    assert "/api/instant/reports" in APP
    assert "正在准备本地排序与三张规范表" in APP
    assert "report-preparing-animation" in APP


def test_workflow_steps_are_clickable_and_normative_tables_scroll_horizontally():
    style = (ROOT / "frontend/src/style.css").read_text(encoding="utf-8")
    assert "jumpToWorkflowStep(index)" in APP
    assert ':aria-label="`跳转到${label}`"' in APP
    assert "instant-preflight-action" in APP
    assert "workspace-latest-result" in APP
    assert "workflow-jump-highlight" in APP
    assert ".workflow-step:focus-visible" in style
    assert ".report-table-disclosure>.table-scroll" in style
    assert "overflow-x:auto" in style
    assert ".ai-report-tables table { width:max-content; min-width:100%" in style


def test_batch_results_render_before_background_exports_are_ready():
    assert "monitorBatchExport" in APP
    assert "result.batch_export?.status === 'preparing'" in APP
    assert "批次结果已可查看" in APP
    assert "下载文件正在后台整理，不影响结果总览和逐批查看" in APP
    backend = (ROOT / "datawork/web/app.py").read_text(encoding="utf-8")
    assert re.search(
        r"background_tasks\.add_task\(\s*generate_batch_export_artifacts",
        backend,
    )
    assert 'status="preparing"' in backend
    assert 'status="ready"' in backend


def test_ai_normative_report_uses_restricted_evidence_packet():
    service = (ROOT / "datawork/application/ai_assistant_service.py").read_text(encoding="utf-8")
    assert '"ai_evidence_packet": evidence_packet' in service
    assert '"normative_tables"' in service
    assert '"assumption_checks"' in service
    assert '"effect_sizes_in_table_2"' in service
    assert '"read_only_ordering"' in service
    assert "raw_preview[:20]" in service
    assert "三张规范表与 assumption_checks 是统计结论的唯一数值依据" in service
    assert "不能覆盖表格结果、重新计算 p 值" in service
    assert "先报告最高阶交互" in service
    assert "简单简单效应" in service
    assert "主效应显著且因素有三个及以上水平" in service
    assert "MANOVA 必须先报告预先指定的整体多变量判据" in service
    assert "overview[:500]" not in service
    assert "contrasts\", []) or [])[:20]" not in service


def test_assistant_contexts_are_disabled_until_their_sources_exist():
    assert "available: Boolean(props.context.data_profile)" in ASSISTANT
    assert "available: Boolean(props.context.data_profile && props.context.selected_method)" in ASSISTANT
    assert "available: Boolean(props.result)" in ASSISTANT
    assert ':disabled="!item.available"' in ASSISTANT
    assert "function contextEnabled" in ASSISTANT
    assert "if (!item.available) next[item.key] = false" not in ASSISTANT


def test_batch_and_combination_reports_expose_all_merged_exports():
    assert "下载合并结果 XLSX" in APP
    assert "下载完整规范报告 ZIP" in APP
    assert "markdown_download_url" in APP
    assert "json_download_url" in APP
    assert "workspaceReportLinks?.markdown" in APP
    assert "workspaceReportLinks?.json" in APP
    assert 'v-if="result.kind === \'single\'" type="button" class="secondary compact"' not in APP


def test_v15_pairing_groups_and_hierarchical_preflight_are_visible_and_guarded():
    assert "supportsV15Workflow" in APP
    assert "health.value?.features?.pairing_workflow === true" in APP
    assert "health.value?.features?.dependent_variable_groups === true" in APP
    assert "当前后端不支持 V1.5 配对与联合因变量组" in APP
    assert "<PairingEditor" in APP
    assert "<OutcomeGroupEditor" in APP
    assert "pairing: professional ? pairingPlan.value : null" in APP
    assert "dependent_variable_groups: professional && dependentTaskMode.value === 'manual_groups' ? dependentVariableGroups.value : []" in APP
    assert "pairingPlan.value = null" in APP
    assert "dependentVariableGroups.value = []" in APP
    assert "处理—对照配对计算" in PAIRING
    assert "一一映射；对照不可复用" in PAIRING
    assert "整个计划改为一行一对的处理侧数据域" in PAIRING
    assert "/10；结果最多保留 8 位小数" in PAIRING
    assert "[\\d\\s+\\-*/.()]*$" in PAIRING
    assert "联合因变量组" in OUTCOME_GROUPS
    assert "同一因变量不能重复进入多个组" in OUTCOME_GROUPS
    assert "尚未分组" in OUTCOME_GROUPS
    assert "report.pairing_summary?.enabled" in PREFLIGHT
    assert "原始行" in PREFLIGHT
    assert "匹配分组" in PREFLIGHT
    assert "有效配对" in PREFLIGHT
    assert "拆分与配对关系" in PREFLIGHT
    assert "report.task_hierarchy?.enabled" in PREFLIGHT
    assert "因变量任务" in PREFLIGHT
    assert "最终任务" in PREFLIGHT
    assert "任务键" in PREFLIGHT


def test_v17_manova_dependent_combinations_are_visible_and_guarded():
    assert "supportsV17DependentCombinations" in APP
    assert "health.value?.features?.dependent_variable_combinations === true" in APP
    assert "dependent_task_mode" in APP
    assert "dependent_combination_min_size" in APP
    assert "dependent_combination_max_size" in APP
    assert "dependent_combination_labels" in APP
    assert "自动因变量组合" in OUTCOME_GROUPS
    assert "只生成无序组合" in OUTCOME_GROUPS
    assert "v17_backend_required" in APP


def test_v16_pairing_editor_and_abs_capability_are_explicitly_guarded():
    assert "supportsV16PairAbs" in APP
    assert "health.value?.features?.pairing_abs === true" in APP
    assert "pairingUsesAbsoluteValue" in APP
    assert "当前后端不支持 V1.6 配对公式 abs(...)" in APP
    assert "该计划使用 V1.6 配对公式 abs(...)" in APP
    assert "FORMULA_PRESETS" in PAIRING
    assert "处理—对照绝对差" in PAIRING
    assert "UNIT_SUGGESTIONS" in PAIRING
    assert "绝对量（保留原始尺度）" in PAIRING
    assert "DECIMAL_OPTIONS" in PAIRING
    assert "prepareContinuation(value)" in PAIRING
    assert "derivedNameInput.value?.select()" in PAIRING
    assert "duplicateDerived(index)" in PAIRING
    assert "以此新增" in PAIRING
    assert "清空重新填写" in PAIRING
    assert "normalizeAbsoluteBars" in PAIRING
    assert "validateFormulaStructure" in PAIRING
    assert "syntaxOnly.includes('**')" in PAIRING
    assert "syntaxOnly.includes('//')" in PAIRING
    assert "公式括号必须成对出现" in PAIRING
    assert "模板只填充公式，不会覆盖单位/含义" in PAIRING
    assert "item.unit || '未指定'" in PREFLIGHT


def test_v16_pair_column_rename_reconciles_all_name_based_references():
    assert "const previousById = new Map" in APP
    assert "const currentById = new Map" in APP
    assert "renamed.set(oldName, newName)" in APP
    assert "source_columns: definition.source_columns.map(column => renamed.get(column) ?? column)" in APP
    assert "replaceFormulaReference(formula, oldName, newName)" in APP
    assert "dvs.value = dvs.value.filter(column => !removed.has(column)).map(column => renamed.get(column) ?? column)" in APP
    assert "dependent_variables: group.dependent_variables.filter(column => !removed.has(column)).map(column => renamed.get(column) ?? column)" in APP
    assert "watch(pairingPlan, (current, previous) => reconcilePairingChange('instant', current, previous), { deep: true })" in APP
    assert "watch(workspacePairingPlan, (current, previous) => reconcilePairingChange('workspace', current, previous), { deep: true })" in APP


def test_v16_pairing_semantics_notice_is_mandatory_on_each_page_load():
    assert "const pairingTestNoticeOpen = ref(true)" in APP
    assert "<ReleaseNoticeDialog" in APP
    assert '@acknowledge="pairingTestNoticeOpen = false"' in APP
    assert "version === '1.7.0' || version === '1.7'" in APP
    assert "return 'V1.7'" in APP
    assert "DATAWORK {{ releaseVersionLabel }}" in APP
    assert 'role="alertdialog"' in RELEASE_NOTICE
    assert "V1.7 因变量组合会生成多个独立 MANOVA 模型" in RELEASE_NOTICE
    assert "超过 200 强警告，超过 1000 阻止执行" in RELEASE_NOTICE
    assert "默认使用 Holm 跨模型校正" in RELEASE_NOTICE
    assert "我已了解，谨慎使用" in RELEASE_NOTICE
