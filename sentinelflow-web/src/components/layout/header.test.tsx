import { describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Header } from "./header"

const mocks = vi.hoisted(() => ({ logout: vi.fn(), role: "analyst" }))
vi.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({
    user: { full_name: "Test Analisti", role: mocks.role },
    isAuthenticated: true,
    logout: mocks.logout,
  }),
}))

describe("Header erişilebilirliği", () => {
  it("ana gezinmeyi erişilebilir adıyla sunar ve kullanıcı adını gösterir", () => {
    render(<Header />)
    const nav = screen.getByRole("navigation", { name: "Ana gezinme" })
    expect(within(nav).getByRole("link", { name: "Vakalar" })).toHaveAttribute("href", "/cases")
    expect(within(nav).getByRole("link", { name: "Ağ grafiği" })).toHaveAttribute("href", "/graph")
    expect(screen.getByText("Test Analisti")).toBeInTheDocument()
  })

  it("skorlama ve tarama bağlantılarını analiste gösterir, viewer'a göstermez", () => {
    mocks.role = "analyst"
    const { unmount } = render(<Header />)
    const nav = screen.getByRole("navigation", { name: "Ana gezinme" })
    expect(within(nav).getByRole("link", { name: "Skorlama" })).toHaveAttribute("href", "/score")
    expect(within(nav).getByRole("link", { name: "Müşteri taraması" })).toHaveAttribute("href", "/kyc")
    unmount()

    mocks.role = "viewer"
    render(<Header />)
    expect(screen.queryByRole("link", { name: "Skorlama" })).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "Müşteri taraması" })).not.toBeInTheDocument()
    // The graph page is read-only: viewers see it too.
    expect(screen.getByRole("link", { name: "Ağ grafiği" })).toHaveAttribute("href", "/graph")
    mocks.role = "analyst"
  })

  it("adlandırılmış çıkış düğmesi oturumu kapatır", async () => {
    render(<Header />)
    await userEvent.click(screen.getByRole("button", { name: "Çıkış yap" }))
    expect(mocks.logout).toHaveBeenCalledOnce()
  })
})
