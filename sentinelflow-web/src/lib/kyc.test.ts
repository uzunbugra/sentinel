import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("./auth", async (orig) => ({ ...(await orig()), apiRequest: vi.fn() }))

import { apiRequest } from "./auth"
import { config } from "./config"
import { label, MATCH_TYPE_LABELS, matchSource, riskBand, screenCustomer, validateKycName } from "./kyc"
import { clean, pepExact, sanctionsAlias } from "@/test/kyc-fixtures"

const mockApi = vi.mocked(apiRequest)
beforeEach(() => mockApi.mockReset())

describe("labels", () => {
  it("names every match type the backend sends and keeps unknown values", () => {
    expect(["TAM_ESLESME", "KISMI_ESLESME", "BULANIK_ESLESME", "TAKMA_AD"].map((t) => label(MATCH_TYPE_LABELS, t))).toEqual([
      "Tam",
      "Kısmi",
      "Bulanık",
      "Takma ad",
    ])
    expect(label(MATCH_TYPE_LABELS, "YENI")).toBe("YENI")
    expect(label(MATCH_TYPE_LABELS, undefined)).toBe("—")
  })

  it("marks the list as an example list", () => {
    expect(matchSource(sanctionsAlias.matches[0])).toBe("OFAC SDN (örnek)")
    expect(matchSource(pepExact.matches[0])).toBe("PEP · Yurt içi, yüksek")
  })
})

describe("riskBand", () => {
  it("is high for sanctions, medium for PEP, clean without matches", () => {
    expect(riskBand(sanctionsAlias)).toBe("high")
    expect(riskBand(pepExact)).toBe("medium")
    expect(riskBand(clean)).toBe("clean")
  })
})

describe("validateKycName", () => {
  it("mirrors the 2–200 character rule", () => {
    expect(validateKycName(" A ")).toMatch(/en az 2/)
    expect(validateKycName("x".repeat(201))).toMatch(/en fazla 200/)
    expect(validateKycName("Ayşe Temiz")).toBeNull()
  })
})

describe("screenCustomer", () => {
  it("sends the trimmed name and omits an empty country", async () => {
    mockApi.mockResolvedValueOnce(clean)
    await screenCustomer("  Ayşe Temiz ", " ")
    expect(mockApi).toHaveBeenCalledWith(config.endpoints.kycScreen, {
      method: "POST",
      body: JSON.stringify({ name: "Ayşe Temiz" }),
    })
  })

  it("sends a country when given", async () => {
    mockApi.mockResolvedValueOnce(clean)
    await screenCustomer("Ayşe Temiz", "TR")
    expect(JSON.parse(mockApi.mock.calls[0][1]!.body as string)).toEqual({ name: "Ayşe Temiz", country: "TR" })
  })
})
