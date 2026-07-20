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
    title: code === 'invalid_plan' ? '分析计划需要修改' : '操作未完成',
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
    response = await fetch(url, options)
  } catch (cause) {
    throw friendlyError({ detail: cause instanceof Error ? cause.message : String(cause) }, '无法连接本地服务')
  }
  const payload = await readPayload(response)
  if (!response.ok) throw friendlyError(payload, fallback)
  return payload
}

export function errorMessage(cause: unknown): string {
  if (cause && typeof cause === 'object' && 'message' in cause) return String((cause as any).message)
  return cause instanceof Error ? cause.message : String(cause)
}
