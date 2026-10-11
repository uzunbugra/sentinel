import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { apiRequest } from "@/lib/auth"
import { sampleCase } from "@/test/case-fixtures"
import { LinkCaseDialog } from "./link-case-dialog"

vi.mock("@/lib/auth", async (original) => ({ ...(await original()), apiRequest: vi.fn() }))
const mockApi = vi.mocked(apiRequest)
beforeEach(() => { mockApi.mockReset() })

async function openExisting() {
  render(<LinkCaseDialog
    alertId="ALT-1"
    suggestedTitle="İnceleme"
    onLinked={vi.fn()}
    onSuccess={vi.fn()}
    onClose={vi.fn()}
  />)
  const user = userEvent.setup()
  await user.click(screen.getByLabelText("Mevcut vakaya bağla"))
  await screen.findByLabelText("Vaka ara")
  return user
}

describe("Vaka seçimi araması", () => {
  it("kimlik ve başlıkta harf duyarsız arar, filtre dışı seçimi temizler", async () => {
    mockApi.mockResolvedValueOnce({ total: 2, cases: [
      { ...sampleCase, case_id: "CASE-ABC", title: "İnceleme" },
      { ...sampleCase, case_id: "CASE-XYZ", title: "Transfer zinciri" },
    ] })
    const user = await openExisting()
    await user.selectOptions(screen.getByLabelText("Açık vaka"), "CASE-ABC")
    expect(screen.getByRole("button", { name: "Alarmı bağla" })).toBeEnabled()
    await user.type(screen.getByLabelText("Vaka ara"), "case-xyz")
    const select = screen.getByLabelText("Açık vaka")
    expect(select).toHaveValue("")
    expect(within(select).queryByRole("option", { name: /CASE-ABC/ })).toBeNull()
    expect(within(select).getByRole("option", { name: /CASE-XYZ/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Alarmı bağla" })).toBeDisabled()
    await user.clear(screen.getByLabelText("Vaka ara"))
    await user.type(screen.getByLabelText("Vaka ara"), "İNCELEME")
    expect(screen.getByRole("option", { name: /CASE-ABC/ })).toBeInTheDocument()
    expect(screen.queryByRole("option", { name: /CASE-XYZ/ })).toBeNull()
  })

  it("eşleşme yokken mesaj gösterir ve gönderimi engeller", async () => {
    mockApi.mockResolvedValueOnce({ total: 1, cases: [sampleCase] })
    const user = await openExisting()
    await user.selectOptions(screen.getByLabelText("Açık vaka"), sampleCase.case_id)
    await user.type(screen.getByLabelText("Vaka ara"), "bulunmayan")
    expect(screen.getByText("Eşleşen vaka yok.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Alarmı bağla" })).toBeDisabled()
    await user.click(screen.getByRole("button", { name: "Alarmı bağla" }))
    expect(mockApi.mock.calls.some(([, options]) => options?.method === "POST")).toBe(false)
  })

  it("500 vaka sınırında açıklama gösterir", async () => {
    mockApi.mockImplementation(async (endpoint) => {
      const page = Number(new URLSearchParams(endpoint.split("?")[1]).get("page"))
      return { total: 501, cases: Array.from({ length: 100 }, (_, index) => ({
        ...sampleCase, case_id: `CASE-${page}-${index}`,
      })) }
    })
    await openExisting()
    expect(screen.getByText("İlk 500 açık vaka gösteriliyor.")).toBeInTheDocument()
    expect(mockApi).toHaveBeenCalledTimes(5)
  })
})
