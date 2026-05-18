import { apiFetch, HttpError } from '../../../api'
import type { AuthUser } from '../types'
import { AuthError, type AuthErrorCode } from '../types'

const ACCESS_KEY = 'kb.auth.access_token'
const REFRESH_KEY = 'kb.auth.refresh_token'
const USER_KEY = 'kb.auth.user'

type RegisterInput = {
  name: string
  email: string
  password: string
  confirmPassword: string
}

type LoginInput = {
  email: string
  password: string
}

type ServerUser = {
  id: number | string
  email: string
  name?: string
  role?: string
  is_active?: boolean
  created_at?: string
}

type TokenBundle = {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  refresh_expires_in: number
  user?: ServerUser
}

const SERVER_ERROR_MAP: Record<string, AuthErrorCode> = {
  invalid_credentials: 'invalid_credentials',
  email_taken: 'email_taken',
  weak_password: 'weak_password',
  invalid_email: 'invalid_email',
  invalid_name: 'invalid_name',
}

function mapHttpError(err: unknown, fallback: AuthErrorCode): AuthError {
  if (!(err instanceof HttpError)) {
    return new AuthError(fallback)
  }
  let code: string | undefined
  if (err.details && typeof err.details === 'object') {
    const detail = (err.details as { detail?: unknown }).detail
    if (typeof detail === 'string') code = detail
  }
  if (!code && err.message) {
    try {
      const parsed = JSON.parse(err.message)
      if (parsed && typeof parsed.detail === 'string') code = parsed.detail
    } catch {
      code = err.message
    }
  }
  if (code && code in SERVER_ERROR_MAP) {
    return new AuthError(SERVER_ERROR_MAP[code])
  }
  if (err.status === 401) return new AuthError('invalid_credentials')
  return new AuthError(fallback)
}

function toPublicUser(server: ServerUser | undefined | null): AuthUser | null {
  if (!server) return null
  return {
    id: String(server.id),
    name: server.name || server.email.split('@')[0],
    email: server.email,
    role: 'teacher',
    createdAt: server.created_at || new Date().toISOString(),
  }
}

function persistBundle(bundle: TokenBundle): AuthUser {
  localStorage.setItem(ACCESS_KEY, bundle.access_token)
  localStorage.setItem(REFRESH_KEY, bundle.refresh_token)
  const user = toPublicUser(bundle.user) ?? readUserCache()
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
  if (!user) throw new AuthError('invalid_credentials')
  return user
}

function readUserCache(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? (JSON.parse(raw) as AuthUser) : null
  } catch {
    return null
  }
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export function clearAuthStorage(): void {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_KEY)
}

export async function registerUser(input: RegisterInput): Promise<AuthUser> {
  if (input.password !== input.confirmPassword) {
    throw new AuthError('password_mismatch')
  }
  try {
    const bundle = await apiFetch<TokenBundle>('/v1/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: input.email.trim().toLowerCase(),
        password: input.password,
        name: input.name.trim(),
      }),
    })
    return persistBundle(bundle)
  } catch (err) {
    throw mapHttpError(err, 'weak_password')
  }
}

export async function loginUser(input: LoginInput): Promise<AuthUser> {
  try {
    const bundle = await apiFetch<TokenBundle>('/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: input.email.trim().toLowerCase(),
        password: input.password,
      }),
    })
    return persistBundle(bundle)
  } catch (err) {
    throw mapHttpError(err, 'invalid_credentials')
  }
}

export async function logoutUser(): Promise<void> {
  const access = getAccessToken()
  clearAuthStorage()
  if (!access) return
  try {
    await apiFetch('/v1/auth/logout', { method: 'POST' })
  } catch {
    // best-effort; токены уже стерты локально
  }
}

export async function refreshSession(): Promise<string | null> {
  const refresh = getRefreshToken()
  if (!refresh) return null
  try {
    const bundle = await apiFetch<TokenBundle>('/v1/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    })
    persistBundle(bundle)
    return bundle.access_token
  } catch {
    clearAuthStorage()
    return null
  }
}

export async function bootstrapCurrentUser(): Promise<AuthUser | null> {
  const access = getAccessToken()
  if (!access) return null
  try {
    const server = await apiFetch<ServerUser>('/v1/auth/me')
    const user = toPublicUser(server)
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
    return user
  } catch (err) {
    if (err instanceof HttpError && err.status === 401) {
      const refreshed = await refreshSession()
      if (!refreshed) return null
      try {
        const server = await apiFetch<ServerUser>('/v1/auth/me')
        const user = toPublicUser(server)
        if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
        return user
      } catch {
        clearAuthStorage()
        return null
      }
    }
    return readUserCache()
  }
}

export function getCurrentUserSync(): AuthUser | null {
  if (!getAccessToken()) return null
  return readUserCache()
}
