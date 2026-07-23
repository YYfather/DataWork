<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { apiRequest, errorMessage } from '../api'

type ContextKey = 'data' | 'plan' | 'result' | 'aiReport'
type ResultScope = 'normative_evidence' | 'full_result'
type ConversationMessage = {
  id: number
  role: 'user' | 'assistant' | 'system'
  text?: string
  payload?: any
  contextLabel?: string
}
type PresetPrompt = { label: string; prompt: string; contexts: ContextKey[] }

const props = defineProps<{
  open: boolean
  step: string
  context: Record<string, unknown>
  result?: Record<string, unknown> | null
  aiReport?: Record<string, unknown> | null
  resultContextId?: string
  resultTimestamp?: string
  aiReportContextId?: string
  aiReady?: boolean
}>()
const emit = defineEmits<{ close: []; settings: []; authenticate: [] }>()

const question = ref('')
const loading = ref(false)
const error = ref('')
const errorCode = ref('')
const messages = ref<ConversationMessage[]>([])
const selectedContext = ref<Record<ContextKey, boolean>>({ data: false, plan: false, result: false, aiReport: false })
const resultScope = ref<ResultScope>('normative_evidence')
const includeOrdering = ref(true)
const minimized = ref(false)
const expanded = ref(false)
const panelRef = ref<HTMLElement | null>(null)
const messageListRef = ref<HTMLElement | null>(null)
const mobileMode = ref(false)
const geometry = ref({ x: 0, y: 12, width: 440, height: 760 })
const detached = ref(false)
let pointerAction: null | { mode: 'drag' | 'resize'; x: number; y: number; start: typeof geometry.value; pointerId: number } = null
let requestId = 0
let messageId = 0
let dataDefaultApplied = false

const PLAN_STEPS = new Set(['build_plan', 'choose_method', 'review_plan', 'run_analysis'])
const STEP_LABELS: Record<string, string> = {
  welcome: '开始使用', import_data: '导入与检查数据', workspace: '项目工作区',
  build_plan: '建立分析计划', choose_method: '选择统计方法', review_plan: '审查分析计划',
  run_analysis: '执行分析', interpret_results: '解释分析结果', calibration: '数据校正',
}
const PRESETS: Record<string, PresetPrompt[]> = {
  import_data: [
    { label: '检查数据是否可分析', prompt: '请检查当前数据画像，指出会阻止或影响后续分析的问题，并按优先级给出处理建议。', contexts: ['data'] },
    { label: '解释缺失与重复', prompt: '请解释当前数据中的缺失、重复行和列类型意味着什么，哪些问题需要先处理？', contexts: ['data'] },
    { label: '告诉我下一步', prompt: '结合当前导入状态，告诉我下一步最应该做什么。', contexts: ['data'] },
  ],
  build_plan: [
    { label: '评估当前方法', prompt: '请明确判断当前统计方法是否适合这份数据和变量角色，并说明证据。', contexts: ['data', 'plan'] },
    { label: '给出修改清单', prompt: '请把当前分析计划中需要修改或核对的设置列成有优先级的操作清单。', contexts: ['data', 'plan'] },
    { label: '检查变量角色', prompt: '请检查因变量、因素、协变量、对象 ID 和重复因素的分配是否合理。', contexts: ['data', 'plan'] },
    { label: '比较替代方法', prompt: '当前方法有哪些真正相关的替代方案？请说明各自在什么条件下更合适。', contexts: ['data', 'plan'] },
  ],
  review_plan: [
    { label: '评估当前方法', prompt: '请明确判断当前统计方法是否合理，给出结论、依据和必须修改的项目。', contexts: ['data', 'plan'] },
    { label: '解释风险项', prompt: '请解释当前设计审查中的风险项，以及每一项会怎样影响结果。', contexts: ['data', 'plan'] },
    { label: '生成执行前清单', prompt: '请生成一份可以逐项确认的执行前检查清单。', contexts: ['data', 'plan'] },
  ],
  run_analysis: [
    { label: '解释预检问题', prompt: '请解释当前分析计划最可能在预检中遇到的问题，以及如何修正。', contexts: ['data', 'plan'] },
    { label: '确认能否执行', prompt: '请判断当前计划是否已经可以执行，并列出仍未确认的条件。', contexts: ['data', 'plan'] },
  ],
  interpret_results: [
    { label: '总结核心结论', prompt: '请用研究者容易理解的语言总结当前结果，并区分统计证据与实际意义。', contexts: ['plan', 'result'] },
    { label: '解释效应量和区间', prompt: '请解释当前结果中的效应量和置信区间，避免只依据 p 值下结论。', contexts: ['plan', 'result'] },
    { label: '检查过度解读', prompt: '请检查我可能对当前结果做出的过度解读，并说明结论边界。', contexts: ['plan', 'result'] },
    { label: '建议下一步分析', prompt: '基于当前结果，建议下一步最有价值的核对或补充分析。', contexts: ['data', 'plan', 'result'] },
  ],
}

const panelStyle = computed(() => mobileMode.value || minimized.value || expanded.value ? {} : {
  left: `${geometry.value.x}px`, top: `${geometry.value.y}px`,
  width: `${geometry.value.width}px`, height: `${geometry.value.height}px`,
})
const isPlanStep = computed(() => PLAN_STEPS.has(props.step))
const methodLabel = computed(() => String(props.context.selected_method_label || props.context.selected_method || '未选择'))
const presets = computed(() => PRESETS[props.step] ?? (isPlanStep.value ? PRESETS.build_plan : PRESETS.import_data))
const aiReportAvailable = computed(() => Boolean(
  props.aiReport
  && ['ai', 'ai_guard_partial'].includes(String(props.aiReport.source || ''))
  && props.resultContextId
  && props.resultContextId === props.aiReportContextId,
))
const resultTimestampValue = computed(() => String(props.resultTimestamp || '').trim())
const resultTimestampLabel = computed(() => formatResultTimestamp(resultTimestampValue.value))
const availableContexts = computed(() => [
  { key: 'data' as const, label: '数据画像', description: '样本量、列类型与缺失概况', available: Boolean(props.context.data_profile) },
  { key: 'plan' as const, label: '分析计划', description: '统计方法、变量角色与关键参数', available: Boolean(props.context.data_profile && props.context.selected_method) },
  { key: 'result' as const, label: '当前分析结果', description: '规范表、效应量与前提检验', available: Boolean(props.result) },
  { key: 'aiReport' as const, label: 'AI 生成的文字报告', description: '仅作为已生成结论的解释材料', available: aiReportAvailable.value },
])
const selectedContextCount = computed(() => availableContexts.value
  .filter(item => item.available && selectedContext.value[item.key]).length)
const selectedContextLabel = computed(() => availableContexts.value
  .filter(item => item.available && selectedContext.value[item.key])
  .map(item => item.key === 'result'
    ? `当前分析结果（${resultScope.value === 'full_result' ? '完整结果与诊断' : '规范化证据'}${includeOrdering.value ? '，含组别排序' : ''}）`
    : item.label).join('、') || '未选择额外依据')
const liveContextItems = computed(() => [
  ['模式', props.context.mode === 'workspace' ? '项目工作区' : '即时分析'],
  ['方法', methodLabel.value],
  ['因变量', summarizeSelection(props.context.dependent_variables)],
  ['因素', summarizeSelection(props.context.fixed_factors)],
  ['拆分列', summarizeSelection(props.context.split_by)],
  ['结果状态', props.result ? '已完成，可用于问答' : '尚无分析结果'],
])

onMounted(() => {
  restoreGeometry()
  updateViewport()
  applyInitialContextDefaults()
  window.addEventListener('resize', updateViewport)
  window.addEventListener('pointermove', movePanel)
  window.addEventListener('pointerup', endPointerAction)
  window.addEventListener('pointercancel', endPointerAction)
})

onBeforeUnmount(() => {
  requestId += 1
  window.removeEventListener('resize', updateViewport)
  window.removeEventListener('pointermove', movePanel)
  window.removeEventListener('pointerup', endPointerAction)
  window.removeEventListener('pointercancel', endPointerAction)
})

watch(() => props.step, (current, previous) => {
  question.value = ''
  if (previous && current !== previous && messages.value.length) {
    messages.value.push({ id: ++messageId, role: 'system', text: `工作流已切换到“${STEP_LABELS[current] ?? current}”，后续问题将使用新的上下文。` })
    scrollToLatest()
  }
})

watch(() => props.open, open => {
  if (!open) return
  minimized.value = false
  clampGeometry()
  scrollToLatest()
})

watch(() => Boolean(props.context.data_profile), (available, wasAvailable) => {
  if (available && !wasAvailable) applyInitialContextDefaults()
})

function applyInitialContextDefaults() {
  const hasData = Boolean(props.context.data_profile)
  if (!hasData || dataDefaultApplied) return
  selectedContext.value = {
    data: true,
    plan: false,
    result: false,
    aiReport: false,
  }
  dataDefaultApplied = true
}

function summarizeSelection(value: unknown) {
  if (!Array.isArray(value) || !value.length) return '未选择'
  const labels = value.map(item => String(item)).filter(Boolean)
  if (labels.length <= 3) return labels.join('、')
  return `${labels.slice(0, 3).join('、')} 等 ${labels.length} 项`
}

function formatResultTimestamp(value: string) {
  if (!value) return '时间未记录'
  const timestamp = new Date(value)
  if (Number.isNaN(timestamp.getTime())) return value
  const twoDigits = (part: number) => String(part).padStart(2, '0')
  return `${timestamp.getFullYear()}-${twoDigits(timestamp.getMonth() + 1)}-${twoDigits(timestamp.getDate())} ${twoDigits(timestamp.getHours())}:${twoDigits(timestamp.getMinutes())}:${twoDigits(timestamp.getSeconds())}`
}

function toggleContext(key: ContextKey) {
  const item = availableContexts.value.find(candidate => candidate.key === key)
  if (!item?.available) return
  selectedContext.value = { ...selectedContext.value, [key]: !selectedContext.value[key] }
}

function contextEnabled(key: ContextKey) {
  return Boolean(
    selectedContext.value[key]
    && availableContexts.value.find(item => item.key === key)?.available
  )
}

function defaultGeometry() {
  const width = Math.min(440, window.innerWidth - 24)
  return { x: Math.max(12, window.innerWidth - width - 12), y: 12, width, height: Math.min(760, window.innerHeight - 24) }
}

function restoreGeometry() {
  geometry.value = defaultGeometry()
  try {
    const saved = JSON.parse(localStorage.getItem('datawork.ai-assistant-panel.v5') || 'null')
    if (saved && [saved.x, saved.y, saved.width, saved.height].every(Number.isFinite)) geometry.value = saved
  } catch { /* 使用默认位置。 */ }
  clampGeometry()
}

function persistGeometry() {
  try { localStorage.setItem('datawork.ai-assistant-panel.v5', JSON.stringify(geometry.value)) } catch { /* 不影响助手使用。 */ }
}

function updateViewport() {
  mobileMode.value = window.matchMedia('(max-width: 760px)').matches
  clampGeometry()
}

function clampGeometry() {
  if (mobileMode.value || expanded.value) return
  const width = Math.min(Math.max(geometry.value.width, 380), window.innerWidth - 24)
  const height = Math.min(Math.max(geometry.value.height, 420), window.innerHeight - 24)
  geometry.value = {
    width, height,
    x: Math.min(Math.max(geometry.value.x, 12), window.innerWidth - width - 12),
    y: Math.min(Math.max(geometry.value.y, 12), window.innerHeight - (minimized.value ? 70 : height) - 12),
  }
}

function startDrag(event: PointerEvent) {
  if (mobileMode.value || expanded.value || event.button !== 0 || (event.target as HTMLElement).closest('button')) return
  pointerAction = { mode: 'drag', x: event.clientX, y: event.clientY, start: { ...geometry.value }, pointerId: event.pointerId }
  detached.value = true
  panelRef.value?.setPointerCapture?.(event.pointerId)
  event.preventDefault()
}

function startResize(event: PointerEvent) {
  if (mobileMode.value || minimized.value || expanded.value || event.button !== 0) return
  pointerAction = { mode: 'resize', x: event.clientX, y: event.clientY, start: { ...geometry.value }, pointerId: event.pointerId }
  detached.value = true
  panelRef.value?.setPointerCapture?.(event.pointerId)
  event.preventDefault()
}

function movePanel(event: PointerEvent) {
  if (!pointerAction || event.pointerId !== pointerAction.pointerId) return
  const dx = event.clientX - pointerAction.x
  const dy = event.clientY - pointerAction.y
  geometry.value = pointerAction.mode === 'drag'
    ? { ...pointerAction.start, x: pointerAction.start.x + dx, y: pointerAction.start.y + dy }
    : { ...pointerAction.start, width: pointerAction.start.width + dx, height: pointerAction.start.height + dy }
  clampGeometry()
}

function endPointerAction(event?: PointerEvent) {
  if (!pointerAction || (event && event.pointerId !== pointerAction.pointerId)) return
  pointerAction = null
  persistGeometry()
}

function toggleExpanded() {
  expanded.value = !expanded.value
  minimized.value = false
  if (!expanded.value) clampGeometry()
}

function filteredContext() {
  const context = props.context ?? {}
  const output: Record<string, unknown> = {
    mode: context.mode, workflow_step: props.step, workflow_progress: context.workflow_progress,
    interface_mode: context.interface_mode,
  }
  if (contextEnabled('data')) {
    output.source_name = context.source_name
    output.data_profile = context.data_profile
  }
  if (contextEnabled('plan')) {
    const keys = [
      'selected_method', 'selected_method_label', 'dependent_variables', 'fixed_factors', 'covariates',
      'random_factors', 'random_slopes', 'estimate_marginal_means', 'emm_factors', 'subject_id',
      'repeated_factor', 'split_by', 'split_rules', 'method_parameters', 'factor_combinations_enabled',
      'factor_combination_order', 'factor_combination_min_order', 'factor_combination_max_order',
      'factor_combination_labels', 'dependent_task_mode', 'dependent_combination_min_size',
      'dependent_combination_max_size', 'dependent_combination_labels',
      'combination_p_adjust', 'calibration_enabled', 'calibration_method',
      'calibration_columns', 'alpha', 'ss_type', 'run_id', 'project',
    ]
    for (const key of keys) output[key] = context[key]
  }
  output.result_available = Boolean(contextEnabled('result') && props.result)
  output.result_context_id = props.resultContextId || ''
  return output
}

async function sendPreset(preset: PresetPrompt) {
  await sendQuestion(preset.prompt)
}

async function sendQuestion(text = question.value) {
  const prompt = text.trim()
  if (!prompt || loading.value) return
  const currentRequest = ++requestId
  const contextSnapshot = filteredContext()
  const resultSnapshot = props.result ?? {}
  const selectionSnapshot = {
    data_profile: contextEnabled('data'),
    analysis_plan: contextEnabled('plan'),
    current_result: contextEnabled('result'),
    result_scope: resultScope.value,
    include_ordering: includeOrdering.value,
    ai_report: contextEnabled('aiReport'),
  }
  const aiReportSnapshot = contextEnabled('aiReport') ? props.aiReport : null
  const contextLabel = selectedContextLabel.value
  messages.value.push({ id: ++messageId, role: 'user', text: prompt, contextLabel })
  question.value = ''
  loading.value = true
  error.value = ''
  errorCode.value = ''
  let responseAdded = false
  scrollToLatest()
  try {
    const body = {
      question: prompt,
      context: contextSnapshot,
      result: contextEnabled('result') ? resultSnapshot : {},
      selection: selectionSnapshot,
      ai_report: aiReportSnapshot,
      result_context_id: props.resultContextId || '',
      ai_report_context_id: props.aiReportContextId || '',
    }
    const payload = await apiRequest('/api/ai/ask', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }, '问答请求失败')
    if (currentRequest === requestId) {
      messages.value.push({ id: ++messageId, role: 'assistant', payload, contextLabel })
      responseAdded = true
    }
  } catch (cause) {
    if (currentRequest === requestId) {
      error.value = errorMessage(cause)
      errorCode.value = cause && typeof cause === 'object' && 'code' in cause
        ? String((cause as any).code || '')
        : ''
    }
  } finally {
    if (currentRequest === requestId) loading.value = false
    scrollToLatest(responseAdded)
  }
}

function handleComposerKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  void sendQuestion()
}

function renderMarkdown(value: unknown) {
  const markdown = typeof value === 'string' ? value : ''
  return DOMPurify.sanitize(marked.parse(markdown, { breaks: true, gfm: true }) as string)
}

async function scrollToLatest(showResponseStart = false) {
  await nextTick()
  const list = messageListRef.value
  if (!list) return
  if (!messages.value.length) {
    list.scrollTop = 0
    return
  }
  if (showResponseStart) {
    const responses = list.querySelectorAll<HTMLElement>('.assistant-response-message')
    const latest = responses.item(responses.length - 1)
    if (latest) {
      list.scrollTop = Math.max(0, latest.offsetTop - list.offsetTop - 8)
      return
    }
  }
  list.scrollTop = list.scrollHeight
}

function clearConversation() {
  if (loading.value) return
  messages.value = []
  error.value = ''
  errorCode.value = ''
}
</script>

<template>
  <div v-if="open" class="assistant-side-layer">
    <aside ref="panelRef" class="assistant-drawer assistant-side-panel" :class="{ minimized, detached, expanded }" :style="panelStyle" aria-label="AI 小助手">
      <button v-if="minimized" class="assistant-collapsed-bubble" type="button" aria-label="展开 AI 小助手" title="展开 AI 小助手" @click="minimized = false">AI</button>
      <header v-else class="assistant-head assistant-simple-drag" title="拖动标题栏移动助手" @pointerdown="startDrag">
        <div class="assistant-brand-mark" aria-hidden="true">AI</div>
        <div class="assistant-title-block">
          <p class="assistant-kicker">DataWork</p>
          <h2>AI 小助手</h2>
          <small><span aria-hidden="true">✓</span> 统计值由本地计算锁定</small>
        </div>
        <div class="assistant-window-actions">
          <button v-if="!mobileMode" class="icon-button" :aria-label="expanded ? '恢复悬浮尺寸' : '展开 AI 小助手'" :title="expanded ? '恢复悬浮尺寸' : '展开为右侧大窗'" @click="toggleExpanded">{{ expanded ? '↙' : '□' }}</button>
          <button class="icon-button" aria-label="收起 AI 小助手" title="收起为小圆钮" @click="minimized = true">−</button>
          <button class="icon-button" aria-label="关闭 AI 小助手" title="关闭" @click="emit('close')">×</button>
        </div>
      </header>

      <template v-if="!minimized">
        <details class="assistant-context-picker">
          <summary>
            <span class="assistant-context-summary-title"><strong>回答依据</strong><small>{{ selectedContextCount }} 项已启用</small></span>
            <span class="assistant-context-summary-value" :title="selectedContextLabel">{{ selectedContextLabel }}</span>
          </summary>
          <div class="assistant-context-body">
            <div class="assistant-context-choices" role="group" aria-label="选择发送给助手的上下文">
              <button v-for="item in availableContexts" :key="item.key" type="button" :disabled="!item.available" :class="{ active: item.available && selectedContext[item.key] }" :aria-pressed="item.available && selectedContext[item.key]" @click="toggleContext(item.key)">
                <span class="assistant-context-indicator" aria-hidden="true">{{ selectedContext[item.key] ? '✓' : '+' }}</span>
                <span class="assistant-context-choice-copy">
                  <strong>{{ item.label }}</strong>
                  <small>{{ item.description }}</small>
                  <time v-if="item.key === 'result' && item.available" class="assistant-result-timestamp" :datetime="resultTimestampValue || undefined" :title="resultTimestampValue || '未记录原始时间'">结果时间 {{ resultTimestampLabel }}</time>
                </span>
                <span class="assistant-context-choice-state">{{ !item.available ? '不可用' : selectedContext[item.key] ? '已选择' : '未选择' }}</span>
              </button>
            </div>
            <fieldset v-if="selectedContext.result && availableContexts.find(item => item.key === 'result')?.available" class="assistant-result-scope">
              <legend>结果证据范围</legend>
              <label><input v-model="resultScope" type="radio" value="normative_evidence"><span><strong>规范化证据（默认）</strong><small>三张规范表、效应量与前提检验。</small></span></label>
              <label><input v-model="resultScope" type="radio" value="full_result"><span><strong>完整结果与诊断</strong><small>追加拟合、警告、系数、可复现信息与失败任务。</small></span></label>
              <label class="assistant-ordering-toggle"><input v-model="includeOrdering" type="checkbox"><span><strong>组别排序（A &gt; B &gt; C）</strong><small>发送只读排序，便于总结稳定规律；不代表组间必然显著。</small></span></label>
            </fieldset>
            <details class="assistant-context-facts">
              <summary><span>当前工作流信息</span><small>{{ methodLabel }}</small></summary>
              <dl><template v-for="item in liveContextItems" :key="item[0]"><dt>{{ item[0] }}</dt><dd>{{ item[1] }}</dd></template></dl>
            </details>
            <p class="assistant-privacy-note"><strong>隐私提示</strong><span>原始数据行默认不发送。每条回答保留发送时的依据快照。</span></p>
          </div>
        </details>

        <div class="assistant-preset-bar" aria-label="当前工作流的快捷提问">
          <span>可直接提问</span>
          <div><button v-for="preset in presets" :key="preset.label" type="button" :disabled="loading" @click="sendPreset(preset)">{{ preset.label }}</button></div>
        </div>

        <div class="assistant-chat-shell">
          <div ref="messageListRef" class="assistant-message-list" aria-live="polite">
            <template v-for="message in messages" :key="message.id">
              <div v-if="message.role === 'system'" class="assistant-system-message">{{ message.text }}</div>
              <article v-else-if="message.role === 'user'" class="assistant-message user-message">
                <div class="assistant-message-meta"><strong>你</strong><small>上下文：{{ message.contextLabel }}</small></div>
                <p>{{ message.text }}</p>
              </article>
              <article v-else class="assistant-message assistant-response-message">
                <div class="assistant-message-meta"><strong>{{ message.payload?.source === 'ai' ? 'AI 回答' : '系统提示' }}</strong><small v-if="message.payload?.model">{{ message.payload.provider }} · {{ message.payload.model }}</small><small v-else>{{ message.contextLabel }}</small></div>
                <section v-if="message.payload?.context_basis?.items?.length || message.payload?.context_basis?.warning" class="assistant-context-basis">
                  <strong>本回答依据</strong>
                  <div v-if="message.payload?.context_basis?.items?.length"><span v-for="item in message.payload.context_basis.items" :key="item.key">{{ item.label }}</span></div>
                  <p v-if="message.payload?.context_basis?.warning">{{ message.payload.context_basis.warning }}</p>
                  <small v-if="message.payload?.context_basis?.raw_rows_sent === false">未发送原始数据行</small>
                </section>
                <div class="assistant-markdown" v-html="renderMarkdown(message.payload?.answer_markdown)"></div>
                <small v-if="message.payload?.ai_access?.configuration_source === 'server' && !message.payload?.ai_access?.owner_authenticated" class="assistant-quota-note">服务器免费额度：剩余 {{ message.payload.ai_access.guest_quota?.remaining ?? 0 }} / {{ message.payload.ai_access.guest_quota?.limit ?? 10 }}，首次提问满 24 小时重置</small>
                <div class="assistant-inline-note" v-if="message.payload?.warning">{{ message.payload.warning }}</div>
                <button v-if="message.payload?.setup_required" class="text-button" @click="emit('settings')">打开 AI 设置</button>
              </article>
            </template>

            <div v-if="loading" class="assistant-loading" role="status"><span class="inline-spinner"></span><div><strong>正在结合当前上下文整理建议</strong><p>你可以继续查看之前的回答。</p></div></div>
            <div class="alert assistant-quota-alert" v-if="error">
              <span>{{ error }}</span>
              <div v-if="errorCode === 'ai_free_quota_exhausted'" class="assistant-quota-actions">
                <button type="button" class="primary" @click="emit('authenticate')">验证工作区密码</button>
                <button type="button" class="secondary" @click="emit('settings')">填写自己的 API</button>
              </div>
            </div>
          </div>

          <div class="assistant-chat-composer">
            <div class="assistant-composer-head"><label for="assistant-question-input">继续提问</label><span>{{ selectedContextCount }} 项回答依据</span></div>
            <textarea id="assistant-question-input" v-model="question" aria-describedby="assistant-composer-help" :placeholder="step === 'interpret_results' ? '询问显著性、效应量、组别关系或结论边界…' : isPlanStep ? '例如：哪些设置需要修改，为什么？' : '例如：现在最需要检查什么？'" @keydown="handleComposerKeydown"></textarea>
            <div class="assistant-question-actions"><small id="assistant-composer-help">Enter 发送，Shift + Enter 换行</small><button class="primary" :disabled="loading || !question.trim()" @click="sendQuestion()">{{ loading ? '整理中…' : '发送' }}</button></div>
          </div>
        </div>

        <footer class="assistant-footer"><span>统计证据只读</span><div><button v-if="messages.length" class="text-button" :disabled="loading" @click="clearConversation">清空对话</button><button class="text-button" @click="emit('settings')">AI 设置</button></div></footer>
        <button v-if="!expanded" class="assistant-corner-resize" type="button" aria-label="调整 AI 小助手大小" title="拖动调整大小" @pointerdown="startResize"></button>
      </template>
    </aside>
  </div>
</template>
