export type ApiError = {
  status: number
  message: string
  details?: unknown
}

export class HttpError extends Error {
  status: number
  details?: unknown

  constructor(status: number, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.details = details
  }
}

function getApiBaseUrl() {
  const w = window as unknown as { __ENV__?: Record<string, string> }
  const fromEnvJs = w.__ENV__?.VITE_API_BASE_URL
  const fromVite = (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_BASE_URL
  return fromEnvJs || fromVite || ''
}

const ACCESS_KEY = 'kb.auth.access_token'
const REFRESH_KEY = 'kb.auth.refresh_token'

function readToken(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeToken(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    // ignore — приватные режимы могут блокировать localStorage
  }
}

async function parseBody(res: Response) {
  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('application/json')) return (await res.json()) as unknown
  return await res.text()
}

function withAuthHeaders(init: RequestInit | undefined, token: string | null): RequestInit {
  if (!token) return init || {}
  const headers = new Headers(init?.headers || {})
  if (!headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`)
  return { ...(init || {}), headers }
}

let refreshInflight: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  if (refreshInflight) return refreshInflight
  const refresh = readToken(REFRESH_KEY)
  if (!refresh) return null
  refreshInflight = (async () => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      })
      if (!res.ok) {
        writeToken(ACCESS_KEY, null)
        writeToken(REFRESH_KEY, null)
        return null
      }
      const data = (await res.json()) as { access_token?: string; refresh_token?: string }
      if (data.access_token) writeToken(ACCESS_KEY, data.access_token)
      if (data.refresh_token) writeToken(REFRESH_KEY, data.refresh_token)
      return data.access_token ?? null
    } catch {
      writeToken(ACCESS_KEY, null)
      writeToken(REFRESH_KEY, null)
      return null
    } finally {
      refreshInflight = null
    }
  })()
  return refreshInflight
}

const NO_AUTH_PATHS = ['/v1/auth/login', '/v1/auth/register', '/v1/auth/refresh']

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getApiBaseUrl()}${path}`
  const skipAuth = NO_AUTH_PATHS.some((p) => path.startsWith(p))

  let accessToken = skipAuth ? null : readToken(ACCESS_KEY)
  let response = await fetch(url, withAuthHeaders(init, accessToken))

  // Если access token истёк — пробуем рефреш и повторяем запрос ровно один раз.
  if (response.status === 401 && !skipAuth && accessToken) {
    const refreshed = await refreshAccessToken()
    if (refreshed) {
      accessToken = refreshed
      response = await fetch(url, withAuthHeaders(init, accessToken))
    }
  }

  if (!response.ok) {
    const body = await parseBody(response)
    const message = typeof body === 'string' ? body : JSON.stringify(body)
    throw new HttpError(response.status, message || `HTTP ${response.status}`, body)
  }
  return (await parseBody(response)) as T
}
