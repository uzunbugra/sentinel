import { beforeEach, describe, expect, it, vi } from "vitest"
import userEvent from "@testing-library/user-event"
import { render, screen, within } from "@testing-library/react"
import type { User } from "@/lib/auth"

const mocks = vi.hoisted(() => ({ user: null as User | null }))
vi.mock("@/lib/auth", async (orig) => ({ ...(await orig()), apiRequest: vi.fn() }))
vi.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({
    user: mocks.user,
    isLoading: false,
    isAuthenticated: !!mocks.user,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}))
vi.mock("@/hooks/use-websocket", () => ({
  useWebSocket: () => ({ isConnected: false, alerts: [] }),
}))

import { apiRequest, ApiError } from "@/lib/auth"
import { config } from "@/lib/config"
import ScorePage from "./page"

const mockApi = vi.mocked(apiRequest)

const user = (role: User["role"]): User => ({
  user_id: "u1",
  username: role,
  email: `${role}@example.com`,
  full_name: `Demo ${role}`,
  role,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
})

const result = {
  transaction_id: "TXN-1",
  model_version: "fraud-lgbm-20261030-0e0c647",
  feature_set_version: "fs-1",
  score: 0.99867,
  threshold: 0.11301,
  is_fraud: true,
  contribution_unit: "log_odds",
  base_value: -3.2,
  top_features: [
    { feature: "log_amount", value: 10.13, contribution: 2.4 },
    { feature: "payment_type_code", value: 2, contribution: 1.1 },
  ],
  history_cold_start: true,
  latency_ms: 1.234,
}

beforeEach(() => {
  mocks.user = user("analyst")
  mockApi.mockReset()
})

describe("ScorePage", () => {
  it("says the tool does not change account history", () => {
    render(<ScorePage />)
    expect(screen.getByText(/hesap geçmişi\s+değişmez/)).toBeInTheDocument()
  })

  it("hides the form from a viewer", () => {
    mocks.user = user("viewer")
    render(<ScorePage />)
    expect(screen.queryByRole("button", { name: "Skorla" })).not.toBeInTheDocument()
    expect(screen.getByRole("alert")).toHaveTextContent(/analist ve yönetici/)
  })

  it("scores the transaction and shows score, threshold, decision and contributions", async () => {
    mockApi.mockResolvedValue(result)
    render(<ScorePage />)
    await userEvent.click(screen.getByRole("button", { name: "Skorla" }))

    expect(mockApi).toHaveBeenCalledOnce()
    const [endpoint, options] = mockApi.mock.calls[0]
    expect(endpoint).toBe(config.endpoints.predict)
    expect(JSON.parse(options!.body as string)).toMatchObject({
      sender_iban: "TR000000000000000000000001",
      amount: 25000,
    })

    const panel = screen.getByRole("region", { name: "Skor sonucu" })
    expect(await within(panel).findByTestId("score-decision")).toHaveTextContent("şüpheli")
    expect(within(panel).getByText("0.9987")).toBeInTheDocument()
    expect(within(panel).getByText("0.1130")).toBeInTheDocument()
    expect(within(panel).getByText("Skorlayan model")).toBeInTheDocument()
    expect(within(panel).getByText("fraud-lgbm-20261030-0e0c647")).toBeInTheDocument()
    expect(within(panel).getByText("Tutar (log)")).toBeInTheDocument()
  })

  it("validates the form before calling the API", async () => {
    render(<ScorePage />)
    const amount = screen.getByLabelText("Tutar")
    await userEvent.clear(amount)
    await userEvent.type(amount, "0")
    await userEvent.click(screen.getByRole("button", { name: "Skorla" }))
    expect(mockApi).not.toHaveBeenCalled()
    expect(screen.getByRole("alert")).toHaveTextContent(/Tutar/)
  })

  it("explains a 503 when no model is loaded", async () => {
    mockApi.mockRejectedValue(
      new ApiError(503, "Request failed (503)", {
        code: "model_not_loaded",
        message: "No valid fraud model is loaded",
        status: "not_loaded",
      }),
    )
    render(<ScorePage />)
    await userEvent.click(screen.getByRole("button", { name: "Skorla" }))
    expect(await screen.findByText(/Model yüklü değil/)).toBeInTheDocument()
  })

  it("shows a readable message when the API answers 403", async () => {
    mockApi.mockRejectedValue(new ApiError(403, "Forbidden"))
    render(<ScorePage />)
    await userEvent.click(screen.getByRole("button", { name: "Skorla" }))
    expect(await screen.findByText("Bu işlem için yetkiniz yok.")).toBeInTheDocument()
  })
})
