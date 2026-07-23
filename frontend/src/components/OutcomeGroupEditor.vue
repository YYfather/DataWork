<script setup lang="ts">
import { computed } from 'vue'

type OutcomeGroupDraft = { name: string; dependent_variables: string[] }
type DependentTaskMode = 'joint_all' | 'manual_groups' | 'combinations'
const props = defineProps<{
  modelValue: OutcomeGroupDraft[]
  dependentVariables: string[]
  minimumSize: number
  taskMode: DependentTaskMode
  combinationMinSize: number
  combinationMaxSize: number
  combinationLabels: Record<string, string>
  busy?: boolean
}>()
const emit = defineEmits<{
  'update:modelValue': [value: OutcomeGroupDraft[]]
  'update:taskMode': [value: DependentTaskMode]
  'update:combinationMinSize': [value: number]
  'update:combinationMaxSize': [value: number]
  'update:combinationLabels': [value: Record<string, string>]
}>()

function choose(total: number, selected: number) {
  if (selected < 0 || selected > total) return 0
  let value = 1
  for (let index = 1; index <= selected; index += 1) {
    value = value * (total - selected + index) / index
  }
  return Math.round(value)
}

function enumerate(values: string[], size: number, limit = 24) {
  const output: string[] = []
  const visit = (start: number, selected: string[]) => {
    if (output.length >= limit) return
    if (selected.length === size) {
      output.push(selected.join(' + '))
      return
    }
    for (let index = start; index < values.length; index += 1) {
      visit(index + 1, [...selected, values[index]])
      if (output.length >= limit) return
    }
  }
  visit(0, [])
  return output
}

const combinationCount = computed(() => {
  let count = 0
  for (let size = props.combinationMinSize; size <= props.combinationMaxSize; size += 1) {
    count += choose(props.dependentVariables.length, size)
  }
  return count
})
const combinationPreview = computed(() => {
  const output: string[] = []
  for (let size = props.combinationMinSize; size <= props.combinationMaxSize; size += 1) {
    output.push(...enumerate(props.dependentVariables, size, Math.max(0, 12 - output.length)))
    if (output.length >= 12) break
  }
  return output
})
const combinationNameIssues = computed(() => {
  const labels = combinationPreview.value.map(name => props.combinationLabels[name]?.trim() || name)
  return labels.length !== new Set(labels).size
    ? ['因变量组合名称不能重复，也不能与其他组合的默认名称相同']
    : []
})

const issues = computed(() => {
  if (!props.modelValue.length) return []
  const assigned = props.modelValue.flatMap(item => item.dependent_variables)
  const output: string[] = []
  if (props.modelValue.some(item => !item.name.trim())) output.push('每个联合因变量组都必须命名')
  if (new Set(props.modelValue.map(item => item.name.trim())).size !== props.modelValue.length) output.push('联合因变量组名称不能重复')
  if (props.modelValue.some(item => item.dependent_variables.length < props.minimumSize)) output.push(`每组至少需要 ${props.minimumSize} 个因变量`)
  if (new Set(assigned).size !== assigned.length) output.push('同一因变量不能重复进入多个组')
  const missing = props.dependentVariables.filter(item => !assigned.includes(item))
  if (missing.length) output.push(`尚未分组：${missing.join('、')}`)
  return output
})

function updateGroup(index: number, values: Partial<OutcomeGroupDraft>) {
  emit('update:modelValue', props.modelValue.map((item, itemIndex) => itemIndex === index ? { ...item, ...values } : item))
}
function addGroup() { emit('update:modelValue', [...props.modelValue, { name: `组 ${props.modelValue.length + 1}`, dependent_variables: [] }]) }
function removeGroup(index: number) { emit('update:modelValue', props.modelValue.filter((_, itemIndex) => itemIndex !== index)) }
function toggleVariable(groupIndex: number, variable: string) {
  const alreadyHere = props.modelValue[groupIndex]?.dependent_variables.includes(variable)
  const next = props.modelValue.map((item, itemIndex) => ({
    ...item,
    dependent_variables: itemIndex === groupIndex
      ? (alreadyHere ? item.dependent_variables.filter(value => value !== variable) : [...item.dependent_variables.filter(value => value !== variable), variable])
      : item.dependent_variables.filter(value => value !== variable),
  }))
  emit('update:modelValue', next)
}
function autoArrange() {
  if (!props.dependentVariables.length) return
  const groups: OutcomeGroupDraft[] = []
  for (let index = 0; index < props.dependentVariables.length; index += props.minimumSize) {
    const chunk = props.dependentVariables.slice(index, index + props.minimumSize)
    if (chunk.length < props.minimumSize && groups.length) groups[groups.length - 1].dependent_variables.push(...chunk)
    else groups.push({ name: `组 ${groups.length + 1}`, dependent_variables: chunk })
  }
  emit('update:modelValue', groups)
}
function setMode(mode: DependentTaskMode) {
  if (mode === 'combinations' && props.taskMode !== 'combinations') {
    const accepted = window.confirm(
      '自动因变量组合会重复使用同一因变量并生成多个独立 MANOVA 模型。'
      + '系统将按组合、因素模型和拆分组计算总任务数，并默认进行跨模型 Holm 校正。是否启用？',
    )
    if (!accepted) return
  }
  emit('update:taskMode', mode)
  if (mode !== 'manual_groups') emit('update:modelValue', [])
}
function updateMinimum(value: number) {
  const minimum = Math.max(props.minimumSize, Math.min(value, props.dependentVariables.length))
  emit('update:combinationMinSize', minimum)
  if (props.combinationMaxSize < minimum) emit('update:combinationMaxSize', minimum)
}
function updateMaximum(value: number) {
  emit('update:combinationMaxSize', Math.max(props.combinationMinSize, Math.min(value, props.dependentVariables.length)))
}
function setCombinationLabel(name: string, value: string) {
  emit('update:combinationLabels', { ...props.combinationLabels, [name]: value })
}
</script>

<template>
  <div class="outcome-group-editor">
    <div class="group-toolbar"><div><strong>联合响应任务</strong><small>选择全部联合、手工互斥分组或自动生成可重叠的因变量组合。</small></div></div>
    <div class="outcome-mode-options" role="group" aria-label="联合响应任务模式">
      <button type="button" class="choice" :class="{ active: taskMode === 'joint_all' }" :disabled="busy" @click="setMode('joint_all')">全部联合一次</button>
      <button type="button" class="choice" :class="{ active: taskMode === 'manual_groups' }" :disabled="busy" @click="setMode('manual_groups')">手工分组</button>
      <button type="button" class="choice" :class="{ active: taskMode === 'combinations' }" :disabled="busy || dependentVariables.length < minimumSize" @click="setMode('combinations')">自动因变量组合</button>
    </div>
    <p class="mode-note" v-if="taskMode === 'joint_all'">当前 {{ dependentVariables.length }} 个因变量共同进入一次 MANOVA。</p>
    <template v-if="taskMode === 'manual_groups'">
      <div class="group-toolbar"><div><strong>手工联合因变量组</strong><small>每个因变量必须且只能进入一个组。</small></div><div><button type="button" class="text-button" :disabled="busy || !dependentVariables.length" @click="autoArrange">按顺序自动整理</button><button type="button" class="secondary compact" :disabled="busy" @click="addGroup">添加组</button></div></div>
      <article v-for="(group, index) in modelValue" :key="index"><div class="group-head"><input :value="group.name" :disabled="busy" maxlength="120" aria-label="联合因变量组名称" @input="updateGroup(index, { name: ($event.target as HTMLInputElement).value })" /><button type="button" class="text-button danger-text" :disabled="busy" @click="removeGroup(index)">删除</button></div><div class="group-options"><button v-for="variable in dependentVariables" :key="variable" type="button" class="choice" :class="{ active: group.dependent_variables.includes(variable) }" :disabled="busy" @click="toggleVariable(index, variable)">{{ variable }}</button></div><small>已选 {{ group.dependent_variables.length }} 个；至少 {{ minimumSize }} 个。</small></article>
      <p class="selection-warning" v-for="issue in issues" :key="issue">{{ issue }}</p>
    </template>
    <template v-if="taskMode === 'combinations'">
      <section class="combination-card">
        <div class="combination-range">
          <label>最小组合大小<select :value="combinationMinSize" :disabled="busy" @change="updateMinimum(Number(($event.target as HTMLSelectElement).value))"><option v-for="size in dependentVariables.length" :key="`min-${size}`" :value="size" :disabled="size < minimumSize">{{ size }}</option></select></label>
          <label>最大组合大小<select :value="combinationMaxSize" :disabled="busy" @change="updateMaximum(Number(($event.target as HTMLSelectElement).value))"><option v-for="size in dependentVariables.length" :key="`max-${size}`" :value="size" :disabled="size < combinationMinSize">{{ size }}</option></select></label>
        </div>
        <div class="combination-estimate"><span>候选因变量</span><strong>{{ dependentVariables.length }}</strong><span>因变量组合</span><strong>{{ combinationCount }}</strong></div>
        <p>只生成无序组合；例如 Y1 + Y2 与 Y2 + Y1 只计算一次。同一因变量可以进入多个组合。</p>
        <details v-if="combinationPreview.length"><summary>组合预览与名称（前 {{ combinationPreview.length }} 个）</summary><div class="combination-name-list"><label v-for="name in combinationPreview" :key="name"><span>{{ name }}</span><input type="text" :value="combinationLabels[name] ?? ''" :placeholder="name" :aria-label="`因变量组合名称 ${name}`" @input="setCombinationLabel(name, ($event.target as HTMLInputElement).value)" /></label></div></details>
        <small v-if="combinationCount > combinationPreview.length">当前共 {{ combinationCount }} 个组合，预览仅展示前 {{ combinationPreview.length }} 个。</small>
        <p class="selection-warning" v-for="issue in combinationNameIssues" :key="issue">{{ issue }}</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.outcome-group-editor{display:grid;gap:10px}.group-toolbar,.group-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.group-toolbar>div:first-child{display:grid;gap:4px}.group-toolbar small,article>small,.mode-note,.combination-card p,.combination-card>small{color:var(--muted)}article,.combination-card{display:grid;gap:10px;padding:12px;border:1px solid var(--line);border-radius:12px}.group-head input{max-width:260px}.group-options,.outcome-mode-options{display:flex;flex-wrap:wrap;gap:8px}.combination-range{display:grid;grid-template-columns:repeat(2,minmax(150px,1fr));gap:10px}.combination-range label{display:grid;gap:6px}.combination-estimate{display:grid;grid-template-columns:1fr auto 1fr auto;gap:8px;align-items:center;padding:10px;border-radius:10px;background:var(--surface-soft)}.combination-name-list{display:grid;gap:8px;margin-top:10px}.combination-name-list label{display:grid;grid-template-columns:minmax(120px,1fr) minmax(180px,1fr);align-items:center;gap:10px}@media(max-width:700px){.group-toolbar{align-items:flex-start;flex-direction:column}.combination-range,.combination-name-list label{grid-template-columns:1fr}}
</style>
