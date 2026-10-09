import { beforeEach, describe, expect, it, vi } from "vitest"
import userEvent from "@testing-library/user-event"
import { render, screen } from "@testing-library/react"
import type { User } from "@/lib/auth"

const mocks = vi.hoisted(() => ({
  user: null as User | null,
}))
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
import CasesPage from "./page"

const mockApi = vi.mocked(apiRequest)

const sampleUser: User = {
  user_id: "u1",
  username: "analyst",
  email: "a@x.com",
  full_name: "A",
  role: "analyst",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
}

const sampleCase = {
  case_id: "CASE-001",
  title: "Kara para aklama şüphesi",
  description: "Şüpheli işlem zinciri tespit edildi",
  status: "new",
  priority: "P1",
  primary_fraud_type: "money_laundering",
  alert_count: 3,
  total_amount: 150000,
  max_severity: "high",
  assigned_to: null,
  created_at: "2026-01-15T10:00:00Z",
  updated_at: "2026-01-15T10:00:00Z",
  sla_breached: false,
}

const casesResponse = {
  total: 1,
  page: 1,
  page_size: 20,
  cases: [sampleCase],
}

const statsResponse = {
  total: 12,
  open: 7,
  closed: 5,
}

function mockApiResolve() {
  mockApi.mockImplementation(async (endpoint: string) => {
    if (endpoint.includes("/stats")) return statsResponse
    return casesResponse
  })
}

beforeEach(() => {
  mocks.user = sampleUser
  mockApi.mockReset()
})

describe("CasesPage", () => {
  it("shows the loading state while the list is being fetched", () => {
    mockApi.mockImplementation(() => new Promise(() => {}))
    render(<CasesPage />)
    expect(screen.getByRole("status")).toHaveTextContent("Vakalar yükleniyor...")
  })

  it("renders the case list and the stats row when both calls resolve", async () => {
    mockApiResolve()
    render(<CasesPage />)

    // Case row
    expect(await screen.findByText("Kara para aklama şüphesi")).toBeInTheDocument()

    // Stats row
    const totalCard = screen.getByText("Toplam").closest("div")
    expect(totalCard).toHaveTextContent("12")
    const openCard = screen.getByText("Açık").closest("div")
    expect(openCard).toHaveTextContent("7")

    // Both endpoints were requested through the auth client
    const endpoints = mockApi.mock.calls.map((call) => call[0])
    expect(endpoints).toContain(`${config.endpoints.cases}?page=1&page_size=20`)
    expect(endpoints).toContain(`${config.endpoints.cases}/stats`)
  })

  it("shows the error state and recovers after retry", async () => {
    mockApi.mockImplementation(async (endpoint: string) => {
      if (endpoint.includes("/stats")) return statsResponse
      throw new ApiError(0, "Network error")
    })
    render(<CasesPage />)

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("Sunucuya ulaşılamıyor. Bağlantınızı kontrol edin.")

    mockApiResolve()
    await userEvent.click(screen.getByRole("button", { name: "Tekrar dene" }))

    expect(await screen.findByText("Kara para aklama şüphesi")).toBeInTheDocument()
  })

  it("shows the empty state when there are no cases", async () => {
    mockApi.mockImplementation(async (endpoint: string) => {
      if (endpoint.includes("/stats")) return statsResponse
      return { total: 0, page: 1, page_size: 20, cases: [] }
    })
    render(<CasesPage />)

    expect(await screen.findByText("Vaka bulunamadı")).toBeInTheDocument()
  })
})
