import { beforeEach, describe, expect, it, vi } from "vitest"
import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { apiRequest, ApiError } from "@/lib/auth"
import { sampleEvent, sampleEvents } from "@/test/case-fixtures"
import { CaseTimeline } from "./case-timeline"

vi.mock("@/lib/auth", async (original) => ({ ...(await original()), apiRequest: vi.fn() }))
const mockApi = vi.mocked(apiRequest)
beforeEach(() => {
  mockApi.mockReset()
})

describe("Vaka timeline", () => {
  it("yükleme durumunu gösterir", () => {
    mockApi.mockImplementation(() => new Promise(() => {}))
    render(<CaseTimeline caseId="CASE-001" revision={0} />)
    expect(screen.getByRole("status")).toHaveTextContent("İşlem geçmişi yükleniyor...")
  })

  it("sayfalar ve filtre değiştiğinde birinci sayfaya döner", async () => {
    mockApi.mockResolvedValue({ ...sampleEvents, total: 45 })
    render(<CaseTimeline caseId="CASE-001" revision={0} />)
    const user = userEvent.setup()
    await screen.findByText("İnceleme başlatıldı")
    expect(screen.getByRole("button", { name: "Önceki" })).toBeDisabled()
    await user.click(screen.getByRole("button", { name: "Sonraki" }))
    expect(mockApi).toHaveBeenLastCalledWith("/api/v1/cases/CASE-001/events?page=2&page_size=20")
    await screen.findByText("Sayfa 2 / 3")
    await user.selectOptions(screen.getByLabelText("Olay türü"), "note_added")
    expect(mockApi).toHaveBeenLastCalledWith(
      "/api/v1/cases/CASE-001/events?page=1&page_size=20&event_type=note_added",
    )
    expect(await screen.findByText("Sayfa 1 / 3")).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText("Olay türü"), "")
    expect(mockApi).toHaveBeenLastCalledWith("/api/v1/cases/CASE-001/events?page=1&page_size=20")
    expect(screen.getAllByRole("option")).toHaveLength(7)
  })

  it("boş olay listesinde boş durumunu gösterir", async () => {
    mockApi.mockResolvedValue({ ...sampleEvents, total: 0, events: [] })
    render(<CaseTimeline caseId="CASE-001" revision={0} />)
    expect(await screen.findByText("Henüz olay yok.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Sonraki" })).toBeDisabled()
  })

  it("olay yükleme hatası tekrar denenebilir", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(0, "Network error"))
    render(<CaseTimeline caseId="CASE-001" revision={0} />)
    expect(await screen.findByRole("alert")).toHaveTextContent("Sunucuya ulaşılamıyor.")
    mockApi.mockResolvedValueOnce(sampleEvents)
    await userEvent.click(screen.getByRole("button", { name: "Tekrar dene" }))
    expect(await screen.findByText("İnceleme başlatıldı")).toBeInTheDocument()
  })

  it("tanımadığı olay türünü ham adıyla gösterir", async () => {
    mockApi.mockResolvedValue({ ...sampleEvents, events: [
      { ...sampleEvent, event_type: "case_escalated" as never },
    ] })
    render(<CaseTimeline caseId="CASE-001" revision={0} />)
    expect(await screen.findByRole("heading", { name: "case_escalated" })).toBeInTheDocument()
  })

  it("sunucunun en yeni önce sırasını korur ve boş önceki değeri gösterir", async () => {
    mockApi.mockResolvedValue({ ...sampleEvents, events: [
      { ...sampleEvent, event_id: "EVT-2", description: "Son olay", previous_value: null },
      { ...sampleEvent, description: "İlk olay" },
    ] })
    render(<CaseTimeline caseId="CASE-001" revision={0} />)
    await screen.findByText("Son olay")
    const items = screen.getAllByRole("listitem")
    expect(items[0]).toHaveTextContent("Son olay")
    expect(items[0]).toHaveTextContent("— → investigating")
    expect(items[1]).toHaveTextContent("İlk olay")
  })

  it("eski filtre isteği yeni filtre sonucunu ezmez", async () => {
    let resolve!: (value: typeof sampleEvents) => void
    mockApi.mockReturnValueOnce(new Promise((done) => { resolve = done }))
    render(<CaseTimeline caseId="CASE-001" revision={0} />)
    mockApi.mockResolvedValueOnce({ ...sampleEvents, events: [] })
    await userEvent.selectOptions(screen.getByLabelText("Olay türü"), "note_added")
    await screen.findByText("Henüz olay yok.")
    await act(async () => { resolve(sampleEvents) })
    expect(screen.queryByText("İnceleme başlatıldı")).toBeNull()
    await waitFor(() => expect(screen.getByText("Henüz olay yok.")).toBeInTheDocument())
  })
})
