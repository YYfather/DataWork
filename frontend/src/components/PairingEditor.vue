<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'

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

const FORMULA_PRESETS = [
  { value: '', label: '自定义公式', formula: '' },
  { value: 'treatment', label: '处理值', formula: '[处理值]' },
  { value: 'control', label: '对照值', formula: '[对照值]' },
  { value: 'difference', label: '处理－对照', formula: '[处理值] - [对照值]' },
  { value: 'reverse_difference', label: '对照－处理', formula: '[对照值] - [处理值]' },
  { value: 'ratio', label: '处理/对照', formula: '[处理值] / [对照值]' },
  { value: 'relative', label: '相对变化', formula: '([处理值] - [对照值]) / [对照值]' },
  { value: 'relative_percent', label: '相对变化百分比', formula: '([处理值] - [对照值]) / [对照值] * 100' },
  { value: 'abs_treatment', label: '处理值的数学绝对值', formula: 'abs([处理值])' },
  { value: 'abs_control', label: '对照值的数学绝对值', formula: 'abs([对照值])' },
  { value: 'abs_difference', label: '处理—对照绝对差', formula: 'abs([处理值] - [对照值])' },
] as const
const UNIT_SUGGESTIONS = [
  '无单位', '%', '百分点', '比例（0–1）', '相对量',
  '绝对量（保留原始尺度）', '差值', '比值', '倍数', '与来源列相同',
]
const DECIMAL_OPTIONS = Array.from({ length: 9 }, (_, index) => index)

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
const derivedNameInput = ref<HTMLInputElement | null>(null)
const derivedSource = ref('')
const derivedFormula = ref('')
const derivedUnit = ref('')
const derivedDecimalPlaces = ref(8)
const formulaPreset = ref('')
const editingIndex = ref<number | null>(null)
const localError = ref('')
const continuingFromLast = ref(false)

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

function normalizeAbsoluteBars(formula: string) {
  if (!formula.includes('|')) return formula
  const parts = formula.split('|')
  if (parts.length % 2 === 0) throw new Error('数学绝对值竖线必须成对出现')
  let normalized = parts[0]
  for (let index = 1; index < parts.length; index += 2) {
    const inner = parts[index].trim()
    if (!inner) throw new Error('数学绝对值表达式不能为空')
    normalized += `abs(${inner})${parts[index + 1]}`
  }
  return normalized
}

function inferFormulaPreset(formula: string) {
  const compact = formula.replace(/\s+/g, '')
  return FORMULA_PRESETS.find(item => item.formula.replace(/\s+/g, '') === compact)?.value ?? ''
}

function applyFormulaPreset() {
  const preset = FORMULA_PRESETS.find(item => item.value === formulaPreset.value)
  if (preset?.formula) derivedFormula.value = preset.formula
  localError.value = ''
}

function validateFormulaStructure(formula: string) {
  const syntaxOnly = formula.replace(/\[[^\[\]]+\]/g, '').replace(/\babs\s*\(/g, '(')
  if (!/^[\d\s+\-*/.()]*$/.test(syntaxOnly) || syntaxOnly.includes('**') || syntaxOnly.includes('//')) {
    return '公式只允许四则运算、数值、括号和 abs(...)'
  }
  let depth = 0
  for (const character of syntaxOnly) {
    if (character === '(') depth += 1
    if (character === ')') depth -= 1
    if (depth < 0) return '公式括号必须成对出现'
  }
  return depth === 0 ? '' : '公式括号必须成对出现'
}

function clearDerivedDraft() {
  derivedName.value = ''
  derivedSource.value = ''
  derivedFormula.value = ''
  derivedUnit.value = ''
  derivedDecimalPlaces.value = 8
  formulaPreset.value = ''
  editingIndex.value = null
  localError.value = ''
  continuingFromLast.value = false
}

function prepareContinuation(item: PairDerivedColumnDraft) {
  derivedName.value = item.name
  derivedSource.value = item.source_column
  derivedFormula.value = item.formula
  derivedUnit.value = item.unit
  derivedDecimalPlaces.value = item.decimal_places
  formulaPreset.value = inferFormulaPreset(item.formula)
  editingIndex.value = null
  localError.value = ''
  continuingFromLast.value = true
  nextTick(() => {
    derivedNameInput.value?.focus()
    derivedNameInput.value?.select()
  })
}

function duplicateDerived(index: number) {
  const item = props.modelValue?.derived_columns[index]
  if (item) prepareContinuation(item)
}

function saveDerived() {
  if (!props.modelValue) return
  const name = derivedName.value.trim()
  let formula = derivedFormula.value.trim()
  try {
    formula = normalizeAbsoluteBars(formula)
  } catch (error) {
    localError.value = error instanceof Error ? error.message : '数学绝对值公式无效'
    return
  }
  const references = Array.from(formula.matchAll(/\[([^\[\]]+)\]/g), match => match[1].trim())
  if (!name || !derivedSource.value || !formula) { localError.value = '请填写新列名、来源指标和公式'; return }
  if (!references.length || references.some(item => !['处理值', '对照值'].includes(item))) { localError.value = '公式只能引用 [处理值] 和 [对照值]，且至少引用一个'; return }
  const structureError = validateFormulaStructure(formula)
  if (structureError) { localError.value = structureError; return }
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
  if (editingIndex.value === null) prepareContinuation(value)
  else clearDerivedDraft()
}

function editDerived(index: number) {
  const item = props.modelValue?.derived_columns[index]
  if (!item) return
  derivedName.value = item.name
  derivedSource.value = item.source_column
  derivedFormula.value = item.formula
  derivedUnit.value = item.unit
  derivedDecimalPlaces.value = item.decimal_places
  formulaPreset.value = inferFormulaPreset(item.formula)
  editingIndex.value = index
  continuingFromLast.value = false
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
        <div class="pair-derived-list" v-if="modelValue.derived_columns.length"><article v-for="(item, index) in modelValue.derived_columns" :key="item.id"><div><strong>{{ item.name }}</strong><code>{{ item.formula }}</code><small>来源：{{ item.source_column }} · {{ item.decimal_places }} 位小数<template v-if="item.unit"> · 单位/含义：{{ item.unit }}</template></small></div><div><button type="button" class="text-button" :disabled="busy || modelValue.derived_columns.length >= 10" @click="duplicateDerived(index)">以此新增</button><button type="button" class="text-button" :disabled="busy" @click="editDerived(index)">编辑</button><button type="button" class="text-button danger-text" :disabled="busy" @click="removeDerived(index)">删除</button></div></article></div>
        <p v-if="continuingFromLast && editingIndex === null" class="continuation-note">已沿用上一列参数。名称已选中，请修改为唯一名称；也可以调整来源、公式、单位或精度。</p>
        <div class="pair-derived-builder"><label class="field"><span>新列名称</span><input ref="derivedNameInput" v-model="derivedName" :disabled="busy" maxlength="120" placeholder="例如：ΔDR7" /><small>自由命名；不会提供常驻名称选项。</small></label><label class="field"><span>来源数值指标</span><select v-model="derivedSource" :disabled="busy"><option value="">请选择</option><option v-for="column in numericColumns" :key="column.name" :value="column.name">{{ column.name }}</option></select></label><label class="field"><span>单位/含义</span><input v-model="derivedUnit" :disabled="busy" list="pair-unit-suggestions" maxlength="80" placeholder="选择常用项或自行输入" /><datalist id="pair-unit-suggestions"><option v-for="option in UNIT_SUGGESTIONS" :key="option" :value="option" /></datalist><small>“绝对量”只描述原始尺度；数学取绝对值请使用 abs 公式。</small></label><label class="field"><span>保留小数位</span><select v-model.number="derivedDecimalPlaces" :disabled="busy"><option v-for="value in DECIMAL_OPTIONS" :key="value" :value="value">{{ value }} 位</option></select></label><label class="field formula-preset-field"><span>常用计算模板</span><select v-model="formulaPreset" :disabled="busy" @change="applyFormulaPreset"><option v-for="preset in FORMULA_PRESETS" :key="preset.value || 'custom'" :value="preset.value">{{ preset.label }}</option></select><small>模板只填充公式，不会覆盖单位/含义。</small></label><label class="field formula-field"><span>公式</span><input v-model="derivedFormula" :disabled="busy" maxlength="10000" placeholder="[处理值] - [对照值]" /><small>支持基础四则运算、括号、abs(x) 或 |x|；禁止引用任何其他列。</small></label></div>
        <div class="formula-palette"><button v-for="token in ['[处理值]', '[对照值]', '+', '-', '*', '/', '(', ')', 'abs(']" :key="token" type="button" class="formula-token" :disabled="busy" @click="appendFormula(token)">{{ token }}</button></div>
        <p class="selection-warning" v-if="localError">{{ localError }}</p>
        <div class="editor-actions"><button type="button" class="secondary" :disabled="busy" @click="clearDerivedDraft">清空重新填写</button><button type="button" class="primary" :disabled="busy || (editingIndex === null && modelValue.derived_columns.length >= 10)" @click="saveDerived">{{ editingIndex === null ? '添加计算列' : '保存计算列' }}</button></div>
      </section>
      <p class="selection-warning" v-for="issue in structureIssues" :key="issue">{{ issue }}</p>
    </template>
  </div>
</template>

<style scoped>
.pairing-editor{display:grid;gap:16px}.pairing-toggle{display:flex;gap:12px;align-items:flex-start;padding:14px;border:1px solid var(--line);border-radius:14px;background:var(--surface)}.pairing-toggle span{display:grid;gap:4px}.pairing-toggle small,.pairing-block small{color:var(--muted)}.pairing-grid,.pair-derived-builder{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.pairing-block{display:grid;gap:12px;padding:14px;border:1px solid var(--line);border-radius:14px}.pairing-block-head,.mapping-row,.pair-derived-list article,.editor-actions{display:flex;align-items:center;justify-content:space-between;gap:10px}.pairing-block-head>div,.pair-derived-list article>div:first-child{display:grid;gap:3px}.mapping-row select{flex:1}.token-grid,.formula-palette{display:flex;flex-wrap:wrap;gap:8px}.pair-derived-list{display:grid;gap:8px}.pair-derived-list article{padding:10px;border-radius:10px;background:var(--surface)}.pair-derived-list code{display:block}.formula-field{grid-column:1/-1}.continuation-note{margin:0;padding:10px 12px;border-radius:10px;background:var(--accent-soft);color:var(--text)}@media(max-width:760px){.pairing-grid,.pair-derived-builder{grid-template-columns:1fr}.mapping-row{align-items:stretch;flex-direction:column}.mapping-row span{display:none}}
</style>
