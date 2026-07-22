<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, toRaw, watch } from 'vue'
import { apiRequest, appUrl, errorMessage, friendlyError, releaseDataworkSession, resetDataworkSession } from './api'
import AIAssistantPanel from './components/AIAssistantPanel.vue'
import AISettingsPanel from './components/AISettingsPanel.vue'
import AIResultReportPanel from './components/AIResultReportPanel.vue'
import AnalysisGuidanceCard from './components/AnalysisGuidanceCard.vue'
import AnalysisResultView from './components/AnalysisResultView.vue'
import PreflightDialog from './components/PreflightDialog.vue'
import LoadingOverlay from './components/LoadingOverlay.vue'
import ErrorNotice from './components/ErrorNotice.vue'
import DerivedColumnEditor from './components/DerivedColumnEditor.vue'

type MethodSpec = {
  name: string
  label_zh: string
  category: string
  status: 'implemented' | 'experimental' | 'unavailable'
  runnable: boolean
  purpose: string
  variable_relationship: string
  variable_requirements: Array<{ role: string; label_zh: string; count: string; description: string }>
  output_metrics: string[]
  assumptions: string[]
  typical_uses: string[]
  min_dependent_vars: number
  max_dependent_vars: number | null
  dependent_mode: 'none' | 'single' | 'joint'
  min_fixed_factors: number
  max_fixed_factors: number | null
  min_covariates: number
  max_covariates: number | null
  min_random_factors: number
  max_random_factors: number | null
  min_random_slopes: number
  max_random_slopes: number | null
  requires_subject_id: boolean
  requires_repeated_factor: boolean
  requires_any_predictor: boolean
  exact_factor_levels: number | null
  supports_batch: boolean
  supports_emm: boolean
  supports_diagnostic_plots: boolean
  parameters: Array<{
    key: string
    label_zh: string
    kind: 'boolean' | 'integer' | 'number' | 'select' | 'multi_select' | 'text' | 'number_list'
    default: any
    description: string
    options: Array<{ value: string; label: string }>
    minimum: number | null
    maximum: number | null
    step: number | null
    advanced: boolean
    simple_description: string
    recommended_options: string[]
    recommendation_note: string
    option_help: Record<string, string>
  }>
  notes: string
}

type ColumnProfile = {
  name: string
  dtype: string
  n_unique: number
  n_missing: number
  missing_rate: number
  unique_values: string[]
  inferred_role: string
  note: string
}

type ProfileResponse = {
  sheet: string
  columns: string[]
  preview: Record<string, unknown>[]
  cleaning_log?: Array<{ operation: string; details: Record<string, any> }>
  profile: {
    n_rows: number
    n_cols: number
    total_missing_rate: number
    n_duplicate_rows: number
    columns: ColumnProfile[]
  }
}

type WorkspaceProject = { id: string; name: string; description: string; dataset_count?: number; plan_count?: number; run_count?: number }
type WorkspaceDataset = { id: string; name: string; original_filename: string; profile_json: ProfileResponse['profile']; fingerprint_json: Record<string, any> }
type WorkspacePlan = { id: string; name: string; dataset_id: string; revision: number; plan_json: Record<string, any> }
type WorkspaceRun = { id: string; status: string; plan_id: string; plan_name?: string; dataset_name?: string; result_json?: any; error_json?: any; started_at: string; completed_at?: string }
type SessionState = {
  active: boolean
  expired: boolean
  active_users: number
  max_users: number
  idle_timeout_seconds: number
  session_label?: string | null
  expires_in_seconds: number
}
type WorkspaceAuthState = {
  required: boolean
  authenticated: boolean
  idle_timeout_seconds: number
  temporary_session_cleanup: boolean
}
type WorkspaceProjectDetail = WorkspaceProject & { datasets: WorkspaceDataset[]; plans: WorkspacePlan[]; runs: WorkspaceRun[] }
type FactorOverflowPrompt = {
  open: boolean
  target: 'instant' | 'workspace'
  column: string
  methodLabel: string
  maximum: number
  selectedCount: number
  projectedCount: number
  combinationCount: number
  combinations: string[]
  correctionLabel: string
}

type SplitGroupDraft = {
  id: number
  label: string
  values: string[]
  lower: string | number
  upper: string | number
  includeLower: boolean
  includeUpper: boolean
}
type SplitRuleDraft = { column: string; kind: 'categorical' | 'numeric'; groups: SplitGroupDraft[] }
type DerivedColumnDraft = { name: string; formula: string; source_columns: string[] }

const DEFAULT_INSTANT_METHOD = 'welch_ttest'
const HIGH_ORDER_FACTORIAL_METHODS = new Set(['multifactor_anova', 'multifactor_manova'])

const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const methods = ref<MethodSpec[]>([])
const profile = ref<ProfileResponse | null>(null)
const sourceProfile = ref<ProfileResponse | null>(null)
const derivedColumns = ref<DerivedColumnDraft[]>([])
const derivedWarnings = ref<string[]>([])
const derivedPreviewLoading = ref(false)
const selectedMethod = ref(DEFAULT_INSTANT_METHOD)
const dependentVariables = ref<string[]>([])
const fixedFactors = ref<string[]>([])
const covariates = ref<string[]>([])
const randomFactors = ref<string[]>([])
const randomSlopes = ref<string[]>([])
const estimateMarginalMeans = ref(false)
const emmFactors = ref<string[]>([])
const contrastCorrection = ref<'none' | 'bonferroni' | 'holm' | 'fdr_bh'>('holm')
const diagnosticPlots = ref(false)
const subjectId = ref('')
const repeatedFactor = ref('')
const testValue = ref(0)
const expectedProportionsText = ref('')
const methodParameters = ref<Record<string, any>>({})
const factorCombinationsEnabled = ref(false)
const factorCombinationMinOrder = ref(1)
const factorCombinationMaxOrder = ref(1)
const factorCombinationLabels = ref<Record<string, string>>({})
const combinationPAdjust = ref<'none' | 'bonferroni' | 'holm' | 'fdr_bh'>('holm')
const calibrationEnabled = ref(false)
const calibrationMethod = ref<'zscore' | 'robust_zscore' | 'baseline_center'>('zscore')
const calibrationColumns = ref<string[]>([])
const calibrationBaselineColumn = ref('')
const calibrationBaselineValue = ref('')
const splitBy = ref<string[]>([])
const instantSplitRules = ref<SplitRuleDraft[]>([])
const alpha = ref(0.05)
const ssType = ref(3)
const percentageScale = ref<'percent_points' | 'proportion'>('percent_points')
const loadingProfile = ref(false)
const loadingAnalysis = ref(false)
const error = ref('')
const errorTitle = ref('')
const errorHints = ref<string[]>([])
const result = ref<any>(null)
const resultInvalidated = ref(false)
const resultInvalidatedReason = ref('')
const instantDetailedResults = ref(false)
const workspaceDetailedResults = ref(false)
const instantExpertMode = ref(false)
const workspaceExpertMode = ref(false)
const instantReportLoading = ref(false)
const instantReportLinks = ref<{ zip: string; xlsx: string; markdown: string } | null>(null)
const instantBuiltinReport = ref<any>(null)
const instantAIReport = ref<any>(null)
const workspaceBuiltinReport = ref<any>(null)
const workspaceAIReport = ref<any>(null)
const instantResultContextId = ref('')
const instantResultCompletedAt = ref('')
const instantAIReportContextId = ref('')
const workspaceAIReportContextId = ref('')
let instantResultContextSequence = 0
const aiReportErrors = ref<Record<'instant' | 'workspace', string>>({ instant: '', workspace: '' })
const aiReportLoadingTarget = ref<'instant' | 'workspace' | ''>('')
const builtinReportLoading = ref<Record<'instant' | 'workspace', boolean>>({ instant: false, workspace: false })
const builtinReportPromises: Record<'instant' | 'workspace', Promise<any> | null> = { instant: null, workspace: null }
let batchExportPollId = 0
const workspaceResultInvalidated = ref(false)
const workspaceResultInvalidatedReason = ref('')
const health = ref<any>(null)
const sessionState = ref<SessionState | null>(null)
const sessionAccessError = ref<any>(null)
let sessionStatusTimer: number | undefined
const SESSION_HEARTBEAT_INTERVAL_MS = 2 * 60 * 1000
const SESSION_ACTIVITY_THROTTLE_MS = 30 * 1000
let lastSessionActivityAt = 0
const mode = ref<'instant' | 'workspace'>('instant')
const workspaceAuthState = ref<WorkspaceAuthState | null>(null)
const workspaceAuthOpen = ref(false)
const workspaceAuthPassword = ref('')
const workspaceAuthLoading = ref(false)
const workspaceAuthError = ref<any>(null)
const workspaceAuthPurpose = ref<'workspace' | 'ai'>('workspace')
const workspaceInfo = ref<any>(null)
const workspaceProjects = ref<WorkspaceProject[]>([])
const workspaceProject = ref<WorkspaceProjectDetail | null>(null)
const workspaceProjectName = ref('')
const workspaceProjectDescription = ref('')
const workspaceDatasetFile = ref<File | null>(null)
const workspaceFileInput = ref<HTMLInputElement | null>(null)
const workspaceDatasetName = ref('')
const workspaceDatasetId = ref('')
const workspaceMethod = ref('welch_ttest')
const workspaceDvs = ref<string[]>([])
const workspaceFactors = ref<string[]>([])
const workspaceCovariates = ref<string[]>([])
const workspaceRandomFactors = ref<string[]>([])
const workspaceRandomSlopes = ref<string[]>([])
const workspaceEstimateMarginalMeans = ref(false)
const workspaceEmmFactors = ref<string[]>([])
const workspaceContrastCorrection = ref<'none' | 'bonferroni' | 'holm' | 'fdr_bh'>('holm')
const workspaceDiagnosticPlots = ref(false)
const workspaceSubjectId = ref('')
const workspaceRepeatedFactor = ref('')
const workspaceSplits = ref<string[]>([])
const workspaceSplitRules = ref<SplitRuleDraft[]>([])
const workspaceDerivedColumns = ref<DerivedColumnDraft[]>([])
const workspaceDerivedProfile = ref<ProfileResponse['profile'] | null>(null)
const workspaceDerivedWarnings = ref<string[]>([])
const workspaceDerivedPreviewLoading = ref(false)
const workspacePlanName = ref('分析计划 1')
const workspaceMethodParameters = ref<Record<string, any>>({})
const workspaceFactorCombinationsEnabled = ref(false)
const workspaceFactorCombinationMinOrder = ref(1)
const workspaceFactorCombinationMaxOrder = ref(1)
const workspaceFactorCombinationLabels = ref<Record<string, string>>({})
const workspaceCombinationPAdjust = ref<'none' | 'bonferroni' | 'holm' | 'fdr_bh'>('holm')
const workspaceCalibrationEnabled = ref(false)
const workspaceCalibrationMethod = ref<'zscore' | 'robust_zscore' | 'baseline_center'>('zscore')
const workspaceCalibrationColumns = ref<string[]>([])
const workspaceCalibrationBaselineColumn = ref('')
const workspaceCalibrationBaselineValue = ref('')
const workspaceSelectedPlanId = ref('')
const workspaceRun = ref<WorkspaceRun | null>(null)
const workspaceReportId = ref('')
const workspaceReportLinks = ref<Record<string, string> | null>(null)
const workspaceLoading = ref(false)
const workspaceError = ref('')
const workspaceErrorTitle = ref('')
const workspaceErrorHints = ref<string[]>([])
const aiSettingsOpen = ref(false)
const aiAssistantOpen = ref(false)
const aiStatus = ref<any>(null)
const manualHelpStep = ref('')
const showBackToTop = ref(false)
const preflightOpen = ref(false)
const preflightLoading = ref(false)
const preflightReport = ref<any>(null)
const pendingAnalysisAction = ref<'instant' | 'workspace' | ''>('')
const pendingWorkspacePlanId = ref('')
const instantCompletedRunCount = ref(0)
const preflightPriorRunCount = ref(0)
const focusedField = ref('')
const workflowJumpTarget = ref('')
let workflowJumpTimer: number | undefined
const operationTitle = ref('')
const operationDetail = ref('')
const factorOverflowPrompt = ref<FactorOverflowPrompt>({
  open: false, target: 'instant', column: '', methodLabel: '', maximum: 1,
  selectedCount: 0, projectedCount: 0, combinationCount: 0, combinations: [], correctionLabel: 'Holm',
})

const currentMethod = computed(() => methods.value.find((item) => item.name === selectedMethod.value))
const isInstantHighOrderFactorial = computed(() => HIGH_ORDER_FACTORIAL_METHODS.has(selectedMethod.value))
const instantFactorCombinationsAllowed = computed(() => instantExpertMode.value)
const showInstantSplitRole = computed(() => Boolean(currentMethod.value?.supports_batch))
const showInstantSplitRuleEditor = computed(() => Boolean(instantExpertMode.value && currentMethod.value?.supports_batch && splitBy.value.length))
function exactFactorCount(method?: MethodSpec) {
  if (!method) return null
  if (method.min_fixed_factors > 0 && method.max_fixed_factors === method.min_fixed_factors) return method.min_fixed_factors
  return null
}
function configuredMultiFactorOrder(target: 'instant' | 'workspace') {
  const method = target === 'instant' ? currentMethod.value : workspaceCurrentMethod.value
  if (!['multifactor_anova', 'multifactor_manova'].includes(method?.name ?? '')) return null
  const parameters = target === 'instant' ? methodParameters.value : workspaceMethodParameters.value
  const order = Number(parameters.factor_model_order ?? 4)
  return Number.isInteger(order) && order >= 4 && order <= 8 ? order : 4
}
function factorRequirementText(method: MethodSpec | undefined, target: 'instant' | 'workspace') {
  const configured = configuredMultiFactorOrder(target)
  if (configured !== null) return `分类因素恰好 ${configured} 个（当前模型阶数）`
  const exact = exactFactorCount(method)
  if (exact !== null) return `分类因素恰好 ${exact} 个`
  return `分类因素至少 ${method?.min_fixed_factors ?? 0} 个`
}
function effectiveFactorOrder(target: 'instant' | 'workspace') {
  const method = target === 'instant' ? currentMethod.value : workspaceCurrentMethod.value
  const configured = configuredMultiFactorOrder(target)
  if (configured !== null) return configured
  return Math.max(1, method?.max_fixed_factors ?? method?.min_fixed_factors ?? 1)
}
const methodCategories = computed(() => {
  const grouped = new Map<string, MethodSpec[]>()
  for (const method of methods.value) {
    if (!grouped.has(method.category)) grouped.set(method.category, [])
    grouped.get(method.category)!.push(method)
  }
  return Array.from(grouped.entries()).map(([category, items]) => ({ category, items }))
})
function roleAvailable(maximum: number | null | undefined, minimum = 0, extra = false) {
  return maximum === null || (maximum ?? 0) > 0 || minimum > 0 || extra
}
const showDependentRole = computed(() => roleAvailable(currentMethod.value?.max_dependent_vars, currentMethod.value?.min_dependent_vars))
const showFixedRole = computed(() => roleAvailable(currentMethod.value?.max_fixed_factors, currentMethod.value?.min_fixed_factors))
const showCovariateRole = computed(() => roleAvailable(currentMethod.value?.max_covariates, currentMethod.value?.min_covariates, Boolean(currentMethod.value?.requires_any_predictor)))
const showRandomSlopeRole = computed(() => roleAvailable(currentMethod.value?.max_random_slopes, currentMethod.value?.min_random_slopes))
const showRandomRole = computed(() => roleAvailable(currentMethod.value?.max_random_factors, currentMethod.value?.min_random_factors))
const showSubjectRole = computed(() => Boolean(currentMethod.value?.requires_subject_id))
const showRepeatedRole = computed(() => Boolean(currentMethod.value?.requires_repeated_factor))
const dependentRoleLabel = computed(() => currentMethod.value?.dependent_mode === 'joint'
  ? `联合因变量（至少 ${currentMethod.value.min_dependent_vars} 个）` : '因变量/分析变量')
const workspaceDependentRoleLabel = computed(() => workspaceCurrentMethod.value?.dependent_mode === 'joint'
  ? `联合因变量（至少 ${workspaceCurrentMethod.value.min_dependent_vars} 个）` : '因变量')
const factorSelectionOverflow = computed(() => fixedFactors.value.length > effectiveFactorOrder('instant'))
const workspaceFactorSelectionOverflow = computed(() => workspaceFactors.value.length > effectiveFactorOrder('workspace'))
const columns = computed(() => profile.value?.columns ?? [])
const previewColumns = computed(() => profile.value?.preview.length ? Object.keys(profile.value.preview[0]) : [])
const excludedColumns = computed(() => {
  const step = profile.value?.cleaning_log?.find(item => item.operation === 'conservative_clean')
  return (step?.details?.excluded_columns ?? []) as Array<{ name: string; reason: string; non_empty_cells: number }>
})
const interactionBusy = computed(() => Boolean(operationTitle.value) || loadingProfile.value || preflightLoading.value || loadingAnalysis.value || workspaceLoading.value || derivedPreviewLoading.value || workspaceDerivedPreviewLoading.value)
const canAnalyze = computed(() => Boolean(file.value && profile.value && currentMethod.value?.runnable && !interactionBusy.value))
const workspaceCurrentMethod = computed(() => methods.value.find((item) => item.name === workspaceMethod.value))
function commonParameterIsRelevant(parameter: MethodSpec['parameters'][number], parameters: Record<string, any>) {
  if (parameter.key === 'control_group') return (parameters.posthoc_methods ?? []).includes('dunnett')
  return true
}
const instantCommonParameters = computed(() => (currentMethod.value?.parameters ?? []).filter(item => !item.advanced && commonParameterIsRelevant(item, methodParameters.value)))
const instantAdvancedParameters = computed(() => (currentMethod.value?.parameters ?? []).filter(item => item.advanced))
const workspaceCommonParameters = computed(() => (workspaceCurrentMethod.value?.parameters ?? []).filter(item => !item.advanced && commonParameterIsRelevant(item, workspaceMethodParameters.value)))
const workspaceAdvancedParameters = computed(() => (workspaceCurrentMethod.value?.parameters ?? []).filter(item => item.advanced))
function commonParameterOptions(parameter: MethodSpec['parameters'][number], selected: any) {
  const selectedValues = Array.isArray(selected) ? selected : []
  const recommended = new Set([...(parameter.recommended_options ?? []), ...selectedValues])
  if (!recommended.size) return parameter.options
  return parameter.options.filter(option => recommended.has(option.value))
}
function parameterHelp(parameter: MethodSpec['parameters'][number]) {
  return parameter.simple_description || parameter.description
}
function optionHelp(parameter: MethodSpec['parameters'][number], value: string) {
  return parameter.option_help?.[value] ?? ''
}
const instantRecommendedSummary = computed(() => {
  const parts = [`显著性标准：${alpha.value}`]
  const posthoc = instantCommonParameters.value.find(item => item.key === 'posthoc_methods')
  if (posthoc) {
    const selected = methodParameters.value.posthoc_methods ?? posthoc.default
    const labels = posthoc.options.filter(option => selected.includes(option.value)).map(option => option.label)
    if (labels.length) parts.push(`事后比较：${labels.join('、')}`)
  }
  if (['twoway_anova','threeway_anova','multifactor_anova','ancova'].includes(selectedMethod.value)) parts.push(`平方和：Type ${ssType.value}`)
  return parts
})
const workspaceRecommendedSummary = computed(() => {
  const parts = [`显著性标准：${alpha.value}`]
  const posthoc = workspaceCommonParameters.value.find(item => item.key === 'posthoc_methods')
  if (posthoc) {
    const selected = workspaceMethodParameters.value.posthoc_methods ?? posthoc.default
    const labels = posthoc.options.filter(option => selected.includes(option.value)).map(option => option.label)
    if (labels.length) parts.push(`事后比较：${labels.join('、')}`)
  }
  if (['twoway_anova','threeway_anova','multifactor_anova','ancova'].includes(workspaceMethod.value)) parts.push(`平方和：Type ${ssType.value}`)
  return parts
})
const workspaceShowDependentRole = computed(() => roleAvailable(workspaceCurrentMethod.value?.max_dependent_vars, workspaceCurrentMethod.value?.min_dependent_vars))
const workspaceShowFixedRole = computed(() => roleAvailable(workspaceCurrentMethod.value?.max_fixed_factors, workspaceCurrentMethod.value?.min_fixed_factors))
const workspaceShowCovariateRole = computed(() => roleAvailable(workspaceCurrentMethod.value?.max_covariates, workspaceCurrentMethod.value?.min_covariates, Boolean(workspaceCurrentMethod.value?.requires_any_predictor)))
const workspaceShowRandomSlopeRole = computed(() => roleAvailable(workspaceCurrentMethod.value?.max_random_slopes, workspaceCurrentMethod.value?.min_random_slopes))
const workspaceShowRandomRole = computed(() => roleAvailable(workspaceCurrentMethod.value?.max_random_factors, workspaceCurrentMethod.value?.min_random_factors))
const workspaceShowSubjectRole = computed(() => Boolean(workspaceCurrentMethod.value?.requires_subject_id))
const workspaceShowRepeatedRole = computed(() => Boolean(workspaceCurrentMethod.value?.requires_repeated_factor))
const workspaceDataset = computed(() => workspaceProject.value?.datasets.find((item) => item.id === workspaceDatasetId.value) ?? null)
const workspaceColumns = computed(() => workspaceDerivedProfile.value?.columns ?? workspaceDataset.value?.profile_json?.columns ?? [])
const instantDerivedNames = computed(() => new Set(derivedColumns.value.map(column => column.name)))
const workspaceDerivedNames = computed(() => new Set(workspaceDerivedColumns.value.map(column => column.name)))
const isInstantDerivedColumn = (column: string) => instantDerivedNames.value.has(column)
const isWorkspaceDerivedColumn = (column: string) => workspaceDerivedNames.value.has(column)
function inheritedSplitText(column: string, target: 'instant' | 'workspace') {
  const definition = (target === 'instant' ? derivedColumns.value : workspaceDerivedColumns.value).find(item => item.name === column)
  if (!definition) return ''
  const activeSplits = target === 'instant' ? splitBy.value : workspaceSplits.value
  const sourceSplits = definition.source_columns.filter(item => activeSplits.includes(item))
  const unrelatedSplits = activeSplits.filter(item => !sourceSplits.includes(item))
  const parts = sourceSplits.length ? [`继承来源拆分：${sourceSplits.join(' × ')}`] : ['来源列未拆分']
  if (unrelatedSplits.length) parts.push(`分析附加拆分：${unrelatedSplits.join(' × ')}`)
  return parts.join('；')
}
const workspaceMissingSelections = computed(() => {
  const method = workspaceCurrentMethod.value
  if (!method) return ['统计方法']
  const missing: string[] = []
  if (workspaceDvs.value.length < method.min_dependent_vars) missing.push(`因变量至少 ${method.min_dependent_vars} 个`)
  const requiredFactorCount = configuredMultiFactorOrder('workspace')
  if (requiredFactorCount !== null ? workspaceFactors.value.length !== requiredFactorCount : workspaceFactors.value.length < method.min_fixed_factors) missing.push(factorRequirementText(method, 'workspace'))
  const factorLimit = method.max_fixed_factors
  if (!workspaceFactorCombinationsEnabled.value && factorLimit !== null && workspaceFactors.value.length > factorLimit) missing.push(`分类因素超过当前 ${factorLimit} 阶模型；需确认组合实验`)
  if (workspaceCovariates.value.length < method.min_covariates) missing.push(`连续自变量至少 ${method.min_covariates} 个`)
  if (workspaceRandomFactors.value.length < method.min_random_factors) missing.push(`随机分组至少 ${method.min_random_factors} 个`)
  if (method.requires_any_predictor && workspaceFactors.value.length + workspaceCovariates.value.length === 0) missing.push('至少一个分类或连续预测变量')
  if (method.requires_subject_id && !workspaceSubjectId.value) missing.push('对象 ID')
  if (method.requires_repeated_factor && !workspaceRepeatedFactor.value) missing.push('重复/时间因素')
  if (workspaceEstimateMarginalMeans.value && workspaceEmmCandidates.value.length && !workspaceEmmFactors.value.length) missing.push('EMM 因素')
  missing.push(...workspaceSplitRuleIssues.value)
  missing.push(...factorCombinationNameIssues('workspace'))
  return missing
})
const canCreateWorkspacePlan = computed(() => Boolean(workspaceDataset.value && workspaceCurrentMethod.value?.runnable && workspaceMissingSelections.value.length === 0 && !interactionBusy.value))
const currentHelpStep = computed(() => {
  if (manualHelpStep.value) return manualHelpStep.value
  if (mode.value === 'workspace') {
    if (workspaceRun.value?.result_json) return 'interpret_results'
    if (workspaceProject.value?.plans?.length) return 'run_analysis'
    if (workspaceDataset.value) return 'build_plan'
    return 'workspace'
  }
  if (result.value) return 'interpret_results'
  if (profile.value) return 'build_plan'
  return 'import_data'
})
const aiContext = computed(() => ({
  mode: mode.value,
  workflow_step: currentHelpStep.value,
  workflow_progress: mode.value === 'instant' ? instantWorkflowStep.value : workspaceWorkflowStep.value,
  interface_mode: mode.value === 'instant' ? (instantExpertMode.value ? 'professional' : 'concise') : (workspaceExpertMode.value ? 'professional' : 'concise'),
  source_name: mode.value === 'instant' ? file.value?.name ?? '' : workspaceDataset.value?.name ?? '',
  data_profile: mode.value === 'instant'
    ? profile.value?.profile ?? null
    : workspaceDataset.value?.profile_json ?? null,
  selected_method: mode.value === 'instant' ? selectedMethod.value : workspaceMethod.value,
  selected_method_label: mode.value === 'instant' ? currentMethod.value?.label_zh ?? '' : workspaceCurrentMethod.value?.label_zh ?? '',
  dependent_variables: mode.value === 'instant' ? dependentVariables.value : workspaceDvs.value,
  fixed_factors: mode.value === 'instant' ? fixedFactors.value : workspaceFactors.value,
  covariates: mode.value === 'instant' ? covariates.value : workspaceCovariates.value,
  random_factors: mode.value === 'instant' ? randomFactors.value : workspaceRandomFactors.value,
  random_slopes: mode.value === 'instant' ? randomSlopes.value : workspaceRandomSlopes.value,
  estimate_marginal_means: mode.value === 'instant' ? estimateMarginalMeans.value : workspaceEstimateMarginalMeans.value,
  emm_factors: mode.value === 'instant' ? emmFactors.value : workspaceEmmFactors.value,
  subject_id: mode.value === 'instant' ? subjectId.value : workspaceSubjectId.value,
  repeated_factor: mode.value === 'instant' ? repeatedFactor.value : workspaceRepeatedFactor.value,
  split_by: mode.value === 'instant' ? splitBy.value : workspaceSplits.value,
  split_rules: mode.value === 'instant' ? serializeInstantSplitRules() : serializeWorkspaceSplitRules(),
  derived_columns: mode.value === 'instant' ? derivedColumns.value : workspaceDerivedColumns.value,
  method_parameters: mode.value === 'instant' ? methodParameters.value : workspaceMethodParameters.value,
  factor_combinations_enabled: mode.value === 'instant' ? (instantFactorCombinationsAllowed.value && factorCombinationsEnabled.value) : workspaceFactorCombinationsEnabled.value,
  factor_combination_order: mode.value === 'instant' ? factorCombinationMaxOrder.value : workspaceFactorCombinationMaxOrder.value,
  factor_combination_min_order: mode.value === 'instant' ? factorCombinationMinOrder.value : workspaceFactorCombinationMinOrder.value,
  factor_combination_max_order: mode.value === 'instant' ? factorCombinationMaxOrder.value : workspaceFactorCombinationMaxOrder.value,
  factor_combination_labels: mode.value === 'instant' ? serializeFactorCombinationLabels('instant') : serializeFactorCombinationLabels('workspace'),
  combination_p_adjust: mode.value === 'instant' ? combinationPAdjust.value : workspaceCombinationPAdjust.value,
  calibration_enabled: mode.value === 'instant' ? calibrationEnabled.value : workspaceCalibrationEnabled.value,
  calibration_method: mode.value === 'instant' ? calibrationMethod.value : workspaceCalibrationMethod.value,
  calibration_columns: mode.value === 'instant' ? calibrationColumns.value : workspaceCalibrationColumns.value,
  calibration_baseline_column: mode.value === 'instant' ? calibrationBaselineColumn.value : workspaceCalibrationBaselineColumn.value,
  calibration_baseline_value: mode.value === 'instant' ? calibrationBaselineValue.value : workspaceCalibrationBaselineValue.value,
  alpha: alpha.value,
  ss_type: ssType.value,
  result_available: mode.value === 'instant'
    ? Boolean(result.value)
    : Boolean(workspaceRun.value?.result_json),
  run_id: mode.value === 'instant' ? result.value?.run_id ?? '' : workspaceRun.value?.id ?? '',
  project: workspaceProject.value ? { id: workspaceProject.value.id, name: workspaceProject.value.name } : null,
}))
const assistantResult = computed(() => mode.value === 'instant'
  ? result.value
  : workspaceRun.value?.result_json ?? null)
const assistantResultContextId = computed(() => mode.value === 'instant'
  ? instantResultContextId.value
  : workspaceRun.value?.id ? `workspace:${workspaceRun.value.id}` : '')
const assistantResultTimestamp = computed(() => mode.value === 'instant'
  ? instantResultCompletedAt.value
  : workspaceRun.value?.completed_at || workspaceRun.value?.started_at || '')
const assistantAIReport = computed(() => mode.value === 'instant'
  ? instantAIReport.value
  : workspaceAIReport.value)
const assistantAIReportContextId = computed(() => mode.value === 'instant'
  ? instantAIReportContextId.value
  : workspaceAIReportContextId.value)
const aiReady = computed(() => Boolean(aiStatus.value?.enabled && aiStatus.value?.configured))
const automaticAIReportAllowed = computed(() => Boolean(
  aiReady.value && (
    aiStatus.value?.configuration_source === 'personal'
    || aiStatus.value?.owner_authenticated
  ),
))

watch(result, current => {
  if (current) return
  instantResultContextId.value = ''
  instantResultCompletedAt.value = ''
})
watch(instantAIReport, current => { if (!current) instantAIReportContextId.value = '' })
watch(workspaceAIReport, current => { if (!current) workspaceAIReportContextId.value = '' })
const instantSplitRuleIssues = computed(() => {
  if (!instantExpertMode.value) return []
  const issues: string[] = []
  for (const rule of instantSplitRules.value) {
    if (!splitBy.value.includes(rule.column)) continue
    if (!rule.groups.length) { issues.push(`${rule.column} 至少需要一个自定义组`); continue }
    const dualRole = fixedFactors.value.includes(rule.column)
    if (dualRole && rule.groups.length < 2) issues.push(`${rule.column} 同时作为分类因素时至少需要两个自定义组`)
    const labels = rule.groups.map(group => group.label.trim()).filter(Boolean)
    if (labels.length !== rule.groups.length) issues.push(`${rule.column} 存在未命名组`)
    if (new Set(labels).size !== labels.length) issues.push(`${rule.column} 的组名不能重复`)
    if (rule.kind === 'categorical') {
      if (rule.groups.some(group => !group.values.length)) issues.push(`${rule.column} 的每个类别组都要选择值`)
      if (dualRole && rule.groups.some(group => group.values.length < 2)) issues.push(`${rule.column} 同时作为分类因素时，每组至少需要两个原始水平`)
      const values = rule.groups.flatMap(group => group.values)
      if (new Set(values).size !== values.length) issues.push(`${rule.column} 的类别值不能分配到多个组`)
    } else {
      for (const group of rule.groups) {
        const lowerText = String(group.lower).trim()
        const upperText = String(group.upper).trim()
        const lower = lowerText === '' ? Number.NEGATIVE_INFINITY : Number(group.lower)
        const upper = upperText === '' ? Number.POSITIVE_INFINITY : Number(group.upper)
        if (!Number.isFinite(lower) && lowerText !== '' || !Number.isFinite(upper) && upperText !== '' || lower >= upper) {
          issues.push(`${rule.column} 的数值区间无效`)
          break
        }
      }
    }
  }
  return Array.from(new Set(issues))
})
const workspaceSplitRuleIssues = computed(() => {
  if (!workspaceExpertMode.value) return []
  const issues: string[] = []
  for (const rule of workspaceSplitRules.value) {
    if (!workspaceSplits.value.includes(rule.column)) continue
    if (!rule.groups.length) { issues.push(`${rule.column} 至少需要一个自定义组`); continue }
    const dualRole = workspaceFactors.value.includes(rule.column)
    if (dualRole && rule.groups.length < 2) issues.push(`${rule.column} 同时作为分类因素时至少需要两个自定义组`)
    const labels = rule.groups.map(group => group.label.trim()).filter(Boolean)
    if (labels.length !== rule.groups.length) issues.push(`${rule.column} 存在未命名组`)
    if (new Set(labels).size !== labels.length) issues.push(`${rule.column} 的组名不能重复`)
    if (rule.kind === 'categorical') {
      if (rule.groups.some(group => !group.values.length)) issues.push(`${rule.column} 的每个类别组都要选择值`)
      if (dualRole && rule.groups.some(group => group.values.length < 2)) issues.push(`${rule.column} 同时作为分类因素时，每组至少需要两个原始水平`)
      const values = rule.groups.flatMap(group => group.values)
      if (new Set(values).size !== values.length) issues.push(`${rule.column} 的类别值不能分配到多个组`)
    } else {
      for (const group of rule.groups) {
        const lowerText = String(group.lower).trim()
        const upperText = String(group.upper).trim()
        const lower = lowerText === '' ? Number.NEGATIVE_INFINITY : Number(group.lower)
        const upper = upperText === '' ? Number.POSITIVE_INFINITY : Number(group.upper)
        if (!Number.isFinite(lower) && lowerText !== '' || !Number.isFinite(upper) && upperText !== '' || lower >= upper) {
          issues.push(`${rule.column} 的数值区间无效`)
          break
        }
      }
    }
  }
  return Array.from(new Set(issues))
})
const instantMissingSelections = computed(() => {
  const method = currentMethod.value
  if (!method) return ['统计方法']
  const missing: string[] = []
  if (dependentVariables.value.length < method.min_dependent_vars) missing.push(`联合/分析变量至少 ${method.min_dependent_vars} 个`)
  const requiredFactorCount = configuredMultiFactorOrder('instant')
  if (requiredFactorCount !== null ? fixedFactors.value.length !== requiredFactorCount : fixedFactors.value.length < method.min_fixed_factors) missing.push(factorRequirementText(method, 'instant'))
  const factorLimit = method.max_fixed_factors
  if (!factorCombinationsEnabled.value && factorLimit !== null && fixedFactors.value.length > factorLimit) {
    missing.push(isInstantHighOrderFactorial.value
      ? `高阶多因素即时分析最多使用 ${factorLimit} 个因素；请移除额外因素`
      : `分类因素超过当前 ${factorLimit} 阶模型；需确认组合实验`)
  }
  if (covariates.value.length < method.min_covariates) missing.push(`连续自变量至少 ${method.min_covariates} 个`)
  if (randomFactors.value.length < method.min_random_factors) missing.push(`随机分组至少 ${method.min_random_factors} 个`)
  if (method.requires_any_predictor && fixedFactors.value.length + covariates.value.length === 0) missing.push('至少一个分类或连续预测变量')
  if (method.requires_subject_id && !subjectId.value) missing.push('对象 ID')
  if (method.requires_repeated_factor && !repeatedFactor.value) missing.push('重复/时间因素')
  if (estimateMarginalMeans.value && emmCandidates.value.length && !emmFactors.value.length) missing.push('EMM 因素')
  missing.push(...instantSplitRuleIssues.value)
  missing.push(...factorCombinationNameIssues('instant'))
  return missing
})
const instantWorkflowStep = computed(() => result.value ? 4 : preflightOpen.value ? 3 : profile.value ? 2 : file.value ? 1 : 0)
const workspaceWorkflowStep = computed(() => workspaceRun.value?.result_json ? 4 : workspaceProject.value?.plans?.length ? 3 : workspaceDataset.value ? 2 : workspaceProject.value ? 1 : 0)

function parameterDefaultLabel(value: any) {
  if (Array.isArray(value)) return value.join('、') || '无'
  if (value === true) return '开启'
  if (value === false) return '关闭'
  return String(value ?? '') || '空'
}

function resetMethodParameter(target: 'instant' | 'workspace', key: string) {
  const method = target === 'instant' ? currentMethod.value : workspaceCurrentMethod.value
  const parameter = method?.parameters.find(item => item.key === key)
  if (!parameter) return
  const parameters = target === 'instant' ? methodParameters : workspaceMethodParameters
  parameters.value = { ...parameters.value, [key]: Array.isArray(parameter.default) ? [...parameter.default] : parameter.default }
}

function invalidateInstantResult(reason: string) {
  if (loadingAnalysis.value) return
  const hadCurrentOutput = Boolean(
    result.value || instantReportLinks.value || instantBuiltinReport.value || instantAIReport.value,
  )
  if (!hadCurrentOutput) return
  batchExportPollId += 1
  result.value = null
  instantReportLinks.value = null
  instantBuiltinReport.value = null
  instantAIReport.value = null
  resultInvalidated.value = true
  resultInvalidatedReason.value = reason
}

function invalidateWorkspaceResult(reason: string) {
  if (workspaceLoading.value) return
  const hadCurrentOutput = Boolean(
    workspaceRun.value || workspaceReportId.value || workspaceReportLinks.value
    || workspaceBuiltinReport.value || workspaceAIReport.value,
  )
  if (!hadCurrentOutput) return
  workspaceRun.value = null
  workspaceReportId.value = ''
  workspaceReportLinks.value = null
  workspaceBuiltinReport.value = null
  workspaceAIReport.value = null
  workspaceResultInvalidated.value = true
  workspaceResultInvalidatedReason.value = reason
}

function setInstantExpertMode(expert: boolean) {
  if (instantExpertMode.value === expert) return
  if (!expert) {
    const hasProfessionalData = derivedColumns.value.length > 0 || instantSplitRules.value.length > 0 || splitBy.value.some(column => fixedFactors.value.includes(column))
    if (hasProfessionalData && !window.confirm('当前计划包含简洁模式不支持的自定义列或专业拆分配置。继续切换将自动整理这些设置，原始数据和历史结果不会被删除。是否继续？')) return
    const derivedNames = new Set(derivedColumns.value.map(column => column.name))
    dependentVariables.value = dependentVariables.value.filter(column => !derivedNames.has(column))
    fixedFactors.value = fixedFactors.value.filter(column => !derivedNames.has(column))
    covariates.value = covariates.value.filter(column => !derivedNames.has(column))
    randomFactors.value = randomFactors.value.filter(column => !derivedNames.has(column))
    randomSlopes.value = randomSlopes.value.filter(column => !derivedNames.has(column))
    splitBy.value = splitBy.value.filter(column => !derivedNames.has(column) && !fixedFactors.value.includes(column))
    derivedColumns.value = []
    derivedWarnings.value = []
    if (sourceProfile.value) profile.value = structuredClone(toRaw(sourceProfile.value))
  }
  instantExpertMode.value = expert
  instantDetailedResults.value = expert
  if (!expert) {
    methodParameters.value = defaultMethodParameters(currentMethod.value)
    factorCombinationsEnabled.value = false
    factorCombinationLabels.value = {}
    resetFactorCombinationSettings('instant')
    alpha.value = 0.05
    ssType.value = 3
    estimateMarginalMeans.value = false
    emmFactors.value = []
    diagnosticPlots.value = false
    randomSlopes.value = []
    instantSplitRules.value = []
    calibrationEnabled.value = false
    calibrationColumns.value = []
    calibrationBaselineColumn.value = ''
    calibrationBaselineValue.value = ''
  }
  if (result.value) {
    invalidateInstantResult(`已切换到${expert ? '专业' : '简洁'}模式，旧结果已隐藏；请检查当前参数后重新执行分析。`)
  }
}

function setWorkspaceExpertMode(expert: boolean) {
  if (workspaceExpertMode.value === expert) return
  if (!expert) {
    const hasProfessionalData = workspaceDerivedColumns.value.length > 0 || workspaceSplitRules.value.length > 0 || workspaceSplits.value.some(column => workspaceFactors.value.includes(column))
    if (hasProfessionalData && !window.confirm('当前计划包含简洁模式不支持的自定义列或专业拆分配置。继续切换将自动整理这些设置，原始数据和历史结果不会被删除。是否继续？')) return
    const derivedNames = new Set(workspaceDerivedColumns.value.map(column => column.name))
    workspaceDvs.value = workspaceDvs.value.filter(column => !derivedNames.has(column))
    workspaceFactors.value = workspaceFactors.value.filter(column => !derivedNames.has(column))
    workspaceCovariates.value = workspaceCovariates.value.filter(column => !derivedNames.has(column))
    workspaceRandomFactors.value = workspaceRandomFactors.value.filter(column => !derivedNames.has(column))
    workspaceRandomSlopes.value = workspaceRandomSlopes.value.filter(column => !derivedNames.has(column))
    workspaceSplits.value = workspaceSplits.value.filter(column => !derivedNames.has(column) && !workspaceFactors.value.includes(column))
    workspaceDerivedColumns.value = []
    workspaceDerivedProfile.value = null
    workspaceDerivedWarnings.value = []
    workspaceSplitRules.value = []
  }
  workspaceExpertMode.value = expert
  workspaceDetailedResults.value = expert
  if (!expert) {
    workspaceMethodParameters.value = defaultMethodParameters(workspaceCurrentMethod.value)
    workspaceFactorCombinationsEnabled.value = false
    workspaceFactorCombinationLabels.value = {}
    resetFactorCombinationSettings('workspace')
    alpha.value = 0.05
    ssType.value = 3
    workspaceEstimateMarginalMeans.value = false
    workspaceEmmFactors.value = []
    workspaceDiagnosticPlots.value = false
    workspaceRandomSlopes.value = []
    workspaceSplitRules.value = []
    workspaceCalibrationEnabled.value = false
    workspaceCalibrationColumns.value = []
    workspaceCalibrationBaselineColumn.value = ''
    workspaceCalibrationBaselineValue.value = ''
  }
  if (workspaceRun.value?.result_json) {
    invalidateWorkspaceResult(`已切换到${expert ? '专业' : '简洁'}模式，当前结果已隐藏；请检查计划、保存并重新运行。`)
  }
}

function prepareFileReselection(event: Event) {
  if (interactionBusy.value) return
  ;(event.target as HTMLInputElement).value = ''
}

function startNewInstantAnalysis() {
  if (interactionBusy.value) return
  result.value = null
  file.value = null
  profile.value = null
  sourceProfile.value = null
  derivedColumns.value = []
  derivedWarnings.value = []
  selectedMethod.value = DEFAULT_INSTANT_METHOD
  instantExpertMode.value = false
  dependentVariables.value = []
  fixedFactors.value = []
  covariates.value = []
  randomFactors.value = []
  randomSlopes.value = []
  estimateMarginalMeans.value = false
  emmFactors.value = []
  contrastCorrection.value = 'holm'
  diagnosticPlots.value = false
  subjectId.value = ''
  repeatedFactor.value = ''
  splitBy.value = []
  instantSplitRules.value = []
  testValue.value = 0
  expectedProportionsText.value = ''
  alpha.value = 0.05
  ssType.value = 3
  const defaultMethod = methods.value.find(item => item.name === DEFAULT_INSTANT_METHOD)
  methodParameters.value = defaultMethodParameters(defaultMethod)
  factorCombinationsEnabled.value = false
  factorCombinationLabels.value = {}
  combinationPAdjust.value = 'holm'
  instantCompletedRunCount.value = 0
  preflightPriorRunCount.value = 0
  calibrationEnabled.value = false
  calibrationMethod.value = 'zscore'
  calibrationColumns.value = []
  calibrationBaselineColumn.value = ''
  calibrationBaselineValue.value = ''
  resetFactorCombinationSettings('instant')
  instantDetailedResults.value = false
  instantReportLinks.value = null
  instantBuiltinReport.value = null
  instantAIReport.value = null
  resultInvalidated.value = false
  resultInvalidatedReason.value = ''
  preflightOpen.value = false
  preflightReport.value = null
  pendingAnalysisAction.value = ''
  pendingWorkspacePlanId.value = ''
  if (fileInput.value) fileInput.value.value = ''
  clearInstantError()
  void nextTick(() => document.getElementById('instant-data-import')?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
}

function enumerateCombinations(items: string[], order: number, limit = 12) {
  const output: string[] = []
  const walk = (start: number, chosen: string[]) => {
    if (output.length >= limit) return
    if (chosen.length === order) { output.push(chosen.join(' × ')); return }
    for (let index = start; index < items.length; index += 1) walk(index + 1, [...chosen, items[index]])
  }
  walk(0, [])
  return output
}

function activeFactorCombinationNames(target: 'instant' | 'workspace') {
  const factors = target === 'instant' ? fixedFactors.value : workspaceFactors.value
  const enabled = target === 'instant' ? factorCombinationsEnabled.value : workspaceFactorCombinationsEnabled.value
  const minOrder = target === 'instant' ? factorCombinationMinOrder.value : workspaceFactorCombinationMinOrder.value
  const maxOrder = target === 'instant' ? factorCombinationMaxOrder.value : workspaceFactorCombinationMaxOrder.value
  if (!enabled) return []
  return Array.from({ length: Math.max(0, maxOrder - minOrder + 1) }, (_, index) =>
    enumerateCombinations(factors, minOrder + index, 1000)
  ).flat()
}

function serializeFactorCombinationLabels(target: 'instant' | 'workspace') {
  const aliases = target === 'instant' ? factorCombinationLabels.value : workspaceFactorCombinationLabels.value
  return Object.fromEntries(activeFactorCombinationNames(target).flatMap(name => {
    const label = String(aliases[name] ?? '').trim()
    return label && label !== name ? [[name, label]] : []
  }))
}

function factorCombinationNameIssues(target: 'instant' | 'workspace') {
  const aliases = target === 'instant' ? factorCombinationLabels.value : workspaceFactorCombinationLabels.value
  const names = activeFactorCombinationNames(target)
  const finalNames = names.map(name => String(aliases[name] ?? '').trim() || name)
  return finalNames.length !== new Set(finalNames).size ? ['组合名称不能重复，也不能与其他组合的默认名称相同'] : []
}

function setFactorCombinationLabel(target: 'instant' | 'workspace', name: string, value: string) {
  const labels = target === 'instant' ? factorCombinationLabels : workspaceFactorCombinationLabels
  labels.value = { ...labels.value, [name]: value }
}

function combinationCount(n: number, minOrder: number, maxOrder: number) {
  const choose = (total: number, selected: number) => {
    if (selected < 0 || selected > total) return 0
    let value = 1
    for (let index = 1; index <= selected; index += 1) value = value * (total - selected + index) / index
    return Math.round(value)
  }
  let count = 0
  for (let order = minOrder; order <= maxOrder; order += 1) count += choose(n, order)
  return count
}

function openFactorOverflowPrompt(target: 'instant' | 'workspace', column: string) {
  const method = target === 'instant' ? currentMethod.value : workspaceCurrentMethod.value
  const factors = target === 'instant' ? fixedFactors.value : workspaceFactors.value
  const maximum = effectiveFactorOrder(target)
  if (!method || maximum < 1 || !method.supports_batch) return
  if (target === 'instant' && !instantFactorCombinationsAllowed.value) return
  const projectedFactors = Array.from(new Set([...factors, ...(column ? [column] : [])]))
  const projectedCount = projectedFactors.length
  const correction = target === 'instant' ? combinationPAdjust.value : workspaceCombinationPAdjust.value
  factorOverflowPrompt.value = {
    open: true, target, column, methodLabel: method.label_zh, maximum,
    selectedCount: factors.length, projectedCount,
    combinationCount: combinationCount(projectedCount, 1, maximum),
    combinations: Array.from({ length: maximum }, (_, index) => enumerateCombinations(projectedFactors, index + 1, 12)).flat().slice(0, 12),
    correctionLabel: correction === 'fdr_bh' ? 'FDR-BH' : correction === 'none' ? '不校正' : correction[0].toUpperCase() + correction.slice(1),
  }
}

function closeFactorOverflowPrompt() {
  factorOverflowPrompt.value.open = false
}

function confirmFactorOverflow() {
  const prompt = factorOverflowPrompt.value
  if (!prompt.open) return
  if (prompt.target === 'instant') {
    if (prompt.column) clearColumnFromOtherRoles(prompt.column, 'factor')
    factorCombinationsEnabled.value = true
    if (prompt.column) fixedFactors.value = Array.from(new Set([...fixedFactors.value, prompt.column]))
    factorCombinationMinOrder.value = 1
    factorCombinationMaxOrder.value = prompt.maximum
  } else {
    workspaceDvs.value = workspaceDvs.value.filter(item => item !== prompt.column)
    workspaceCovariates.value = workspaceCovariates.value.filter(item => item !== prompt.column)
    workspaceRandomFactors.value = workspaceRandomFactors.value.filter(item => item !== prompt.column)
    workspaceSplits.value = workspaceSplits.value.filter(item => item !== prompt.column)
    workspaceRandomSlopes.value = workspaceRandomSlopes.value.filter(item => item !== prompt.column)
    workspaceEmmFactors.value = workspaceEmmFactors.value.filter(item => item !== prompt.column)
    if (workspaceSubjectId.value === prompt.column) workspaceSubjectId.value = ''
    if (workspaceRepeatedFactor.value === prompt.column) workspaceRepeatedFactor.value = ''
    workspaceFactorCombinationsEnabled.value = true
    if (prompt.column) workspaceFactors.value = Array.from(new Set([...workspaceFactors.value, prompt.column]))
    workspaceFactorCombinationMinOrder.value = 1
    workspaceFactorCombinationMaxOrder.value = prompt.maximum
  }
  factorOverflowPrompt.value.open = false
}

function toggleMultiSelectParameter(target: 'instant' | 'workspace', key: string, value: string) {
  const parameters = target === 'instant' ? methodParameters : workspaceMethodParameters
  const current = Array.isArray(parameters.value[key]) ? [...parameters.value[key]] : []
  let next = current.includes(value) ? current.filter(item => item !== value) : [...current, value]
  if (value === 'none' && next.includes('none')) next = ['none']
  else if (value === 'auto' && next.includes('auto')) next = ['auto']
  else next = next.filter(item => item !== 'none' && item !== 'auto')
  if (!next.length) next = ['none']
  parameters.value = { ...parameters.value, [key]: next }
}

function onFactorCombinationToggle(target: 'instant' | 'workspace', event: Event) {
  const checked = Boolean((event.target as HTMLInputElement | null)?.checked)
  const method = target === 'instant' ? currentMethod.value : workspaceCurrentMethod.value
  const factors = target === 'instant' ? fixedFactors.value : workspaceFactors.value
  const enabled = target === 'instant' ? factorCombinationsEnabled : workspaceFactorCombinationsEnabled
  if (target === 'instant' && !instantFactorCombinationsAllowed.value) {
    enabled.value = false
    resetFactorCombinationSettings(target)
    return
  }
  if (checked && !enabled.value && factors.length > effectiveFactorOrder(target)) {
    openFactorOverflowPrompt(target, '')
    enabled.value = false
    return
  }
  if (!checked && factors.length > effectiveFactorOrder(target)) {
    enabled.value = true
    return
  }
  enabled.value = checked
  resetFactorCombinationSettings(target)
}

function ensureMinimumDependentSelection(target: 'instant' | 'workspace') {
  const method = target === 'instant' ? currentMethod.value : workspaceCurrentMethod.value
  if (!method || method.dependent_mode !== 'joint') return
  const candidates = target === 'instant'
    ? (profile.value?.profile.columns ?? []).filter(item => item.inferred_role === 'dependent').map(item => item.name)
    : workspaceColumns.value.filter(item => item.inferred_role === 'dependent').map(item => item.name)
  const selected = target === 'instant' ? dependentVariables : workspaceDvs
  const needed = Math.max(0, method.min_dependent_vars - selected.value.length)
  if (needed > 0) {
    const additions = candidates.filter(item => !selected.value.includes(item)).slice(0, needed)
    selected.value = [...selected.value, ...additions]
  }
}


function restoreSuggestedRoles(target: 'instant' | 'workspace') {
  const method = target === 'instant' ? currentMethod.value : workspaceCurrentMethod.value
  const sourceColumns = target === 'instant' ? (profile.value?.profile.columns ?? []) : workspaceColumns.value
  if (!method || !sourceColumns.length) return
  const inferredDvs = sourceColumns.filter(item => item.inferred_role === 'dependent').map(item => item.name)
  const inferredFactors = sourceColumns.filter(item => item.inferred_role === 'between').map(item => item.name)
  const dvCount = method.dependent_mode === 'joint' ? Math.max(method.min_dependent_vars, 2) : Math.max(method.min_dependent_vars, method.dependent_mode === 'none' ? 0 : 1)
  const factorCount = Math.max(configuredMultiFactorOrder(target) ?? method.min_fixed_factors, method.requires_any_predictor ? 1 : 0)
  if (target === 'instant') {
    dependentVariables.value = inferredDvs.slice(0, dvCount)
    fixedFactors.value = inferredFactors.filter(item => !dependentVariables.value.includes(item)).slice(0, factorCount)
    covariates.value = []
    randomFactors.value = []
    randomSlopes.value = []
    subjectId.value = ''
    repeatedFactor.value = ''
    splitBy.value = []
    instantSplitRules.value = []
    factorCombinationsEnabled.value = false
    estimateMarginalMeans.value = false
    emmFactors.value = []
  } else {
    workspaceDvs.value = inferredDvs.slice(0, dvCount)
    workspaceFactors.value = inferredFactors.filter(item => !workspaceDvs.value.includes(item)).slice(0, factorCount)
    workspaceCovariates.value = []
    workspaceRandomFactors.value = []
    workspaceRandomSlopes.value = []
    workspaceSubjectId.value = ''
    workspaceRepeatedFactor.value = ''
    workspaceSplits.value = []
    workspaceFactorCombinationsEnabled.value = false
    workspaceEstimateMarginalMeans.value = false
    workspaceEmmFactors.value = []
  }
  resetFactorCombinationSettings(target)
}

const factorOrderLimit = computed(() => Math.max(1, Math.min(fixedFactors.value.length, currentMethod.value?.max_fixed_factors ?? fixedFactors.value.length)))
const emmCandidates = computed(() => Array.from(new Set([...fixedFactors.value, ...(repeatedFactor.value ? [repeatedFactor.value] : [])])))
const workspaceEmmCandidates = computed(() => Array.from(new Set([...workspaceFactors.value, ...(workspaceRepeatedFactor.value ? [workspaceRepeatedFactor.value] : [])])))
const factorCombinationCount = computed(() => factorCombinationsEnabled.value ? combinationCount(fixedFactors.value.length, factorCombinationMinOrder.value, factorCombinationMaxOrder.value) : 1)
const factorCombinationNames = computed(() => activeFactorCombinationNames('instant'))
const workspaceFactorOrderLimit = computed(() => Math.max(1, Math.min(workspaceFactors.value.length, workspaceCurrentMethod.value?.max_fixed_factors ?? workspaceFactors.value.length)))
const workspaceFactorCombinationCount = computed(() => workspaceFactorCombinationsEnabled.value ? combinationCount(workspaceFactors.value.length, workspaceFactorCombinationMinOrder.value, workspaceFactorCombinationMaxOrder.value) : 1)
const workspaceFactorCombinationNames = computed(() => activeFactorCombinationNames('workspace'))

function defaultMethodParameters(method?: MethodSpec) {
  return Object.fromEntries((method?.parameters ?? []).map(parameter => [parameter.key, parameter.default]))
}

function resetFactorCombinationSettings(target: 'instant' | 'workspace') {
  const method = target === 'instant' ? currentMethod.value : workspaceCurrentMethod.value
  const enabled = target === 'instant' ? factorCombinationsEnabled : workspaceFactorCombinationsEnabled
  const minimum = target === 'instant' ? factorCombinationMinOrder : workspaceFactorCombinationMinOrder
  const maximum = target === 'instant' ? factorCombinationMaxOrder : workspaceFactorCombinationMaxOrder
  const factors = target === 'instant' ? fixedFactors.value : workspaceFactors.value
  if (method?.max_fixed_factors === 0 || (target === 'instant' && !instantFactorCombinationsAllowed.value)) enabled.value = false
  const minOrder = Math.max(1, method?.min_fixed_factors ?? 1)
  const maxAllowed = Math.max(1, Math.min(factors.length || minOrder, method?.max_fixed_factors ?? (factors.length || minOrder)))
  minimum.value = enabled.value ? 1 : minOrder
  maximum.value = maxAllowed
  const labels = target === 'instant' ? factorCombinationLabels : workspaceFactorCombinationLabels
  const allowed = new Set(activeFactorCombinationNames(target))
  const pruned = Object.fromEntries(Object.entries(labels.value).filter(([name]) => allowed.has(name)))
  if (Object.keys(pruned).length !== Object.keys(labels.value).length) labels.value = pruned
}

watch(selectedMethod, () => {
  const method = currentMethod.value
  if (!method) return
  invalidateInstantResult('分析方法已经改变，旧结果与旧报告已清除；请检查新方法的变量角色后重新执行分析。')
  methodParameters.value = defaultMethodParameters(method)
  factorCombinationsEnabled.value = false
  factorCombinationLabels.value = {}
  if (factorOverflowPrompt.value.target === 'instant') factorOverflowPrompt.value.open = false
  restoreSuggestedRoles('instant')
})

watch(workspaceMethod, () => {
  const method = workspaceCurrentMethod.value
  if (!method) return
  invalidateWorkspaceResult('分析方法已经改变，旧运行结果与旧报告已清除；请按新方法保存并重新运行计划。')
  workspaceMethodParameters.value = defaultMethodParameters(method)
  workspaceFactorCombinationsEnabled.value = false
  workspaceFactorCombinationLabels.value = {}
  restoreSuggestedRoles('workspace')
})

watch([fixedFactors, factorCombinationsEnabled], () => resetFactorCombinationSettings('instant'), { deep: true })
watch([workspaceFactors, workspaceFactorCombinationsEnabled], () => resetFactorCombinationSettings('workspace'), { deep: true })
watch([fixedFactors, covariates, repeatedFactor], () => {
  const allowed = new Set([...fixedFactors.value, ...covariates.value, ...(repeatedFactor.value ? [repeatedFactor.value] : [])])
  randomSlopes.value = randomSlopes.value.filter(item => allowed.has(item))
  emmFactors.value = emmFactors.value.filter(item => emmCandidates.value.includes(item))
}, { deep: true })
watch([workspaceFactors, workspaceCovariates, workspaceRepeatedFactor], () => {
  const allowed = new Set([...workspaceFactors.value, ...workspaceCovariates.value, ...(workspaceRepeatedFactor.value ? [workspaceRepeatedFactor.value] : [])])
  workspaceRandomSlopes.value = workspaceRandomSlopes.value.filter(item => allowed.has(item))
  workspaceEmmFactors.value = workspaceEmmFactors.value.filter(item => workspaceEmmCandidates.value.includes(item))
}, { deep: true })

watch([
  workspaceDatasetId, workspaceDvs, workspaceFactors, workspaceCovariates, workspaceRandomFactors,
  workspaceRandomSlopes, workspaceSubjectId, workspaceRepeatedFactor, workspaceSplits,
  workspaceSplitRules, workspaceDerivedColumns, workspaceCalibrationEnabled, workspaceCalibrationMethod,
  workspaceCalibrationColumns, workspaceCalibrationBaselineColumn, workspaceCalibrationBaselineValue,
  workspaceMethodParameters, workspaceFactorCombinationsEnabled, workspaceFactorCombinationMinOrder,
  workspaceFactorCombinationMaxOrder, workspaceFactorCombinationLabels, workspaceCombinationPAdjust, workspaceEstimateMarginalMeans,
  workspaceEmmFactors, workspaceContrastCorrection, workspaceDiagnosticPlots,
], () => {
  invalidateWorkspaceResult('分析计划或数据选择已经改变，旧运行结果已隐藏；请保存并重新运行计划。')
}, { deep: true })

watch(percentageScale, () => {
  if (!profile.value) return
  profile.value = null
  result.value = null
  applyInstantError(friendlyError({ detail: '百分比解释方式已改变，请重新点击“读取并检查数据”，确保预览与统计计算使用同一尺度。' }, '需要重新读取数据'))
})

watch([
  selectedMethod, dependentVariables, fixedFactors, covariates, randomFactors, randomSlopes,
  subjectId, repeatedFactor, splitBy, instantSplitRules, alpha, ssType, methodParameters, factorCombinationsEnabled,
  derivedColumns, calibrationEnabled, calibrationMethod, calibrationColumns, calibrationBaselineColumn, calibrationBaselineValue,
  factorCombinationMinOrder, factorCombinationMaxOrder, factorCombinationLabels, combinationPAdjust, estimateMarginalMeans,
  emmFactors, contrastCorrection, diagnosticPlots, testValue, expectedProportionsText,
], () => {
  invalidateInstantResult('分析方法、变量角色或参数已经改变，旧结果已隐藏；请重新执行分析。')
}, { deep: true })

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  if (factorOverflowPrompt.value.open) closeFactorOverflowPrompt()
  else if (preflightOpen.value) preflightOpen.value = false
  else if (workspaceAuthOpen.value && !workspaceAuthLoading.value) workspaceAuthOpen.value = false
  else if (aiSettingsOpen.value) aiSettingsOpen.value = false
  else if (aiAssistantOpen.value) closeHelp()
}

function handleSessionError(event: Event) {
  sessionAccessError.value = (event as CustomEvent).detail
  operationTitle.value = ''
  operationDetail.value = ''
}

function retrySessionAdmission() {
  resetDataworkSession()
  window.location.reload()
}

function clearWorkspaceView() {
  workspaceProjects.value = []
  workspaceProject.value = null
  workspaceInfo.value = null
  workspaceDatasetId.value = ''
  workspaceSelectedPlanId.value = ''
  workspaceRun.value = null
  workspaceReportId.value = ''
  workspaceReportLinks.value = null
}

function handleWorkspaceAuthRequired(event: Event) {
  workspaceAuthPurpose.value = 'workspace'
  workspaceAuthState.value = workspaceAuthState.value
    ? { ...workspaceAuthState.value, authenticated: false }
    : { required: true, authenticated: false, idle_timeout_seconds: 600, temporary_session_cleanup: true }
  workspaceAuthError.value = (event as CustomEvent).detail
  workspaceAuthPassword.value = ''
  workspaceAuthOpen.value = true
  mode.value = 'instant'
  clearWorkspaceView()
}

async function enterWorkspace() {
  if (interactionBusy.value) return
  workspaceAuthPurpose.value = 'workspace'
  if (!workspaceAuthState.value) {
    try {
      workspaceAuthState.value = await apiRequest('/api/workspace-auth/status', undefined, '工作区认证状态读取失败')
    } catch (cause) {
      workspaceAuthError.value = friendlyError(cause, '工作区认证状态读取失败')
      workspaceAuthOpen.value = true
      return
    }
  }
  const access = workspaceAuthState.value
  if (!access?.authenticated) {
    workspaceAuthError.value = null
    workspaceAuthPassword.value = ''
    workspaceAuthOpen.value = true
    return
  }
  mode.value = 'workspace'
  try {
    await refreshWorkspaceProjects()
  } catch (cause) {
    applyWorkspaceError(cause, '项目列表读取失败')
  }
}

function authenticateForAi() {
  workspaceAuthPurpose.value = 'ai'
  workspaceAuthError.value = null
  workspaceAuthPassword.value = ''
  workspaceAuthOpen.value = true
}

async function unlockWorkspace() {
  if (!workspaceAuthPassword.value || workspaceAuthLoading.value) return
  workspaceAuthLoading.value = true
  workspaceAuthError.value = null
  try {
    workspaceAuthState.value = await apiRequest('/api/workspace-auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: workspaceAuthPassword.value }),
    }, '工作区登录失败')
    workspaceAuthPassword.value = ''
    workspaceAuthOpen.value = false
    if (workspaceAuthPurpose.value === 'ai') {
      aiStatus.value = await apiRequest('/api/ai/status', undefined, 'AI 状态读取失败')
    } else {
      mode.value = 'workspace'
      await refreshWorkspaceProjects()
    }
  } catch (cause) {
    workspaceAuthError.value = friendlyError(cause, '工作区登录失败')
  } finally {
    workspaceAuthLoading.value = false
  }
}

async function logoutWorkspace() {
  if (workspaceLoading.value) return
  try {
    workspaceAuthState.value = await apiRequest('/api/workspace-auth/logout', { method: 'POST' }, '工作区退出失败')
  } finally {
    mode.value = 'instant'
    clearWorkspaceView()
  }
}

async function refreshSessionStatus() {
  try {
    const status = await apiRequest('/api/session/heartbeat', { method: 'POST' }, '用户状态读取失败') as SessionState
    sessionState.value = status
    if (!status.active) {
      const code = status.expired ? 'session_expired' : 'session_capacity_reached'
      sessionAccessError.value = friendlyError({
        error: {
          code,
          message: status.expired
            ? '当前会话已因超过 10 分钟未实际操作而退出。'
            : '当前会话已不在活跃用户列表中。',
        },
      })
    }
  } catch (cause) {
    const problem = friendlyError(cause, '用户状态读取失败')
    if (problem.code === 'session_expired' || problem.code === 'session_capacity_reached') {
      sessionAccessError.value = problem
    }
  }
}

function recordSessionActivity() {
  const now = Date.now()
  if (now - lastSessionActivityAt < SESSION_ACTIVITY_THROTTLE_MS) return
  lastSessionActivityAt = now
  void apiRequest('/api/session/activity', { method: 'POST' }, '用户活动状态更新失败')
    .then(status => { sessionState.value = status as SessionState })
    .catch(() => undefined)
}

function handlePageHide(event: PageTransitionEvent) {
  if (!event.persisted) releaseDataworkSession()
}

onMounted(async () => {
  window.addEventListener('keydown', handleGlobalKeydown)
  window.addEventListener('scroll', handlePageScroll, { passive: true })
  window.addEventListener('datawork-session-error', handleSessionError)
  window.addEventListener('datawork-workspace-auth-required', handleWorkspaceAuthRequired)
  window.addEventListener('pagehide', handlePageHide)
  window.addEventListener('pointerdown', recordSessionActivity, { passive: true })
  window.addEventListener('keydown', recordSessionActivity)
  handlePageScroll()
  operationTitle.value = '正在初始化 DataWork'
  operationDetail.value = '正在检查统计方法、工作区与可选 AI 配置。'
  try {
    sessionState.value = await apiRequest('/api/session', undefined, '用户会话建立失败')
  } catch (cause) {
    sessionAccessError.value = friendlyError(cause, '用户会话建立失败')
    operationTitle.value = ''
    operationDetail.value = ''
    return
  }
  sessionStatusTimer = window.setInterval(refreshSessionStatus, SESSION_HEARTBEAT_INTERVAL_MS)
  const requests = await Promise.allSettled([
    apiRequest('/api/methods', undefined, '统计方法目录读取失败'),
    apiRequest('/api/health', undefined, '服务状态读取失败'),
    apiRequest('/api/workspace-auth/status', undefined, '工作区认证状态读取失败'),
    apiRequest('/api/ai/status', undefined, 'AI 状态读取失败'),
  ])
  if (requests[0].status === 'fulfilled') methods.value = requests[0].value
  else applyInstantError(requests[0].reason, '统计方法目录读取失败')
  if (requests[1].status === 'fulfilled') health.value = requests[1].value
  if (requests[2].status === 'fulfilled') workspaceAuthState.value = requests[2].value
  if (requests[3].status === 'fulfilled') aiStatus.value = requests[3].value
  methodParameters.value = defaultMethodParameters(currentMethod.value)
  workspaceMethodParameters.value = defaultMethodParameters(workspaceCurrentMethod.value)
  resetFactorCombinationSettings('instant')
  resetFactorCombinationSettings('workspace')
  operationTitle.value = ''
  operationDetail.value = ''
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleGlobalKeydown)
  window.removeEventListener('scroll', handlePageScroll)
  window.removeEventListener('datawork-session-error', handleSessionError)
  window.removeEventListener('datawork-workspace-auth-required', handleWorkspaceAuthRequired)
  window.removeEventListener('pagehide', handlePageHide)
  window.removeEventListener('pointerdown', recordSessionActivity)
  window.removeEventListener('keydown', recordSessionActivity)
  if (workflowJumpTimer !== undefined) window.clearTimeout(workflowJumpTimer)
  if (sessionStatusTimer !== undefined) window.clearInterval(sessionStatusTimer)
})

function handlePageScroll() {
  showBackToTop.value = window.scrollY > 360
}

function scrollToTop() {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' })
}

function jumpToWorkflowStep(index: number) {
  const targetIds = mode.value === 'instant'
    ? ['instant-data-import', 'instant-data-check', 'analysis-roles', 'instant-preflight-action', 'instant-analysis-result']
    : ['workspace-project-selection', 'workspace-data-selection', 'workspace-analysis-roles', 'workspace-run-plans', 'workspace-latest-result']
  let target: HTMLElement | null = document.getElementById(targetIds[index])
  if (!target) {
    for (let fallbackIndex = Math.min(index, targetIds.length - 1); fallbackIndex >= 0; fallbackIndex -= 1) {
      target = document.getElementById(targetIds[fallbackIndex])
      if (target) break
    }
  }
  if (!target) return
  workflowJumpTarget.value = target.id
  if (workflowJumpTimer !== undefined) window.clearTimeout(workflowJumpTimer)
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  target.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' })
  workflowJumpTimer = window.setTimeout(() => {
    if (workflowJumpTarget.value === target?.id) workflowJumpTarget.value = ''
  }, 1800)
}

function clearInstantError() {
  error.value = ''
  errorTitle.value = ''
  errorHints.value = []
}

function clearWorkspaceError() {
  workspaceError.value = ''
  workspaceErrorTitle.value = ''
  workspaceErrorHints.value = []
}

function applyInstantError(cause: unknown, fallback = '操作失败') {
  const info = cause && typeof cause === 'object' && 'hints' in cause
    ? cause as any
    : friendlyError({ detail: errorMessage(cause) }, fallback)
  error.value = info.message || fallback
  errorTitle.value = info.title || '操作未完成'
  errorHints.value = info.hints || []
}

function applyWorkspaceError(cause: unknown, fallback = '工作区操作失败') {
  const info = cause && typeof cause === 'object' && 'hints' in cause
    ? cause as any
    : friendlyError({ detail: errorMessage(cause) }, fallback)
  workspaceError.value = info.message || fallback
  workspaceErrorTitle.value = info.title || '工作区操作未完成'
  workspaceErrorHints.value = info.hints || []
}

function beginOperation(title: string, detail: string) {
  operationTitle.value = title
  operationDetail.value = detail
}

function endOperation() {
  operationTitle.value = ''
  operationDetail.value = ''
}

function parseExpectedProportions(): number[] {
  const raw = expectedProportionsText.value.trim()
  if (!raw) return []
  const parts = raw.split(',').map(item => item.trim())
  if (parts.some(item => !item)) throw friendlyError({ detail: '理论比例中存在空项，请使用英文逗号分隔完整数值。' }, '理论比例格式错误')
  const values = parts.map(Number)
  if (values.some(item => !Number.isFinite(item))) throw friendlyError({ detail: '理论比例必须全部是有效数值。' }, '理论比例格式错误')
  return values
}

function openHelp(step = '') {
  manualHelpStep.value = step
  aiAssistantOpen.value = true
}

function closeHelp() {
  aiAssistantOpen.value = false
  manualHelpStep.value = ''
}

function updateAiStatus(status: any) {
  aiStatus.value = status
}

function buildInstantPlan() {
  const combinationsEnabled = instantFactorCombinationsAllowed.value && factorCombinationsEnabled.value
  const professional = instantExpertMode.value
  return {
    interface_mode: professional ? 'professional' : 'concise',
    dependent_variables: dependentVariables.value,
    fixed_factors: fixedFactors.value,
    covariates: covariates.value,
    random_factors: randomFactors.value,
    random_slopes: randomSlopes.value,
    estimate_marginal_means: professional && estimateMarginalMeans.value,
    emm_factors: professional && estimateMarginalMeans.value ? emmFactors.value : [],
    contrast_correction: professional ? contrastCorrection.value : 'holm',
    diagnostic_plots: professional && diagnosticPlots.value,
    subject_id: subjectId.value || null,
    repeated_factor: repeatedFactor.value || null,
    split_by: splitBy.value,
    split_rules: serializeInstantSplitRules(),
    derived_columns: professional ? derivedColumns.value : [],
    test_value: testValue.value,
    expected_proportions: parseExpectedProportions(),
    method_parameters: professional ? methodParameters.value : defaultMethodParameters(currentMethod.value),
    factor_combinations_enabled: combinationsEnabled,
    factor_combination_order: combinationsEnabled ? factorCombinationMaxOrder.value : null,
    factor_combination_min_order: combinationsEnabled ? 1 : null,
    factor_combination_max_order: combinationsEnabled ? factorCombinationMaxOrder.value : null,
    factor_combination_labels: professional && combinationsEnabled ? serializeFactorCombinationLabels('instant') : {},
    cross_model_p_adjust: combinationPAdjust.value,
    combination_p_adjust: combinationPAdjust.value,
    calibration_enabled: professional && calibrationEnabled.value,
    calibration_method: calibrationMethod.value,
    calibration_columns: professional && calibrationEnabled.value ? calibrationColumns.value : [],
    calibration_baseline_column: professional && calibrationEnabled.value ? calibrationBaselineColumn.value || null : null,
    calibration_baseline_value: professional && calibrationEnabled.value ? calibrationBaselineValue.value || null : null,
    method: selectedMethod.value,
    alpha: professional ? alpha.value : 0.05,
    ss_type: professional ? ssType.value : 3,
  }
}

type CrossModelCorrection = 'none' | 'bonferroni' | 'holm' | 'fdr_bh'

const CROSS_MODEL_CORRECTION_LABELS: Record<CrossModelCorrection, string> = {
  none: '不校正',
  bonferroni: 'Bonferroni',
  holm: 'Holm',
  fdr_bh: 'FDR-BH',
}

function correctionMethodFromSettings(settings: any): CrossModelCorrection | '' {
  const raw = String(settings?.cross_model_p_adjust ?? settings?.combination_p_adjust ?? settings?.p_adjust ?? '').trim().toLowerCase()
  return raw in CROSS_MODEL_CORRECTION_LABELS ? raw as CrossModelCorrection : ''
}

function correctionMethodFromPreflight(report: any): CrossModelCorrection | '' {
  const batchMethod = correctionMethodFromSettings({ p_adjust: report?.batch_summary?.p_adjust })
  return batchMethod || correctionMethodFromSettings(report?.selections)
}

function correctionMethodFromExecution(execution: any): CrossModelCorrection | '' {
  return correctionMethodFromSettings(execution?.result?.settings)
    || correctionMethodFromSettings(execution?.plan)
    || correctionMethodFromSettings(execution?.settings)
}

function correctionMismatchMessage(requested: CrossModelCorrection, returned: CrossModelCorrection) {
  return `页面选择了“${CROSS_MODEL_CORRECTION_LABELS[requested]}”，但当前后端返回“${CROSS_MODEL_CORRECTION_LABELS[returned]}”。这通常表示旧后端进程仍在运行。本次分析已阻止，请完全退出并重新启动 DataWork 后再试。`
}

function guardPreflightCorrection(report: any, requestedPlan: any) {
  const requested = correctionMethodFromSettings(requestedPlan)
  const returned = correctionMethodFromPreflight(report)
  if (!requested || !returned || requested === returned) return report
  return {
    ...report,
    ready: false,
    issues: [
      ...(Array.isArray(report?.issues) ? report.issues : []),
      {
        severity: 'error',
        field: 'cross_model_p_adjust',
        code: 'correction_setting_mismatch',
        message: correctionMismatchMessage(requested, returned),
      },
    ],
  }
}

function assertExecutionCorrection(execution: any, requestedPlan: any) {
  const requested = correctionMethodFromSettings(requestedPlan)
  const returned = correctionMethodFromExecution(execution)
  if (!requested || !returned || requested === returned) return
  const message = correctionMismatchMessage(requested, returned)
  throw friendlyError({
    error: {
      code: 'correction_setting_mismatch',
      message,
      issues: [{ severity: 'error', field: 'cross_model_p_adjust', code: 'correction_setting_mismatch', message }],
    },
  }, '分析校正设置不一致')
}

function workspacePlanJson(planId: string) {
  return workspaceProject.value?.plans.find(item => item.id === planId)?.plan_json ?? null
}

function locatePreflightField(field: string) {
  preflightOpen.value = false
  const baseField = field.split('.')[0]
  const targetMap: Record<string, string> = {
    method: 'analysis-method', dependent_variables: 'analysis-roles', fixed_factors: 'analysis-roles',
    covariates: 'analysis-roles', random_factors: 'analysis-roles', random_slopes: 'phase3-options',
    subject_id: 'analysis-roles', repeated_factor: 'analysis-roles', split_by: 'analysis-roles', split_rules: 'analysis-roles',
    expected_proportions: 'advanced-parameters', method_parameters: 'advanced-parameters',
    emm_factors: 'phase3-options', columns: 'analysis-roles',
  }
  const id = mode.value === 'workspace' ? `workspace-${targetMap[baseField] ?? 'analysis-roles'}` : (targetMap[baseField] ?? 'analysis-roles')
  focusedField.value = id
  window.setTimeout(() => { focusedField.value = '' }, 2400)
  window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50)
}

function handleFile(event: Event) {
  if (interactionBusy.value) return
  const target = event.target as HTMLInputElement
  file.value = target.files?.[0] ?? null
  profile.value = null
  sourceProfile.value = null
  derivedColumns.value = []
  derivedWarnings.value = []
  result.value = null
  instantDetailedResults.value = false
  instantReportLinks.value = null
  instantBuiltinReport.value = null
  instantAIReport.value = null
  preflightOpen.value = false
  preflightReport.value = null
  pendingAnalysisAction.value = ''
  pendingWorkspacePlanId.value = ''
  instantCompletedRunCount.value = 0
  preflightPriorRunCount.value = 0
  resultInvalidated.value = false
  resultInvalidatedReason.value = ''
  clearInstantError()
}

async function loadProfile() {
  if (!file.value || interactionBusy.value) return
  loadingProfile.value = true
  clearInstantError()
  result.value = null
  beginOperation('正在读取并检查数据', '正在识别编码、清理空白列、检查缺失值并推断变量角色。')
  try {
    const body = new FormData()
    body.append('file', file.value)
    body.append('percentage_scale', percentageScale.value)
    const payload = await apiRequest('/api/profile', { method: 'POST', body }, '数据读取失败')
    profile.value = payload
    sourceProfile.value = structuredClone(payload)
    resultInvalidated.value = false
    resultInvalidatedReason.value = ''

    const inferredDvs = payload.profile.columns
      .filter((column: ColumnProfile) => column.inferred_role === 'dependent')
      .map((column: ColumnProfile) => column.name)
    const inferredFactors = payload.profile.columns
      .filter((column: ColumnProfile) => column.inferred_role === 'between')
      .map((column: ColumnProfile) => column.name)
    const initialDvCount = currentMethod.value?.dependent_mode === 'joint'
      ? Math.max(currentMethod.value?.min_dependent_vars ?? 1, 1) : 1
    dependentVariables.value = inferredDvs.slice(0, initialDvCount)
    const factorLimit = configuredMultiFactorOrder('instant') ?? (currentMethod.value?.max_fixed_factors === null ? Math.max(currentMethod.value?.min_fixed_factors ?? 0, currentMethod.value?.requires_any_predictor ? 1 : 0) : (currentMethod.value?.max_fixed_factors ?? 1))
    fixedFactors.value = inferredFactors.slice(0, factorLimit)
    covariates.value = []
    randomFactors.value = []
    randomSlopes.value = []
    estimateMarginalMeans.value = false
    emmFactors.value = []
    subjectId.value = ''
    repeatedFactor.value = ''
  } catch (cause) {
    profile.value = null
    applyInstantError(cause, '数据读取失败')
  } finally {
    loadingProfile.value = false
    endOperation()
  }
}

function removeUnavailableInstantRoles() {
  const available = new Set(profile.value?.profile.columns.map(column => column.name) ?? [])
  const derived = instantDerivedNames.value
  dependentVariables.value = dependentVariables.value.filter(column => available.has(column))
  fixedFactors.value = fixedFactors.value.filter(column => available.has(column) && !derived.has(column))
  covariates.value = covariates.value.filter(column => available.has(column) && !derived.has(column))
  randomFactors.value = randomFactors.value.filter(column => available.has(column) && !derived.has(column))
  randomSlopes.value = randomSlopes.value.filter(column => available.has(column) && !derived.has(column))
  splitBy.value = splitBy.value.filter(column => available.has(column) && !derived.has(column))
  instantSplitRules.value = instantSplitRules.value.filter(rule => available.has(rule.column) && !derived.has(rule.column))
  if (!available.has(subjectId.value) || derived.has(subjectId.value)) subjectId.value = ''
  if (!available.has(repeatedFactor.value) || derived.has(repeatedFactor.value)) repeatedFactor.value = ''
}

async function refreshInstantDerivedPreview() {
  if (!file.value || !sourceProfile.value || !instantExpertMode.value) return
  derivedPreviewLoading.value = true
  clearInstantError()
  try {
    if (!derivedColumns.value.length) {
      profile.value = structuredClone(toRaw(sourceProfile.value))
      derivedWarnings.value = []
      removeUnavailableInstantRoles()
      return
    }
    const body = new FormData()
    body.append('file', file.value)
    body.append('percentage_scale', percentageScale.value)
    body.append('derived_columns_json', JSON.stringify(derivedColumns.value))
    const payload = await apiRequest('/api/derived/preview', { method: 'POST', body }, '自定义列计算失败')
    profile.value = {
      ...sourceProfile.value,
      profile: payload.profile,
      columns: payload.columns,
      preview: payload.preview,
    }
    derivedWarnings.value = payload.warnings ?? []
    removeUnavailableInstantRoles()
    invalidateInstantResult('自定义列已修改，旧结果已隐藏；请重新执行分析。')
  } catch (cause) {
    applyInstantError(cause, '自定义列计算失败')
  } finally {
    derivedPreviewLoading.value = false
  }
}

function clearColumnFromOtherRoles(column: string, keep: string) {
  if (keep !== 'dv') dependentVariables.value = dependentVariables.value.filter(item => item !== column)
  if (keep !== 'factor' && !(instantExpertMode.value && keep === 'split')) fixedFactors.value = fixedFactors.value.filter(item => item !== column)
  if (keep !== 'covariate') covariates.value = covariates.value.filter(item => item !== column)
  if (keep !== 'random') randomFactors.value = randomFactors.value.filter(item => item !== column)
  if (!['factor','covariate','repeated','random_slope'].includes(keep)) randomSlopes.value = randomSlopes.value.filter(item => item !== column)
  if (keep !== 'split' && !(instantExpertMode.value && keep === 'factor')) {
    splitBy.value = splitBy.value.filter(item => item !== column)
    instantSplitRules.value = instantSplitRules.value.filter(rule => rule.column !== column)
  }
  if (keep !== 'subject' && subjectId.value === column) subjectId.value = ''
  if (keep !== 'repeated' && repeatedFactor.value === column) repeatedFactor.value = ''
}

function toggleSelection(target: 'dv' | 'factor' | 'covariate' | 'random' | 'subject' | 'repeated' | 'split', column: string) {
  const method = currentMethod.value
  if (isInstantDerivedColumn(column) && target !== 'dv') return
  if (target === 'split' && !showInstantSplitRole.value) return
  if (target === 'subject') { subjectId.value = subjectId.value === column ? '' : column; if (subjectId.value) clearColumnFromOtherRoles(column, 'subject'); return }
  if (target === 'repeated') { repeatedFactor.value = repeatedFactor.value === column ? '' : column; if (repeatedFactor.value) clearColumnFromOtherRoles(column, 'repeated'); return }
  const map = { dv: dependentVariables, factor: fixedFactors, covariate: covariates, random: randomFactors, split: splitBy }
  const list = map[target]
  if (list.value.includes(column)) {
    list.value = list.value.filter(item => item !== column)
    if (target === 'split') instantSplitRules.value = instantSplitRules.value.filter(rule => rule.column !== column)
    return
  }
  const max = target === 'dv' ? (method?.dependent_mode === 'single' && method?.supports_batch ? null : method?.max_dependent_vars)
    : target === 'factor' ? (instantFactorCombinationsAllowed.value && factorCombinationsEnabled.value ? null : effectiveFactorOrder('instant'))
    : target === 'covariate' ? method?.max_covariates
    : target === 'random' ? method?.max_random_factors : null
  if (max !== null && max !== undefined && list.value.length >= max) {
    if (target === 'factor' && configuredMultiFactorOrder('instant') === null) openFactorOverflowPrompt('instant', column)
    return
  }
  clearColumnFromOtherRoles(column, target)
  list.value = [...list.value, column]
  if (instantExpertMode.value && ((target === 'split' && fixedFactors.value.includes(column)) || (target === 'factor' && splitBy.value.includes(column)))) {
    enableCustomSplit(column)
  }
}

let splitGroupSequence = 0
function newSplitGroup(index: number): SplitGroupDraft {
  return { id: ++splitGroupSequence, label: `分组 ${index}`, values: [], lower: '', upper: '', includeLower: true, includeUpper: false }
}

function splitRuleFor(column: string) {
  return instantSplitRules.value.find(rule => rule.column === column)
}

function splitColumnProfile(column: string) {
  return profile.value?.profile.columns.find(item => item.name === column)
}

function enableCustomSplit(column: string) {
  if (splitRuleFor(column)) return
  const dtype = splitColumnProfile(column)?.dtype.toLowerCase() ?? ''
  const kind: SplitRuleDraft['kind'] = /(int|float|double|decimal)/.test(dtype) ? 'numeric' : 'categorical'
  instantSplitRules.value = [...instantSplitRules.value, { column, kind, groups: [newSplitGroup(1)] }]
}

function disableCustomSplit(column: string) {
  instantSplitRules.value = instantSplitRules.value.filter(rule => rule.column !== column)
}

function addSplitGroup(rule: SplitRuleDraft) {
  rule.groups.push(newSplitGroup(rule.groups.length + 1))
}

function removeSplitGroup(rule: SplitRuleDraft, groupId: number) {
  rule.groups = rule.groups.filter(group => group.id !== groupId)
}

function updateCategoricalValues(rule: SplitRuleDraft, group: SplitGroupDraft, raw: string) {
  const values = raw.split(/[，,、;；\n]/).map(value => value.trim()).filter(Boolean)
  const occupied = new Set(rule.groups.filter(item => item.id !== group.id).flatMap(item => item.values))
  group.values = Array.from(new Set(values)).filter(value => !occupied.has(value))
}

function toggleCategoricalValue(rule: SplitRuleDraft, group: SplitGroupDraft, value: string) {
  for (const item of rule.groups) {
    if (item.id !== group.id) item.values = item.values.filter(existing => existing !== value)
  }
  group.values = group.values.includes(value) ? group.values.filter(existing => existing !== value) : [...group.values, value]
}

function serializeInstantSplitRules() {
  if (!instantExpertMode.value) return []
  return instantSplitRules.value.filter(rule => splitBy.value.includes(rule.column)).map(rule => ({
    column: rule.column,
    kind: rule.kind,
    groups: rule.groups.map(group => rule.kind === 'categorical'
      ? { label: group.label.trim(), values: group.values }
      : {
          label: group.label.trim(), values: [],
          lower: String(group.lower).trim() === '' ? null : Number(group.lower),
          upper: String(group.upper).trim() === '' ? null : Number(group.upper),
          include_lower: group.includeLower, include_upper: group.includeUpper,
        }),
  }))
}

function workspaceSplitRuleFor(column: string) {
  return workspaceSplitRules.value.find(rule => rule.column === column)
}

function enableWorkspaceCustomSplit(column: string) {
  if (workspaceSplitRuleFor(column)) return
  const dtype = workspaceColumns.value.find(item => item.name === column)?.dtype.toLowerCase() ?? ''
  const kind: SplitRuleDraft['kind'] = /(int|float|double|decimal)/.test(dtype) ? 'numeric' : 'categorical'
  workspaceSplitRules.value = [...workspaceSplitRules.value, { column, kind, groups: [newSplitGroup(1)] }]
}

function disableWorkspaceCustomSplit(column: string) {
  workspaceSplitRules.value = workspaceSplitRules.value.filter(rule => rule.column !== column)
}

function serializeWorkspaceSplitRules() {
  if (!workspaceExpertMode.value) return []
  return workspaceSplitRules.value.filter(rule => workspaceSplits.value.includes(rule.column)).map(rule => ({
    column: rule.column,
    kind: rule.kind,
    groups: rule.groups.map(group => rule.kind === 'categorical'
      ? { label: group.label.trim(), values: group.values }
      : {
          label: group.label.trim(), values: [],
          lower: String(group.lower).trim() === '' ? null : Number(group.lower),
          upper: String(group.upper).trim() === '' ? null : Number(group.upper),
          include_lower: group.includeLower, include_upper: group.includeUpper,
        }),
  }))
}

function toggleRandomSlope(column: string) {
  if (isInstantDerivedColumn(column)) return
  const allowed = fixedFactors.value.includes(column) || covariates.value.includes(column) || repeatedFactor.value === column
  if (!allowed) return
  if (randomSlopes.value.includes(column)) { randomSlopes.value = randomSlopes.value.filter(item => item !== column); return }
  const max = currentMethod.value?.max_random_slopes
  if (max !== null && max !== undefined && randomSlopes.value.length >= max) return
  randomSlopes.value = [...randomSlopes.value, column]
}

function toggleEmmFactor(column: string) {
  emmFactors.value = emmFactors.value.includes(column) ? emmFactors.value.filter(item => item !== column) : [...emmFactors.value, column]
}

async function requestAnalysis() {
  if (!file.value || !profile.value || interactionBusy.value) return
  pendingAnalysisAction.value = 'instant'
  pendingWorkspacePlanId.value = ''
  preflightPriorRunCount.value = instantCompletedRunCount.value
  preflightOpen.value = true
  preflightLoading.value = true
  preflightReport.value = null
  clearInstantError()
  try {
    const plan = buildInstantPlan()
    const body = new FormData()
    body.append('file', file.value)
    body.append('plan_json', JSON.stringify(plan))
    body.append('percentage_scale', percentageScale.value)
    const report = await apiRequest('/api/preflight', { method: 'POST', body }, '分析前检查失败')
    preflightReport.value = guardPreflightCorrection(report, plan)
  } catch (cause) {
    const info = cause && typeof cause === 'object' && 'message' in cause ? cause as any : friendlyError({ detail: errorMessage(cause) }, '分析前检查失败')
    preflightReport.value = {
      ready: false,
      issues: [...(info.issues ?? []), { severity: 'error', field: info.issues?.[0]?.field ?? '', code: info.code ?? 'preflight_failed', message: info.message }],
      selections: {},
      batch_summary: { enabled: Boolean(splitBy.value.length), split_by: splitBy.value, group_count: 0 },
    }
  } finally {
    preflightLoading.value = false
  }
}

async function confirmPreflight() {
  if (!preflightReport.value?.ready || interactionBusy.value) return
  preflightOpen.value = false
  const action = pendingAnalysisAction.value
  const workspacePlanId = pendingWorkspacePlanId.value
  pendingAnalysisAction.value = ''
  pendingWorkspacePlanId.value = ''
  if (action === 'workspace') await executeWorkspacePlan(workspacePlanId)
  else if (action === 'instant') await executeAnalysis()
}

async function executeAnalysis() {
  if (!file.value || loadingAnalysis.value) return
  loadingAnalysis.value = true
  clearInstantError()
  result.value = null
  instantReportLinks.value = null
  instantBuiltinReport.value = null
  instantAIReport.value = null
  beginOperation('正在执行统计分析', '正在拟合模型、计算检验与效应量；复杂批量任务可能需要更长时间。')
  try {
    const plan = buildInstantPlan()
    const body = new FormData()
    body.append('file', file.value)
    body.append('plan_json', JSON.stringify(plan))
    body.append('percentage_scale', percentageScale.value)
    const execution = await apiRequest('/api/analyze', { method: 'POST', body }, '分析失败')
    assertExecutionCorrection(execution, plan)
    result.value = execution
    instantResultCompletedAt.value = new Date().toISOString()
    instantResultContextId.value = `instant:${Date.now()}:${++instantResultContextSequence}`
    instantCompletedRunCount.value += 1
    instantDetailedResults.value = instantExpertMode.value
    resultInvalidated.value = false
    resultInvalidatedReason.value = ''
    await nextTick()
    document.getElementById('instant-analysis-result')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    void monitorBatchExport(result.value)
    void prepareResultReports('instant', result.value)
  } catch (cause) {
    applyInstantError(cause, '分析失败')
  } finally {
    loadingAnalysis.value = false
    endOperation()
  }
}


async function generateInstantReport() {
  if (!result.value || result.value.kind !== 'single' || instantReportLoading.value) return
  instantReportLoading.value = true
  clearInstantError()
  beginOperation('正在生成可下载结果', '正在整理 Excel、Markdown、结果 JSON 与可复现信息。')
  try {
    const payload = await apiRequest('/api/instant/reports', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ execution: result.value, title: `${result.value.result?.method?.label_zh ?? 'DataWork'} 统计分析报告` }),
    }, '结果文件生成失败')
    instantReportLinks.value = {
      zip: payload.download_url,
      xlsx: payload.xlsx_download_url,
      markdown: payload.markdown_download_url,
    }
  } catch (cause) {
    applyInstantError(cause, '结果文件生成失败')
  } finally {
    instantReportLoading.value = false
    endOperation()
  }
}

function resultMethodLabel(execution: any) {
  if (execution?.kind === 'batch') {
    const methodName = String(execution?.result?.method ?? execution?.plan?.method ?? '')
    return methods.value.find(method => method.name === methodName)?.label_zh || methodName || '多模型分析'
  }
  return execution?.result?.method?.label_zh ?? '统计分析'
}

const AI_REPORT_PREVIEW_LIMIT = 20
const AI_REPORT_ROLE_KEYS = [
  'dependent_variables', 'fixed_factors', 'covariates', 'random_factors',
  'random_slopes', 'subject_id', 'repeated_factor', 'split_by', 'split_rules', 'derived_columns',
] as const

function resultAnalysisSettings(execution: any) {
  return execution?.plan ?? execution?.result?.settings ?? {}
}

function buildAIReportContext(target: 'instant' | 'workspace', execution: any) {
  const settings = resultAnalysisSettings(execution)
  const dataRoles: Record<string, string[]> = {}
  const relevantColumns = new Set<string>()
  for (const key of AI_REPORT_ROLE_KEYS) {
    const raw = settings?.[key]
    const values = (Array.isArray(raw) ? raw : raw ? [raw] : [])
      .map((item: unknown) => String(item).trim())
      .filter(Boolean)
    dataRoles[key] = values
    values.forEach(value => relevantColumns.add(value))
  }
  const dataProfile = target === 'instant' ? profile.value?.profile : workspaceDataset.value?.profile_json
  const selectedProfiles = (dataProfile?.columns ?? []).filter(column => relevantColumns.has(column.name))
  const rawPreview = target === 'instant' ? (profile.value?.preview ?? []) : []
  const dataPreview = rawPreview.slice(0, AI_REPORT_PREVIEW_LIMIT).map(row =>
    Object.fromEntries([...relevantColumns].filter(column => column in row).map(column => [column, row[column]])),
  )
  return {
    execution_kind: String(execution?.kind ?? 'single'),
    method: {
      name: String(settings?.method ?? execution?.result?.method?.name ?? execution?.result?.method ?? ''),
      label_zh: resultMethodLabel(execution),
    },
    data_roles: dataRoles,
    analysis_settings: {
      alpha: settings?.alpha ?? execution?.result?.alpha,
      ss_type: settings?.ss_type,
      combination_p_adjust: settings?.combination_p_adjust ?? execution?.result?.settings?.combination_p_adjust,
      contrast_correction: settings?.contrast_correction,
      method_parameters: settings?.method_parameters ?? {},
    },
    data_profile: dataProfile ? {
      n_rows: dataProfile.n_rows,
      n_cols: dataProfile.n_cols,
      total_missing_rate: dataProfile.total_missing_rate,
      columns: selectedProfiles,
    } : {},
    data_preview: dataPreview,
    preview_policy: {
      max_rows: AI_REPORT_PREVIEW_LIMIT,
      included_columns: [...relevantColumns],
      workspace_preview_available: target === 'instant',
    },
  }
}

async function loadBuiltinResultReport(target: 'instant' | 'workspace', execution: any, showError = false) {
  if (!execution) return null
  if (builtinReportPromises[target]) return builtinReportPromises[target]
  builtinReportLoading.value = { ...builtinReportLoading.value, [target]: true }
  const request = (async () => {
    try {
      const payload = await apiRequest('/api/ai/report/result', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          result: execution,
          title: `${resultMethodLabel(execution)}规范统计结果报告`,
          use_ai: false,
          analysis_context: buildAIReportContext(target, execution),
        }),
      }, '本地排序与规范表生成失败')
      if (!isCurrentExecution(target, execution)) return null
      if (target === 'instant') instantBuiltinReport.value = payload
      else workspaceBuiltinReport.value = payload
      return payload
    } catch (cause) {
      if (showError) {
        if (target === 'instant') applyInstantError(cause, '本地排序与规范表生成失败')
        else applyWorkspaceError(cause, '本地排序与规范表生成失败')
      }
      return null
    } finally {
      builtinReportLoading.value = { ...builtinReportLoading.value, [target]: false }
    }
  })()
  builtinReportPromises[target] = request
  try { return await request }
  finally { if (builtinReportPromises[target] === request) builtinReportPromises[target] = null }
}

function isCurrentExecution(target: 'instant' | 'workspace', execution: any) {
  return target === 'instant' ? result.value === execution : workspaceRun.value?.result_json === execution
}

async function monitorBatchExport(execution: any) {
  if (execution?.kind !== 'batch' || execution?.batch_export?.status !== 'preparing') return
  const pollId = ++batchExportPollId
  const statusUrl = String(execution.batch_export.status_url || '')
  if (!statusUrl) return
  for (let attempt = 0; attempt < 300; attempt += 1) {
    if (pollId !== batchExportPollId || result.value !== execution) return
    try {
      const status = await apiRequest(statusUrl, undefined, '批量导出状态读取失败')
      execution.batch_export = { ...execution.batch_export, ...status }
      if (status.status === 'ready' || status.status === 'failed') return
    } catch {
      // 后台任务刚启动时允许短暂重试，统计结果不受影响。
    }
    await new Promise(resolve => window.setTimeout(resolve, 700))
  }
  if (result.value === execution) execution.batch_export.status = 'failed'
}

async function prepareResultReports(target: 'instant' | 'workspace', execution: any) {
  const builtin = await loadBuiltinResultReport(target, execution)
  if (!builtin || !isCurrentExecution(target, execution) || !automaticAIReportAllowed.value) return
  void generateAIResultReport(target, { background: true, execution })
}

async function generateAIResultReport(
  target: 'instant' | 'workspace',
  options: { background?: boolean; execution?: any } = {},
) {
  if ((!options.background && interactionBusy.value) || aiReportLoadingTarget.value) return
  const execution = options.execution ?? (target === 'instant' ? result.value : workspaceRun.value?.result_json)
  if (!execution) return
  const reportContextId = target === 'instant'
    ? instantResultContextId.value
    : workspaceRun.value?.id ? `workspace:${workspaceRun.value.id}` : ''
  let builtin = target === 'instant' ? instantBuiltinReport.value : workspaceBuiltinReport.value
  if (!builtin) builtin = await loadBuiltinResultReport(target, execution, !options.background)
  if (!builtin || !isCurrentExecution(target, execution)) return
  if (!options.background) {
    await nextTick()
    document.getElementById(`${target}-ai-result-report`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  if (!aiReady.value) {
    if (!options.background) aiSettingsOpen.value = true
    return
  }
  aiReportLoadingTarget.value = target
  aiReportErrors.value = { ...aiReportErrors.value, [target]: '' }
  if (target === 'instant') clearInstantError()
  else clearWorkspaceError()
  if (target === 'instant') instantAIReport.value = null
  else workspaceAIReport.value = null
  try {
    const methodLabel = resultMethodLabel(execution)
    const payload = await apiRequest('/api/ai/report/result', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        result: execution,
        title: `${methodLabel}规范统计结果报告`,
        use_ai: true,
        analysis_context: buildAIReportContext(target, execution),
      }),
    }, 'AI 规范报告生成失败')
    if (!isCurrentExecution(target, execution)) return
    if (target === 'instant') {
      instantAIReport.value = payload
      instantAIReportContextId.value = reportContextId
    } else {
      workspaceAIReport.value = payload
      workspaceAIReportContextId.value = reportContextId
    }
    if (!['ai', 'ai_guard_partial'].includes(String(payload?.source ?? ''))) {
      aiReportErrors.value = {
        ...aiReportErrors.value,
        [target]: String(payload?.warning || 'AI 未返回可应用的文字总结；本地排序与三张规范表仍可正常使用。'),
      }
    }
    if (!options.background) {
      await nextTick()
      document.getElementById(`${target}-ai-result-report`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  } catch (cause) {
    const info = cause && typeof cause === 'object' && 'message' in cause
      ? cause as any
      : friendlyError({ detail: errorMessage(cause) }, 'AI 规范报告生成失败')
    aiReportErrors.value = { ...aiReportErrors.value, [target]: info.message || 'AI 规范报告生成失败' }
    if (!options.background) {
      if (target === 'instant') applyInstantError(cause, 'AI 规范报告生成失败')
      else applyWorkspaceError(cause, 'AI 规范报告生成失败')
    }
  } finally {
    if (aiReportLoadingTarget.value === target) aiReportLoadingTarget.value = ''
  }
}

async function refreshWorkspaceProjects(selectId?: string) {
  const [projects, info] = await Promise.all([
    apiRequest('/api/projects', undefined, '项目列表读取失败'),
    apiRequest('/api/workspace', undefined, '工作区存储信息读取失败'),
  ])
  workspaceProjects.value = projects
  workspaceInfo.value = info
  const target = selectId ?? workspaceProject.value?.id
  if (target) await loadWorkspaceProject(target)
}

async function createWorkspaceProject() {
  if (!workspaceProjectName.value.trim() || workspaceLoading.value) return
  workspaceLoading.value = true
  clearWorkspaceError()
  beginOperation('正在创建项目', '正在建立本地工作区与项目索引。')
  try {
    const payload = await apiRequest('/api/projects', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: workspaceProjectName.value, description: workspaceProjectDescription.value }),
    }, '项目创建失败')
    workspaceProjectName.value = ''
    workspaceProjectDescription.value = ''
    await refreshWorkspaceProjects(payload.id)
  } catch (cause) {
    applyWorkspaceError(cause, '项目创建失败')
  } finally { workspaceLoading.value = false; endOperation() }
}

async function loadWorkspaceProject(projectId: string) {
  if (!projectId) return
  const ownsBusyState = !workspaceLoading.value
  if (ownsBusyState) {
    workspaceLoading.value = true
    clearWorkspaceError()
    beginOperation('正在读取项目', '正在载入数据集、分析计划与运行历史。')
  }
  workspaceRun.value = null
  workspaceReportId.value = ''
  workspaceReportLinks.value = null
  workspaceBuiltinReport.value = null
  workspaceAIReport.value = null
  try {
    const payload = await apiRequest(`/api/projects/${projectId}`, undefined, '项目读取失败')
    workspaceProject.value = payload
    if (!payload.datasets.some((item: WorkspaceDataset) => item.id === workspaceDatasetId.value)) workspaceDatasetId.value = payload.datasets[0]?.id ?? ''
    selectWorkspaceDataset(workspaceDatasetId.value)
    if (!payload.plans.some((item: WorkspacePlan) => item.id === workspaceSelectedPlanId.value)) workspaceSelectedPlanId.value = payload.plans[0]?.id ?? ''
  } catch (cause) {
    applyWorkspaceError(cause, '项目读取失败')
  } finally {
    if (ownsBusyState) { workspaceLoading.value = false; endOperation() }
  }
}

function handleWorkspaceFile(event: Event) {
  const target = event.target as HTMLInputElement
  workspaceDatasetFile.value = target.files?.[0] ?? null
  workspaceDatasetName.value = workspaceDatasetFile.value?.name.replace(/\.[^.]+$/, '') ?? ''
}

async function uploadWorkspaceDataset() {
  if (!workspaceProject.value || !workspaceDatasetFile.value || workspaceLoading.value) return
  workspaceLoading.value = true
  clearWorkspaceError()
  beginOperation('正在导入项目数据集', '正在清理空白列、计算数据指纹并写入工作区。')
  try {
    const body = new FormData()
    body.append('file', workspaceDatasetFile.value)
    body.append('name', workspaceDatasetName.value)
    body.append('percentage_scale', percentageScale.value)
    const payload = await apiRequest(`/api/projects/${workspaceProject.value.id}/datasets`, { method: 'POST', body }, '数据集上传失败')
    workspaceDatasetFile.value = null
    if (workspaceFileInput.value) workspaceFileInput.value.value = ''
    workspaceDatasetId.value = payload.id
    await refreshWorkspaceProjects(workspaceProject.value.id)
  } catch (cause) {
    applyWorkspaceError(cause, '数据集上传失败')
  } finally { workspaceLoading.value = false; endOperation() }
}

function selectWorkspaceDataset(datasetId: string) {
  workspaceDatasetId.value = datasetId
  const dataset = workspaceProject.value?.datasets.find((item) => item.id === datasetId)
  const columns = dataset?.profile_json?.columns ?? []
  const method = workspaceCurrentMethod.value
  workspaceDvs.value = columns.filter((item) => item.inferred_role === 'dependent').map((item) => item.name).slice(0, method?.dependent_mode === 'joint' ? (method.max_dependent_vars ?? method.min_dependent_vars) : 1)
  workspaceFactors.value = columns.filter((item) => item.inferred_role === 'between').map((item) => item.name).slice(0, configuredMultiFactorOrder('workspace') ?? (method?.max_fixed_factors === null ? (method.min_fixed_factors || 1) : (method?.max_fixed_factors ?? 1)))
  workspaceCovariates.value = []
  workspaceRandomFactors.value = []
  workspaceRandomSlopes.value = []
  workspaceEstimateMarginalMeans.value = false
  workspaceEmmFactors.value = []
  workspaceSubjectId.value = ''
  workspaceRepeatedFactor.value = ''
  workspaceSplits.value = []
  workspaceSplitRules.value = []
  workspaceDerivedColumns.value = []
  workspaceDerivedProfile.value = null
  workspaceDerivedWarnings.value = []
  workspaceFactorCombinationLabels.value = {}
}

function removeUnavailableWorkspaceRoles() {
  const available = new Set(workspaceColumns.value.map(column => column.name))
  const derived = workspaceDerivedNames.value
  workspaceDvs.value = workspaceDvs.value.filter(column => available.has(column))
  workspaceFactors.value = workspaceFactors.value.filter(column => available.has(column) && !derived.has(column))
  workspaceCovariates.value = workspaceCovariates.value.filter(column => available.has(column) && !derived.has(column))
  workspaceRandomFactors.value = workspaceRandomFactors.value.filter(column => available.has(column) && !derived.has(column))
  workspaceRandomSlopes.value = workspaceRandomSlopes.value.filter(column => available.has(column) && !derived.has(column))
  workspaceSplits.value = workspaceSplits.value.filter(column => available.has(column) && !derived.has(column))
  workspaceSplitRules.value = workspaceSplitRules.value.filter(rule => available.has(rule.column) && !derived.has(rule.column))
  if (!available.has(workspaceSubjectId.value) || derived.has(workspaceSubjectId.value)) workspaceSubjectId.value = ''
  if (!available.has(workspaceRepeatedFactor.value) || derived.has(workspaceRepeatedFactor.value)) workspaceRepeatedFactor.value = ''
}

async function refreshWorkspaceDerivedPreview() {
  if (!workspaceDataset.value || !workspaceExpertMode.value) return
  workspaceDerivedPreviewLoading.value = true
  clearWorkspaceError()
  try {
    if (!workspaceDerivedColumns.value.length) {
      workspaceDerivedProfile.value = null
      workspaceDerivedWarnings.value = []
      removeUnavailableWorkspaceRoles()
      return
    }
    const payload = await apiRequest(`/api/datasets/${workspaceDataset.value.id}/derived-preview`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ derived_columns: workspaceDerivedColumns.value }),
    }, '自定义列计算失败')
    workspaceDerivedProfile.value = payload.profile
    workspaceDerivedWarnings.value = payload.warnings ?? []
    removeUnavailableWorkspaceRoles()
    invalidateWorkspaceResult('自定义列已修改，当前结果已隐藏；请保存计划并重新运行。')
  } catch (cause) {
    applyWorkspaceError(cause, '自定义列计算失败')
  } finally {
    workspaceDerivedPreviewLoading.value = false
  }
}

function toggleWorkspaceSelection(target: 'dv' | 'factor' | 'covariate' | 'random' | 'subject' | 'repeated' | 'split', column: string) {
  if (isWorkspaceDerivedColumn(column) && target !== 'dv') return
  const scalar = target === 'subject' ? workspaceSubjectId : target === 'repeated' ? workspaceRepeatedFactor : null
  const lists = { dv: workspaceDvs, factor: workspaceFactors, covariate: workspaceCovariates, random: workspaceRandomFactors, split: workspaceSplits }
  const allLists = Object.entries(lists)
  if (scalar) {
    scalar.value = scalar.value === column ? '' : column
    if (scalar.value) {
      allLists.forEach(([, list]) => { list.value = list.value.filter(item => item !== column) })
      workspaceRandomSlopes.value = workspaceRandomSlopes.value.filter(item => item !== column)
      workspaceEmmFactors.value = workspaceEmmFactors.value.filter(item => item !== column)
      if (target === 'subject' && workspaceRepeatedFactor.value === column) workspaceRepeatedFactor.value = ''
      if (target === 'repeated' && workspaceSubjectId.value === column) workspaceSubjectId.value = ''
    }
    return
  }
  const list = lists[target as keyof typeof lists]
  if (list.value.includes(column)) {
    list.value = list.value.filter(item => item !== column)
    if (target === 'split') workspaceSplitRules.value = workspaceSplitRules.value.filter(rule => rule.column !== column)
    return
  }
  const method = workspaceCurrentMethod.value
  const max = target === 'dv' ? (method?.dependent_mode === 'single' && method?.supports_batch ? null : method?.max_dependent_vars)
    : target === 'factor' ? (workspaceFactorCombinationsEnabled.value ? null : effectiveFactorOrder('workspace')) : target === 'covariate' ? method?.max_covariates : target === 'random' ? method?.max_random_factors : null
  if (max !== null && max !== undefined && list.value.length >= max) {
    if (target === 'factor' && configuredMultiFactorOrder('workspace') === null) openFactorOverflowPrompt('workspace', column)
    return
  }
  allLists.forEach(([name, other]) => {
    const professionalDualRole = workspaceExpertMode.value && ((target === 'factor' && name === 'split') || (target === 'split' && name === 'factor'))
    if (name !== target && !professionalDualRole) other.value = other.value.filter(item => item !== column)
  })
  if (!['factor', 'covariate', 'repeated'].includes(target)) workspaceRandomSlopes.value = workspaceRandomSlopes.value.filter(item => item !== column)
  if (target !== 'factor') workspaceEmmFactors.value = workspaceEmmFactors.value.filter(item => item !== column)
  if (workspaceSubjectId.value === column) workspaceSubjectId.value = ''
  if (workspaceRepeatedFactor.value === column) workspaceRepeatedFactor.value = ''
  list.value = [...list.value, column]
  if (workspaceExpertMode.value && ((target === 'split' && workspaceFactors.value.includes(column)) || (target === 'factor' && workspaceSplits.value.includes(column)))) {
    enableWorkspaceCustomSplit(column)
  }
}

function toggleWorkspaceRandomSlope(column: string) {
  if (isWorkspaceDerivedColumn(column)) return
  const allowed = workspaceFactors.value.includes(column) || workspaceCovariates.value.includes(column) || workspaceRepeatedFactor.value === column
  if (!allowed) return
  if (workspaceRandomSlopes.value.includes(column)) { workspaceRandomSlopes.value = workspaceRandomSlopes.value.filter(item => item !== column); return }
  const max = workspaceCurrentMethod.value?.max_random_slopes
  if (max !== null && max !== undefined && workspaceRandomSlopes.value.length >= max) return
  workspaceRandomSlopes.value = [...workspaceRandomSlopes.value, column]
}

function toggleWorkspaceEmmFactor(column: string) {
  workspaceEmmFactors.value = workspaceEmmFactors.value.includes(column) ? workspaceEmmFactors.value.filter(item => item !== column) : [...workspaceEmmFactors.value, column]
}

async function createWorkspacePlan() {
  if (!workspaceProject.value || !workspaceDataset.value || workspaceLoading.value) return
  workspaceLoading.value = true
  clearWorkspaceError()
  beginOperation('正在保存分析计划', '正在验证变量角色与高级参数，并保存可复现配置。')
  try {
    const payload = await apiRequest(`/api/projects/${workspaceProject.value.id}/plans`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dataset_id: workspaceDataset.value.id,
        name: workspacePlanName.value,
        plan: {
          interface_mode: workspaceExpertMode.value ? 'professional' : 'concise',
          dependent_variables: workspaceDvs.value, fixed_factors: workspaceFactors.value,
          covariates: workspaceCovariates.value, random_factors: workspaceRandomFactors.value,
          random_slopes: workspaceExpertMode.value ? workspaceRandomSlopes.value : [],
          estimate_marginal_means: workspaceExpertMode.value && workspaceEstimateMarginalMeans.value,
          emm_factors: workspaceExpertMode.value && workspaceEstimateMarginalMeans.value ? workspaceEmmFactors.value : [],
          contrast_correction: workspaceExpertMode.value ? workspaceContrastCorrection.value : 'holm',
          diagnostic_plots: workspaceExpertMode.value && workspaceDiagnosticPlots.value,
          subject_id: workspaceSubjectId.value || null, repeated_factor: workspaceRepeatedFactor.value || null,
          split_by: workspaceSplits.value, method: workspaceMethod.value,
          split_rules: workspaceExpertMode.value ? serializeWorkspaceSplitRules() : [],
          derived_columns: workspaceExpertMode.value ? workspaceDerivedColumns.value : [],
          alpha: workspaceExpertMode.value ? alpha.value : 0.05,
          ss_type: workspaceExpertMode.value ? ssType.value : 3,
          test_value: testValue.value, expected_proportions: parseExpectedProportions(),
          method_parameters: workspaceExpertMode.value ? workspaceMethodParameters.value : defaultMethodParameters(workspaceCurrentMethod.value),
          factor_combinations_enabled: workspaceExpertMode.value && workspaceFactorCombinationsEnabled.value,
          factor_combination_order: workspaceExpertMode.value && workspaceFactorCombinationsEnabled.value ? workspaceFactorCombinationMaxOrder.value : null,
          factor_combination_min_order: workspaceExpertMode.value && workspaceFactorCombinationsEnabled.value ? 1 : null,
          factor_combination_max_order: workspaceExpertMode.value && workspaceFactorCombinationsEnabled.value ? workspaceFactorCombinationMaxOrder.value : null,
          factor_combination_labels: workspaceExpertMode.value && workspaceFactorCombinationsEnabled.value ? serializeFactorCombinationLabels('workspace') : {},
          cross_model_p_adjust: workspaceCombinationPAdjust.value,
          combination_p_adjust: workspaceCombinationPAdjust.value,
          calibration_enabled: workspaceExpertMode.value && workspaceCalibrationEnabled.value,
          calibration_method: workspaceCalibrationMethod.value,
          calibration_columns: workspaceExpertMode.value && workspaceCalibrationEnabled.value ? workspaceCalibrationColumns.value : [],
          calibration_baseline_column: workspaceExpertMode.value && workspaceCalibrationEnabled.value ? workspaceCalibrationBaselineColumn.value || null : null,
          calibration_baseline_value: workspaceExpertMode.value && workspaceCalibrationEnabled.value ? workspaceCalibrationBaselineValue.value || null : null,
        },
      }),
    }, '分析计划创建失败')
    workspaceSelectedPlanId.value = payload.id
    await refreshWorkspaceProjects(workspaceProject.value.id)
  } catch (cause) {
    applyWorkspaceError(cause, '分析计划创建失败')
  } finally { workspaceLoading.value = false; endOperation() }
}

async function runWorkspacePlan(planId?: string) {
  const selected = planId ?? workspaceSelectedPlanId.value
  if (!selected || interactionBusy.value) return
  pendingAnalysisAction.value = 'workspace'
  pendingWorkspacePlanId.value = selected
  preflightPriorRunCount.value = workspaceProject.value?.runs.filter(run => run.plan_id === selected).length ?? 0
  preflightOpen.value = true
  preflightLoading.value = true
  preflightReport.value = null
  clearWorkspaceError()
  try {
    const report = await apiRequest(`/api/plans/${selected}/preflight`, undefined, '分析前检查失败')
    preflightReport.value = guardPreflightCorrection(report, workspacePlanJson(selected))
    preflightPriorRunCount.value = Number(preflightReport.value?.prior_run_count ?? preflightPriorRunCount.value)
  } catch (cause) {
    const info = cause && typeof cause === 'object' && 'message' in cause ? cause as any : friendlyError({ detail: errorMessage(cause) }, '分析前检查失败')
    preflightReport.value = { ready: false, issues: [...(info.issues ?? []), { severity: 'error', field: info.issues?.[0]?.field ?? '', code: info.code ?? 'preflight_failed', message: info.message }], selections: {}, batch_summary: { enabled: false, group_count: 0 } }
  } finally { preflightLoading.value = false }
}

async function executeWorkspacePlan(selected: string) {
  if (!selected || workspaceLoading.value) return
  workspaceLoading.value = true
  clearWorkspaceError()
  workspaceReportId.value = ''
  workspaceReportLinks.value = null
  workspaceBuiltinReport.value = null
  workspaceAIReport.value = null
  beginOperation('正在运行项目分析', '正在校验数据指纹、执行统计模型并保存运行记录。')
  try {
    const payload = await apiRequest(`/api/plans/${selected}/runs`, { method: 'POST' }, '分析运行失败')
    assertExecutionCorrection(payload.result_json, workspacePlanJson(selected))
    workspaceRun.value = payload
    workspaceResultInvalidated.value = false
    workspaceResultInvalidatedReason.value = ''
    endOperation()
    void prepareResultReports('workspace', payload.result_json)
    if (workspaceProject.value) await refreshWorkspaceProjects(workspaceProject.value.id)
    workspaceRun.value = payload
  } catch (cause) {
    applyWorkspaceError(cause, '分析运行失败')
  } finally { workspaceLoading.value = false; endOperation() }
}

async function generateWorkspaceReport(runId: string) {
  if (!runId || workspaceLoading.value) return
  workspaceLoading.value = true
  clearWorkspaceError()
  beginOperation('正在生成报告', '正在整理结果表、诊断图与可复现元数据。')
  try {
    const payload = await apiRequest(`/api/runs/${runId}/reports`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: `${workspaceProject.value?.name ?? 'DataWork'} 统计分析报告` }),
    }, '报告生成失败')
    workspaceReportId.value = payload.id
    workspaceReportLinks.value = payload.artifact_downloads ?? null
    try {
      workspaceRun.value = await apiRequest(`/api/runs/${runId}`, undefined, '运行记录读取失败')
      if (workspaceRun.value?.result_json) void prepareResultReports('workspace', workspaceRun.value.result_json)
    } catch { /* 报告已成功，不因刷新失败撤销 */ }
    try { workspaceInfo.value = await apiRequest('/api/workspace', undefined, '工作区存储信息读取失败') } catch { /* 报告已成功 */ }
  } catch (cause) {
    applyWorkspaceError(cause, '报告生成失败')
  } finally { workspaceLoading.value = false; endOperation() }
}

function formatNumber(value: unknown, digits = 4) {
  if (value === null || value === undefined) return '-'
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : String(value)
}

function formatBytes(value: unknown) {
  const bytes = Number(value ?? 0)
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const amount = bytes / (1024 ** index)
  return `${amount.toFixed(index === 0 ? 0 : amount >= 10 ? 1 : 2)} ${units[index]}`
}
</script>

<template>
  <main class="shell">
    <LoadingOverlay :active="Boolean(operationTitle)" :title="operationTitle" :detail="operationDetail" />
    <div v-if="sessionAccessError" class="session-gate" role="alertdialog" aria-modal="true" aria-labelledby="session-gate-title">
      <div class="session-gate-card">
        <span class="session-gate-icon">👥</span>
        <p class="eyebrow">DATAWORK 使用席位</p>
        <h2 id="session-gate-title">{{ sessionAccessError.title }}</h2>
        <p>{{ sessionAccessError.message }}</p>
        <ul v-if="sessionAccessError.hints?.length"><li v-for="hint in sessionAccessError.hints" :key="hint">{{ hint }}</li></ul>
        <button type="button" class="primary" @click="retrySessionAdmission">重新加入</button>
      </div>
    </div>
    <div v-if="workspaceAuthOpen" class="modal-backdrop workspace-auth-backdrop" @click.self="!workspaceAuthLoading && (workspaceAuthOpen = false)">
      <form class="modal-card workspace-auth-card" role="dialog" aria-modal="true" aria-labelledby="workspace-auth-title" @submit.prevent="unlockWorkspace">
        <div class="workspace-auth-mark" aria-hidden="true">⌂</div>
        <p class="eyebrow">{{ workspaceAuthPurpose === 'ai' ? 'OWNER AI ACCESS' : 'OWNER WORKSPACE' }}</p>
        <h2 id="workspace-auth-title">{{ workspaceAuthPurpose === 'ai' ? '验证后继续使用服务器 AI' : '所有者工作区认证' }}</h2>
        <p class="workspace-auth-copy">{{ workspaceAuthPurpose === 'ai' ? '匿名 10 次额度已用完。验证工作区密码后，本浏览器可继续使用服务器配置的 AI。' : '这里会长期保存原始数据、分析计划和报告。为节省服务器空间，只有所有者验证后才能进入；其他访客仍可使用即时分析。' }}</p>
        <label class="field workspace-password-field">工作区密码
          <input v-model="workspaceAuthPassword" type="password" autocomplete="current-password" autofocus :disabled="workspaceAuthLoading" placeholder="请输入工作区密码" />
        </label>
        <div class="workspace-auth-error" v-if="workspaceAuthError" role="alert">
          <strong>{{ workspaceAuthError.title }}</strong><p>{{ workspaceAuthError.message }}</p>
          <small v-for="hint in workspaceAuthError.hints" :key="hint">{{ hint }}</small>
        </div>
        <div class="workspace-auth-notes"><span>密码只发送到当前服务器验证</span><span>连续错误 5 次锁定 5 分钟</span><span>10 分钟无操作后需重新认证</span></div>
        <div class="modal-actions">
          <button type="button" class="secondary" :disabled="workspaceAuthLoading" @click="workspaceAuthOpen = false">取消</button>
          <button type="submit" class="primary" :disabled="workspaceAuthLoading || !workspaceAuthPassword">{{ workspaceAuthLoading ? '正在验证…' : workspaceAuthPurpose === 'ai' ? '验证并继续使用 AI' : '验证并进入' }}</button>
        </div>
      </form>
    </div>
    <header class="hero">
      <div>
        <p class="eyebrow">DATAWORK {{ health?.version ?? '1.0.0' }}</p>
        <h1>实验统计分析平台</h1>
        <p class="hero-copy">同一套 Python 统计核心，可在 Windows、Linux、macOS 本地运行，也可部署为网页服务。</p>
      </div>
      <div class="hero-statuses">
        <div class="status-card session-status-card" v-if="sessionState?.active">
          <span class="status-dot session-dot"></span>
          <div><strong>{{ sessionState.session_label }} · {{ sessionState.active_users }}/{{ sessionState.max_users }}</strong><small>{{ workspaceAuthState?.authenticated && workspaceAuthState?.required ? '所有者工作区已解锁' : '临时会话' }} · 10 分钟无操作退出</small></div>
        </div>
        <div class="status-card" v-if="health">
          <span class="status-dot"></span>
          <div><strong>服务已就绪</strong><small>{{ health.platform }} · Python {{ health.python }}</small></div>
        </div>
        <button class="status-card ai-status-card" @click="aiSettingsOpen = true">
          <span :class="aiStatus?.enabled && aiStatus?.configured ? 'status-dot ai-on' : 'status-dot ai-off'"></span>
          <div><strong>AI {{ aiStatus?.enabled && aiStatus?.configured ? '已启用' : '可选' }}</strong><small>{{ aiStatus?.configured ? `${aiStatus.provider} · ${aiStatus.model}` : '点击配置 API' }}</small></div>
        </button>
      </div>
    </header>

    <nav class="mode-switch">
      <button :disabled="interactionBusy" :class="{ active: mode === 'instant' }" @click="mode = 'instant'">即时分析</button>
      <button :disabled="interactionBusy" :class="{ active: mode === 'workspace' }" @click="enterWorkspace">{{ workspaceAuthState?.required ? '🔒 项目工作区' : '项目工作区' }}</button>
      <button @click="aiSettingsOpen = true">AI 设置</button>
    </nav>

    <section class="workflow-strip" aria-label="当前工作流进度">
      <template v-if="mode === 'instant'">
        <button v-for="(label, index) in ['选择文件','检查数据','建立计划','预检执行','查看结果']" :key="label" type="button" class="workflow-step" :class="{ active: instantWorkflowStep === index, done: instantWorkflowStep > index }" :aria-current="instantWorkflowStep === index ? 'step' : undefined" :aria-label="`跳转到${label}`" @click="jumpToWorkflowStep(index)"><span>{{ instantWorkflowStep > index ? '✓' : index + 1 }}</span><strong>{{ label }}</strong></button>
      </template>
      <template v-else>
        <button v-for="(label, index) in ['选择项目','选择数据','保存计划','运行计划','查看结果']" :key="label" type="button" class="workflow-step" :class="{ active: workspaceWorkflowStep === index, done: workspaceWorkflowStep > index }" :aria-current="workspaceWorkflowStep === index ? 'step' : undefined" :aria-label="`跳转到${label}`" @click="jumpToWorkflowStep(index)"><span>{{ workspaceWorkflowStep > index ? '✓' : index + 1 }}</span><strong>{{ label }}</strong></button>
      </template>
    </section>

    <template v-if="mode === 'instant'">
    <section id="instant-data-import" class="panel upload-panel workflow-jump-target" :class="{ 'workflow-jump-highlight': workflowJumpTarget === 'instant-data-import' }">
      <div class="section-heading">
        <div><span>01</span><h2>导入数据</h2></div>
        <div class="heading-tools"><p>支持 CSV、TSV、XLSX；旧版 XLS 需要可选依赖。</p></div>
      </div>
      <div class="upload-grid">
        <label class="drop-zone">
          <input ref="fileInput" type="file" accept=".csv,.tsv,.txt,.xlsx,.xls" :disabled="interactionBusy" @click="prepareFileReselection" @change="handleFile" />
          <strong>{{ file ? file.name : '选择实验数据文件' }}</strong>
          <small>{{ file ? `${(file.size / 1024).toFixed(1)} KB` : '文件仅在当前分析请求中处理' }}</small>
        </label>
        <div class="upload-options">
          <label>百分比解释
            <select v-model="percentageScale" :disabled="interactionBusy">
              <option value="percent_points">37% → 37（百分点）</option>
              <option value="proportion">37% → 0.37（比例）</option>
            </select>
          </label>
          <button class="primary" :disabled="!file || loadingProfile" @click="loadProfile">
            {{ loadingProfile ? '正在读取…' : '读取并检查数据' }}
          </button>
        </div>
      </div>
    </section>

    <ErrorNotice :title="errorTitle" :message="error" :hints="errorHints" :retry-label="file ? '重新读取数据' : undefined" @retry="loadProfile" @dismiss="clearInstantError" />
    <div class="state-notice stale" v-if="resultInvalidated"><div><strong>原分析结果已失效</strong><p>{{ resultInvalidatedReason }}</p></div><button class="secondary compact" @click="resultInvalidated = false">知道了</button></div>

    <template v-if="profile">
      <section id="instant-data-check" class="metrics workflow-jump-target" :class="{ 'workflow-jump-highlight': workflowJumpTarget === 'instant-data-check' }">
        <article><span>行数</span><strong>{{ profile.profile.n_rows }}</strong></article>
        <article><span>列数</span><strong>{{ profile.profile.n_cols }}</strong></article>
        <article><span>缺失率</span><strong>{{ (profile.profile.total_missing_rate * 100).toFixed(1) }}%</strong></article>
        <article><span>重复行</span><strong>{{ profile.profile.n_duplicate_rows }}</strong></article>
        <article><span>已排除空列</span><strong>{{ excludedColumns.length }}</strong></article>
      </section>
      <div class="cleaning-notice" v-if="excludedColumns.length">
        已自动排除 {{ excludedColumns.length }} 个空标题或全空列：
        {{ excludedColumns.map(item => item.name).join('、') }}。
        <span v-if="excludedColumns.some(item => item.non_empty_cells > 0)">其中存在零星误填内容，但不会进入分析。</span>
      </div>

      <section class="panel workflow-jump-target" id="analysis-roles" :class="{ 'preflight-focus': focusedField === 'analysis-roles', 'workflow-jump-highlight': workflowJumpTarget === 'analysis-roles' }">
        <div class="section-heading">
          <div><span>02</span><h2>建立分析计划</h2></div>
          <div class="heading-tools"><p>专业模式允许拆分列兼作分类因素，但每个自定义组必须保留至少两个有效水平。</p><button class="help-button" :disabled="interactionBusy" @click="restoreSuggestedRoles('instant')">恢复推荐选择</button></div>
        </div>

        <div class="plan-grid" id="analysis-method" :class="{ 'preflight-focus': focusedField === 'analysis-method' }">
          <label class="field">统计方法
            <select v-model="selectedMethod">
              <optgroup v-for="group in methodCategories" :key="group.category" :label="group.category">
                <option v-for="method in group.items" :key="method.name" :value="method.name" :disabled="!method.runnable">
                  {{ method.label_zh }}{{ method.status === 'experimental' ? '（实验性）' : method.runnable ? '' : '（未实现）' }}
                </option>
              </optgroup>
            </select>
            <small>{{ currentMethod?.notes || currentMethod?.purpose }} 切换方法会按新方法重置变量角色。</small>
          </label>
          <div class="analysis-mode-switch" role="group" aria-label="参数显示模式">
            <button type="button" :class="{ active: !instantExpertMode }" @click="setInstantExpertMode(false)"><strong>简洁模式</strong><small>使用推荐默认值</small></button>
            <button type="button" :class="{ active: instantExpertMode }" @click="setInstantExpertMode(true)"><strong>专业模式</strong><small>显示全部参数</small></button>
          </div>
        </div>

        <section class="method-intro" v-if="currentMethod">
          <div class="method-intro-head"><div><span>{{ currentMethod.category }}</span><h3>{{ currentMethod.label_zh }}</h3></div><span class="method-status" :class="currentMethod.status">{{ currentMethod.status === 'experimental' ? '实验性' : currentMethod.runnable ? '可执行' : '未实现' }}</span></div>
          <div class="method-intro-grid">
            <article><strong>通常用于什么</strong><p>{{ currentMethod.purpose }}</p></article>
            <article><strong>变量如何作用</strong><p>{{ currentMethod.variable_relationship }}</p></article>
          </div>
          <div class="method-requirements">
            <div v-for="item in currentMethod.variable_requirements" :key="item.role"><strong>{{ item.label_zh }} · {{ item.count }}</strong><span>{{ item.description }}</span></div>
          </div>
          <div class="method-output"><strong>通常输出</strong><span v-for="item in currentMethod.output_metrics" :key="item">{{ item }}</span></div>
        </section>

        <section class="recommended-settings-card" v-if="currentMethod">
          <div><span class="source-label">当前采用</span><strong>{{ instantExpertMode ? '专业参数' : '推荐设置' }}</strong><p>{{ instantExpertMode ? '你可以修改全部方法参数；所有修改都会写入分析计划和报告。' : '普通分析可直接使用这些默认值，必要时再展开常用设置。' }}</p></div>
          <div class="setting-chips"><span v-for="item in instantRecommendedSummary" :key="item">{{ item }}</span></div>
          <details class="common-parameter-panel" v-if="instantExpertMode && (instantCommonParameters.length || selectedMethod === 'one_sample_ttest' || selectedMethod === 'chi_square_goodness_of_fit')">
            <summary>调整常用设置（可选）</summary>
            <div class="advanced-method-grid compact-parameter-grid">
              <label class="field" v-if="selectedMethod === 'one_sample_ttest'">单样本参考值<input v-model.number="testValue" type="number" step="any" /><small>默认 0；仅在研究假设需要其他参考值时修改。</small></label>
              <label class="field" v-if="selectedMethod === 'chi_square_goodness_of_fit'">理论比例<input v-model="expectedProportionsText" type="text" placeholder="例如：0.25,0.25,0.5；留空表示等比例" /><small>比例数量需与类别数量一致，总和应为 1。</small></label>
              <div class="field method-parameter" v-for="parameter in instantCommonParameters" :key="parameter.key">
                <span class="field-label">{{ parameter.label_zh }}</span>
                <template v-if="parameter.kind === 'multi_select'"><div class="parameter-toolbar"><small>已选择 {{ (methodParameters[parameter.key] ?? []).length }} 项</small><button type="button" class="text-button" @click="resetMethodParameter('instant', parameter.key)">恢复默认</button></div><div class="multi-choice-grid"><button v-for="option in commonParameterOptions(parameter, methodParameters[parameter.key])" :key="option.value" type="button" class="multi-choice" :aria-pressed="(methodParameters[parameter.key] ?? []).includes(option.value)" :class="{ active: (methodParameters[parameter.key] ?? []).includes(option.value) }" @click="toggleMultiSelectParameter('instant', parameter.key, option.value)"><span class="choice-check">{{ (methodParameters[parameter.key] ?? []).includes(option.value) ? '✓' : '+' }}</span><span class="choice-copy"><strong>{{ option.label }}</strong><small class="choice-help" v-if="optionHelp(parameter, option.value)">{{ optionHelp(parameter, option.value) }}</small></span><small v-if="Array.isArray(parameter.default) && parameter.default.includes(option.value)">默认</small></button></div></template>
                <select v-else-if="parameter.kind === 'select'" v-model="methodParameters[parameter.key]"><option v-for="option in parameter.options" :key="option.value" :value="option.value">{{ option.label }}</option></select>
                <input v-else-if="parameter.kind === 'boolean'" v-model="methodParameters[parameter.key]" type="checkbox" class="parameter-checkbox" />
                <input v-else-if="parameter.kind === 'integer'" v-model.number="methodParameters[parameter.key]" type="number" :min="parameter.minimum ?? undefined" :max="parameter.maximum ?? undefined" :step="parameter.step ?? 1" />
                <input v-else-if="parameter.kind === 'number'" v-model.number="methodParameters[parameter.key]" type="number" :min="parameter.minimum ?? undefined" :max="parameter.maximum ?? undefined" :step="parameter.step ?? 'any'" />
                <input v-else v-model="methodParameters[parameter.key]" type="text" />
                <small>{{ parameterHelp(parameter) }}</small><small class="recommendation-note" v-if="parameter.recommendation_note">{{ parameter.recommendation_note }}</small><small v-if="parameter.recommended_options?.length && parameter.options.length > commonParameterOptions(parameter, methodParameters[parameter.key]).length">更多低频选项可在专业模式中选择。</small>
              </div>
            </div>
          </details>
        </section>

        <details class="advanced-method-panel professional-control-group" open v-if="currentMethod?.supports_batch">
          <summary>批量任务 <small>{{ splitBy.length }} 个拆分字段 · {{ factorCombinationsEnabled ? `${factorCombinationCount} 个因素模型` : '单一因素模型' }}</small></summary>
          <div class="professional-control-body">
        <section class="factor-combination-panel" v-if="instantFactorCombinationsAllowed && showFixedRole && (factorCombinationsEnabled || instantExpertMode)">
          <label class="combination-toggle">
            <input :checked="factorCombinationsEnabled" type="checkbox" :disabled="fixedFactors.length === 0" @change="onFactorCombinationToggle('instant', $event)" />
            <span><strong>分类因素组合实验</strong><small>把已选择的分类因素作为候选池，按指定阶数分别建立多个独立模型，而不是一次全部放入同一模型。</small></span>
          </label>
          <div class="combination-settings" v-if="factorCombinationsEnabled">
            <label class="field">计算阶数（最高阶 k）
              <select v-model.number="factorCombinationMaxOrder">
                <option v-for="order in factorOrderLimit" :key="`max-${order}`" :value="order">1 至 {{ order }} 阶</option>
              </select>
              <small>选中 n 个因素时，自动生成从 1 阶到 k 阶的全部数学组合（1 ≤ k ≤ n）。</small>
            </label>
            <div class="combination-estimate"><span>候选因素</span><strong>{{ fixedFactors.length }}</strong><span>预计组合模型</span><strong>{{ factorCombinationCount }}</strong></div>
          </div>
          <details class="combination-name-editor" v-if="factorCombinationsEnabled && factorCombinationNames.length">
            <summary>编辑组合名称（可选）</summary>
            <p>名称只影响界面、报告和导出显示；实际建模因素仍以“组合因素”单独记录，便于追溯。</p>
            <div class="combination-name-list">
              <label v-for="name in factorCombinationNames" :key="`instant-name-${name}`"><span>{{ name }}</span><input type="text" :value="factorCombinationLabels[name] ?? ''" :placeholder="name" :aria-label="`组合名称 ${name}`" @input="setFactorCombinationLabel('instant', name, ($event.target as HTMLInputElement).value)" /></label>
            </div>
            <small class="selection-warning" v-if="factorCombinationNameIssues('instant').length">{{ factorCombinationNameIssues('instant').join('；') }}</small>
          </details>
          <p class="combination-warning" v-if="factorCombinationsEnabled">已进入组合分析：将生成 1 至 {{ factorCombinationMaxOrder }} 阶的全部因素组合，共执行 {{ factorCombinationCount }} 个独立模型。<template v-if="combinationPAdjust === 'none'">本次明确不做跨模型校正，判断 p 与原始 p 完全相同。</template><template v-else>跨任务主要检验将使用 {{ combinationPAdjust }} 校正。</template><span v-if="factorCombinationCount > 100"> 任务量较大，建议降低计算阶数。</span></p>
        </section>

        <section class="factor-combination-panel cross-model-correction-panel" v-if="currentMethod?.supports_batch">
          <div>
            <strong>跨模型多重校正</strong>
            <p>一次执行展开多个因变量、因素组合或数据拆分时，会产生一组主要检验。校正用于控制整组检验的误报风险；单模型运行不受此选项影响。</p>
          </div>
          <label class="field">校正方法
            <select v-model="combinationPAdjust" aria-label="跨模型校正方法">
              <option value="holm">Holm（默认，稳健）</option>
              <option value="bonferroni">Bonferroni（更保守）</option>
              <option value="fdr_bh">Benjamini-Hochberg FDR</option>
              <option value="none">不校正（仅限预先定义的独立假设）</option>
            </select>
            <small>简洁模式与专业模式使用同一统计内核和同一选项。</small>
            <small class="selection-warning" v-if="combinationPAdjust === 'none'">已选择不校正：结果将直接按每个模型的原始 p 判断，不会修改 p 值；同时应注意多次检验会累积误报风险。</small>
          </label>
        </section>
          </div>
        </details>

        <details id="advanced-parameters" class="advanced-method-panel" :class="{ 'preflight-focus': focusedField === 'advanced-parameters' }" v-if="instantExpertMode">
          <summary>模型与检验 <small>α={{ alpha }} · Type {{ ssType }}</small></summary>
          <div class="advanced-method-grid">
            <label class="field">显著性水平 α<input v-model.number="alpha" type="number" min="0.001" max="0.5" step="0.01" /><small>默认 0.05。除非研究方案预先规定，否则不建议临时修改。</small></label>
            <label class="field" v-if="['twoway_anova','threeway_anova','multifactor_anova','ancova'].includes(selectedMethod)">平方和类型<select v-model.number="ssType"><option :value="1">Type I</option><option :value="2">Type II</option><option :value="3">Type III（Sum 对比）</option></select><small>不平衡析因设计通常使用 Type III；顺序型模型才考虑 Type I。</small></label>
            <div class="field method-parameter" v-for="parameter in instantAdvancedParameters" :key="parameter.key"><span class="field-label">{{ parameter.label_zh }}</span>
              <template v-if="parameter.kind === 'multi_select'"><div class="parameter-toolbar"><small>已选择 {{ (methodParameters[parameter.key] ?? []).length }} 项</small><button type="button" class="text-button" @click="resetMethodParameter('instant', parameter.key)">恢复默认</button></div><div class="multi-choice-grid"><button v-for="option in parameter.options" :key="option.value" type="button" class="multi-choice" :aria-pressed="(methodParameters[parameter.key] ?? []).includes(option.value)" :class="{ active: (methodParameters[parameter.key] ?? []).includes(option.value) }" @click="toggleMultiSelectParameter('instant', parameter.key, option.value)"><span class="choice-check">{{ (methodParameters[parameter.key] ?? []).includes(option.value) ? '✓' : '+' }}</span><span class="choice-copy"><strong>{{ option.label }}</strong><small class="choice-help" v-if="optionHelp(parameter, option.value)">{{ optionHelp(parameter, option.value) }}</small></span><small v-if="Array.isArray(parameter.default) && parameter.default.includes(option.value)">默认</small></button></div></template>
              <select v-else-if="parameter.kind === 'select'" v-model="methodParameters[parameter.key]"><option v-for="option in parameter.options" :key="option.value" :value="option.value">{{ option.label }}</option></select>
              <input v-else-if="parameter.kind === 'boolean'" v-model="methodParameters[parameter.key]" type="checkbox" class="parameter-checkbox" />
              <input v-else-if="parameter.kind === 'integer'" v-model.number="methodParameters[parameter.key]" type="number" :min="parameter.minimum ?? undefined" :max="parameter.maximum ?? undefined" :step="parameter.step ?? 1" />
              <input v-else-if="parameter.kind === 'number'" v-model.number="methodParameters[parameter.key]" type="number" :min="parameter.minimum ?? undefined" :max="parameter.maximum ?? undefined" :step="parameter.step ?? 'any'" />
              <input v-else v-model="methodParameters[parameter.key]" type="text" />
              <small>{{ parameter.description }} <span class="default-value">默认：{{ parameterDefaultLabel(parameter.default) }}</span></small>
            </div>
          </div>
        </details>

        <details class="advanced-method-panel calibration-panel" v-if="instantExpertMode">
          <summary>数据准备与拆分 <small>{{ derivedColumns.length }} 个自定义列 · {{ splitBy.length }} 个拆分字段</small></summary>
          <div class="professional-subsection">
            <h4>自定义计算列</h4>
            <p>从原始数值列逐行计算，支持基础算术与括号；自定义列之间不能互相引用。</p>
            <DerivedColumnEditor v-model="derivedColumns" :columns="sourceProfile?.profile.columns ?? []" :warnings="derivedWarnings" :busy="derivedPreviewLoading" @changed="refreshInstantDerivedPreview" />
          </div>
          <div class="advanced-method-grid">
            <label class="combination-toggle"><input v-model="calibrationEnabled" type="checkbox" /><span><strong>启用数据校正</strong><small>消除数据源系统误差、对齐基准特征空间，或降低极值造成的预测偏移。</small></span></label>
            <label class="field" v-if="calibrationEnabled">校正策略<select v-model="calibrationMethod"><option value="zscore">标准化（均值 / 标准差）</option><option value="robust_zscore">稳健标准化（中位数 / MAD）</option><option value="baseline_center">基线中心化（Baseline）</option></select></label>
            <label class="field" v-if="calibrationEnabled && calibrationMethod === 'baseline_center'">基准列<select v-model="calibrationBaselineColumn"><option value="">请选择</option><option v-for="column in profile?.profile.columns ?? []" :key="`cal-base-${column.name}`" :value="column.name">{{ column.name }}</option></select></label>
            <label class="field" v-if="calibrationEnabled && calibrationMethod === 'baseline_center'">基准值<input v-model="calibrationBaselineValue" type="text" placeholder="例如：control" /></label>
          </div>
          <div class="method-output" v-if="calibrationEnabled"><strong>校正列</strong><button v-for="column in [...dependentVariables, ...covariates]" :key="`cal-${column}`" type="button" class="choice" :class="{ active: calibrationColumns.includes(column) }" @click="calibrationColumns = calibrationColumns.includes(column) ? calibrationColumns.filter(item => item !== column) : [...calibrationColumns, column]">{{ column }}</button></div>
          <p class="setting-note">校正不是为了制造显著性，也不能替代数据质量控制；所有校正参数都会写入可复现日志。</p>
          <button type="button" class="text-button" @click="openHelp('calibration')">查看校正技术说明</button>
        </details>

        <details id="phase3-options" class="advanced-method-panel phase3-panel" :class="{ 'preflight-focus': focusedField === 'phase3-options' }" v-if="instantExpertMode">
          <summary>比较与结果 <small>EMM、对比校正与诊断图</small></summary>
          <div class="advanced-method-grid">
            <label class="combination-toggle" v-if="currentMethod?.supports_emm"><input v-model="estimateMarginalMeans" type="checkbox" /><span><strong>估计边际均值（EMM）</strong><small>在模型中调整其他因素或协变量后比较指定分类因素。</small></span></label>
            <label class="field" v-if="estimateMarginalMeans">对比校正<select v-model="contrastCorrection"><option value="holm">Holm</option><option value="bonferroni">Bonferroni</option><option value="fdr_bh">FDR-BH</option><option value="none">不校正</option></select></label>
            <label class="combination-toggle" v-if="currentMethod?.supports_diagnostic_plots"><input v-model="diagnosticPlots" type="checkbox" /><span><strong>生成诊断图</strong><small>输出残差、Q-Q、尺度位置、影响点或交互图。</small></span></label>
          </div>
          <div class="method-output" v-if="estimateMarginalMeans && emmCandidates.length"><strong>EMM 因素</strong><button v-for="column in emmCandidates" :key="column" class="choice" :class="{ active: emmFactors.includes(column) }" @click="toggleEmmFactor(column)">{{ column }}</button></div>
          <p class="setting-note" v-if="!currentMethod?.supports_emm && !currentMethod?.supports_diagnostic_plots && !showRandomSlopeRole">当前方法没有额外的模型比较或诊断选项。</p>
          <p class="setting-note" v-if="showRandomSlopeRole">随机斜率必须同时作为固定预测量、连续协变量或重复因素进入模型，再在下方表格中勾选。</p>
        </details>

        <section class="split-group-panel" v-if="showInstantSplitRuleEditor">
          <div class="split-group-copy">
            <span class="source-label">专业拆分</span>
            <strong>在原值拆分基础上合并类别或设置区间</strong>
            <p>下方已选择的拆分列默认仍按原值拆分。只有点击“自定义分组”的列才应用新规则；未纳入任何自定义组的数据不会进入批次任务。</p>
          </div>
          <div class="split-group-summary">
            <span>拆分字段</span><strong>{{ splitBy.length }}</strong>
            <span>自定义规则</span><strong>{{ instantSplitRules.length }}</strong>
          </div>
          <div class="split-rule-list">
            <article class="split-rule-card" v-for="column in splitBy" :key="column">
              <div class="split-rule-head">
                <div><strong>{{ column }}</strong><small>{{ splitRuleFor(column) ? '使用自定义分组' : '按每个实际值自动拆分（原方式）' }}</small></div>
                <button v-if="!splitRuleFor(column)" type="button" class="secondary compact" @click="enableCustomSplit(column)">自定义分组</button>
                <button v-else type="button" class="text-button" @click="disableCustomSplit(column)">恢复按原值拆分</button>
              </div>
              <template v-if="splitRuleFor(column)">
                <label class="split-kind">分组类型
                  <select v-model="splitRuleFor(column)!.kind"><option value="categorical">类别水平合并</option><option value="numeric">数值区间</option></select>
                </label>
                <div class="split-custom-group" v-for="group in splitRuleFor(column)!.groups" :key="group.id">
                  <div class="split-custom-head"><label><span>组合名称（可编辑）</span><input v-model="group.label" type="text" aria-label="自定义拆分组合名称" placeholder="输入组合名称" /></label><button type="button" class="icon-button compact-icon" aria-label="删除分组" @click="removeSplitGroup(splitRuleFor(column)!, group.id)">×</button></div>
                  <template v-if="splitRuleFor(column)!.kind === 'categorical'">
                    <input class="split-values-input" type="text" :value="group.values.join('、')" placeholder="输入类别值，用逗号分隔" @input="updateCategoricalValues(splitRuleFor(column)!, group, ($event.target as HTMLInputElement).value)" />
                    <div class="split-value-options" v-if="splitColumnProfile(column)?.unique_values?.length">
                      <button v-for="value in splitColumnProfile(column)!.unique_values" :key="value" type="button" class="mini-choice" :class="{ active: group.values.includes(value) }" @click="toggleCategoricalValue(splitRuleFor(column)!, group, value)">{{ value }}</button>
                    </div>
                  </template>
                  <div v-else class="split-range-fields">
                    <label>下界<input v-model="group.lower" type="number" placeholder="留空为 −∞" /></label>
                    <label>上界<input v-model="group.upper" type="number" placeholder="留空为 +∞" /></label>
                    <label class="inline-check"><input v-model="group.includeLower" type="checkbox" />含下界</label>
                    <label class="inline-check"><input v-model="group.includeUpper" type="checkbox" />含上界</label>
                  </div>
                </div>
                <button type="button" class="choice add-split-group" @click="addSplitGroup(splitRuleFor(column)!)">＋ 添加分组</button>
              </template>
            </article>
          </div>
          <p class="combination-warning" v-if="instantSplitRuleIssues.length">{{ instantSplitRuleIssues.join('；') }}</p>
        </section>

        <div class="role-table role-table-wide">
          <div class="role-head dynamic-role-head">
            <span>列名</span><span>推断</span><span v-if="showDependentRole">{{ dependentRoleLabel }}</span><span v-if="showFixedRole">分类因素</span><span v-if="showCovariateRole">连续自变量</span><span v-if="showRandomRole">随机分组</span><span v-if="showRandomSlopeRole">随机斜率</span><span v-if="showSubjectRole">对象 ID</span><span v-if="showRepeatedRole">重复/时间</span><span v-if="showInstantSplitRole">批量拆分</span>
          </div>
          <div class="role-row dynamic-role-row" v-for="column in profile.profile.columns" :key="column.name">
            <div><strong>{{ column.name }}</strong><small>{{ column.dtype }} · {{ column.n_unique }} 个值</small><small class="dual-role-note" v-if="fixedFactors.includes(column.name) && splitBy.includes(column.name)">分类因素 + 自定义拆分</small><small class="dual-role-note" v-if="isInstantDerivedColumn(column.name)">自定义因变量 · {{ inheritedSplitText(column.name, 'instant') }}</small></div>
            <span class="role-badge">{{ column.inferred_role }}</span>
            <button v-if="showDependentRole" class="choice" :aria-pressed="dependentVariables.includes(column.name)" :class="{ active: dependentVariables.includes(column.name) }" @click="toggleSelection('dv', column.name)">{{ dependentVariables.includes(column.name) ? '已选' : '选择' }}</button>
            <button v-if="showFixedRole" class="choice" :disabled="isInstantDerivedColumn(column.name)" :aria-pressed="fixedFactors.includes(column.name)" :class="{ active: fixedFactors.includes(column.name) }" @click="toggleSelection('factor', column.name)">{{ isInstantDerivedColumn(column.name) ? '不可用' : fixedFactors.includes(column.name) ? '已选' : '选择' }}</button>
            <button v-if="showCovariateRole" class="choice" :disabled="isInstantDerivedColumn(column.name)" :aria-pressed="covariates.includes(column.name)" :class="{ active: covariates.includes(column.name) }" @click="toggleSelection('covariate', column.name)">{{ isInstantDerivedColumn(column.name) ? '不可用' : covariates.includes(column.name) ? '已选' : '选择' }}</button>
            <button v-if="showRandomRole" class="choice" :disabled="isInstantDerivedColumn(column.name)" :aria-pressed="randomFactors.includes(column.name)" :class="{ active: randomFactors.includes(column.name) }" @click="toggleSelection('random', column.name)">{{ isInstantDerivedColumn(column.name) ? '不可用' : randomFactors.includes(column.name) ? '已选' : '选择' }}</button>
            <button v-if="showRandomSlopeRole" class="choice" :disabled="isInstantDerivedColumn(column.name) || !(fixedFactors.includes(column.name) || covariates.includes(column.name) || repeatedFactor === column.name)" :aria-pressed="randomSlopes.includes(column.name)" :class="{ active: randomSlopes.includes(column.name) }" @click="toggleRandomSlope(column.name)">{{ isInstantDerivedColumn(column.name) ? '不可用' : randomSlopes.includes(column.name) ? '已选' : '选择' }}</button>
            <button v-if="showSubjectRole" class="choice" :disabled="isInstantDerivedColumn(column.name)" :aria-pressed="subjectId === column.name" :class="{ active: subjectId === column.name }" @click="toggleSelection('subject', column.name)">{{ isInstantDerivedColumn(column.name) ? '不可用' : subjectId === column.name ? '已选' : '选择' }}</button>
            <button v-if="showRepeatedRole" class="choice" :disabled="isInstantDerivedColumn(column.name)" :aria-pressed="repeatedFactor === column.name" :class="{ active: repeatedFactor === column.name }" @click="toggleSelection('repeated', column.name)">{{ isInstantDerivedColumn(column.name) ? '不可用' : repeatedFactor === column.name ? '已选' : '选择' }}</button>
            <button v-if="showInstantSplitRole" class="choice" :disabled="isInstantDerivedColumn(column.name)" :class="{ active: splitBy.includes(column.name) }" @click="toggleSelection('split', column.name)">{{ isInstantDerivedColumn(column.name) ? '继承' : splitBy.includes(column.name) ? '已选' : '选择' }}</button>
          </div>
        </div>

        <div class="generic-batch-note" v-if="splitBy.length || dependentVariables.length > (currentMethod?.max_dependent_vars ?? 999) || factorCombinationsEnabled">
          <div><strong>通用批量模式已启用</strong><p>程序会展开 {{ dependentVariables.length > 1 ? `${dependentVariables.length} 个因变量` : '当前因变量' }}{{ factorCombinationsEnabled ? ` × ${factorCombinationCount} 个因素组合` : '' }}{{ splitBy.length ? ` × ${splitBy.join(' × ')}` : '' }}，逐任务执行同一分析计划；网页可按批次切换，Excel 会生成总览和逐批子表。</p></div>
          <button class="help-button" @click="openHelp('batch_workflow')">了解批量流程</button>
        </div>

        <AnalysisGuidanceCard :context="aiContext" />

        <div id="instant-preflight-action" class="plan-summary plan-summary-expanded workflow-jump-target" :class="{ 'workflow-jump-highlight': workflowJumpTarget === 'instant-preflight-action' }">
          <div><span>{{ dependentRoleLabel }}</span><strong>{{ dependentVariables.join('、') || (currentMethod?.min_dependent_vars === 0 ? '该方法不需要' : '未选择') }}</strong></div>
          <div><span>{{ factorCombinationsEnabled ? '候选分类因素' : '分类因素' }}</span><strong>{{ fixedFactors.join(' × ') || '未选择' }}</strong><small v-if="factorCombinationsEnabled">{{ factorCombinationCount }} 个组合 · {{ combinationPAdjust }}</small></div>
          <div v-if="showCovariateRole"><span>连续自变量</span><strong>{{ covariates.join('、') || '未选择' }}</strong></div>
          <div v-if="showRandomRole"><span>随机分组</span><strong>{{ randomFactors.join('、') || '未选择' }}</strong></div><div v-if="showRandomSlopeRole"><span>随机斜率</span><strong>{{ randomSlopes.join('、') || '随机截距' }}</strong></div><div v-if="estimateMarginalMeans"><span>EMM</span><strong>{{ emmFactors.join('、') || '等待选择因素' }}</strong></div>
          <div v-if="showSubjectRole"><span>对象 ID</span><strong>{{ subjectId || '未选择' }}</strong></div>
          <div v-if="showRepeatedRole"><span>重复/时间</span><strong>{{ repeatedFactor || '未选择' }}</strong></div>
          <div v-if="showInstantSplitRole"><span>拆分</span><strong>{{ splitBy.join('、') || '不拆分' }}</strong><small v-if="instantExpertMode && instantSplitRules.length">{{ instantSplitRules.length }} 条自定义规则</small></div>
          <div class="plan-execute-action">
            <small v-if="instantMissingSelections.length" class="selection-warning">还需选择：{{ instantMissingSelections.join('；') }}</small>
            <small v-else class="selection-ready">分析计划已具备预检条件</small>
            <button class="primary" :disabled="!canAnalyze || preflightLoading || loadingAnalysis" :aria-busy="preflightLoading || loadingAnalysis" @click="requestAnalysis">
              {{ preflightLoading ? '正在检查…' : loadingAnalysis ? '正在分析…' : '检查并执行分析' }}
            </button>
          </div>
        </div>
      </section>

      <section id="instant-analysis-result" class="panel workflow-jump-target" :class="{ 'workflow-jump-highlight': workflowJumpTarget === 'instant-analysis-result' }" v-if="result">
        <div class="section-heading"><div><span>03</span><h2>分析结果</h2></div><div class="heading-tools"><p>默认仅显示核心结论；完整数值和表格可在详细结果或下载文件中查看。</p><button class="secondary compact" :disabled="interactionBusy" @click="startNewInstantAnalysis">开始新分析</button></div></div>
        <AnalysisResultView :execution="result" :detailed="instantDetailedResults" :professional="instantExpertMode" @toggle-details="instantDetailedResults = !instantDetailedResults">
          <template #actions>
            <button type="button" class="secondary compact" :disabled="interactionBusy || builtinReportLoading.instant || aiReportLoadingTarget === 'instant'" @click="generateAIResultReport('instant')">{{ builtinReportLoading.instant ? '正在准备排序与三表…' : aiReportLoadingTarget === 'instant' ? 'AI 总结中…' : instantAIReport ? '重新生成 AI 文字总结' : '生成 AI 文字总结' }}</button>
            <button v-if="result.kind === 'single' && !instantReportLinks" type="button" class="primary compact" :disabled="instantReportLoading" @click="generateInstantReport">{{ instantReportLoading ? '正在生成…' : '生成下载文件' }}</button>
            <a v-if="instantReportLinks" class="download-link compact-link" :href="appUrl(instantReportLinks.xlsx)">下载结果 Excel</a>
            <a v-if="instantReportLinks" class="download-link compact-link secondary-link" :href="appUrl(instantReportLinks.zip)">下载完整报告 ZIP</a>
          </template>
          <template #batch-actions>
            <div v-if="result.batch_export?.status === 'preparing'" class="batch-export-preparing" role="status"><span class="inline-spinner"></span><div><strong>批次结果已可查看</strong><small>下载文件正在后台整理，不影响结果总览和逐批查看。</small></div></div>
            <div v-else-if="result.batch_export?.status === 'failed'" class="batch-export-failed"><strong>下载文件准备失败</strong><small>{{ result.batch_export.error || '计算结果不受影响，可重新执行后生成。' }}</small></div>
            <div v-else class="result-toolbar-actions"><a class="download-link" v-if="result.batch_export?.download_url" :href="appUrl(result.batch_export.download_url)">下载合并结果 XLSX</a><a class="download-link secondary-link" v-if="result.batch_export?.standardized_report?.download_url" :href="appUrl(result.batch_export.standardized_report.download_url)">下载完整规范报告 ZIP</a><a class="download-link secondary-link" v-if="result.batch_export?.standardized_report?.markdown_download_url" :href="appUrl(result.batch_export.standardized_report.markdown_download_url)">下载规范报告 Markdown</a><a class="download-link secondary-link" v-if="result.batch_export?.standardized_report?.json_download_url" :href="appUrl(result.batch_export.standardized_report.json_download_url)">下载完整结果 JSON</a></div>
          </template>
        </AnalysisResultView>
      </section>
      <section class="panel report-preparing-panel" v-if="result && builtinReportLoading.instant && !instantBuiltinReport" aria-live="polite">
        <div class="report-preparing-animation" aria-hidden="true"><span></span><span></span><span></span></div>
        <div><p class="eyebrow">REPORT PREPARATION</p><h2>正在准备本地排序与三张规范表</h2><p>计算结果已经可以查看。本地证据完成后会立即显示，随后 AI 将在后台生成文字总结。</p></div>
      </section>
      <AIResultReportPanel id="instant-ai-result-report" v-if="instantBuiltinReport || instantAIReport" :builtin-payload="instantBuiltinReport" :ai-payload="instantAIReport" :ai-loading="aiReportLoadingTarget === 'instant'" :ai-ready="aiReady" :ai-error="aiReportErrors.instant" :batch="result?.kind === 'batch'" @generate-ai="generateAIResultReport('instant')" />

      <section class="panel preview-panel">
        <details>
          <summary>查看数据预览（前 20 行）</summary>
          <div class="table-wrap"><table><thead><tr><th v-for="column in previewColumns" :key="column">{{ column }}</th></tr></thead>
            <tbody><tr v-for="(row, index) in profile.preview" :key="index"><td v-for="column in previewColumns" :key="column">{{ row[column] ?? '-' }}</td></tr></tbody>
          </table></div>
        </details>
      </section>
    </template>

    </template>

    <template v-else>
      <ErrorNotice :title="workspaceErrorTitle" :message="workspaceError" :hints="workspaceErrorHints" @dismiss="clearWorkspaceError" />
      <div class="state-notice stale" v-if="workspaceResultInvalidated"><div><strong>当前运行结果已失效</strong><p>{{ workspaceResultInvalidatedReason }}</p></div><button class="secondary compact" @click="workspaceResultInvalidated = false">知道了</button></div>
      <section class="workspace-layout">
        <aside id="workspace-project-selection" class="panel workspace-sidebar workflow-jump-target" :class="{ 'workflow-jump-highlight': workflowJumpTarget === 'workspace-project-selection' }">
          <div class="section-heading compact"><div><span>01</span><h2>项目</h2></div></div>
          <div class="workspace-storage-card" v-if="workspaceInfo">
            <span>所有者持久存储</span><strong>{{ formatBytes(workspaceInfo.used_bytes) }}</strong><small>{{ workspaceInfo.project_count }} 个项目 · 访客临时数据会在闲置退出后清理</small>
          </div>
          <div class="project-list">
            <button v-for="project in workspaceProjects" :key="project.id" :class="{ active: workspaceProject?.id === project.id }" @click="loadWorkspaceProject(project.id)">
              <strong>{{ project.name }}</strong><small>{{ project.dataset_count ?? 0 }} 数据集 · {{ project.run_count ?? 0 }} 运行</small>
            </button>
          </div>
          <div class="stack-form">
            <input v-model="workspaceProjectName" placeholder="新项目名称" />
            <textarea v-model="workspaceProjectDescription" placeholder="项目说明（可选）"></textarea>
            <button class="primary" :disabled="workspaceLoading || !workspaceProjectName.trim()" @click="createWorkspaceProject">创建项目</button>
            <button v-if="workspaceAuthState?.required" class="secondary workspace-logout" :disabled="workspaceLoading" @click="logoutWorkspace">锁定并退出工作区</button>
          </div>
        </aside>

        <div class="workspace-main">
          <section class="panel empty-state" v-if="!workspaceProject">
            <h2>选择或创建一个项目</h2><p>项目工作区会持久保存原始数据、分析计划、运行记录和报告。</p>
          </section>

          <template v-else>
            <section id="workspace-data-selection" class="panel workflow-jump-target" :class="{ 'workflow-jump-highlight': workflowJumpTarget === 'workspace-data-selection' }">
              <div class="section-heading"><div><span>02</span><h2>{{ workspaceProject.name }}</h2></div><div class="heading-tools"><p>{{ workspaceProject.description || '无项目说明' }}</p><button class="help-button" @click="openHelp('workspace')">工作区说明</button></div></div>
              <div class="workspace-upload">
                <label class="drop-zone small"><input ref="workspaceFileInput" type="file" accept=".csv,.tsv,.txt,.xlsx,.xls" :disabled="workspaceLoading" @click="prepareFileReselection" @change="handleWorkspaceFile" /><strong>{{ workspaceDatasetFile?.name ?? '添加数据集' }}</strong><small>原始文件将保存到本地工作区</small></label>
                <div class="stack-form"><input v-model="workspaceDatasetName" placeholder="数据集名称" /><button class="primary" :disabled="!workspaceDatasetFile || workspaceLoading" @click="uploadWorkspaceDataset">上传并建立指纹</button></div>
              </div>
              <div class="dataset-cards" v-if="workspaceProject.datasets.length">
                <button v-for="dataset in workspaceProject.datasets" :key="dataset.id" :disabled="workspaceLoading" :class="{ active: workspaceDatasetId === dataset.id }" @click="selectWorkspaceDataset(dataset.id)">
                  <strong>{{ dataset.name }}</strong><small>{{ dataset.profile_json.n_rows }} 行 × {{ dataset.profile_json.n_cols }} 列</small><code>{{ dataset.fingerprint_json.cleaned_sha256.slice(0, 12) }}</code>
                </button>
              </div>
            </section>

            <section id="workspace-analysis-roles" class="panel workflow-jump-target" :class="{ 'preflight-focus': focusedField === 'workspace-analysis-roles', 'workflow-jump-highlight': workflowJumpTarget === 'workspace-analysis-roles' }" v-if="workspaceDataset">
              <div class="section-heading"><div><span>03</span><h2>保存分析计划</h2></div><div class="heading-tools"><p>计划会记录修订号和 SHA-256，可复制后调整。</p><button class="help-button" :disabled="interactionBusy" @click="restoreSuggestedRoles('workspace')">恢复推荐选择</button></div></div>
              <div id="workspace-analysis-method" class="plan-grid" :class="{ 'preflight-focus': focusedField === 'workspace-analysis-method' }">
                <label class="field">计划名称<input v-model="workspacePlanName" /></label>
                <label class="field">统计方法<select v-model="workspaceMethod"><optgroup v-for="group in methodCategories" :key="group.category" :label="group.category"><option v-for="method in group.items" :key="method.name" :value="method.name" :disabled="!method.runnable">{{ method.label_zh }}{{ method.status === 'experimental' ? '（实验性）' : method.runnable ? '' : '（未实现）' }}</option></optgroup></select><small>切换方法会重置变量角色，并按新方法重新应用推荐划分。</small></label>
                <div class="analysis-mode-switch" role="group" aria-label="参数显示模式"><button type="button" :class="{ active: !workspaceExpertMode }" @click="setWorkspaceExpertMode(false)"><strong>简洁模式</strong><small>使用推荐默认值</small></button><button type="button" :class="{ active: workspaceExpertMode }" @click="setWorkspaceExpertMode(true)"><strong>专业模式</strong><small>显示全部参数</small></button></div>
              </div>
              <section class="method-intro" v-if="workspaceCurrentMethod"><div class="method-intro-head"><div><span>{{ workspaceCurrentMethod.category }}</span><h3>{{ workspaceCurrentMethod.label_zh }}</h3></div></div><div class="method-intro-grid"><article><strong>通常用于什么</strong><p>{{ workspaceCurrentMethod.purpose }}</p></article><article><strong>变量如何作用</strong><p>{{ workspaceCurrentMethod.variable_relationship }}</p></article></div></section>
              <section class="recommended-settings-card" v-if="workspaceCurrentMethod"><div><span class="source-label">当前采用</span><strong>{{ workspaceExpertMode ? '专业参数' : '推荐设置' }}</strong><p>{{ workspaceExpertMode ? '参数修改会随计划一起保存。' : '默认值适合大多数常规分析，必要时再展开常用设置。' }}</p></div><div class="setting-chips"><span v-for="item in workspaceRecommendedSummary" :key="item">{{ item }}</span></div>
                <details class="common-parameter-panel" v-if="workspaceExpertMode && (workspaceCommonParameters.length || workspaceMethod === 'one_sample_ttest' || workspaceMethod === 'chi_square_goodness_of_fit')"><summary>调整常用设置（可选）</summary><div class="advanced-method-grid compact-parameter-grid">
                  <label class="field" v-if="workspaceMethod === 'one_sample_ttest'">单样本参考值<input v-model.number="testValue" type="number" step="any" /><small>默认 0。</small></label>
                  <label class="field" v-if="workspaceMethod === 'chi_square_goodness_of_fit'">理论比例<input v-model="expectedProportionsText" type="text" placeholder="例如：0.25,0.25,0.5" /><small>留空表示等比例。</small></label>
                  <div class="field method-parameter" v-for="parameter in workspaceCommonParameters" :key="parameter.key"><span class="field-label">{{ parameter.label_zh }}</span><template v-if="parameter.kind === 'multi_select'"><div class="parameter-toolbar"><small>已选择 {{ (workspaceMethodParameters[parameter.key] ?? []).length }} 项</small><button type="button" class="text-button" @click="resetMethodParameter('workspace', parameter.key)">恢复默认</button></div><div class="multi-choice-grid"><button v-for="option in commonParameterOptions(parameter, workspaceMethodParameters[parameter.key])" :key="option.value" type="button" class="multi-choice" :aria-pressed="(workspaceMethodParameters[parameter.key] ?? []).includes(option.value)" :class="{ active: (workspaceMethodParameters[parameter.key] ?? []).includes(option.value) }" @click="toggleMultiSelectParameter('workspace', parameter.key, option.value)"><span class="choice-check">{{ (workspaceMethodParameters[parameter.key] ?? []).includes(option.value) ? '✓' : '+' }}</span><span class="choice-copy"><strong>{{ option.label }}</strong><small class="choice-help" v-if="optionHelp(parameter, option.value)">{{ optionHelp(parameter, option.value) }}</small></span><small v-if="Array.isArray(parameter.default) && parameter.default.includes(option.value)">默认</small></button></div></template><select v-else-if="parameter.kind === 'select'" v-model="workspaceMethodParameters[parameter.key]"><option v-for="option in parameter.options" :key="option.value" :value="option.value">{{ option.label }}</option></select><input v-else-if="parameter.kind === 'boolean'" v-model="workspaceMethodParameters[parameter.key]" type="checkbox" class="parameter-checkbox" /><input v-else-if="parameter.kind === 'integer'" v-model.number="workspaceMethodParameters[parameter.key]" type="number" :min="parameter.minimum ?? undefined" :max="parameter.maximum ?? undefined" :step="parameter.step ?? 1" /><input v-else-if="parameter.kind === 'number'" v-model.number="workspaceMethodParameters[parameter.key]" type="number" :min="parameter.minimum ?? undefined" :max="parameter.maximum ?? undefined" :step="parameter.step ?? 'any'" /><input v-else v-model="workspaceMethodParameters[parameter.key]" type="text" /><small>{{ parameterHelp(parameter) }}</small><small class="recommendation-note" v-if="parameter.recommendation_note">{{ parameter.recommendation_note }}</small><small v-if="parameter.recommended_options?.length && parameter.options.length > commonParameterOptions(parameter, workspaceMethodParameters[parameter.key]).length">更多低频选项可在专业模式中选择。</small></div>
                </div></details>
              </section>
              <details class="advanced-method-panel professional-control-group" open v-if="workspaceCurrentMethod?.supports_batch"><summary>批量任务 <small>{{ workspaceSplits.length }} 个拆分字段 · {{ workspaceFactorCombinationsEnabled ? `${workspaceFactorCombinationCount} 个因素模型` : '单一因素模型' }}</small></summary><div class="professional-control-body">
              <section class="factor-combination-panel" v-if="workspaceShowFixedRole && (workspaceFactorCombinationsEnabled || workspaceExpertMode)">
                <label class="combination-toggle"><input :checked="workspaceFactorCombinationsEnabled" type="checkbox" :disabled="workspaceFactors.length === 0" @change="onFactorCombinationToggle('workspace', $event)" /><span><strong>分类因素组合实验</strong><small>将选中因素作为候选池，按指定阶数组合后分别运行；超额因素必须先确认。</small></span></label>
                <div class="combination-settings" v-if="workspaceFactorCombinationsEnabled">
                  <label class="field">计算阶数（最高阶 k）<select v-model.number="workspaceFactorCombinationMaxOrder"><option v-for="order in workspaceFactorOrderLimit" :key="`wmax-${order}`" :value="order">1 至 {{ order }} 阶</option></select><small>自动遍历 1 阶到 k 阶的全部因素组合。</small></label>
                  <div class="combination-estimate"><span>预计模型</span><strong>{{ workspaceFactorCombinationCount }}</strong></div>
                </div>
                <details class="combination-name-editor" v-if="workspaceFactorCombinationsEnabled && workspaceFactorCombinationNames.length"><summary>编辑组合名称（可选）</summary><p>名称只用于显示，底层因素会以“组合因素”保留。</p><div class="combination-name-list"><label v-for="name in workspaceFactorCombinationNames" :key="`workspace-name-${name}`"><span>{{ name }}</span><input type="text" :value="workspaceFactorCombinationLabels[name] ?? ''" :placeholder="name" :aria-label="`工作区组合名称 ${name}`" @input="setFactorCombinationLabel('workspace', name, ($event.target as HTMLInputElement).value)" /></label></div><small class="selection-warning" v-if="factorCombinationNameIssues('workspace').length">{{ factorCombinationNameIssues('workspace').join('；') }}</small></details>
                <p class="combination-warning" v-if="workspaceFactorCombinationsEnabled">将执行 1 至 {{ workspaceFactorCombinationMaxOrder }} 阶的 {{ workspaceFactorCombinationCount }} 个独立组合模型。<template v-if="workspaceCombinationPAdjust === 'none'">本次不校正，判断 p 与原始 p 完全相同。</template></p>
              </section>
              <section class="factor-combination-panel cross-model-correction-panel" v-if="workspaceCurrentMethod?.supports_batch">
                <div><strong>跨模型多重校正</strong><p>一次计划展开多个因变量、因素组合或数据拆分时控制整组主要检验的误报风险；历史运行之间不会自动合并校正。</p></div>
                <label class="field">校正方法<select v-model="workspaceCombinationPAdjust" aria-label="工作区跨模型校正方法"><option value="holm">Holm（默认，稳健）</option><option value="bonferroni">Bonferroni（更保守）</option><option value="fdr_bh">FDR-BH</option><option value="none">不校正（仅限预先定义的独立假设）</option></select><small>简洁模式与专业模式均可设置，并随计划保存。</small><small class="selection-warning" v-if="workspaceCombinationPAdjust === 'none'">已选择不校正：直接按原始 p 判断，不修改 p 值，并保留多重检验误报风险提示。</small></label>
              </section>
              </div></details>
              <details id="workspace-advanced-parameters" class="advanced-method-panel" :class="{ 'preflight-focus': focusedField === 'workspace-advanced-parameters' }" v-if="workspaceExpertMode"><summary>模型与检验 <small>α={{ alpha }} · Type {{ ssType }}</small></summary><div class="advanced-method-grid"><label class="field">显著性水平 α<input v-model.number="alpha" type="number" min="0.001" max="0.5" step="0.01" /><small>默认 0.05。</small></label><label class="field" v-if="['twoway_anova','threeway_anova','multifactor_anova','ancova'].includes(workspaceMethod)">平方和类型<select v-model.number="ssType"><option :value="1">Type I</option><option :value="2">Type II</option><option :value="3">Type III</option></select><small>不平衡析因设计通常使用 Type III。</small></label>
                <div class="field method-parameter" v-for="parameter in workspaceAdvancedParameters" :key="parameter.key"><span class="field-label">{{ parameter.label_zh }}</span><template v-if="parameter.kind === 'multi_select'"><div class="parameter-toolbar"><small>已选择 {{ (workspaceMethodParameters[parameter.key] ?? []).length }} 项</small><button type="button" class="text-button" @click="resetMethodParameter('workspace', parameter.key)">恢复默认</button></div><div class="multi-choice-grid"><button v-for="option in parameter.options" :key="option.value" type="button" class="multi-choice" :aria-pressed="(workspaceMethodParameters[parameter.key] ?? []).includes(option.value)" :class="{ active: (workspaceMethodParameters[parameter.key] ?? []).includes(option.value) }" @click="toggleMultiSelectParameter('workspace', parameter.key, option.value)"><span class="choice-check">{{ (workspaceMethodParameters[parameter.key] ?? []).includes(option.value) ? '✓' : '+' }}</span><span class="choice-copy"><strong>{{ option.label }}</strong><small class="choice-help" v-if="optionHelp(parameter, option.value)">{{ optionHelp(parameter, option.value) }}</small></span><small v-if="Array.isArray(parameter.default) && parameter.default.includes(option.value)">默认</small></button></div></template><select v-else-if="parameter.kind === 'select'" v-model="workspaceMethodParameters[parameter.key]"><option v-for="option in parameter.options" :key="option.value" :value="option.value">{{ option.label }}</option></select><input v-else-if="parameter.kind === 'boolean'" v-model="workspaceMethodParameters[parameter.key]" type="checkbox" class="parameter-checkbox" /><input v-else-if="parameter.kind === 'integer'" v-model.number="workspaceMethodParameters[parameter.key]" type="number" :min="parameter.minimum ?? undefined" :max="parameter.maximum ?? undefined" :step="parameter.step ?? 1" /><input v-else-if="parameter.kind === 'number'" v-model.number="workspaceMethodParameters[parameter.key]" type="number" :min="parameter.minimum ?? undefined" :max="parameter.maximum ?? undefined" :step="parameter.step ?? 'any'" /><input v-else v-model="workspaceMethodParameters[parameter.key]" type="text" /><small>{{ parameter.description }} <span class="default-value">默认：{{ parameterDefaultLabel(parameter.default) }}</span></small></div>
              </div></details>
              <details id="workspace-phase3-options" class="advanced-method-panel phase3-panel" :class="{ 'preflight-focus': focusedField === 'workspace-phase3-options' }" v-if="workspaceExpertMode">
                <summary>比较与结果 <small>EMM、对比校正与诊断图</small></summary>
                <div class="advanced-method-grid">
                  <label class="combination-toggle" v-if="workspaceCurrentMethod?.supports_emm"><input v-model="workspaceEstimateMarginalMeans" type="checkbox" /><span><strong>估计边际均值（EMM）</strong><small>保存到分析计划和可复现记录。</small></span></label>
                  <label class="field" v-if="workspaceEstimateMarginalMeans">对比校正<select v-model="workspaceContrastCorrection"><option value="holm">Holm</option><option value="bonferroni">Bonferroni</option><option value="fdr_bh">FDR-BH</option><option value="none">不校正</option></select></label>
                  <label class="combination-toggle" v-if="workspaceCurrentMethod?.supports_diagnostic_plots"><input v-model="workspaceDiagnosticPlots" type="checkbox" /><span><strong>生成诊断图</strong><small>报告包中同时保存 PNG 图形。</small></span></label>
                </div>
                <div class="method-output" v-if="workspaceEstimateMarginalMeans && workspaceEmmCandidates.length"><strong>EMM 因素</strong><button v-for="column in workspaceEmmCandidates" :key="column" class="choice" :class="{ active: workspaceEmmFactors.includes(column) }" @click="toggleWorkspaceEmmFactor(column)">{{ column }}</button></div>
                <p class="setting-note" v-if="!workspaceCurrentMethod?.supports_emm && !workspaceCurrentMethod?.supports_diagnostic_plots && !workspaceShowRandomSlopeRole">当前方法没有额外的模型比较或诊断选项。</p>
              </details>
              <details class="advanced-method-panel calibration-panel" v-if="workspaceExpertMode">
                <summary>数据准备与拆分 <small>{{ workspaceDerivedColumns.length }} 个自定义列 · {{ workspaceSplits.length }} 个拆分字段</small></summary>
                <div class="professional-subsection"><h4>自定义计算列</h4><p>从当前数据集的原始数值列逐行计算，自定义列之间不能互相引用。</p><DerivedColumnEditor v-model="workspaceDerivedColumns" :columns="workspaceDataset?.profile_json.columns ?? []" :warnings="workspaceDerivedWarnings" :busy="workspaceDerivedPreviewLoading" @changed="refreshWorkspaceDerivedPreview" /></div>
                <div class="advanced-method-grid"><label class="combination-toggle"><input v-model="workspaceCalibrationEnabled" type="checkbox" /><span><strong>启用数据校正</strong><small>用于消除系统误差、对齐 Baseline 或降低极值预测偏移。</small></span></label><label class="field" v-if="workspaceCalibrationEnabled">校正策略<select v-model="workspaceCalibrationMethod"><option value="zscore">标准化</option><option value="robust_zscore">稳健标准化</option><option value="baseline_center">基线中心化</option></select></label><label class="field" v-if="workspaceCalibrationEnabled && workspaceCalibrationMethod === 'baseline_center'">基准列<select v-model="workspaceCalibrationBaselineColumn"><option value="">请选择</option><option v-for="column in workspaceColumns" :key="`wcal-base-${column.name}`" :value="column.name">{{ column.name }}</option></select></label><label class="field" v-if="workspaceCalibrationEnabled && workspaceCalibrationMethod === 'baseline_center'">基准值<input v-model="workspaceCalibrationBaselineValue" type="text" /></label></div>
                <div class="method-output" v-if="workspaceCalibrationEnabled"><strong>校正列</strong><button v-for="column in [...workspaceDvs, ...workspaceCovariates]" :key="`wcal-${column}`" type="button" class="choice" :class="{ active: workspaceCalibrationColumns.includes(column) }" @click="workspaceCalibrationColumns = workspaceCalibrationColumns.includes(column) ? workspaceCalibrationColumns.filter(item => item !== column) : [...workspaceCalibrationColumns, column]">{{ column }}</button></div>
                <button type="button" class="text-button" @click="openHelp('calibration')">查看校正技术说明</button>
              </details>
              <section class="split-group-panel" v-if="workspaceExpertMode && workspaceCurrentMethod?.supports_batch && workspaceSplits.length">
                <div class="split-group-copy"><span class="source-label">专业拆分</span><strong>合并类别水平或设置数值区间</strong><p>未分配水平对应的数据不参与计算；兼作分类因素时，每组必须保留至少两个有效水平。</p></div>
                <div class="split-rule-list">
                  <article class="split-rule-card" v-for="column in workspaceSplits" :key="`workspace-split-${column}`">
                    <div class="split-rule-head"><div><strong>{{ column }}</strong><small>{{ workspaceSplitRuleFor(column) ? '使用自定义分组' : '按每个实际值拆分' }}</small></div><button v-if="!workspaceSplitRuleFor(column)" type="button" class="secondary compact" @click="enableWorkspaceCustomSplit(column)">自定义分组</button><button v-else type="button" class="text-button" @click="disableWorkspaceCustomSplit(column)">恢复按原值拆分</button></div>
                    <template v-if="workspaceSplitRuleFor(column)">
                      <label class="split-kind">分组类型<select v-model="workspaceSplitRuleFor(column)!.kind"><option value="categorical">类别水平合并</option><option value="numeric">数值区间</option></select></label>
                      <div class="split-custom-group" v-for="group in workspaceSplitRuleFor(column)!.groups" :key="group.id">
                        <div class="split-custom-head"><label><span>组合名称</span><input v-model="group.label" type="text" /></label><button type="button" class="icon-button compact-icon" aria-label="删除分组" @click="removeSplitGroup(workspaceSplitRuleFor(column)!, group.id)">×</button></div>
                        <template v-if="workspaceSplitRuleFor(column)!.kind === 'categorical'">
                          <input class="split-values-input" type="text" :value="group.values.join('、')" placeholder="输入类别值，用逗号分隔" @input="updateCategoricalValues(workspaceSplitRuleFor(column)!, group, ($event.target as HTMLInputElement).value)" />
                          <div class="split-value-options"><button v-for="value in workspaceColumns.find(item => item.name === column)?.unique_values ?? []" :key="value" type="button" class="mini-choice" :class="{ active: group.values.includes(value) }" @click="toggleCategoricalValue(workspaceSplitRuleFor(column)!, group, value)">{{ value }}</button></div>
                        </template>
                        <div v-else class="split-range-fields"><label>下界<input v-model="group.lower" type="number" placeholder="留空为 −∞" /></label><label>上界<input v-model="group.upper" type="number" placeholder="留空为 +∞" /></label><label class="inline-check"><input v-model="group.includeLower" type="checkbox" />含下界</label><label class="inline-check"><input v-model="group.includeUpper" type="checkbox" />含上界</label></div>
                      </div>
                      <button type="button" class="choice add-split-group" @click="addSplitGroup(workspaceSplitRuleFor(column)!)">＋ 添加分组</button>
                    </template>
                  </article>
                </div>
                <p class="combination-warning" v-if="workspaceSplitRuleIssues.length">{{ workspaceSplitRuleIssues.join('；') }}</p>
              </section>
              <div class="role-table role-table-wide">
                <div class="role-head dynamic-role-head"><span>列名</span><span>推断</span><span v-if="workspaceShowDependentRole">{{ workspaceDependentRoleLabel }}</span><span v-if="workspaceShowFixedRole">分类因素</span><span v-if="workspaceShowCovariateRole">连续自变量</span><span v-if="workspaceShowRandomRole">随机分组</span><span v-if="workspaceShowRandomSlopeRole">随机斜率</span><span v-if="workspaceShowSubjectRole">对象 ID</span><span v-if="workspaceShowRepeatedRole">重复/时间</span><span>批量拆分</span></div>
                <div class="role-row dynamic-role-row" v-for="column in workspaceColumns" :key="column.name">
                  <div><strong>{{ column.name }}</strong><small>{{ column.dtype }} · {{ column.n_unique }} 个值</small><small class="dual-role-note" v-if="workspaceFactors.includes(column.name) && workspaceSplits.includes(column.name)">分类因素 + 自定义拆分</small><small class="dual-role-note" v-if="isWorkspaceDerivedColumn(column.name)">自定义因变量 · {{ inheritedSplitText(column.name, 'workspace') }}</small></div><span class="role-badge">{{ column.inferred_role }}</span>
                  <button v-if="workspaceShowDependentRole" class="choice" :aria-pressed="workspaceDvs.includes(column.name)" :class="{ active: workspaceDvs.includes(column.name) }" @click="toggleWorkspaceSelection('dv', column.name)">{{ workspaceDvs.includes(column.name) ? '已选' : '选择' }}</button>
                  <button v-if="workspaceShowFixedRole" class="choice" :disabled="isWorkspaceDerivedColumn(column.name)" :aria-pressed="workspaceFactors.includes(column.name)" :class="{ active: workspaceFactors.includes(column.name) }" @click="toggleWorkspaceSelection('factor', column.name)">{{ isWorkspaceDerivedColumn(column.name) ? '不可用' : workspaceFactors.includes(column.name) ? '已选' : '选择' }}</button>
                  <button v-if="workspaceShowCovariateRole" class="choice" :disabled="isWorkspaceDerivedColumn(column.name)" :aria-pressed="workspaceCovariates.includes(column.name)" :class="{ active: workspaceCovariates.includes(column.name) }" @click="toggleWorkspaceSelection('covariate', column.name)">{{ isWorkspaceDerivedColumn(column.name) ? '不可用' : workspaceCovariates.includes(column.name) ? '已选' : '选择' }}</button>
                  <button v-if="workspaceShowRandomRole" class="choice" :disabled="isWorkspaceDerivedColumn(column.name)" :aria-pressed="workspaceRandomFactors.includes(column.name)" :class="{ active: workspaceRandomFactors.includes(column.name) }" @click="toggleWorkspaceSelection('random', column.name)">{{ isWorkspaceDerivedColumn(column.name) ? '不可用' : workspaceRandomFactors.includes(column.name) ? '已选' : '选择' }}</button>
                  <button v-if="workspaceShowRandomSlopeRole" class="choice" :disabled="isWorkspaceDerivedColumn(column.name) || !(workspaceFactors.includes(column.name) || workspaceCovariates.includes(column.name) || workspaceRepeatedFactor === column.name)" :aria-pressed="workspaceRandomSlopes.includes(column.name)" :class="{ active: workspaceRandomSlopes.includes(column.name) }" @click="toggleWorkspaceRandomSlope(column.name)">{{ isWorkspaceDerivedColumn(column.name) ? '不可用' : workspaceRandomSlopes.includes(column.name) ? '已选' : '选择' }}</button>
                  <button v-if="workspaceShowSubjectRole" class="choice" :disabled="isWorkspaceDerivedColumn(column.name)" :aria-pressed="workspaceSubjectId === column.name" :class="{ active: workspaceSubjectId === column.name }" @click="toggleWorkspaceSelection('subject', column.name)">{{ isWorkspaceDerivedColumn(column.name) ? '不可用' : workspaceSubjectId === column.name ? '已选' : '选择' }}</button>
                  <button v-if="workspaceShowRepeatedRole" class="choice" :disabled="isWorkspaceDerivedColumn(column.name)" :aria-pressed="workspaceRepeatedFactor === column.name" :class="{ active: workspaceRepeatedFactor === column.name }" @click="toggleWorkspaceSelection('repeated', column.name)">{{ isWorkspaceDerivedColumn(column.name) ? '不可用' : workspaceRepeatedFactor === column.name ? '已选' : '选择' }}</button>
                  <button class="choice" :disabled="!workspaceCurrentMethod?.supports_batch || isWorkspaceDerivedColumn(column.name)" :class="{ active: workspaceSplits.includes(column.name) }" @click="toggleWorkspaceSelection('split', column.name)">{{ isWorkspaceDerivedColumn(column.name) ? '继承' : '选择' }}</button>
                </div>
              </div>
              <AnalysisGuidanceCard :context="aiContext" />
              <div class="plan-summary plan-summary-expanded"><div><span>{{ workspaceDependentRoleLabel }}</span><strong>{{ workspaceDvs.join('、') || (workspaceCurrentMethod?.min_dependent_vars === 0 ? '该方法不需要' : '未选择') }}</strong></div><div><span>{{ workspaceFactorCombinationsEnabled ? '候选分类因素' : '分类因素' }}</span><strong>{{ workspaceFactors.join(' × ') || '未选择' }}</strong><small v-if="workspaceFactorCombinationsEnabled">{{ workspaceFactorCombinationCount }} 个组合</small></div><div v-if="workspaceShowCovariateRole"><span>连续自变量</span><strong>{{ workspaceCovariates.join('、') || '未选择' }}</strong></div><div v-if="workspaceShowRandomRole"><span>随机分组</span><strong>{{ workspaceRandomFactors.join('、') || '未选择' }}</strong></div><div v-if="workspaceShowRandomSlopeRole"><span>随机斜率</span><strong>{{ workspaceRandomSlopes.join('、') || '随机截距' }}</strong></div><div v-if="workspaceEstimateMarginalMeans"><span>EMM</span><strong>{{ workspaceEmmFactors.join('、') || '等待选择因素' }}</strong></div><div v-if="workspaceShowSubjectRole"><span>对象 ID</span><strong>{{ workspaceSubjectId || '未选择' }}</strong></div><div v-if="workspaceShowRepeatedRole"><span>重复/时间</span><strong>{{ workspaceRepeatedFactor || '未选择' }}</strong></div><div><span>拆分</span><strong>{{ workspaceSplits.join('、') || '不拆分' }}</strong></div><div class="plan-save-action"><small v-if="workspaceMissingSelections.length" class="selection-warning">还需选择：{{ workspaceMissingSelections.join('；') }}</small><button class="primary" :disabled="!canCreateWorkspacePlan || workspaceLoading" @click="createWorkspacePlan">保存计划</button></div></div>
            </section>

            <section id="workspace-run-plans" class="panel workflow-jump-target" :class="{ 'workflow-jump-highlight': workflowJumpTarget === 'workspace-run-plans' }" v-if="workspaceProject.plans.length">
              <div class="section-heading"><div><span>04</span><h2>计划与运行历史</h2></div><p>重新运行不会覆盖旧结果。</p></div>
              <div class="history-list">
                <article v-for="plan in workspaceProject.plans" :key="plan.id"><div><strong>{{ plan.name }}</strong><small>修订 {{ plan.revision }} · {{ plan.plan_json.method }}</small></div><button class="choice active" :disabled="interactionBusy" @click="runWorkspacePlan(plan.id)">{{ preflightLoading && pendingWorkspacePlanId === plan.id ? '检查中…' : '运行' }}</button></article>
              </div>
              <div class="history-list runs" v-if="workspaceProject.runs.length">
                <article v-for="run in workspaceProject.runs" :key="run.id"><div><strong>{{ run.plan_name }}</strong><small>{{ run.status }} · {{ run.started_at }}</small></div><button class="choice" :disabled="run.status !== 'completed' || interactionBusy" @click="generateWorkspaceReport(run.id)">{{ workspaceLoading ? '处理中…' : '生成报告' }}</button></article>
              </div>
            </section>

            <section id="workspace-latest-result" class="panel workflow-jump-target" :class="{ 'workflow-jump-highlight': workflowJumpTarget === 'workspace-latest-result' }" v-if="workspaceRun?.result_json">
              <div class="section-heading"><div><span>05</span><h2>最新运行</h2></div><div class="heading-tools"><p>运行 ID：{{ workspaceRun.id }}</p></div></div>
              <AnalysisResultView :execution="workspaceRun.result_json" :detailed="workspaceDetailedResults" :professional="workspaceExpertMode" @toggle-details="workspaceDetailedResults = !workspaceDetailedResults">
                <template #actions><button type="button" class="secondary compact" :disabled="interactionBusy || builtinReportLoading.workspace || aiReportLoadingTarget === 'workspace'" @click="generateAIResultReport('workspace')">{{ builtinReportLoading.workspace ? '正在准备排序与三表…' : aiReportLoadingTarget === 'workspace' ? 'AI 总结中…' : workspaceAIReport ? '重新生成 AI 文字总结' : '生成 AI 文字总结' }}</button><button type="button" class="primary compact" :disabled="workspaceLoading" @click="generateWorkspaceReport(workspaceRun.id)">{{ workspaceLoading ? '处理中…' : workspaceReportId ? '重新生成报告' : '生成报告' }}</button><a class="download-link compact-link" v-if="workspaceReportId && workspaceRun.result_json.kind === 'single'" :href="appUrl(`/api/reports/${workspaceReportId}/download`)">下载报告 ZIP</a></template>
                <template #batch-actions><div class="result-toolbar-actions" v-if="workspaceReportId"><a class="download-link" :href="appUrl(workspaceReportLinks?.xlsx || `/api/reports/${workspaceReportId}/download`)">下载合并结果 XLSX</a><a class="download-link secondary-link" v-if="workspaceReportLinks?.zip" :href="appUrl(workspaceReportLinks.zip)">下载完整规范报告 ZIP</a><a class="download-link secondary-link" v-if="workspaceReportLinks?.markdown" :href="appUrl(workspaceReportLinks.markdown)">下载规范报告 Markdown</a><a class="download-link secondary-link" v-if="workspaceReportLinks?.json" :href="appUrl(workspaceReportLinks.json)">下载完整结果 JSON</a></div></template>
              </AnalysisResultView>
            </section>
            <section class="panel report-preparing-panel" v-if="workspaceRun?.result_json && builtinReportLoading.workspace && !workspaceBuiltinReport" aria-live="polite">
              <div class="report-preparing-animation" aria-hidden="true"><span></span><span></span><span></span></div>
              <div><p class="eyebrow">REPORT PREPARATION</p><h2>正在准备本地排序与三张规范表</h2><p>最新运行结果已经可以查看，本地证据完成后会立即显示，AI 文字总结随后在后台生成。</p></div>
            </section>
            <AIResultReportPanel id="workspace-ai-result-report" v-if="workspaceBuiltinReport || workspaceAIReport" :builtin-payload="workspaceBuiltinReport" :ai-payload="workspaceAIReport" :ai-loading="aiReportLoadingTarget === 'workspace'" :ai-ready="aiReady" :ai-error="aiReportErrors.workspace" :batch="workspaceRun?.result_json?.kind === 'batch'" @generate-ai="generateAIResultReport('workspace')" />
          </template>
        </div>
      </section>
    </template>

    <div class="modal-backdrop" v-if="factorOverflowPrompt.open" @click.self="closeFactorOverflowPrompt">
      <section class="modal-card factor-overflow-dialog" role="dialog" aria-modal="true" aria-labelledby="factor-overflow-title">
        <div class="modal-head"><div><span class="dialog-kicker">需要明确确认</span><h2 id="factor-overflow-title">已选择额外候选因素</h2></div><button class="icon-button" @click="closeFactorOverflowPrompt">×</button></div>
        <p v-if="factorOverflowPrompt.column"><strong>{{ factorOverflowPrompt.methodLabel }}</strong> 固定为 {{ factorOverflowPrompt.maximum }} 因素模型。继续加入“{{ factorOverflowPrompt.column }}”不会建立一个超阶模型，而会把 {{ factorOverflowPrompt.projectedCount }} 个因素作为候选池。</p>
        <p v-else><strong>{{ factorOverflowPrompt.methodLabel }}</strong> 已选择 {{ factorOverflowPrompt.projectedCount }} 个候选因素。当前方法每个模型固定使用 {{ factorOverflowPrompt.maximum }} 个因素，将按组合方式执行多个独立模型。</p>
        <div class="overflow-preview"><span>执行规则</span><strong>每次选择 {{ factorOverflowPrompt.maximum }} 个因素</strong><span>预计独立模型</span><strong>{{ factorOverflowPrompt.combinationCount }} 个</strong><span>跨模型校正</span><strong>{{ factorOverflowPrompt.correctionLabel }}（可在组合设置中修改）</strong></div>
        <div class="combination-list" v-if="factorOverflowPrompt.combinations.length"><strong>任务预览</strong><div><span v-for="(item,index) in factorOverflowPrompt.combinations" :key="item">{{ index + 1 }}. {{ item }}</span></div><small v-if="factorOverflowPrompt.combinationCount > factorOverflowPrompt.combinations.length">仅显示前 {{ factorOverflowPrompt.combinations.length }} 个，共 {{ factorOverflowPrompt.combinationCount }} 个任务。</small></div>
        <div class="combination-warning">这是重复的排列组合分析，会增加检验数量。系统默认不启用；只有点击下方确认后才会加入该因素并进入组合实验模式。</div>
        <div class="modal-actions"><button class="secondary" @click="closeFactorOverflowPrompt">{{ factorOverflowPrompt.column ? '取消，不加入' : '取消，不更改' }}</button><button class="primary" @click="confirmFactorOverflow">确认并启用组合实验</button></div>
      </section>
    </div>

    <PreflightDialog
      :open="preflightOpen"
      :report="preflightReport"
      :loading="preflightLoading"
      :prior-run-count="preflightPriorRunCount"
      :confirm-label="pendingAnalysisAction === 'workspace' ? '确认并运行计划' : '确认并开始分析'"
      @close="preflightOpen = false"
      @confirm="confirmPreflight"
      @locate="locatePreflightField"
    />

    <button v-if="!aiAssistantOpen" class="assistant-launcher" aria-label="打开 AI 小助手" @click="openHelp()"><span>AI</span> AI 小助手</button>
    <button v-show="showBackToTop" class="back-to-top" :class="{ shifted: aiAssistantOpen }" type="button" aria-label="回到页面顶部" title="回到顶部" @click="scrollToTop">↑</button>
    <AIAssistantPanel
      :open="aiAssistantOpen"
      :step="currentHelpStep"
      :context="aiContext"
      :result="assistantResult"
      :ai-report="assistantAIReport"
      :result-context-id="assistantResultContextId"
      :result-timestamp="assistantResultTimestamp"
      :ai-report-context-id="assistantAIReportContextId"
      :ai-ready="aiReady"
      @close="closeHelp"
      @settings="aiSettingsOpen = true"
      @authenticate="authenticateForAi"
    />
    <AISettingsPanel
      :open="aiSettingsOpen"
      @close="aiSettingsOpen = false"
      @updated="updateAiStatus"
    />
    <footer>DataWork · Local-first statistical workflow · AI 仅辅助解释</footer>
  </main>
</template>
