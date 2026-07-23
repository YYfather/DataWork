<script setup lang="ts">
import { computed } from 'vue'

type OutcomeGroupDraft = { name: string; dependent_variables: string[] }
const props = defineProps<{ modelValue: OutcomeGroupDraft[]; dependentVariables: string[]; minimumSize: number; busy?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: OutcomeGroupDraft[]] }>()

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
</script>

<template>
  <div class="outcome-group-editor">
    <div class="group-toolbar"><div><strong>联合因变量组</strong><small>每组展开为一次独立联合分析；留空则保持全部因变量一次联合分析。</small></div><div><button type="button" class="text-button" :disabled="busy || !dependentVariables.length" @click="autoArrange">按顺序自动整理</button><button type="button" class="secondary compact" :disabled="busy" @click="addGroup">添加组</button></div></div>
    <article v-for="(group, index) in modelValue" :key="index"><div class="group-head"><input :value="group.name" :disabled="busy" maxlength="120" aria-label="联合因变量组名称" @input="updateGroup(index, { name: ($event.target as HTMLInputElement).value })" /><button type="button" class="text-button danger-text" :disabled="busy" @click="removeGroup(index)">删除</button></div><div class="group-options"><button v-for="variable in dependentVariables" :key="variable" type="button" class="choice" :class="{ active: group.dependent_variables.includes(variable) }" :disabled="busy" @click="toggleVariable(index, variable)">{{ variable }}</button></div><small>已选 {{ group.dependent_variables.length }} 个；至少 {{ minimumSize }} 个。</small></article>
    <p class="selection-warning" v-for="issue in issues" :key="issue">{{ issue }}</p>
  </div>
</template>

<style scoped>
.outcome-group-editor{display:grid;gap:10px}.group-toolbar,.group-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.group-toolbar>div:first-child{display:grid;gap:4px}.group-toolbar small,article>small{color:var(--muted)}article{display:grid;gap:10px;padding:12px;border:1px solid var(--line);border-radius:12px}.group-head input{max-width:260px}.group-options{display:flex;flex-wrap:wrap;gap:8px}@media(max-width:700px){.group-toolbar{align-items:flex-start;flex-direction:column}}
</style>
