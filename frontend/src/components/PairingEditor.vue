<script setup lang="ts">
import { computed, ref } from 'vue'

type ColumnProfile = { name: string; dtype: string; n_unique: number; n_missing: number; unique_values: string[] }
type PairMappingDraft = { treatment: string; control: string }
type PairDerivedColumnDraft = { id: string; name: string; source_column: string; formula: string; unit: string; decimal_places: number }
type PairingDraft = {
  group_column: string
  mappings: PairMappingDraft[]
  match_columns: string[]
  pair_id_column: string | null
  derived_columns: PairDerivedColumnDraft[]
}

const props = defineProps<{
  columns: ColumnProfile[]
  modelValue: PairingDraft | null
  ordinaryNames?: string[]
  busy?: boolean
}>()
const emit = defineEmits<{
  'update:modelValue': [value: PairingDraft | null]
  changed: []
}>()

const derivedName = ref('')
const derivedSource = ref('')
const derivedFormula = ref('')
const derivedUnit = ref('')
const derivedDecimalPlaces = ref(8)
const editingIndex = ref<number | null>(null)
const localError = ref('')

const numericColumns = computed(() => props.columns.filter(column => /(^|\b)(u?int|float|double|decimal|number)/i.test(column.dtype)))
const groupLevels = computed(() => props.columns.find(column => column.name === props.modelValue?.group_column)?.unique_values ?? [])
const structureIssues = computed(() => {
  const plan = props.modelValue
  if (!plan) return []
  const issues: string[] = []
  if (!plan.group_column) issues.push('请选择配对分组列')
  if (!plan.mappings.length) issues.push('至少添加一组处理—对照映射')
  if (!plan.derived_columns.length) issues.push('至少添加一个配对计算列')
  const treatments = plan.mappings.map(item => item.treatment).filter(Boolean)
  const controls = plan.mappings.map(item => item.control).filter(Boolean)
  if (treatments.length !== plan.mappings.length || controls.length !== plan.mappings.length) issues.push('每组映射都要选择处理和对照水平')
  if (new Set(treatments).size !== treatments.length) issues.push('处理水平不能重复映射')
  if (new Set(controls).size !== controls.length) issues.push('对照水平不能被复用')
  if (treatments.some(item => controls.includes(item))) issues.push('处理水平与对照水平不能重叠')
  return issues
})

function stableId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `pair-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function update(next: PairingDraft) {
  emit('update:modelValue', next)
  emit('changed')
}

function setEnabled(enabled: boolean) {
  if (!enabled) { emit('update:modelValue', null); emit('changed'); return }
  update({ group_column: '', mappings: [], match_columns: [], pair_id_column: null, derived_columns: [] })
}

function patch(values: Partial<PairingDraft>) {
  if (!props.modelValue) return
  update({ ...props.modelValue, ...values })
}

function selectGroup(column: string) {
  patch({ group_column: column, mappings: [], match_columns: props.modelValue?.match_columns.filter(item => item !== column) ?? [], pair_id_column: props.modelValue?.pair_id_column === column ? null : props.modelValue?.pair_id_column ?? null })
}

function addMapping() {
  if (!props.modelValue || props.modelValue.mappings.length >= 100) return
  patch({ mappings: [...props.modelValue.mappings, { treatment: '', control: '' }] })
}

function updateMapping(index: number, field: keyof PairMappingDraft, value: string) {
  if (!props.modelValue) return
  const mappings = props.modelValue.mappings.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item)
  patch({ mappings })
}

function removeMapping(index: number) {
  if (!props.modelValue) return
  patch({ mappings: props.modelValue.mappings.filter((_, itemIndex) => itemIndex !== index) })
}

function toggleMatch(column: string) {
  if (!props.modelValue || column === props.modelValue.group_column || column === props.modelValue.pair_id_column) return
  const selected = props.modelValue.match_columns.includes(column)
  patch({ match_columns: selected ? props.modelValue.match_columns.filter(item => item !== column) : [...props.modelValue.match_columns, column] })
}

function appendFormula(token: string) {
  derivedFormula.value = `${derivedFormula.value}${derivedFormula.value && !derivedFormula.value.endsWith(' ') ? ' ' : ''}${token} `
  localError.value = ''
}

function clearDerivedDraft() {
  derivedName.value = ''
  derivedSource.value = ''
  derivedFormula.value = ''
  derivedUnit.value = ''
  derivedDecimalPlaces.value = 8
  editingIndex.value = null
  localError.value = ''
}

function saveDerived() {
  if (!props.modelValue) return
  const name = derivedName.value.trim()
  const formula = derivedFormula.value.trim()
  const references = Array.from(formula.matchAll(/\[([^\[\]]+)\]/g), match => match[1].trim())
  if (!name || !derivedSource.value || !formula) { localError.value = '请填写新列名、来源指标和公式'; return }
  if (!references.length || references.some(item => !['处理值', '对照值'].includes(item))) { localError.value = '公式只能引用 [处理值] 和 [对照值]，且至少引用一个'; return }
  if (!/^[\d\s+\-*/.()]*$/.test(formula.replace(/\[[^\[\]]+\]/g, ''))) { localError.value = '公式只允许四则运算、数值和括号'; return }
  if (!Number.isInteger(derivedDecimalPlaces.value) || derivedDecimalPlaces.value < 0 || derivedDecimalPlaces.value > 8) { localError.value = '小数位数必须是 0 到 8 的整数'; return }
  if (editingIndex.value === null && props.modelValue.derived_columns.length >= 10) { localError.value = '一个配对方案最多生成 10 个计算列'; return }
  const forbidden = new Set([...props.columns.map(item => item.name), ...(props.ordinaryNames ?? [])])
  if (forbidden.has(name)) { localError.value = '新列名不能与原始列或普通自定义列重名'; return }
  if (props.modelValue.derived_columns.some((item, index) => item.name === name && index !== editingIndex.value)) { localError.value = '配对计算列名称不能重复'; return }
  const next = [...props.modelValue.derived_columns]
  const previous = editingIndex.value === null ? null : next[editingIndex.value]
  const value: PairDerivedColumnDraft = { id: previous?.id ?? stableId(), name, source_column: derivedSource.value, formula, unit: derivedUnit.value.trim(), decimal_places: derivedDecimalPlaces.value }
  if (editingIndex.value === null) next.push(value)
  else next[editingIndex.value] = value
  patch({ derived_columns: next })
  clearDerivedDraft()
}

function editDerived(index: number) {
  const item = props.modelValue?.derived_columns[index]
  if (!item) return
  derivedName.value = item.name
  derivedSource.value = item.source_column
  derivedFormula.value = item.formula
  derivedUnit.value = item.unit
  derivedDecimalPlaces.value = item.decimal_places
  editingIndex.value = index
}

function removeDerived(index: number) {
  if (!props.modelValue) return
  patch({ derived_columns: props.modelValue.derived_columns.filter((_, itemIndex) => itemIndex !== index) })
  if (editingIndex.value === index) clearDerivedDraft()
}
</script>

<template>
  <div class="pairing-editor">
    <label class="pairing-toggle"><input type="checkbox" :checked="Boolean(modelValue)" :disabled="busy" @change="setEnabled(($event.target as HTMLInputElement).checked)" /><span><strong>启用处理—对照配对计算</strong><small>整个计划改为一行一对的处理侧数据域；任何已配置映射不完整都会停止整次分析。</small></span></label>
    <template v-if="modelValue">
      <div class="pairing-grid">
        <label class="field"><span>配对分组列</span><select :value="modelValue.group_column" :disabled="busy" @change="selectGroup(($event.target as HTMLSelectElement).value)"><option value="">请选择</option><option v-for="column in columns" :key="column.name" :value="column.name">{{ column.name }}</option></select><small>例如脱叶剂喷施时间；配对后保留处理水平。</small></label>
        <label class="field"><span>重复样本对应</span><select :value="modelValue.pair_id_column ?? ''" :disabled="busy" @change="patch({ pair_id_column: ($event.target as HTMLSelectElement).value || null })"><option value="">按匹配组内原始导入行顺序</option><option v-for="column in columns.filter(item => item.name !== modelValue?.group_column && !modelValue?.match_columns.includes(item.name))" :key="column.name" :value="column.name">显式 ID：{{ column.name }}</option></select><small>显式 ID 缺失或重复会阻止执行；默认顺序不会受页面排序影响。</small></label>
      </div>

      <section class="pairing-block">
        <div class="pairing-block-head"><div><strong>处理—对照映射</strong><small>一一映射；对照不可复用。</small></div><button type="button" class="secondary compact" :disabled="busy || !modelValue.group_column" @click="addMapping">添加映射</button></div>
        <div class="mapping-row" v-for="(mapping, index) in modelValue.mappings" :key="index"><select :value="mapping.treatment" :disabled="busy" @change="updateMapping(index, 'treatment', ($event.target as HTMLSelectElement).value)"><option value="">处理水平</option><option v-for="level in groupLevels" :key="`t-${level}`" :value="level">{{ level }}</option></select><span>→</span><select :value="mapping.control" :disabled="busy" @change="updateMapping(index, 'control', ($event.target as HTMLSelectElement).value)"><option value="">对照水平</option><option v-for="level in groupLevels" :key="`c-${level}`" :value="level">{{ level }}</option></select><button type="button" class="text-button danger-text" :disabled="busy" @click="removeMapping(index)">删除</button></div>
      </section>

      <section class="pairing-block">
        <div class="pairing-block-head"><div><strong>匹配标签</strong><small>处理和对照必须在这些标签组合内一致；可同时用于拆分。</small></div></div>
        <div class="token-grid"><button v-for="column in columns.filter(item => item.name !== modelValue?.group_column && item.name !== modelValue?.pair_id_column)" :key="column.name" type="button" class="choice" :class="{ active: modelValue.match_columns.includes(column.name) }" :disabled="busy" @click="toggleMatch(column.name)">{{ column.name }}</button></div>
      </section>

      <section class="pairing-block">
        <div class="pairing-block-head"><div><strong>配对计算列</strong><small>{{ modelValue.derived_columns.length }}/10；结果最多保留 8 位小数。</small></div></div>
        <div class="pair-derived-list" v-if="modelValue.derived_columns.length"><article v-for="(item, index) in modelValue.derived_columns" :key="item.id"><div><strong>{{ item.name }}</strong><code>{{ item.formula }}</code><small>来源：{{ item.source_column }} · {{ item.decimal_places }} 位小数<template v-if="item.unit"> · 单位：{{ item.unit }}</template></small></div><div><button type="button" class="text-button" :disabled="busy" @click="editDerived(index)">编辑</button><button type="button" class="text-button danger-text" :disabled="busy" @click="removeDerived(index)">删除</button></div></article></div>
        <div class="pair-derived-builder"><label class="field"><span>新列名称</span><input v-model="derivedName" :disabled="busy" maxlength="120" placeholder="例如：ΔDR7" /></label><label class="field"><span>来源数值指标</span><select v-model="derivedSource" :disabled="busy"><option value="">请选择</option><option v-for="column in numericColumns" :key="column.name" :value="column.name">{{ column.name }}</option></select></label><label class="field"><span>单位/含义</span><input v-model="derivedUnit" :disabled="busy" maxlength="80" placeholder="例如：百分点" /></label><label class="field"><span>保留小数位</span><input v-model.number="derivedDecimalPlaces" :disabled="busy" type="number" min="0" max="8" step="1" /></label><label class="field formula-field"><span>公式</span><input v-model="derivedFormula" :disabled="busy" maxlength="10000" placeholder="[处理值] - [对照值]" /><small>可只使用一个操作数；禁止引用任何其他列。</small></label></div>
        <div class="formula-palette"><button v-for="token in ['[处理值]', '[对照值]', '+', '-', '*', '/', '(', ')']" :key="token" type="button" class="formula-token" :disabled="busy" @click="appendFormula(token)">{{ token }}</button></div>
        <p class="selection-warning" v-if="localError">{{ localError }}</p>
        <div class="editor-actions"><button type="button" class="secondary" :disabled="busy" @click="clearDerivedDraft">清空</button><button type="button" class="primary" :disabled="busy || (editingIndex === null && modelValue.derived_columns.length >= 10)" @click="saveDerived">{{ editingIndex === null ? '添加计算列' : '保存计算列' }}</button></div>
      </section>
      <p class="selection-warning" v-for="issue in structureIssues" :key="issue">{{ issue }}</p>
    </template>
  </div>
</template>

<style scoped>
.pairing-editor{display:grid;gap:16px}.pairing-toggle{display:flex;gap:12px;align-items:flex-start;padding:14px;border:1px solid var(--line);border-radius:14px;background:var(--surface)}.pairing-toggle span{display:grid;gap:4px}.pairing-toggle small,.pairing-block small{color:var(--muted)}.pairing-grid,.pair-derived-builder{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.pairing-block{display:grid;gap:12px;padding:14px;border:1px solid var(--line);border-radius:14px}.pairing-block-head,.mapping-row,.pair-derived-list article,.editor-actions{display:flex;align-items:center;justify-content:space-between;gap:10px}.pairing-block-head>div,.pair-derived-list article>div:first-child{display:grid;gap:3px}.mapping-row select{flex:1}.token-grid,.formula-palette{display:flex;flex-wrap:wrap;gap:8px}.pair-derived-list{display:grid;gap:8px}.pair-derived-list article{padding:10px;border-radius:10px;background:var(--surface)}.pair-derived-list code{display:block}.formula-field{grid-column:1/-1}@media(max-width:760px){.pairing-grid,.pair-derived-builder{grid-template-columns:1fr}.mapping-row{align-items:stretch;flex-direction:column}.mapping-row span{display:none}}
</style>
