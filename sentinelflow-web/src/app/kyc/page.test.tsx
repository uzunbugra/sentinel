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
import { clean, pepExact, sanctionsAlias } from "@/test/kyc-fixtures"
import KycPage from "./page"

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

beforeEach(() => {
  mocks.user = user("analyst")
  mockApi.mockReset()
})

function result() {
  return screen.getByRole("region", { name: "Tarama sonucu" })
}

describe("KycPage", () => {
  it("states that the lists are examples, not official lists", () => {
    render(<KycPage />)
    expect(screen.getByRole("note")).toHaveTextContent(/örnek listelere/)
    expect(screen.getByRole("note")).toHaveTextContent(/resmî listelere bağlı değildir/)
  })

  it("hides the form from a viewer but keeps the notice", () => {
    mocks.user = user("viewer")
    render(<KycPage />)
    expect(screen.queryByRole("button", { name: "Tara" })).not.toBeInTheDocument()
    expect(screen.getByRole("alert")).toHaveTextContent(/analist ve yönetici/)
  })

  it("shows a sanctions alias match with list, match type and score", async () => {
    mockApi.mockResolvedValueOnce(sanctionsAlias)
    render(<KycPage />)
    await userEvent.type(screen.getByLabelText("Ad soyad"), "Banned Person")
    await userEvent.click(screen.getByRole("button", { name: "Tara" }))

    expect(await within(result()).findByTestId("kyc-recommendation")).toHaveTextContent("İŞLEM YAPILAMAZ")
    const row = within(result()).getByRole("row", { name: /Yasak Kişi/ })
    expect(row).toHaveTextContent("takma ad: Banned Person")
    expect(row).toHaveTextContent("Tam")
    expect(row).toHaveTextContent("OFAC SDN (örnek)")
    expect(row).toHaveTextContent("100")
  })

  it("runs an example name in one click and shows a PEP match", async () => {
    mockApi.mockResolvedValueOnce(pepExact)
    render(<KycPage />)
    await userEvent.click(screen.getByRole("button", { name: "Ahmet Politikacı" }))
    expect(JSON.parse(mockApi.mock.calls[0][1]!.body as string)).toEqual({ name: "Ahmet Politikacı" })
    expect(await within(result()).findByText("PEP · Yurt içi, yüksek")).toBeInTheDocument()
    expect(within(result()).getByText("Eski Bakan")).toBeInTheDocument()
  })

  it("shows an empty state for a clean name", async () => {
    mockApi.mockResolvedValueOnce(clean)
    render(<KycPage />)
    await userEvent.click(screen.getByRole("button", { name: "Ayşe Temiz" }))
    expect(await within(result()).findByText(/eşleşme yok/)).toBeInTheDocument()
    expect(within(result()).getByTestId("kyc-recommendation")).toHaveTextContent("Tarama temiz")
  })

  it("validates the name before calling the API", async () => {
    render(<KycPage />)
    await userEvent.type(screen.getByLabelText("Ad soyad"), "A")
    await userEvent.click(screen.getByRole("button", { name: "Tara" }))
    expect(mockApi).not.toHaveBeenCalled()
    expect(screen.getByRole("alert")).toHaveTextContent(/en az 2/)
  })

  it("shows a readable message on 403", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(403, "Forbidden"))
    render(<KycPage />)
    await userEvent.click(screen.getByRole("button", { name: "Ayşe Temiz" }))
    expect(await screen.findByText("Bu işlem için yetkiniz yok.")).toBeInTheDocument()
  })
})
