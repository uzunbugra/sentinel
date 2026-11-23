import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { apiRequest } from "@/lib/auth"
import { fraudTypeLabel } from "@/lib/fraud-types"
import { CaseAlerts } from "./case-alerts"

vi.mock("@/lib/auth", async (original) => ({ ...(await original()), apiRequest: vi.fn() }))
const mockApi = vi.mocked(apiRequest)
beforeEach(() => {
  mockApi.mockReset()
})

describe("Vaka bağlı alarmlar", () => {
  it("backend başlığı yerine Türkçe alarm tipini gösterir", async () => {
    mockApi.mockResolvedValue({
      alert_id: "ALERT-001",
      fraud_type: "circular_ring",
      title: "Circular Ring Detected",
      severity: "critical",
      amount: 25000,
      currency: "TRY",
    })
    render(<CaseAlerts alertIds={["ALERT-001"]} />)

    expect(await screen.findByText("Döngüsel Transfer")).toBeInTheDocument()
    expect(screen.queryByText("Circular Ring Detected")).not.toBeInTheDocument()
    expect(mockApi).toHaveBeenCalledWith("/api/v1/alerts/ALERT-001")
  })
})

describe("fraudTypeLabel", () => {
  it("bilinmeyen tipi olduğu gibi, boş tipi açıklamayla döndürür", () => {
    expect(fraudTypeLabel("ml_model")).toBe("ML Model")
    expect(fraudTypeLabel("new_engine")).toBe("new_engine")
    expect(fraudTypeLabel(undefined)).toBe("Bilinmeyen tip")
  })
})
