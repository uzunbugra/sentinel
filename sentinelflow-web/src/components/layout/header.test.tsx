import { describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Header } from "./header"

const mocks = vi.hoisted(() => ({ logout: vi.fn() }))
vi.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({
    user: { full_name: "Test Analisti", role: "analyst" },
    isAuthenticated: true,
    logout: mocks.logout,
  }),
}))

describe("Header erişilebilirliği", () => {
  it("ana gezinmeyi erişilebilir adıyla sunar ve kullanıcı adını gösterir", () => {
    render(<Header />)
    const nav = screen.getByRole("navigation", { name: "Ana gezinme" })
    expect(within(nav).getByRole("link", { name: "Vakalar" })).toHaveAttribute("href", "/cases")
    expect(screen.getByText("Test Analisti")).toBeInTheDocument()
  })

  it("adlandırılmış çıkış düğmesi oturumu kapatır", async () => {
    render(<Header />)
    await userEvent.click(screen.getByRole("button", { name: "Çıkış yap" }))
    expect(mocks.logout).toHaveBeenCalledOnce()
  })
})
