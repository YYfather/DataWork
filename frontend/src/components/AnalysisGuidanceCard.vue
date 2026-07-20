<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { apiRequest, errorMessage } from '../api'

const props = defineProps<{
  context: Record<string, unknown>
}>()

const guidance = ref<any>(null)
const loading = ref(false)
const error = ref('')
let timer: ReturnType<typeof setTimeout> | null = null
let requestId = 0

const canExplain = computed(() => Boolean(String(props.context.selected_method ?? '')))

watch(
  () => JSON.stringify(props.context),
  () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(loadGuidance, 250)
  },
  { immediate: true },
)

onBeforeUnmount(() => { if (timer) clearTimeout(timer) })

async function loadGuidance() {
  if (!canExplain.value) {
    guidance.value = null
    return
  }
  const currentRequest = ++requestId
  loading.value = true
  error.value = ''
  try {
    const payload = await apiRequest('/api/ai/explain/analysis-plan', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ context: props.context, use_ai: false }),
    }, '分析说明生成失败')
    if (currentRequest !== requestId) return
    guidance.value = payload.guidance
    if (payload.warning) error.value = payload.warning
  } catch (cause) {
    if (currentRequest !== requestId) return
    error.value = errorMessage(cause)
  } finally {
    if (currentRequest === requestId) loading.value = false
  }
}
</script>

<template>
  <section class="analysis-guidance-card compact-guidance" v-if="canExplain">
    <div class="analysis-guidance-head">
      <div>
        <p class="eyebrow">ANALYSIS SUMMARY</p>
        <h3>分析目的与预期效果</h3>
      </div>
      <span v-if="guidance" class="guidance-verdict" :class="guidance.suitability_status">{{ guidance.suitability_label }}</span>
    </div>

    <div v-if="guidance" class="guidance-summary-grid">
      <article class="guidance-primary">
        <span>分析目的</span>
        <p>{{ guidance.analysis_purpose }}</p>
      </article>
      <article class="guidance-primary expected">
        <span>预期效果（Expected Outcome）</span>
        <p>{{ guidance.expected_outcome }}</p>
      </article>
    </div>
    <div v-else class="guidance-placeholder" :class="{ loading }"><span v-if="loading" class="inline-spinner small"></span>{{ loading ? '正在生成当前分析摘要…' : '请选择统计方法后查看说明。' }}</div>
    <div v-if="guidance?.design_review_summary" class="guidance-design-review">
      <span>统计设计审查</span>
      <p v-if="guidance.suitability_reason"><strong>结论：</strong>{{ guidance.suitability_reason }}</p>
      <p>{{ guidance.design_review_summary }}</p>
      <div class="guidance-review-lists">
        <ul v-if="guidance.design_checks?.length"><li v-for="item in guidance.design_checks.slice(0, 3)" :key="item">{{ item }}</li></ul>
        <ul v-if="guidance.recommended_actions?.length" class="actions"><li v-for="item in guidance.recommended_actions.slice(0, 2)" :key="item">{{ item }}</li></ul>
      </div>
    </div>
    <div class="guide-warning" v-if="error">{{ error }}</div>
  </section>
</template>
