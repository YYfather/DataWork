<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  payload?: any
  builtinPayload?: any
  aiPayload?: any
  aiLoading?: boolean
  aiReady?: boolean
  aiError?: string
  batch?: boolean
}>()
const emit = defineEmits<{ 'generate-ai': [] }>()
const payloadIsAI = computed(() => ['ai', 'ai_guard_partial'].includes(String(props.payload?.source ?? '')))
const builtin = computed(() => props.builtinPayload ?? (!payloadIsAI.value ? props.payload : null))
const ai = computed(() => props.aiPayload ?? (payloadIsAI.value ? props.payload : null))
const aiApplied = computed(() => ['ai', 'ai_guard_partial'].includes(String(ai.value?.source ?? '')))
const activePage = ref<'builtin' | 'ai'>('builtin')
const pages = computed(() => [
  ...(builtin.value?.report ? [{ key: 'builtin' as const, label: '本地排序与规范表' }] : []),
  ...(aiApplied.value && ai.value?.report ? [{ key: 'ai' as const, label: 'AI 文字总结' }] : []),
])
const currentPayload = computed(() => activePage.value === 'ai' && ai.value?.report ? ai.value : builtin.value ?? ai.value)
const report = computed(() => currentPayload.value?.report ?? {})
const reportControl = computed(() => currentPayload.value?.report_control ?? null)
const orderedComparisons = computed(() => {
  const current = report.value.ordered_comparisons
  return Array.isArray(current) && current.length ? current : builtin.value?.report?.ordered_comparisons ?? []
})
type SequenceToken = { kind: 'label' | 'operator'; value: string }
type SequenceCard = { scope: string; detail: string; ariaLabel: string; tokens: SequenceToken[] }
function sequenceCard(value: unknown): SequenceCard {
  const text = String(value ?? '').trim()
  const separator = text.indexOf('：')
  const scope = separator >= 0 ? text.slice(0, separator).trim() : '组别比较'
  const body = separator >= 0 ? text.slice(separator + 1).trim() : text
  const detailStart = body.indexOf('（')
  const expression = (detailStart >= 0 ? body.slice(0, detailStart) : body).trim()
  const detail = detailStart >= 0 ? body.slice(detailStart).trim() : ''
  const tokens = expression.split(/\s+(>|=|≈)\s+/).filter(Boolean).map((token, index) => ({
    kind: index % 2 === 0 ? 'label' as const : 'operator' as const,
    value: token,
  }))
  return { scope, detail, ariaLabel: tokens.map(token => token.value).join(' '), tokens }
}
const comparisonSequences = computed(() => orderedComparisons.value.map(sequenceCard))
const currentPageNumber = computed(() => Math.max(1, pages.value.findIndex(page => page.key === activePage.value) + 1))
const internalReportTerms: Record<string, string> = {
  read_only_ordering: '本地只读排序',
  ordered_comparisons: '本地只读排序',
  ai_evidence_packet: '本地证据包',
  normative_tables: '三张规范表',
  canonical_result: '原始统计结果',
}
function readableReportText(value: unknown) {
  let text = String(value ?? '').trim()
  for (const [internal, readable] of Object.entries(internalReportTerms)) text = text.replaceAll(internal, readable)
  return text.replace(/\s+/g, ' ')
}
function reportPoints(paragraphs: unknown[]): string[] {
  const points: string[] = []
  for (const paragraph of paragraphs) {
    const text = readableReportText(paragraph)
    const sentences = text.match(/[^。！？]+[。！？]?/g) ?? [text]
    for (const sentence of sentences) {
      const cleanSentence = sentence.trim()
      if (cleanSentence.length <= 220) {
        if (cleanSentence) points.push(cleanSentence)
        continue
      }
      const clauses = cleanSentence.split(/(?<=；)/).map(item => item.trim()).filter(Boolean)
      points.push(...(clauses.length > 1 ? clauses : [cleanSentence]))
    }
  }
  return points
}
const sections = computed(() => [
  { heading: '研究目的、统计方法与设计', paragraphs: [...(report.value.analysis_overview ?? []), ...(report.value.data_and_design ?? [])] },
  { heading: '描述性统计', paragraphs: report.value.descriptive_statistics ?? [] },
  { heading: '前提与模型诊断', paragraphs: report.value.assumption_review ?? [] },
  { heading: '交互作用、主效应与整体检验', paragraphs: report.value.inferential_results ?? [] },
  { heading: '后续分析与具体差异', paragraphs: report.value.follow_up_results ?? [] },
  { heading: '效应量、结论与解释边界', paragraphs: [...(report.value.effect_sizes_and_uncertainty ?? []), ...(report.value.conclusion ?? []), ...(report.value.limitations ?? [])] },
].map(section => ({ heading: section.heading, points: reportPoints(section.paragraphs) })).filter(section => section.points.length))
const evidenceSummary = computed(() => currentPayload.value?.evidence_summary ?? ai.value?.evidence_summary ?? builtin.value?.evidence_summary ?? {})
const evidenceMetrics = computed(() => [
  { label: '规范表', value: evidenceSummary.value.table_count ?? report.value.tables?.length ?? 0, detail: '本地只读' },
  { label: '效应量', value: evidenceSummary.value.effect_size_count ?? 0, detail: '已并入表2' },
  { label: '前提检验', value: evidenceSummary.value.assumption_check_count ?? 0, detail: '结构化证据' },
  { label: '排序结论', value: evidenceSummary.value.ordering_count ?? orderedComparisons.value.length, detail: '顺序锁定' },
])

watch(builtin, value => {
  if (value?.report) activePage.value = 'builtin'
})

watch(() => props.aiLoading, loading => {
  if (loading) activePage.value = 'builtin'
})

watch(ai, value => {
  if (value?.report && ['ai', 'ai_guard_partial'].includes(String(value.source ?? ''))) activePage.value = 'ai'
})

function setPage(page: 'builtin' | 'ai') {
  if (page === 'ai' && !ai.value?.report) return
  activePage.value = page
}

function movePage(offset: number) {
  const index = pages.value.findIndex(page => page.key === activePage.value)
  const target = pages.value[index + offset]
  if (target) activePage.value = target.key
}

function downloadMarkdown() {
  const content = String(currentPayload.value?.report_markdown ?? '')
  if (!content) return
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = activePage.value === 'ai' ? 'DataWork_AI文字总结.md' : 'DataWork_本地排序与规范表.md'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

const guardViolations = computed(() => currentPayload.value?.guard_filtered?.violations ?? currentPayload.value?.guard?.violations ?? [])
</script>

<template>
  <section class="panel ai-result-report-panel" v-if="report?.title">
    <div class="section-heading">
      <div><span>{{ activePage === 'ai' ? 'AI' : '01' }}</span><h2>{{ report.title || '规范统计结果报告' }}</h2></div>
      <div class="heading-tools">
        <span class="ai-report-source" :class="currentPayload?.source">
          {{ activePage === 'builtin' ? '本地统计内核 · 排序与三表' : currentPayload?.source === 'ai' ? `${currentPayload.provider} · ${currentPayload.model}` : 'AI 总结 · 守卫删减' }}
        </span>
        <button type="button" class="secondary compact" @click="downloadMarkdown">下载当前页 Markdown</button>
      </div>
    </div>

    <nav class="report-page-tabs" aria-label="规范报告分页">
      <button v-for="page in pages" :key="page.key" type="button" :class="{ active: activePage === page.key }" :aria-current="activePage === page.key ? 'page' : undefined" @click="setPage(page.key)">
        {{ page.label }}
      </button>
      <span>{{ currentPageNumber }} / {{ Math.max(pages.length, 1) }}</span>
    </nav>

    <section class="report-evidence-strip" v-if="activePage === 'builtin'" aria-label="报告证据概览">
      <article v-for="metric in evidenceMetrics" :key="metric.label">
        <span>{{ metric.label }}</span><strong>{{ metric.value }}</strong><small>{{ metric.detail }}</small>
      </article>
    </section>

    <div class="state-notice ready ai-report-progress" v-if="aiLoading">
      <div><strong>本地排序与三张规范表已就绪</strong><p>AI 正在后台根据受保护证据生成文字总结；当前页可立即查看和下载，排序与表格不会交给 AI 改写。</p></div>
      <div class="inline-spinner" aria-hidden="true"></div>
    </div>
    <div class="state-notice stale ai-report-action" v-else-if="builtin?.report && !aiApplied">
      <div>
        <strong>{{ aiError ? 'AI 文字未应用' : aiReady ? 'AI 文字总结尚未生成' : '当前仅显示本地统计证据' }}</strong>
        <p>{{ aiError || (aiReady ? 'AI 已配置，但本次尚未返回可应用的文字；可在此重新生成。' : 'AI 尚未启用或配置未完成；本地排序与三张规范表不受影响。') }}</p>
      </div>
      <button type="button" class="secondary compact" @click="emit('generate-ai')">{{ aiReady ? '重新生成 AI 文字总结' : '配置并生成 AI 文字总结' }}</button>
    </div>
    <div class="report-status-line" v-if="activePage === 'ai' && ['ai', 'ai_guard_partial'].includes(String(currentPayload?.source ?? ''))">
      <span aria-hidden="true">✓</span><div><strong>AI 文字总结已通过守卫并应用</strong><p>依据三张规范表、表2中的效应量、{{ evidenceSummary.assumption_check_count ?? 0 }} 项前提检验及只读排序撰写；{{ evidenceSummary.preview_rows_sent ? `另附 ${evidenceSummary.preview_rows_sent} 行数据预览用于标签语境` : '未发送原始数据行' }}。本页只显示优化后的文字。</p></div>
    </div>
    <details class="report-control-disclosure" v-if="activePage === 'builtin' && reportControl?.mode === 'deterministic'">
      <summary><strong>统计报告规范控制已启用</strong><small>查看解释边界</small></summary>
      <p>总体/多变量父检验、交互层级、简单效应与事后比较触发条件由本地规则锁定。统计表保留完整计算行，但不表示每一行都可以脱离父检验独立解释。</p>
    </details>
    <div class="state-notice ready local-ai-page-notice" v-if="activePage === 'builtin' && aiApplied"><div><strong>AI 文字总结已经生成</strong><p>当前为本地证据页，只展示排序和三张规范表；请切换到“AI 文字总结”查看优化后的文字。</p></div></div>
    <div class="state-notice stale" v-if="currentPayload?.warning && !(activePage === 'builtin' && aiApplied)"><div><strong>报告生成说明</strong><p>{{ currentPayload.warning }}</p></div></div>
    <details class="ai-guard-details" v-if="guardViolations.length">
      <summary>查看数值一致性检查明细（{{ guardViolations.length }} 项）</summary>
      <p>{{ currentPayload?.source === 'ai_guard_partial' ? '以下问题所在的 AI 章节已移除，其余通过检查的 AI 文字仍然保留；系统没有用内置文字回填。' : '这些明细仅针对 AI 可改写的叙述段落；本地生成的组别排序、统计表和表号不参与 AI 审计。' }}</p>
      <ul><li v-for="item in guardViolations" :key="item">{{ item }}</li></ul>
    </details>

    <details class="report-content-disclosure" v-if="activePage === 'ai' && aiApplied && sections.length" :open="!batch">
      <summary><div><span>TEXT</span><strong>AI 文字总结</strong></div><small>{{ sections.length }} 节 · {{ batch ? '批量总结默认折叠' : '点击折叠' }}</small></summary>
      <div class="ai-report-sections">
        <article v-for="(section, index) in sections" :key="section.heading">
          <span>{{ String(index + 1).padStart(2, '0') }}</span>
          <div>
            <h3>{{ section.heading }}</h3>
            <ul class="ai-report-points"><li v-for="(point, pointIndex) in section.points.slice(0, 3)" :key="pointIndex">{{ point }}</li></ul>
            <details class="ai-report-more" v-if="section.points.length > 3">
              <summary>展开其余 {{ section.points.length - 3 }} 条统计细节</summary>
              <ul class="ai-report-points secondary"><li v-for="(point, pointIndex) in section.points.slice(3)" :key="pointIndex">{{ point }}</li></ul>
            </details>
          </div>
        </article>
      </div>
    </details>
    <details class="comparison-sequence-disclosure" v-if="activePage === 'builtin' && comparisonSequences.length" :open="!batch">
      <summary><div><span>ORDER</span><strong>组别序列化结论</strong></div><small>固定可视高度 · 共 {{ comparisonSequences.length }} 项 · 整体滚动查看</small></summary>
      <section class="comparison-sequence-panel">
        <div class="comparison-sequence-heading"><span>ORDER</span><div><h3>组别序列化结论</h3><p>显著性字母层级优先，其次为估计边际均值，最后为描述性排序；全部项目位于同一列表中，列表整体上下滚动。</p></div></div>
        <div class="comparison-sequence-list scrollable" tabindex="0" aria-label="全部组别序列化结论，可上下滚动">
          <article v-for="(sequence, sequenceIndex) in comparisonSequences" :key="`${sequence.scope}-${sequenceIndex}`">
            <span class="comparison-sequence-scope">{{ sequence.scope }}</span>
            <div class="comparison-sequence-flow" :aria-label="sequence.ariaLabel">
              <template v-for="(token, tokenIndex) in sequence.tokens" :key="`${token.value}-${tokenIndex}`">
                <strong v-if="token.kind === 'label'">{{ token.value }}</strong>
                <span v-else class="comparison-sequence-operator" aria-hidden="true">{{ token.value }}</span>
              </template>
            </div>
            <p v-if="sequence.detail">{{ sequence.detail }}</p>
          </article>
        </div>
      </section>
    </details>
    <div class="ai-report-tables" v-if="activePage === 'builtin' && report.tables?.length">
      <div class="report-table-heading"><div><span>TABLES</span><h3>规范结果表</h3></div><p>效应量与对应推断检验集中在表2；表格默认折叠，可横向滚动。</p></div>
      <details class="report-table-disclosure" v-for="(table, tableIndex) in report.tables" :key="table.title">
        <summary><strong>{{ table.title }}</strong><small>{{ table.rows?.length ?? 0 }} 行 · {{ tableIndex === 1 && evidenceSummary.effect_size_count ? `含 ${evidenceSummary.effect_size_count} 项效应量` : '点击展开' }}</small></summary>
        <div class="table-scroll"><table><thead><tr><th v-for="column in table.columns" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, rowIndex) in table.rows" :key="rowIndex" :class="{ 'effect-size-row': tableIndex === 1 && table.columns?.indexOf('效应量（含区间）') >= 0 && row[table.columns.indexOf('效应量（含区间）')] !== '—' }"><td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td></tr></tbody></table></div>
      </details>
    </div>

    <footer class="report-page-footer" v-if="pages.length > 1">
      <button type="button" class="secondary compact" :disabled="currentPageNumber <= 1" @click="movePage(-1)">{{ currentPageNumber <= 1 ? '当前：本地排序与规范表' : '上一页：本地排序与规范表' }}</button>
      <span>第 {{ currentPageNumber }} 页，共 {{ pages.length }} 页</span>
      <button type="button" class="primary compact" :disabled="currentPageNumber >= pages.length" @click="movePage(1)">{{ currentPageNumber >= pages.length ? '当前：AI 文字总结' : '下一页：AI 文字总结' }}</button>
    </footer>
    <p class="ai-report-disclaimer">{{ activePage === 'ai' ? 'AI 页只显示通过数值与推断层级守卫的优化文字；只读排序和规范表请返回本地证据页查看。' : '本地页只显示确定性排序和三张规范表，不生成内置文字报告。' }}统计数值以 DataWork 原始结果、合并工作簿和 canonical JSON 为准。</p>
  </section>
</template>
