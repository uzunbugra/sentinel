// =============================================================================
// SentinelFlow Authentication Library
// =============================================================================
// Token storage, login/refresh and the shared client for protected API calls.
// Every protected REST request must go through `fetchWithAuth` or `apiRequest`.

import { config, getApiUrl } from "./config"

export type UserRole = "admin" | "analyst" | "viewer"

export interface User {
  user_id: string
  username: string
  email: string
  full_name: string
  role: UserRole
  is_active: boolean
  created_at: string
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

const TOKEN_KEY = "sentinelflow_token"
const REFRESH_TOKEN_KEY = "sentinelflow_refresh_token"
const USER_KEY = "sentinelflow_user"

export function getToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem(TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function setTokens(tokens: AuthTokens): void {
  localStorage.setItem(TOKEN_KEY, tokens.access_token)
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
}

export function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function getStoredUser(): User | null {
  if (typeof window === "undefined") return null
  const userJson = localStorage.getItem(USER_KEY)
  if (!userJson) return null
  try {
    return JSON.parse(userJson)
  } catch {
    return null
  }
}

export function setStoredUser(user: User): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

// -----------------------------------------------------------------------------
// Roles
// -----------------------------------------------------------------------------

export function hasRole(user: User | null, ...roles: UserRole[]): boolean {
  return !!user && roles.includes(user.role)
}

/** Analyst and Admin may mutate alerts/cases; Viewer is read-only. */
export function canWrite(user: User | null): boolean {
  return hasRole(user, "analyst", "admin")
}

// -----------------------------------------------------------------------------
// Errors
// -----------------------------------------------------------------------------

export type ApiErrorKind =
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "validation"
  | "server"
  | "network"

export class ApiError extends Error {
  readonly status: number
  readonly kind: ApiErrorKind
  readonly detail: unknown

  constructor(status: number, message: string, detail: unknown = null) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.kind = errorKind(status)
    this.detail = detail
  }
}

function errorKind(status: number): ApiErrorKind {
  if (status === 0) return "network"
  if (status === 401) return "unauthorized"
  if (status === 403) return "forbidden"
  if (status === 404) return "not_found"
  if (status === 409) return "conflict"
  if (status === 400 || status === 422) return "validation"
  return "server"
}

async function errorFromResponse(res: Response): Promise<ApiError> {
  const body = await res.json().catch(() => null)
  const detail = body && typeof body === "object" && "detail" in body ? body.detail : body
  const message = typeof detail === "string" ? detail : `Request failed (${res.status})`
  return new ApiError(res.status, message, detail)
}

// -----------------------------------------------------------------------------
// Session expiry
// -----------------------------------------------------------------------------

type SessionExpiredHandler = () => void
let sessionExpiredHandler: SessionExpiredHandler | null = null

/** AuthProvider registers how to leave an expired session (clear state, go to /login). */
export function setSessionExpiredHandler(handler: SessionExpiredHandler | null): void {
  sessionExpiredHandler = handler
}

function expireSession(): void {
  clearTokens()
  if (sessionExpiredHandler) {
    sessionExpiredHandler()
  } else if (typeof window !== "undefined") {
    window.location.assign("/login")
  }
}

// -----------------------------------------------------------------------------
// Login / refresh
// -----------------------------------------------------------------------------

export async function login(username: string, password: string): Promise<User> {
  const res = await fetch(getApiUrl(config.endpoints.login), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username,
      password,
    }),
  })

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Login failed" }))
    throw new Error(error.detail || "Login failed")
  }

  const tokens: AuthTokens = await res.json()
  setTokens(tokens)

  const user = await fetchCurrentUser()
  return user
}

export async function register(
  username: string,
  email: string,
  password: string,
  fullName: string
): Promise<User> {
  const res = await fetch(getApiUrl(config.endpoints.register), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username,
      email,
      password,
      full_name: fullName,
    }),
  })

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Registration failed" }))
    throw new Error(error.detail || "Registration failed")
  }

  return await login(username, password)
}

export async function fetchCurrentUser(): Promise<User> {
  if (!getToken()) {
    throw new Error("No token available")
  }

  const user = await apiRequest<User>(config.endpoints.me)
  setStoredUser(user)
  return user
}

// Refresh tokens are single-use (the backend rotates them), so concurrent 401s
// must share one refresh request instead of racing with the same token.
let refreshInFlight: Promise<AuthTokens | null> | null = null

/**
 * Exchange the refresh token for a new token pair.
 * Resolves to null (and clears tokens) when the backend rejects the refresh
 * token; throws ApiError("network") when the backend cannot be reached, so a
 * network blip does not log the user out.
 */
export function refreshTokens(): Promise<AuthTokens | null> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

async function doRefresh(): Promise<AuthTokens | null> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    return null
  }

  let res: Response
  try {
    res = await fetch(getApiUrl(config.endpoints.refresh), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
  } catch {
    throw new ApiError(0, "Network error")
  }

  if (!res.ok) {
    clearTokens()
    return null
  }

  const tokens: AuthTokens = await res.json()
  setTokens(tokens)
  return tokens
}

export async function logout(): Promise<void> {
  clearTokens()
}

export function getAuthHeader(): Record<string, string> {
  const token = getToken()
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

// -----------------------------------------------------------------------------
// Protected requests
// -----------------------------------------------------------------------------

async function send(endpoint: string, options: RequestInit, token: string | null) {
  const headers = new Headers(options.headers)
  if (token) headers.set("Authorization", `Bearer ${token}`)
  try {
    return await fetch(getApiUrl(endpoint), { ...options, headers })
  } catch {
    throw new ApiError(0, "Network error")
  }
}

/**
 * Fetch a protected endpoint. On 401 the token pair is refreshed once and the
 * request retried; a second 401 (or a rejected refresh) ends the session.
 * Returns the raw Response for every other status. Throws ApiError("network")
 * when the backend is unreachable and ApiError("unauthorized") when the
 * session has ended.
 */
export async function fetchWithAuth(
  endpoint: string,
  options: RequestInit = {}
): Promise<Response> {
  const sentToken = getToken()
  const res = await send(endpoint, options, sentToken)
  if (res.status !== 401) return res

  // Another request may already have rotated the tokens while this one was in
  // flight; retry with the newer token before spending the refresh token.
  const current = getToken()
  const retryToken =
    current && current !== sentToken ? current : (await refreshTokens())?.access_token

  if (retryToken) {
    const retried = await send(endpoint, options, retryToken)
    if (retried.status !== 401) return retried
  }

  expireSession()
  throw new ApiError(401, "Session expired")
}

/**
 * Protected JSON request. Resolves to the parsed body (undefined for 204) and
 * throws ApiError for any non-2xx status.
 */
export async function apiRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (typeof options.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }

  const res = await fetchWithAuth(endpoint, { ...options, headers })
  if (!res.ok) throw await errorFromResponse(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}
