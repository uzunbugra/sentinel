import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("./auth", async (orig) => ({ ...(await orig()), apiRequest: vi.fn() }))

import { ApiError, apiRequest } from "./auth"
import { config } from "./config"
import { fetchAccountNetwork, fetchGraphOverview, ringAccounts, shortIban, validateIban } from "./graph"
import { mockGraph, realGraph, ring, RING_A } from "@/test/graph-fixtures"

const mockApi = vi.mocked(apiRequest)
beforeEach(() => mockApi.mockReset())

describe("fetchGraphOverview", () => {
  it("treats mock data as Neo4j unavailable and does not ask for rings", async () => {
    mockApi.mockResolvedValueOnce(mockGraph)
    expect(await fetchGraphOverview()).toEqual({ kind: "unavailable" })
    expect(mockApi).toHaveBeenCalledTimes(1)
    expect(mockApi.mock.calls[0][0]).toBe(`${config.endpoints.graphData}?limit=100&hours=24`)
  })

  it("returns real data with its rings", async () => {
    mockApi.mockResolvedValueOnce(realGraph).mockResolvedValueOnce([ring])
    expect(await fetchGraphOverview()).toEqual({ kind: "ok", data: realGraph, rings: [ring] })
    expect(mockApi.mock.calls[1][0]).toBe(config.endpoints.graphRings)
  })
})

describe("fetchAccountNetwork", () => {
  it("asks for a two-step neighbourhood", async () => {
    mockApi.mockResolvedValueOnce(realGraph)
    expect(await fetchAccountNetwork(` ${RING_A} `)).toEqual({ kind: "ok", data: realGraph })
    expect(mockApi.mock.calls[0][0]).toBe(`${config.endpoints.graphAccount(RING_A)}?depth=2`)
  })

  it("maps 404 and 503", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(404, "Account not found"))
    expect(await fetchAccountNetwork(RING_A)).toEqual({ kind: "not_found" })
    mockApi.mockRejectedValueOnce(new ApiError(503, "Graph database not available"))
    expect(await fetchAccountNetwork(RING_A)).toEqual({ kind: "unavailable" })
  })

  it("passes other errors on", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(403, "Forbidden"))
    await expect(fetchAccountNetwork(RING_A)).rejects.toBeInstanceOf(ApiError)
  })
})

describe("helpers", () => {
  it("lists each ring account once", () => {
    expect(ringAccounts(ring)).toHaveLength(3)
  })

  it("shortens long IBANs", () => {
    expect(shortIban(RING_A)).toBe("TR330006…1326")
    expect(shortIban("TR12")).toBe("TR12")
  })

  it("validates IBAN shape", () => {
    expect(validateIban(RING_A)).toBeNull()
    expect(validateIban("12345")).toMatch(/IBAN/)
  })
})
