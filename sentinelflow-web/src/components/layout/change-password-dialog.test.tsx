import { beforeEach, describe, expect, it, vi } from "vitest"
import userEvent from "@testing-library/user-event"
import { render, screen } from "@testing-library/react"

const mocks = vi.hoisted(() => ({ logout: vi.fn() }))
vi.mock("@/lib/auth", async (orig) => ({ ...(await orig()), apiRequest: vi.fn() }))
vi.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({ user: { full_name: "Demo", role: "viewer" }, logout: mocks.logout }),
}))

import { apiRequest, ApiError } from "@/lib/auth"
import { ChangePasswordButton } from "./change-password-dialog"

const mockApi = vi.mocked(apiRequest)

beforeEach(() => {
  mockApi.mockReset()
  mocks.logout.mockReset()
})

async function openAndFill(current: string, next: string, confirm = next) {
  render(<ChangePasswordButton />)
  await userEvent.click(screen.getByRole("button", { name: "Parola değiştir" }))
  const dialog = screen.getByRole("dialog", { name: "Parola değiştir" })
  if (current) await userEvent.type(screen.getByLabelText("Mevcut parola"), current)
  if (next) await userEvent.type(screen.getByLabelText("Yeni parola"), next)
  if (confirm) await userEvent.type(screen.getByLabelText("Yeni parola (tekrar)"), confirm)
  return dialog
}

describe("ChangePasswordDialog", () => {
  it("renders outside the header so a blurred header cannot clip it", async () => {
    render(
      <header data-testid="header" className="backdrop-blur-sm">
        <ChangePasswordButton />
      </header>,
    )
    await userEvent.click(screen.getByRole("button", { name: "Parola değiştir" }))
    const dialog = screen.getByRole("dialog", { name: "Parola değiştir" })
    expect(screen.getByTestId("header")).not.toContainElement(dialog)
  })

  it("changes the password and asks the user to sign in again", async () => {
    mockApi.mockResolvedValueOnce({ message: "Password changed successfully" })
    await openAndFill("Eskisifre1", "Yenisifre1")
    await userEvent.click(screen.getByRole("button", { name: "Parolayı değiştir" }))

    expect(mockApi).toHaveBeenCalledOnce()
    expect(await screen.findByRole("status")).toHaveTextContent("Parolanız değişti")
    await userEvent.click(screen.getByRole("button", { name: "Tekrar giriş yap" }))
    expect(mocks.logout).toHaveBeenCalledOnce()
  })

  it("checks the rules and the confirmation before calling the API", async () => {
    await openAndFill("Eskisifre1", "Yenisifre1", "Baskasi12")
    await userEvent.click(screen.getByRole("button", { name: "Parolayı değiştir" }))
    expect(mockApi).not.toHaveBeenCalled()
    expect(screen.getByRole("alert")).toHaveTextContent("tekrarı aynı değil")
  })

  it("says the current password is wrong", async () => {
    mockApi.mockRejectedValueOnce(
      new ApiError(400, "Invalid current password", "Invalid current password"),
    )
    await openAndFill("Yanlis1234", "Yenisifre1")
    await userEvent.click(screen.getByRole("button", { name: "Parolayı değiştir" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Mevcut parola yanlış.")
  })

  it("falls back to the shared message for other errors", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(0, "Network"))
    await openAndFill("Eskisifre1", "Yenisifre1")
    await userEvent.click(screen.getByRole("button", { name: "Parolayı değiştir" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Sunucuya ulaşılamıyor")
  })

  it("closes with Escape and with Vazgeç", async () => {
    render(<ChangePasswordButton />)
    await userEvent.click(screen.getByRole("button", { name: "Parola değiştir" }))
    await userEvent.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: "Parola değiştir" }))
    await userEvent.click(screen.getByRole("button", { name: "Vazgeç" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })
})
