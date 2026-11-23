import { afterEach, describe, expect, it, vi } from "vitest"

// config.ts reads NEXT_PUBLIC_* once at import, so each case re-imports it.
async function loadConfig(env: Record<string, string | undefined>) {
  vi.resetModules()
  for (const [key, value] of Object.entries(env)) vi.stubEnv(key, value as string)
  return import("./config")
}

afterEach(() => {
  vi.unstubAllEnvs()
})

describe("config API adresleri", () => {
  it("tanimsizsa yerel API'ye gider", async () => {
    const { getApiUrl, getWsUrl } = await loadConfig({
      NEXT_PUBLIC_API_URL: undefined,
      NEXT_PUBLIC_WS_URL: undefined,
    })
    expect(getApiUrl("/api/v1/alerts")).toBe("http://127.0.0.1:8000/api/v1/alerts")
    expect(getWsUrl("/ws/alerts")).toBe("ws://127.0.0.1:8000/ws/alerts")
  })

  it("same-origin modunda goreli API ve sayfanin hostundan WebSocket kullanir", async () => {
    const { config, getApiUrl, getWsUrl } = await loadConfig({ NEXT_PUBLIC_API_URL: "same-origin" })
    expect(config.api.sameOrigin).toBe(true)
    expect(getApiUrl("/api/v1/alerts")).toBe("/api/v1/alerts")
    expect(getWsUrl("/ws/alerts", { protocol: "https:", host: "demo.tail1234.ts.net" })).toBe(
      "wss://demo.tail1234.ts.net/ws/alerts",
    )
    expect(getWsUrl("/ws/alerts", { protocol: "http:", host: "localhost:8088" })).toBe(
      "ws://localhost:8088/ws/alerts",
    )
  })
})
