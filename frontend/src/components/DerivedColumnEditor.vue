<script setup lang="ts">
import { computed, ref } from 'vue'

type ColumnProfile = { name: string; dtype: string; n_unique: number; n_missing: number }
type DerivedColumnDraft = { name: string; formula: string; source_columns: string[] }

const props = defineProps<{
  columns: ColumnProfile[]
  modelValue: DerivedColumnDraft[]
  warnings?: string[]
  busy?: boolean
}>()
const emit = defineEmits<{
  'update:modelValue': [value: DerivedColumnDraft[]]
  changed: []
}>()

const name = ref('')
const formula = ref('')
const editingIndex = ref<number | null>(null)
const localError = ref('')
const numericColumns = computed(() => props.columns.filter(column => /(^|\b)(u?int|float|double|decimal|number)/i.test(column.dtype)))
const MAX_SOURCE_COLUMNS = 10
const MAX_DERIVED_COLUMNS = 10

function references(expression: string) {
  return Array.from(expression.matchAll(/\[([^\[\]]+)\]/g), match => match[1].trim())
    .filter((item, index, values) => item && values.indexOf(item) === index)
}

function appendToken(token: string) {
  formula.value = `${formula.value}${formula.value && !formula.value.endsWith(' ') ? ' ' : ''}${token} `
  localError.value = ''
}

function clearDraft() {
  name.value = ''
  formula.value = ''
  editingIndex.value = null
  localError.value = ''
}

function save() {
  const cleanName = name.value.trim()
  const cleanFormula = formula.value.trim()
  const sources = references(cleanFormula)
  const expressionWithoutColumns = cleanFormula.replace(/\[[^\[\]]+\]/g, '')
  if (!cleanName) { localError.value = '请输入自定义列名称'; return }
  if (!cleanFormula || !sources.length) { localError.value = '请至少选择一个原始数值列'; return }
  if (sources.length > MAX_SOURCE_COLUMNS) { localError.value = `单个自定义列最多引用 ${MAX_SOURCE_COLUMNS} 个原始数值列`; return }
  if (editingIndex.value === null && props.modelValue.length >= MAX_DERIVED_COLUMNS) { localError.value = `一个分析计划最多创建 ${MAX_DERIVED_COLUMNS} 个自定义列`; return }
  if (!/^[\d\s+\-*/%.()]+$/.test(expressionWithoutColumns)) {
    localError.value = '公式只允许列、数字、基础运算符和括号'
    return
  }
  const originalNames = new Set(props.columns.map(column => column.name))
  if (originalNames.has(cleanName)) { localError.value = '自定义列不能覆盖原始列'; return }
  const duplicate = props.modelValue.findIndex((item, index) => item.name === cleanName && index !== editingIndex.value)
  if (duplicate >= 0) { localError.value = '自定义列名称不能重复'; return }
  const numericNames = new Set(numericColumns.value.map(column => column.name))
  const invalid = sources.filter(column => !numericNames.has(column))
  if (invalid.length) { localError.value = `只能引用原始数值列：${invalid.join('、')}`; return }

  const next = [...props.modelValue]
  const value = { name: cleanName, formula: cleanFormula, source_columns: sources }
  if (editingIndex.value === null) next.push(value)
  else next[editingIndex.value] = value
  emit('update:modelValue', next)
  emit('changed')
  clearDraft()
}

function edit(index: number) {
  const item = props.modelValue[index]
  name.value = item.name
  formula.value = item.formula
  editingIndex.value = index
  localError.value = ''
}

function remove(index: number) {
  const next = props.modelValue.filter((_, itemIndex) => itemIndex !== index)
  emit('update:modelValue', next)
  emit('changed')
  if (editingIndex.value === index) clearDraft()
}
</script>

<template>
  <div class="derived-column-editor">
    <div class="derived-list" v-if="modelValue.length">
      <article v-for="(item, index) in modelValue" :key="item.name">
        <div><strong>{{ item.name }}</strong><code>{{ item.formula }}</code><small>来源：{{ item.source_columns.join('、') }}</small></div>
        <div class="derived-actions"><button type="button" class="text-button" :disabled="busy" @click="edit(index)">编辑</button><button type="button" class="text-button danger-text" :disabled="busy" @click="remove(index)">删除</button></div>
      </article>
    </div>
    <div class="derived-builder">
      <label class="field"><span>新列名称</span><input v-model="name" :disabled="busy" maxlength="120" placeholder="例如：增长率" /></label>
      <label class="field derived-formula-field"><span>计算公式</span><input v-model="formula" :disabled="busy" maxlength="10000" placeholder="从下方选择列和运算符，可键入数值常量" /><small>最多引用 10 个原始数值列；结果实际保留 8 位小数；不能引用其他自定义列。</small></label>
      <div class="formula-palette">
        <div><strong>原始数值列</strong><button v-for="column in numericColumns" :key="column.name" type="button" class="formula-token" :disabled="busy" @click="appendToken(`[${column.name}]`)">{{ column.name }}</button></div>
        <div><strong>运算符与括号</strong><button v-for="token in ['+', '-', '*', '/', '**', '%', '(', ')']" :key="token" type="button" class="formula-token operator" :disabled="busy" @click="appendToken(token)">{{ token }}</button></div>
      </div>
      <p class="selection-warning" v-if="localError">{{ localError }}</p>
      <p class="selection-warning" v-for="warning in warnings ?? []" :key="warning">{{ warning }}</p>
      <div class="derived-editor-actions"><button type="button" class="secondary" :disabled="busy" @click="clearDraft">清空</button><button type="button" class="primary" :disabled="busy || (editingIndex === null && modelValue.length >= MAX_DERIVED_COLUMNS)" @click="save">{{ editingIndex === null ? '添加并预览' : '保存并预览' }}</button></div>
    </div>
  </div>
</template>
