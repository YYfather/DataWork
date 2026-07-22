export type ApiIssue = {
  code?: string
  message: string
  severity?: 'info' | 'warning' | 'error'
  field?: string | null
  details?: Record<string, unknown>
}

export type FriendlyError = {
  title: string
  message: string
  code?: string
  hints: string[]
  issues: ApiIssue[]
}

const CODE_HINTS: Record<string, string[]> = {
  invalid_plan: ['检查统计方法与变量角色是否匹配。', '点击“分析前检查”中的“去补充”定位缺失项。'],
  invalid_dataset: ['检查文件是否为空、列类型是否正确，以及是否有足够有效观测。'],
  unsupported_file: ['请使用 CSV、TSV、XLSX，旧版 XLS 需要安装可选依赖。'],
  method_unavailable: ['请选择标记为“可执行”的统计方法。'],
  execution_failed: ['保留当前设置，按错误提示减少模型复杂度或检查数据结构后重试。'],
  resource_not_found: ['项目资源可能已被删除或移动，请刷新项目后重试。'],
  ai_config_error: ['重新测试 AI 连接并手动确认 Model ID。'],
  ai_unavailable: ['AI 不影响统计计算；可继续使用内置说明。'],
  ai_request_failed: ['检查网络、API 额度与 Model ID，统计结果不会受影响。'],
  ai_free_quota_exhausted: ['验证工作区密码后可继续使用服务器 AI。', '也可以在 AI 设置中填写自己的 API 密钥。', '匿名额度从首次提问起满 24 小时自动恢复。'],
  session_capacity_reached: ['最多允许 3 位用户同时使用。', '有用户退出或闲置满 10 分钟后可重新尝试。'],
  session_expired: ['当前会话已因 10 分钟未实际操作而退出。', '重新加入后仍会回到该浏览器原有的独立工作区。'],
  workspace_auth_required: ['项目工作区只对所有者开放。', '即时分析仍可正常使用。'],
  workspace_auth_failed: ['请检查密码大小写后重试。', '连续错误 5 次会锁定当前浏览器会话 5 分钟。'],
  workspace_auth_locked: ['等待提示时间后再试；其他浏览器会话不受影响。'],
}

const APPLICATION_BASE_URL = new URL(/* @vite-ignore */ '../', import.meta.url)
const ABSOLUTE_URL_PATTERN = /^[a-z][a-z\d+.-]*:/i
const SESSION_STORAGE_KEY = 'datawork.session.v1'
let memorySessionId = ''
let memoryClientId = ''

function createSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, character => {
    const random = Math.floor(Math.random() * 16)
    const value = character === 'x' ? random : (random & 0x3) | 0x8
    return value.toString(16)
  })
}

export function dataworkSessionId(): string {
  if (memorySessionId) return memorySessionId
  try {
    memorySessionId = localStorage.getItem(SESSION_STORAGE_KEY) || ''
  } catch { /* 无持久存储时退回当前页面内存 */ }
  if (!memorySessionId) {
    memorySessionId = createSessionId()
    try { localStorage.setItem(SESSION_STORAGE_KEY, memorySessionId) } catch { /* ignore */ }
  }
  return memorySessionId
}

export function dataworkClientId(): string {
  if (!memoryClientId) memoryClientId = createSessionId()
  return memoryClientId
}

export function resetDataworkSession(): void {
  memorySessionId = ''
  try { localStorage.removeItem(SESSION_STORAGE_KEY) } catch { /* ignore */ }
}

export function releaseDataworkSession(): void {
  const payload = JSON.stringify({
    session_id: dataworkSessionId(),
    client_id: dataworkClientId(),
  })
  const body = new Blob([payload], { type: 'application/json' })
  if (typeof navigator !== 'undefined' && navigator.sendBeacon(appUrl('/api/session/release'), body)) return
  void fetch(appUrl('/api/session/release'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: payload,
    keepalive: true,
  }).catch(() => undefined)
}

export function appUrl(url: string): string {
  if (ABSOLUTE_URL_PATTERN.test(url) || url.startsWith('//') || url.startsWith('#')) return url
  const relativeUrl = url.startsWith('/') ? url.slice(1) : url
  return new URL(relativeUrl, APPLICATION_BASE_URL).toString()
}

function issueFromUnknown(value: any): ApiIssue | null {
  if (!value) return null
  if (typeof value === 'string') return { message: value }
  if (typeof value === 'object') {
    const location = Array.isArray(value.loc) ? value.loc.join('.') : undefined
    return {
      code: value.code ?? value.type,
      message: String(value.message ?? value.msg ?? value.detail ?? JSON.stringify(value)),
      severity: value.severity,
      field: value.field ?? location ?? null,
      details: value.details ?? {},
    }
  }
  return { message: String(value) }
}

export function friendlyError(payload: any, fallback = '请求失败'): FriendlyError {
  const error = payload?.error ?? payload
  const code = typeof error?.code === 'string' ? error.code : undefined
  let message = ''
  if (typeof payload?.detail === 'string') message = payload.detail
  else if (typeof error?.message === 'string') message = error.message
  else if (typeof payload?.message === 'string') message = payload.message

  const rawIssues = Array.isArray(error?.issues)
    ? error.issues
    : Array.isArray(payload?.detail)
      ? payload.detail
      : []
  const issues = rawIssues.map(issueFromUnknown).filter(Boolean) as ApiIssue[]
  if (!message && issues.length) message = issues.map(item => item.message).join('；')
  if (!message) message = fallback

  const hints = [...(code ? CODE_HINTS[code] ?? [] : [])]
  if (issues.some(item => item.field)) hints.push('错误项已保留在分析计划中，可返回对应字段修正。')
  return {
    title: code === 'invalid_plan'
      ? '分析计划需要修改'
      : code === 'session_capacity_reached'
        ? '当前使用人数已满'
        : code === 'session_expired'
          ? '会话已自动退出'
          : code === 'workspace_auth_required'
            ? '工作区需要认证'
            : code === 'workspace_auth_failed'
              ? '工作区密码不正确'
              : code === 'workspace_auth_locked'
                ? '工作区登录暂时锁定'
              : code === 'ai_free_quota_exhausted'
                ? '免费 AI 提问次数已用完'
          : '操作未完成',
    message,
    code,
    hints: Array.from(new Set(hints)),
    issues,
  }
}

export async function readPayload(response: Response): Promise<any> {
  const text = await response.text()
  if (!text) return null
  try { return JSON.parse(text) } catch { return { detail: text } }
}

export async function apiRequest(url: string, options?: RequestInit, fallback = '请求失败'): Promise<any> {
  let response: Response
  try {
    const headers = new Headers(options?.headers)
    headers.set('X-DataWork-Session', dataworkSessionId())
    headers.set('X-DataWork-Client', dataworkClientId())
    response = await fetch(appUrl(url), { ...options, headers })
  } catch (cause) {
    throw friendlyError({ detail: cause instanceof Error ? cause.message : String(cause) }, '无法连接本地服务')
  }
  const payload = await readPayload(response)
  if (!response.ok) {
    const problem = friendlyError(payload, fallback)
    if (problem.code === 'session_capacity_reached' || problem.code === 'session_expired') {
      window.dispatchEvent(new CustomEvent('datawork-session-error', { detail: problem }))
    }
    if (problem.code === 'workspace_auth_required') {
      window.dispatchEvent(new CustomEvent('datawork-workspace-auth-required', { detail: problem }))
    }
    throw problem
  }
  return payload
}

export function errorMessage(cause: unknown): string {
  if (cause && typeof cause === 'object' && 'message' in cause) return String((cause as any).message)
  return cause instanceof Error ? cause.message : String(cause)
}
