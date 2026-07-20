<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { apiRequest, errorMessage } from '../api'

type ProviderPreset = {
  kind: string
  label: string
  base_url: string
  model: string
  requires_key: boolean
  supports_discovery: boolean
  help: string
}

type ModelInfo = {
  id: string
  display_name: string
  owned_by: string
  description: string
  capabilities: string[]
  input_token_limit: number | null
  output_token_limit: number | null
  parameter_size: string
  quantization_level: string
  size_bytes: number | null
  created_at: number | string | null
  selectable: boolean
  source: string
}

type AIStatus = {
  enabled: boolean
  provider: string
  base_url: string
  model: string
  privacy_mode: string
  remember_key: boolean
  has_api_key: boolean
  keyring_available: boolean
  configured: boolean
  connection_ready: boolean
  selection_required: boolean
  requires_api_key: boolean
  allow_no_api_key: boolean
  timeout_seconds: number
  max_retries: number
  temperature: number
  max_tokens: number
}

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; updated: [status: AIStatus] }>()

const providers = ref<ProviderPreset[]>([])
const status = ref<AIStatus | null>(null)
const enabled = ref(false)
const provider = ref('deepseek')
const baseUrl = ref('')
const model = ref('')
const apiKey = ref('')
const privacyMode = ref('metadata_only')
const storage = ref('session')
const allowNoApiKey = ref(false)
const loading = ref(false)
const testing = ref(false)
const selecting = ref(false)
const message = ref('')
const error = ref('')
const initialized = ref(false)
const discoveredModels = ref<ModelInfo[]>([])
const selectedDiscoveredModel = ref('')
const discoveryCompleted = ref(false)
const manualMode = ref(false)

const selectedPreset = computed(() => providers.value.find((item) => item.kind === provider.value))
const canRemember = computed(() => Boolean(status.value?.keyring_available))
const selectableModels = computed(() => discoveredModels.value.filter((item) => item.selectable))

watch(provider, (next, previous) => {
  if (!initialized.value || next === previous) return
  const preset = providers.value.find((item) => item.kind === next)
  if (!preset) return
  baseUrl.value = preset.base_url
  model.value = ''
  selectedDiscoveredModel.value = ''
  discoveredModels.value = []
  discoveryCompleted.value = false
  manualMode.value = false
  allowNoApiKey.value = !preset.requires_key
  apiKey.value = ''
  message.value = '服务商已切换，请重新测试连接并选择 Model ID。'
})

watch(baseUrl, () => {
  if (!initialized.value) return
  discoveredModels.value = []
  selectedDiscoveredModel.value = ''
  discoveryCompleted.value = false
})

watch(() => props.open, async (open) => {
  if (open) await load()
})

onMounted(load)

async function load() {
  error.value = ''
  loading.value = true
  const results = await Promise.allSettled([
    apiRequest('/api/ai/providers', undefined, 'AI 服务商列表读取失败'),
    apiRequest('/api/ai/status', undefined, 'AI 状态读取失败'),
  ])
  if (results[0].status === 'fulfilled') providers.value = results[0].value
  if (results[1].status === 'fulfilled') applyStatus(results[1].value)
  if (results.some(item => item.status === 'rejected')) {
    const failed = results.find(item => item.status === 'rejected') as PromiseRejectedResult | undefined
    error.value = failed ? errorMessage(failed.reason) : '无法读取 AI 设置。'
  }
  initialized.value = true
  loading.value = false
}

function applyStatus(payload: AIStatus) {
  status.value = payload
  enabled.value = payload.enabled
  provider.value = payload.provider
  baseUrl.value = payload.base_url
  model.value = payload.model
  privacyMode.value = payload.privacy_mode
  storage.value = payload.remember_key && payload.keyring_available ? 'keyring' : 'session'
  allowNoApiKey.value = payload.allow_no_api_key
  apiKey.value = ''
}

function settingsPayload(modelOverride = model.value) {
  return {
    enabled: enabled.value,
    provider: provider.value,
    base_url: baseUrl.value,
    model: modelOverride,
    privacy_mode: privacyMode.value,
    remember_key: storage.value === 'keyring',
    secret_storage: storage.value,
    api_key: apiKey.value || null,
    timeout_seconds: status.value?.timeout_seconds ?? 120,
    max_retries: status.value?.max_retries ?? 2,
    temperature: status.value?.temperature ?? 0.3,
    max_tokens: status.value?.max_tokens ?? 2048,
    allow_no_api_key: allowNoApiKey.value,
  }
}

async function save(modelOverride = model.value, successText = 'AI 设置已保存。') {
  loading.value = true
  error.value = ''
  message.value = ''
  try {
    const payload = await apiRequest('/api/ai/settings', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settingsPayload(modelOverride)),
    }, 'AI 设置保存失败')
    applyStatus(payload.settings)
    message.value = payload.warning || successText
    emit('updated', payload.settings)
    return true
  } catch (cause) {
    error.value = errorMessage(cause)
    return false
  } finally {
    loading.value = false
  }
}

async function testConnection() {
  error.value = ''
  message.value = ''
  discoveredModels.value = []
  selectedDiscoveredModel.value = ''
  discoveryCompleted.value = false
  manualMode.value = false

  const saved = await save('', '连接参数已保存，正在读取模型列表。')
  if (!saved) return

  testing.value = true
  try {
    const payload = await apiRequest('/api/ai/test', { method: 'POST' }, '连接测试失败')
    discoveredModels.value = payload.models ?? []
    discoveryCompleted.value = true
    selectedDiscoveredModel.value = ''
    message.value = `${payload.message} 当前流程已暂停，请手动选择一个 Model ID。`
  } catch (cause) {
    error.value = errorMessage(cause)
    manualMode.value = provider.value === 'openai_compatible'
  } finally {
    testing.value = false
  }
}

async function confirmModel() {
  const chosen = manualMode.value ? model.value.trim() : selectedDiscoveredModel.value
  if (!chosen) {
    error.value = '请先选择或填写一个 Model ID。'
    return
  }
  selecting.value = true
  error.value = ''
  enabled.value = true
  try {
    const saved = await save(chosen, `已选择 Model ID：${chosen}`)
    if (saved) {
      model.value = chosen
      selectedDiscoveredModel.value = chosen
      discoveryCompleted.value = false
      discoveredModels.value = []
    }
  } finally {
    selecting.value = false
  }
}

async function clearKey() {
  if (loading.value || testing.value || selecting.value) return
  loading.value = true
  error.value = ''
  try {
    const payload = await apiRequest('/api/ai/key', { method: 'DELETE' }, 'API 密钥清除失败')
    applyStatus(payload.status)
    discoveredModels.value = []
    selectedDiscoveredModel.value = ''
    discoveryCompleted.value = false
    message.value = '已清除当前服务商的 API 密钥。'
    emit('updated', payload.status)
  } catch (cause) {
    error.value = errorMessage(cause)
  } finally { loading.value = false }
}

function formatTokens(value: number | null) {
  if (!value) return '—'
  return new Intl.NumberFormat('zh-CN').format(value)
}

function formatSize(value: number | null) {
  if (!value) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(index > 2 ? 1 : 0)} ${units[index]}`
}

function capabilityText(item: ModelInfo) {
  return item.capabilities?.length ? item.capabilities.join('、') : '接口未提供'
}
</script>

<template>
  <div v-if="open" class="modal-backdrop" @click.self="emit('close')">
    <section class="modal-card ai-settings-card" role="dialog" aria-modal="true" aria-label="AI 设置">
      <div class="modal-head">
        <div><p class="eyebrow">AI ASSISTANT</p><h2>AI 设置与模型发现</h2></div>
        <button class="icon-button" @click="emit('close')" aria-label="关闭">×</button>
      </div>

      <div v-if="loading || testing || selecting" class="assistant-loading settings-loading" role="status" aria-live="polite"><span class="inline-spinner"></span><div><strong>{{ testing ? '正在测试连接并拉取 Model ID' : selecting ? '正在保存所选模型' : '正在读取或保存 AI 设置' }}</strong><p>请等待当前操作完成，窗口会保持可关闭。</p></div></div>

      <div class="privacy-notice">
        <strong>先测试，再选择 Model ID</strong>
        <p>测试成功后程序会拉取当前接口和密钥可见的全部模型。不会自动选择第一个模型，也不会自动继续调用。</p>
      </div>

      <div class="settings-grid">
        <label class="toggle-field"><input v-model="enabled" type="checkbox" /><span>选择模型后启用 AI 辅助</span></label>
        <label class="field">服务商
          <select v-model="provider"><option v-for="item in providers" :key="item.kind" :value="item.kind">{{ item.label }}</option></select>
          <small>{{ selectedPreset?.help }}</small>
        </label>
        <label class="field span-2">API 地址
          <input v-model="baseUrl" type="url" spellcheck="false" placeholder="https://..." />
        </label>
        <label class="field">当前 Model ID
          <input :value="model || '尚未选择'" readonly class="readonly-input" />
          <small>Model ID 只能在探测完成后确认，兼容接口探测失败时可手动填写。</small>
        </label>
        <label class="field">API 密钥
          <input v-model="apiKey" type="password" autocomplete="new-password" :placeholder="status?.has_api_key ? '已保存；留空则保持不变' : selectedPreset?.requires_key ? '粘贴 API 密钥' : '可选'" />
          <small v-if="status?.has_api_key">当前已有密钥：••••••••</small>
        </label>
        <label class="field">密钥保存方式
          <select v-model="storage">
            <option value="session">仅本次运行</option>
            <option value="keyring" :disabled="!canRemember">保存到系统密钥库</option>
          </select>
          <small v-if="!canRemember">当前系统未检测到可用密钥库，将只支持会话保存。</small>
          <small v-else>Windows 凭据管理器、macOS 钥匙串或 Linux Secret Service。</small>
        </label>
        <label class="field">发送给 AI 的数据范围
          <select v-model="privacyMode">
            <option value="metadata_only">仅列信息、计划和统计结果（推荐）</option>
            <option value="include_preview">允许最多 5 行数据预览</option>
          </select>
        </label>
        <label v-if="provider === 'openai_compatible'" class="toggle-field span-2">
          <input v-model="allowNoApiKey" type="checkbox" /><span>该兼容接口不需要 API 密钥</span>
        </label>
      </div>

      <div class="settings-status" v-if="status">
        <span :class="status.configured ? 'status-pill ready' : 'status-pill'">{{ status.configured ? '已选择模型' : status.connection_ready ? '等待模型选择' : '等待连接配置' }}</span>
        <span>默认不会发送原始数据行</span>
      </div>

      <div v-if="discoveryCompleted" class="model-discovery">
        <div class="model-discovery-head">
          <div><strong>可用 Model ID</strong><small>共 {{ discoveredModels.length }} 个，其中 {{ selectableModels.length }} 个可用于当前生成接口</small></div>
          <span class="status-pill">等待手动选择</span>
        </div>
        <div class="table-wrap model-table-wrap">
          <table class="model-table">
            <thead><tr><th>选择</th><th>Model ID</th><th>名称 / 所有者</th><th>核心能力</th><th>上下文限制</th><th>本地参数</th></tr></thead>
            <tbody>
              <tr v-for="item in discoveredModels" :key="item.id" :class="{ unavailable: !item.selectable }">
                <td><input v-model="selectedDiscoveredModel" type="radio" name="model-id" :value="item.id" :disabled="!item.selectable" /></td>
                <td><code>{{ item.id }}</code><small v-if="!item.selectable">当前生成接口不可用</small></td>
                <td><strong>{{ item.display_name || item.id }}</strong><small>{{ item.owned_by || item.source }}</small></td>
                <td>{{ capabilityText(item) }}</td>
                <td><small>输入 {{ formatTokens(item.input_token_limit) }}</small><small>输出 {{ formatTokens(item.output_token_limit) }}</small></td>
                <td><small>{{ item.parameter_size || '—' }}</small><small>{{ item.quantization_level || formatSize(item.size_bytes) }}</small></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="selection-confirm">
          <span>已选择：<code>{{ selectedDiscoveredModel || '尚未选择' }}</code></span>
          <button class="primary" :disabled="!selectedDiscoveredModel || selecting" @click="confirmModel">{{ selecting ? '保存中…' : '确认所选 Model ID' }}</button>
        </div>
      </div>

      <div v-if="manualMode" class="manual-model-box">
        <strong>兼容接口未提供标准模型列表</strong>
        <p>可以核对服务文档后手动输入 Model ID；程序仍不会替你选择。</p>
        <div class="manual-model-row"><input v-model="model" placeholder="手动填写 Model ID" /><button class="primary" :disabled="!model.trim() || selecting" @click="confirmModel">确认并保存</button></div>
      </div>

      <div class="alert" v-if="error">{{ error }}</div>
      <div class="success-message" v-if="message">{{ message }}</div>

      <div class="modal-actions">
        <button class="secondary" v-if="status?.has_api_key" @click="clearKey">清除密钥</button>
        <span class="action-spacer"></span>
        <button class="secondary" :disabled="loading || testing" @click="save(model)">{{ loading ? '保存中…' : '仅保存参数' }}</button>
        <button class="primary" :disabled="loading || testing" @click="testConnection">{{ testing ? '正在探测模型…' : '测试连接并拉取 Model ID' }}</button>
      </div>
    </section>
  </div>
</template>
