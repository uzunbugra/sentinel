import { beforeEach, describe, expect, it, vi } from "vitest"
import userEvent from "@testing-library/user-event"
import { render, screen, waitFor } from "@testing-library/react"
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
vi.mock("@/components/layout/header", () => ({
  Header: () => <header data-testid="mock-header" />,
}))

import { apiRequest, ApiError } from "@/lib/auth"
import { config } from "@/lib/config"
import AlertsPage from "./page"

const mockApi = vi.mocked(apiRequest)

// -----------------------------------------------------------------------------
// Fixtures
// -----------------------------------------------------------------------------

const analyst: User = {
  user_id: "u1",
  username: "analyst",
  email: "a@x.com",
  full_name: "A",
  role: "analyst",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
}

const viewer: User = { ...analyst, user_id: "u2", username: "viewer", role: "viewer" }

const sampleAlert = {
  alert_id: "alert-1",
  fraud_type: "mule_account",
  severity: "high",
  confidence: 0.87,
  transaction_id: "tx-1",
  sender_iban: "TR111111111111111111111111",
  sender_name: "Ali Yılmaz",
  sender_city: "İstanbul",
  receiver_iban: "TR222222222222222222222222",
  receiver_name: "Ayşe Demir",
  receiver_city: "Ankara",
  amount: 15500,
  currency: "TRY",
  title: "Şüpheli transfer",
  description: "Şüpheli mule hesap aktivitesi tespit edildi.",
  detected_at: "2026-01-15T10:30:00Z",
  is_dismissed: false,
  case_id: null,
}

const listResponse = {
  total: 1,
  page: 1,
  page_size: 20,
  alerts: [sampleAlert],
}

const emptyResponse = {
  total: 0,
  page: 1,
  page_size: 20,
  alerts: [],
}

// -----------------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------------

beforeEach(() => {
  mocks.user = null
  mockApi.mockReset()
})

describe("Alarmlar sayfası", () => {
  it("alarm listesini yükler ve toplam sayısını gösterir", async () => {
    mockApi.mockResolvedValue(listResponse)
    render(<AlertsPage />)

    expect(await screen.findByText("Ali Yılmaz → Ayşe Demir")).toBeInTheDocument()
    expect(screen.getByText("1 toplam")).toBeInTheDocument()
    expect(mockApi).toHaveBeenCalledWith(
      expect.stringContaining(config.endpoints.alerts)
    )
  })

  it("hata durumunda mesaj gösterir ve tekrar deneme listeyi yükler", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(0, "Network error"))
    render(<AlertsPage />)

    const alertBox = await screen.findByRole("alert")
    expect(alertBox).toHaveTextContent("Sunucuya ulaşılamıyor. Bağlantınızı kontrol edin.")

    mockApi.mockResolvedValue(listResponse)
    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "Tekrar dene" }))

    expect(await screen.findByText("Ali Yılmaz → Ayşe Demir")).toBeInTheDocument()
  })

  it("boş liste durumunda mesaj gösterir", async () => {
    mockApi.mockResolvedValue(emptyResponse)
    render(<AlertsPage />)

    expect(await screen.findByText("Alarm bulunamadı")).toBeInTheDocument()
  })

  it("viewer için yazma butonlarını göstermez", async () => {
    mocks.user = viewer
    mockApi.mockResolvedValue(listResponse)
    render(<AlertsPage />)

    const row = await screen.findByText("Ali Yılmaz → Ayşe Demir")
    const user = userEvent.setup()
    await user.click(row)

    expect(await screen.findByText("Alarm Detayı")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Reddet (False Positive)" })).toBeNull()
    expect(screen.queryByRole("button", { name: "Vaka Oluştur" })).toBeNull()
  })

  it("analyst alarmı reddettiğinde satır güncellenir", async () => {
    mocks.user = analyst
    mockApi.mockResolvedValue(listResponse)
    render(<AlertsPage />)

    const row = await screen.findByText("Ali Yılmaz → Ayşe Demir")
    const user = userEvent.setup()
    await user.click(row)

    const dismissButton = await screen.findByRole("button", {
      name: "Reddet (False Positive)",
    })
    await user.click(dismissButton)

    await waitFor(() => {
      expect(mockApi).toHaveBeenLastCalledWith(
        config.endpoints.alertDismiss("alert-1"),
        { method: "POST" }
      )
    })
    expect(await screen.findByText("(Dismissed)")).toBeInTheDocument()
  })
})
