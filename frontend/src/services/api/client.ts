import type { ApiResult } from '../../types'
import * as authModule from '../../stores/auth'

/**
 * Every backend in the workspace sits under `/api`; the next segment says
 * which one. nginx routes on that segment, so a module's calls reach its own
 * team's container without this app knowing anything about it.
 */
const API_BASE_URL = '/api'

/**
 * This app's own namespace — the report backend's `API_PREFIX`. Modules do not
 * use it: they pass their own namespace to `apiClient` (see
 * CONTRIBUTING_MODULES.md), which is the whole point of `apiClient` taking a
 * full path while `hostApi` prefixes one.
 *
 * Changing this means changing the backend's `API_PREFIX` and nginx's
 * `location` in the same commit.
 */
export const HOST_NAMESPACE = '/report/v1'

export const API_UNAUTHORIZED_EVENT = 'api:unauthorized'

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error)
}

function toMessage(value: unknown, fallback: string): string {
  if (typeof value === 'string' && value.trim()) return value
  if (Array.isArray(value)) {
    const messages = value
      .map((item) => (typeof item === 'object' && item && 'msg' in item ? String(item.msg) : ''))
      .filter(Boolean)
    if (messages.length) return messages.join('；')
  }
  return fallback
}

/** Matched by suffix: the login path now carries the host namespace in front of it. */
function isLoginPath(path: string) {
  return path.endsWith('/auth/login')
}

function notifyUnauthorized(path: string) {
  if (isLoginPath(path) || typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(API_UNAUTHORIZED_EVENT))
}

function resolveAuthToken(): string | null {
  try {
    const store = authModule.useAuthStore?.()
    if (!store) return null
    void store.ensureLoaded()
    return store.token ?? null
  } catch {
    return null
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<ApiResult<T>> {
  try {
    const headers: Record<string, string> = options.body instanceof FormData
      ? { ...(options.headers as Record<string, string> | undefined) ?? {} }
      : { 'Content-Type': 'application/json', ...(options.headers as Record<string, string> | undefined) ?? {} }
    const bearer = resolveAuthToken()
    if (bearer && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${bearer}`
    }
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      credentials: 'include',
      headers,
    })

    // 登录接口的 401 是「这次密码不对」，不是「会话过期」——那条通用文案会让
    // 用户以为要重新登录，而不是去改自己敲错的密码。所以放行给下面的常规解析，
    // 用后端给的原因。
    if (response.status === 401 && !isLoginPath(path)) {
      notifyUnauthorized(path)
      return {
        success: false,
        error: { code: 'SESSION_EXPIRED', message: '登录会话已过期，请重新登录。' },
      }
    }

    if (response.status === 403) {
      return {
        success: false,
        error: { code: 'PERMISSION_DENIED', message: '当前账号没有权限执行此操作。' },
      }
    }

    if (!response.ok) {
      const body = await response.json().catch(() => ({})) as Record<string, unknown>
      const fallback = `请求失败 (${response.status})`
      return {
        success: false,
        error: {
          code: typeof body.code === 'string' ? body.code : 'REQUEST_FAILED',
          message: toMessage(body.message ?? body.detail, fallback),
          details: typeof body.details === 'object' && body.details
            ? body.details as Record<string, unknown>
            : undefined,
        },
      }
    }

    if (response.status === 204) return { success: true, data: null as T }
    return { success: true, data: await response.json() as T }
  } catch (error) {
    return {
      success: false,
      error: { code: 'NETWORK_ERROR', message: `无法连接后端服务：${getErrorMessage(error)}` },
    }
  }
}

async function download(path: string): Promise<ApiResult<Blob>> {
  try {
    const headers: Record<string, string> = {}
    const bearer = resolveAuthToken()
    if (bearer) headers['Authorization'] = `Bearer ${bearer}`
    const response = await fetch(`${API_BASE_URL}${path}`, { credentials: 'include', headers })
    if (response.status === 401) {
      notifyUnauthorized(path)
      return { success: false, error: { code: 'SESSION_EXPIRED', message: '登录会话已过期，请重新登录。' } }
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({})) as Record<string, unknown>
      return {
        success: false,
        error: {
          code: typeof body.code === 'string' ? body.code : 'REQUEST_FAILED',
          message: toMessage(body.message ?? body.detail, `下载失败 (${response.status})`),
        },
      }
    }
    return { success: true, data: await response.blob() }
  } catch (error) {
    return {
      success: false,
      error: { code: 'NETWORK_ERROR', message: `无法连接后端服务：${getErrorMessage(error)}` },
    }
  }
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path, { method: 'GET' }),
  post: <T>(path: string, body?: unknown) => request<T>(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  }),
  put: <T>(path: string, body?: unknown) => request<T>(path, {
    method: 'PUT',
    body: body === undefined ? undefined : JSON.stringify(body),
  }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: <T>(path: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<T>(path, { method: 'POST', body: form })
  },
  uploadForm: <T>(path: string, form: FormData) => request<T>(path, { method: 'POST', body: form }),
  download,
}

/**
 * The same client, pinned to this app's own backend.
 *
 * Host code calls `hostApi.get('/conversations')`; a contributed module calls
 * `apiClient.get('/their-tool/v1/items')`. Keeping the two apart means the
 * host's namespace can move without touching a single module.
 */
export const hostApi = {
  get: <T>(path: string) => apiClient.get<T>(`${HOST_NAMESPACE}${path}`),
  post: <T>(path: string, body?: unknown) => apiClient.post<T>(`${HOST_NAMESPACE}${path}`, body),
  put: <T>(path: string, body?: unknown) => apiClient.put<T>(`${HOST_NAMESPACE}${path}`, body),
  delete: <T>(path: string) => apiClient.delete<T>(`${HOST_NAMESPACE}${path}`),
  upload: <T>(path: string, file: File) => apiClient.upload<T>(`${HOST_NAMESPACE}${path}`, file),
  uploadForm: <T>(path: string, form: FormData) =>
    apiClient.uploadForm<T>(`${HOST_NAMESPACE}${path}`, form),
  download: (path: string) => apiClient.download(`${HOST_NAMESPACE}${path}`),
}
