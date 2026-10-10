import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  ApiError,
  apiRequest,
  canWrite,
  fetchWithAuth,
  getRefreshToken,
  getToken,
  setSessionExpiredHandler,
  setTokens,
  type User,
} from "./auth"

const API = "http://127.0.0.1:8000"

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

function tokens(n: number) {
  return {
    access_token: `access-${n}`,
    refresh_token: `refresh-${n}`,
    token_type: "bearer",
    expires_in: 1800,
  }
}

/** Routes each fetch through `handler`, recording calls with their bearer token. */
function mockFetch(handler: (url: string, auth: string | null, init: RequestInit) => Response) {
  const calls: { url: string; auth: string | null }[] = []
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input).replace(API, "")
    const auth = new Headers(init.headers).get("Authorization")
    calls.push({ url, auth })
    return handler(url, auth, init)
  })
  vi.stubGlobal("fetch", fn)
  return calls
}

let expired: ReturnType<typeof vi.fn>

beforeEach(() => {
  localStorage.clear()
  setTokens(tokens(1))
  expired = vi.fn()
  setSessionExpiredHandler(expired)
})

afterEach(() => {
  setSessionExpiredHandler(null)
  vi.unstubAllGlobals()
})

describe("fetchWithAuth", () => {
  it("sends the stored access token", async () => {
    const calls = mockFetch(() => json(200, { ok: true }))

    const res = await fetchWithAuth("/api/v1/alerts")

    expect(res.status).toBe(200)
    expect(calls).toEqual([{ url: "/api/v1/alerts", auth: "Bearer access-1" }])
  })

  it("refreshes once on 401 and retries with the new token", async () => {
    const calls = mockFetch((url, auth) => {
      if (url === "/api/v1/auth/refresh") return json(200, tokens(2))
      return auth === "Bearer access-2" ? json(200, []) : json(401, { detail: "expired" })
    })

    const res = await fetchWithAuth("/api/v1/cases")

    expect(res.status).toBe(200)
    expect(calls.map((c) => c.url)).toEqual([
      "/api/v1/cases",
      "/api/v1/auth/refresh",
      "/api/v1/cases",
    ])
    expect(getToken()).toBe("access-2")
    expect(getRefreshToken()).toBe("refresh-2")
    expect(expired).not.toHaveBeenCalled()
  })

  it("shares one refresh between concurrent 401s", async () => {
    const calls = mockFetch((url, auth) => {
      if (url === "/api/v1/auth/refresh") return json(200, tokens(2))
      return auth === "Bearer access-2" ? json(200, []) : json(401, {})
    })

    const results = await Promise.all([
      fetchWithAuth("/api/v1/alerts"),
      fetchWithAuth("/api/v1/cases"),
      fetchWithAuth("/api/v1/system/stats"),
    ])

    expect(results.map((r) => r.status)).toEqual([200, 200, 200])
    expect(calls.filter((c) => c.url === "/api/v1/auth/refresh")).toHaveLength(1)
  })

  it("ends the session when the retried request is still 401", async () => {
    const calls = mockFetch((url) =>
      url === "/api/v1/auth/refresh" ? json(200, tokens(2)) : json(401, {})
    )

    await expect(fetchWithAuth("/api/v1/alerts")).rejects.toMatchObject({
      kind: "unauthorized",
    })

    expect(calls.filter((c) => c.url === "/api/v1/auth/refresh")).toHaveLength(1)
    expect(expired).toHaveBeenCalledTimes(1)
    expect(getToken()).toBeNull()
  })

  it("ends the session when the refresh token is rejected", async () => {
    mockFetch(() => json(401, {}))

    await expect(fetchWithAuth("/api/v1/alerts")).rejects.toBeInstanceOf(ApiError)

    expect(expired).toHaveBeenCalledTimes(1)
    expect(getToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
  })

  it("keeps the session on a network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")))

    await expect(fetchWithAuth("/api/v1/alerts")).rejects.toMatchObject({ kind: "network" })

    expect(expired).not.toHaveBeenCalled()
    expect(getToken()).toBe("access-1")
  })

  it("passes 403 through without refreshing", async () => {
    const calls = mockFetch(() => json(403, { detail: "Access denied" }))

    const res = await fetchWithAuth("/api/v1/alerts/1/dismiss", { method: "POST" })

    expect(res.status).toBe(403)
    expect(calls).toHaveLength(1)
    expect(expired).not.toHaveBeenCalled()
  })
})

describe("apiRequest", () => {
  it("returns parsed JSON and sets the JSON content type for string bodies", async () => {
    const fetchSpy = vi.fn<typeof fetch>(async () => json(201, { case_id: "c1" }))
    vi.stubGlobal("fetch", fetchSpy)

    const body = await apiRequest<{ case_id: string }>("/api/v1/cases", {
      method: "POST",
      body: JSON.stringify({ title: "x" }),
    })

    expect(body).toEqual({ case_id: "c1" })
    const init = fetchSpy.mock.calls[0][1] as RequestInit
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json")
  })

  it.each([
    [403, "forbidden"],
    [404, "not_found"],
    [409, "conflict"],
    [422, "validation"],
    [500, "server"],
  ] as const)("maps %i to ApiError kind %s with the backend detail", async (status, kind) => {
    mockFetch(() => json(status, { detail: "backend says no" }))

    const err = await apiRequest("/api/v1/cases").catch((e) => e)

    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status, kind, message: "backend says no" })
  })
})

describe("canWrite", () => {
  const user = (role: User["role"]) => ({ role }) as User

  it("allows analyst and admin, not viewer or anonymous", () => {
    expect(canWrite(user("analyst"))).toBe(true)
    expect(canWrite(user("admin"))).toBe(true)
    expect(canWrite(user("viewer"))).toBe(false)
    expect(canWrite(null)).toBe(false)
  })
})
