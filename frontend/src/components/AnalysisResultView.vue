<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import DiagnosticPlotPanel from './DiagnosticPlotPanel.vue'

const props = defineProps<{ execution: any; detailed?: boolean; professional?: boolean }>()
const emit = defineEmits<{ 'toggle-details': [] }>()
const batchPage = ref<'overview' | 'detail'>('overview')
const selectedTaskIndex = ref(0)

const batchOverview = computed<any[]>(() => props.execution?.result?.overview ?? [])
const batchSummary = computed<any[]>(() => props.execution?.result?.summary ?? [])
const batchResults = computed<any[]>(() => props.execution?.result?.results ?? [])
const selectedTask = computed(() => batchResults.value[selectedTaskIndex.value] ?? null)
const selectedTaskId = computed(() => selectedTask.value?.subset_info?.task_id ?? selectedTaskIndex.value + 1)
const selectedAdjustments = computed(() => batchSummary.value.filter(row => (
  String(row.task_id ?? '') === String(selectedTaskId.value ?? '') && isBatchInferenceRow(row)
)))
const selectedSingleExecution = computed(() => selectedTask.value?.result ? {
  kind: 'single',
  result: selectedTask.value.result,
  run_id: props.execution?.run_id,
  provenance: props.execution?.provenance,
} : null)
const failedTaskCount = computed(() => batchResults.value.filter(item => item.error).length)
const warningTaskCount = computed(() => batchResults.value.filter(item => item.result?.warnings?.length).length)
const crossModelAdjustmentMethod = computed(() => String(
  props.execution?.result?.settings?.cross_model_p_adjust
  ?? props.execution?.result?.settings?.combination_p_adjust
  ?? 'holm'
).toLowerCase())
const correctionDisabled = computed(() => crossModelAdjustmentMethod.value === 'none')
const significantTaskCount = computed(() => new Set(batchOverview.value.filter(row => (
  correctionDisabled.value ? row.significant === true : row.significant_adjusted === true
)).map(row => row.task_id)).size)
const significantTaskLabel = computed(() => correctionDisabled.value ? '按原始 p 显著' : '校正后显著')
const judgmentHeading = computed(() => correctionDisabled.value ? '原始显著性结论' : '跨任务校正结论')
const overviewMetaColumns = computed(() => {
  const excluded = new Set(['task_id', 'combination_order'])
  return [...(props.execution?.result?.split_cols ?? []), 'n'].filter((key, index, values) => !excluded.has(key) && values.indexOf(key) === index)
})
const batchSettings = computed(() => Object.entries(props.execution?.result?.settings ?? {}))

watch(() => props.execution, () => {
  batchPage.value = 'overview'
  selectedTaskIndex.value = 0
})

function formatNumber(value: unknown, digits = 4) {
  if (value === null || value === undefined) return '-'
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : String(value)
}

function isBatchInferenceRow(row: any) {
  const pValue = row?.p_value
  return String(row?.result_type ?? '') === 'test'
    && pValue !== null && pValue !== undefined && pValue !== ''
    && Number.isFinite(Number(pValue))
}

function significanceLabel(value: unknown) {
  if (value === null || value === undefined) return '未提供推断检验'
  return value ? '显著' : '不显著'
}
function significanceClass(value: unknown) {
  return value === true ? 'sig yes' : value === false ? 'sig' : 'sig neutral'
}
function overviewConclusionClass(value: unknown) {
  return value === '校正后显著' || value === '原始显著' ? 'sig yes' : value === '执行失败' ? 'sig error' : 'sig'
}
function rawConclusion(row: any) {
  if (row?.raw_conclusion) return String(row.raw_conclusion)
  if (row?.status === 'failed' || row?.error) return '执行失败'
  if (row?.significant === true) return '原始显著'
  if (row?.significant === false) return '原始不显著'
  return '未提供原始判断'
}
function adjustmentConclusion(row: any) {
  if (row?.conclusion) return String(row.conclusion)
  if (row?.status === 'failed' || row?.error) return '执行失败'
  if (correctionDisabled.value) return rawConclusion(row)
  if (row?.significant_adjusted === true) return '校正后显著'
  if (row?.significant_adjusted === false) return '校正后不显著'
  return '未提供判断'
}
function fieldLabel(key: string) {
  const labels: Record<string, string> = {
    factor_combination: '组合名称', factor_columns: '组合因素', dependent_variable: '因变量', dependent_variables: '联合因变量',
    combination_order: '组合阶数', n: '样本量', effect: '效应/检验', statistic_name: '统计量',
    p_value: '原始 p', raw_conclusion: '原始显著性', p_adjusted_across_tasks: '跨任务校正 p', conclusion: '结论',
    factor_combination_labels: '自定义组合名称', cross_model_p_adjust: '跨模型判断方法', combination_p_adjust: '跨模型判断方法',
  }
  return labels[key] ?? key
}
function taskLabel(item: any, index: number) {
  const info = item?.subset_info ?? {}
  const parts = Object.entries(info)
    .filter(([key]) => !['task_id', 'combination_order'].includes(key))
    .map(([key, value]) => `${fieldLabel(key)}=${value}`)
  return parts.length ? parts.join('；') : `批次 ${index + 1}`
}
function selectPreviousTask() {
  selectedTaskIndex.value = Math.max(0, selectedTaskIndex.value - 1)
}
function selectNextTask() {
  selectedTaskIndex.value = Math.min(batchResults.value.length - 1, selectedTaskIndex.value + 1)
}
function settingValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.join('、') || '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
</script>

<template>
  <div class="result-view" v-if="execution">
    <div class="result-toolbar">
      <div>
        <strong>{{ execution.kind === 'single' ? execution.result.method.label_zh : '批量分析结果' }}</strong>
        <small v-if="execution.kind === 'single'">{{ execution.result.method.formula }}</small>
        <small v-else>{{ execution.result.results?.length ?? execution.result.summary?.length ?? 0 }} 个任务</small>
      </div>
      <div class="result-toolbar-actions">
        <button v-if="execution.kind === 'single' && professional" type="button" class="secondary compact" @click="emit('toggle-details')">{{ detailed ? '只看核心结果' : '查看详细结果' }}</button>
        <slot name="actions"></slot>
      </div>
    </div>

    <template v-if="execution.kind === 'single'">
      <div class="result-summary-grid">
        <article><span>方法</span><strong>{{ execution.result.method.label_zh }}</strong></article>
        <article><span>显著结果</span><strong>{{ [...(execution.result.primary_tests ?? []), ...(execution.result.omnibus_tests ?? [])].filter((item:any) => item.is_significant).length }}</strong></article>
        <article><span>分析提醒</span><strong>{{ execution.result.warnings?.length ?? 0 }}</strong></article>
      </div>

      <section class="result-block" v-if="execution.result.primary_tests?.length">
        <details class="result-table-disclosure" open><summary><strong>核心检验</strong><small>{{ execution.result.primary_tests.length }} 项</small></summary>
        <div class="table-wrap"><table><thead><tr><th>检验</th><th>统计结果</th><th>p</th><th>效应量</th><th>结论</th></tr></thead><tbody>
          <tr v-for="test in execution.result.primary_tests" :key="`${test.effect}-${test.statistic_name}`"><td>{{ test.effect }}</td><td>{{ test.statistic_name }}={{ formatNumber(test.statistic_value) }}</td><td>{{ formatNumber(test.p_value, 6) }}</td><td>{{ test.effect_size_name ? `${test.effect_size_name}: ${formatNumber(test.effect_size_value)}` : '-' }}</td><td><span :class="significanceClass(test.is_significant)">{{ significanceLabel(test.is_significant) }}</span></td></tr>
        </tbody></table></div></details>
      </section>

      <section class="result-block" v-if="execution.result.omnibus_tests?.length">
        <details class="result-table-disclosure" open><summary><strong>{{ String(execution.result.method.name).includes('manova') ? '多元总体检验' : '总体效应检验' }}</strong><small>{{ execution.result.omnibus_tests.length }} 项</small></summary>
        <div class="table-wrap"><table><thead><tr><th>效应</th><th>统计结果</th><th>p</th><th>效应量</th><th>结论</th></tr></thead><tbody>
          <tr v-for="test in execution.result.omnibus_tests" :key="`${test.effect}-${test.statistic_name}`"><td>{{ test.effect }}</td><td>{{ test.statistic_name ? `${test.statistic_name}=${formatNumber(test.statistic_value, 6)}；F=${formatNumber(test.f_value)}` : `F=${formatNumber(test.f_value)}` }}</td><td>{{ formatNumber(test.p_value, 6) }}</td><td>{{ test.statistic_name ? '-' : `η²p=${formatNumber(test.eta_sq_p)}` }}</td><td><span :class="significanceClass(test.is_significant)">{{ significanceLabel(test.is_significant) }}</span></td></tr>
        </tbody></table></div></details>
      </section>

      <section class="result-block" v-if="execution.result.coefficients?.length">
        <details class="result-table-disclosure" open><summary><strong>模型参数</strong><small>{{ execution.result.coefficients.length }} 项</small></summary>
        <div class="table-wrap"><table><thead><tr><th>参数</th><th>估计值</th><th>p</th><th>转换值</th><th>结论</th></tr></thead><tbody>
          <tr v-for="item in execution.result.coefficients" :key="item.term"><td>{{ item.term }}</td><td>{{ formatNumber(item.estimate) }}</td><td>{{ formatNumber(item.p_value, 6) }}</td><td>{{ item.transformed_name ? `${item.transformed_name}: ${formatNumber(item.transformed_value)}` : '-' }}</td><td><span :class="item.significant ? 'sig yes' : 'sig'">{{ item.significant ? '显著' : '不显著' }}</span></td></tr>
        </tbody></table></div></details>
      </section>

      <section class="result-block" v-if="execution.result.follow_up_tests?.length">
        <details class="result-table-disclosure" open><summary><strong>单变量跟进</strong><small>{{ execution.result.follow_up_tests.length }} 项</small></summary>
        <div class="table-wrap"><table><thead><tr><th>因变量</th><th>效应</th><th>F</th><th>校正 p</th><th>结论</th></tr></thead><tbody><tr v-for="item in execution.result.follow_up_tests" :key="`${item.outcome}-${item.effect}`"><td>{{ item.outcome }}</td><td>{{ item.effect }}</td><td>{{ formatNumber(item.f_value) }}</td><td>{{ formatNumber(item.p_adjusted,6) }}</td><td><span :class="item.significant ? 'sig yes' : 'sig'">{{ item.significant ? '显著' : '不显著' }}</span></td></tr></tbody></table></div></details>
      </section>

      <section class="result-block letter-groups" v-if="execution.result.significance_letters?.length">
        <details class="result-table-disclosure" open><summary><strong>显著性字母分组</strong><small>{{ execution.result.significance_letters.length }} 项</small></summary>
        <div class="table-wrap"><table><thead><tr><th>方法</th><th>条件</th><th>水平</th><th>均值/EMM</th><th>字母</th></tr></thead><tbody><tr v-for="(item,index) in execution.result.significance_letters" :key="`${item.method}-${item.group}-${index}`"><td>{{ item.method }}</td><td>{{ item.context || item.factor || '总体' }}</td><td>{{ item.group }}</td><td>{{ formatNumber(item.mean) }}</td><td><strong class="letter-badge">{{ item.letters }}</strong></td></tr></tbody></table></div><p class="table-note">共享至少一个字母表示差异不显著；没有共同字母表示差异显著。</p></details>
      </section>

      <div class="warnings" v-if="execution.result.warnings?.length"><strong>分析提醒</strong><p v-for="warning in execution.result.warnings" :key="warning">{{ warning }}</p></div>

      <div class="result-detail-area" v-if="professional && detailed">
        <section class="result-block" v-if="execution.result.primary_tests?.length"><h3>完整主要检验</h3><div class="table-wrap"><table><thead><tr><th>检验</th><th>统计量</th><th>数值</th><th>df₁</th><th>df₂</th><th>p</th><th>95% CI</th><th>说明</th></tr></thead><tbody><tr v-for="test in execution.result.primary_tests" :key="`detail-${test.effect}-${test.statistic_name}`"><td>{{ test.effect }}</td><td>{{ test.statistic_name }}</td><td>{{ formatNumber(test.statistic_value) }}</td><td>{{ formatNumber(test.df_num,2) }}</td><td>{{ formatNumber(test.df_den,2) }}</td><td>{{ formatNumber(test.p_value,6) }}</td><td>[{{ formatNumber(test.ci_lower) }}, {{ formatNumber(test.ci_upper) }}]</td><td>{{ test.detail || '-' }}</td></tr></tbody></table></div></section>
        <section class="result-block" v-if="execution.result.omnibus_tests?.length"><h3>完整总体检验</h3><div class="table-wrap"><table><thead><tr><th>效应</th><th>统计量</th><th>统计量值</th><th>df₁</th><th>df₂</th><th>F</th><th>p</th><th>η²p</th></tr></thead><tbody><tr v-for="test in execution.result.omnibus_tests" :key="`detail-${test.effect}-${test.statistic_name}`"><td>{{ test.effect }}</td><td>{{ test.statistic_name || 'F' }}</td><td>{{ formatNumber(test.statistic_value) }}</td><td>{{ formatNumber(test.df_num,2) }}</td><td>{{ formatNumber(test.df_den,2) }}</td><td>{{ formatNumber(test.f_value) }}</td><td>{{ formatNumber(test.p_value,6) }}</td><td>{{ test.statistic_name ? '-' : formatNumber(test.eta_sq_p) }}</td></tr></tbody></table></div></section>
        <section class="result-block" v-if="execution.result.diagnostics?.length"><h3>假设与数据诊断</h3><div class="table-wrap"><table><thead><tr><th>检查</th><th>统计量</th><th>p</th><th>状态</th><th>说明</th></tr></thead><tbody><tr v-for="(item,index) in execution.result.diagnostics" :key="`${item.test_name}-${index}`"><td>{{ item.test_name }}</td><td>{{ formatNumber(item.statistic) }}</td><td>{{ formatNumber(item.p_value,6) }}</td><td>{{ item.passed === null || item.passed === undefined ? '提示' : item.passed ? '通过' : '需注意' }}</td><td>{{ item.detail }}</td></tr></tbody></table></div></section>
        <div class="detail-meta"><div><span>运行 ID</span><strong>{{ execution.run_id || execution.result.analysis_id || '-' }}</strong></div><div><span>数据指纹</span><strong>{{ execution.provenance?.dataset?.cleaned_sha256?.slice(0, 20) || '-' }}</strong></div></div>
        <section class="result-block" v-if="execution.result.simple_effects?.length"><h3>条件简单效应</h3><div class="table-wrap"><table><thead><tr><th>效应</th><th>固定条件</th><th>df₁</th><th>df₂</th><th>F</th><th>原始 p</th><th>校正 p</th><th>校正</th></tr></thead><tbody><tr v-for="item in execution.result.simple_effects" :key="item.effect"><td>{{ item.effect }}</td><td>{{ item.fixed_level }}</td><td>{{ formatNumber(item.df_num,2) }}</td><td>{{ formatNumber(item.df_den,2) }}</td><td>{{ formatNumber(item.f_value) }}</td><td>{{ formatNumber(item.p_value,6) }}</td><td>{{ formatNumber(item.p_adjusted ?? item.p_value,6) }}</td><td>{{ item.correction }}</td></tr></tbody></table></div></section>
        <section class="result-block" v-if="execution.result.estimated_marginal_means?.length"><h3>估计边际均值</h3><div class="table-wrap"><table><thead><tr><th>组</th><th>均值</th><th>SE</th><th>95% CI</th><th>来源</th></tr></thead><tbody><tr v-for="item in execution.result.estimated_marginal_means" :key="item.group"><td>{{ item.group }}</td><td>{{ formatNumber(item.mean) }}</td><td>{{ formatNumber(item.se) }}</td><td>[{{ formatNumber(item.ci_lower) }}, {{ formatNumber(item.ci_upper) }}]</td><td>{{ item.source }}</td></tr></tbody></table></div></section>
        <section class="result-block" v-if="execution.result.contrasts?.length"><h3>成对比较</h3><div class="table-wrap"><table><thead><tr><th>对比</th><th>差值</th><th>SE</th><th>统计量</th><th>原始 p</th><th>校正 p</th><th>95% CI</th><th>方法</th></tr></thead><tbody><tr v-for="(item,index) in execution.result.contrasts" :key="`${item.contrast}-${index}`"><td>{{ item.contrast }}</td><td>{{ formatNumber(item.estimate) }}</td><td>{{ formatNumber(item.se) }}</td><td>{{ item.statistic_name }}={{ formatNumber(item.t_value) }}</td><td>{{ formatNumber(item.p_value,6) }}</td><td>{{ formatNumber(item.p_adjusted,6) }}</td><td>[{{ formatNumber(item.ci_lower) }}, {{ formatNumber(item.ci_upper) }}]</td><td>{{ item.correction }}</td></tr></tbody></table></div></section>
        <section class="result-block" v-if="execution.result.fit_statistics?.length"><h3>模型拟合</h3><div class="fit-grid"><article v-for="item in execution.result.fit_statistics" :key="item.name"><span>{{ item.name }}</span><strong>{{ formatNumber(item.value) }}</strong><small>{{ item.detail }}</small></article></div></section>
        <section class="result-block" v-if="execution.result.sphericity"><h3>球形性检查</h3><div class="sphericity-card"><strong>Mauchly W={{ formatNumber(execution.result.sphericity.statistic) }}</strong><span>p={{ formatNumber(execution.result.sphericity.p_value, 6) }}</span><p>{{ execution.result.sphericity.detail }}</p></div></section>
        <section class="result-block" v-if="execution.result.diagnostic_plots?.length"><h3>诊断图</h3><DiagnosticPlotPanel :plots="execution.result.diagnostic_plots" /></section>
        <section class="result-block" v-if="execution.result.descriptive_stats?.length"><h3>描述统计</h3><div class="table-wrap"><table><thead><tr><th v-for="key in Object.keys(execution.result.descriptive_stats[0])" :key="key">{{ key }}</th></tr></thead><tbody><tr v-for="(row,index) in execution.result.descriptive_stats" :key="index"><td v-for="key in Object.keys(execution.result.descriptive_stats[0])" :key="key">{{ row[key] ?? '-' }}</td></tr></tbody></table></div></section>
      </div>
    </template>

    <template v-else>
      <nav class="batch-page-tabs" aria-label="批次结果页面">
        <button type="button" :class="{ active: batchPage === 'overview' }" @click="batchPage = 'overview'">结果总览</button>
        <button type="button" :class="{ active: batchPage === 'detail' }" @click="batchPage = 'detail'">逐批查看</button>
      </nav>

      <section v-if="batchPage === 'overview'" class="batch-overview-page">
        <div class="batch-summary-strip">
          <article><span>全部任务</span><strong>{{ batchResults.length }}</strong></article>
          <article><span>{{ significantTaskLabel }}</span><strong>{{ significantTaskCount }}</strong></article>
          <article><span>分析提醒</span><strong>{{ warningTaskCount }}</strong></article>
          <article><span>执行失败</span><strong>{{ failedTaskCount }}</strong></article>
        </div>
        <section class="result-block" v-if="batchOverview.length">
          <details class="result-table-disclosure" open><summary><strong>核心推断结果</strong><small>{{ batchOverview.length }} 项，可折叠</small></summary>
          <div class="table-wrap"><table><thead><tr>
            <th v-for="key in overviewMetaColumns" :key="key">{{ fieldLabel(key) }}</th>
            <th>效应/检验</th><th>统计量</th><th>原始 p</th><th>校正前显著性</th><th v-if="!correctionDisabled">跨任务校正 p</th><th v-if="!correctionDisabled">校正后显著性</th>
          </tr></thead><tbody><tr v-for="(row,index) in batchOverview" :key="`${row.task_id}-${row.effect}-${index}`">
            <td v-for="key in overviewMetaColumns" :key="key">{{ row[key] ?? '-' }}</td>
            <td>{{ row.effect || '-' }}</td>
            <td>{{ row.statistic_name ? `${row.statistic_name}=${formatNumber(row.statistic_value)}` : '-' }}</td>
            <td>{{ formatNumber(row.p_value, 6) }}</td>
            <td><span :class="overviewConclusionClass(rawConclusion(row))">{{ rawConclusion(row) }}</span></td>
            <td v-if="!correctionDisabled">{{ formatNumber(row.p_adjusted_across_tasks, 6) }}</td>
            <td v-if="!correctionDisabled"><span :class="overviewConclusionClass(row.conclusion)">{{ row.conclusion || '已完成' }}</span></td>
          </tr></tbody></table></div></details>
        </section>
        <div class="batch-empty" v-else>暂无可展示的批次推断结果。</div>
      </section>

      <section v-else class="batch-detail-page">
        <div class="batch-task-switcher">
          <label>当前批次
            <select v-model.number="selectedTaskIndex">
              <option v-for="(item,index) in batchResults" :key="`${item.subset_key}-${index}`" :value="index">{{ taskLabel(item, index) }}</option>
            </select>
          </label>
          <div><button type="button" class="secondary compact" :disabled="selectedTaskIndex === 0" @click="selectPreviousTask">上一批</button><button type="button" class="secondary compact" :disabled="selectedTaskIndex >= batchResults.length - 1" @click="selectNextTask">下一批</button></div>
        </div>
        <div class="batch-task-context" v-if="selectedTask">
          <div><span>任务</span><strong>{{ selectedTaskIndex + 1 }} / {{ batchResults.length }}</strong></div>
          <div><span>样本量</span><strong>{{ selectedTask.n_rows }}</strong></div>
          <div><span>批次条件</span><strong>{{ taskLabel(selectedTask, selectedTaskIndex) }}</strong></div>
        </div>
        <section class="result-block" v-if="selectedAdjustments.length">
          <details class="result-table-disclosure" open><summary><strong>{{ judgmentHeading }}</strong><small>{{ selectedAdjustments.length }} 项，可折叠</small></summary>
          <div class="table-wrap"><table><thead><tr><th>效应/检验</th><th>原始 p</th><th>校正前显著性</th><th v-if="!correctionDisabled">跨任务校正 p</th><th v-if="!correctionDisabled">校正后显著性</th></tr></thead><tbody><tr v-for="(row,index) in selectedAdjustments" :key="`${row.effect}-${index}`"><td>{{ row.effect || '-' }}</td><td>{{ formatNumber(row.p_value, 6) }}</td><td><span :class="overviewConclusionClass(rawConclusion(row))">{{ rawConclusion(row) }}</span></td><td v-if="!correctionDisabled">{{ formatNumber(row.p_adjusted_across_tasks, 6) }}</td><td v-if="!correctionDisabled"><span :class="overviewConclusionClass(adjustmentConclusion(row))">{{ adjustmentConclusion(row) }}</span></td></tr></tbody></table></div><p class="table-note">这里只显示当前批次可进行显著性判断的主要/总体检验；因素水平估计、两两比较和字母分组在下方对应结果区展示，不进入跨任务校正表。</p></details>
        </section>
        <div class="warnings" v-if="selectedTask?.error"><strong>该批次执行失败</strong><p>{{ selectedTask.error }}</p></div>
        <AnalysisResultView v-else-if="selectedSingleExecution" :execution="selectedSingleExecution" :detailed="detailed" :professional="professional" @toggle-details="emit('toggle-details')" />
      </section>

      <details class="batch-settings" v-if="professional && batchSettings.length">
        <summary>分析设置与参数</summary>
        <div class="batch-settings-grid"><div v-for="([key,value]) in batchSettings" :key="key"><span>{{ fieldLabel(key) }}</span><strong>{{ settingValue(value) }}</strong></div></div>
      </details>
      <slot name="batch-actions"></slot>
    </template>
  </div>
</template>
