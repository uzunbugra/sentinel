import { beforeEach, describe, expect, it, vi } from "vitest"
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { UserRole } from "@/lib/auth"
import type { Case, CaseUpdateRequest } from "@/lib/cases"
import { sampleCase, sampleEvents } from "@/test/case-fixtures"

const mocks = vi.hoisted(() => ({ role: "analyst" as UserRole, id: "CASE-001" }))
vi.mock("@/lib/auth", async (original) => ({ ...(await original()), apiRequest: vi.fn() }))
vi.mock("next/navigation", () => ({ useParams: () => ({ case_id: mocks.id }) }))
vi.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({ user: { role: mocks.role } }),
}))
vi.mock("@/hooks/use-websocket", () => ({ useWebSocket: () => ({ isConnected: false }) }))
vi.mock("@/components/layout/header", () => ({ Header: () => <header /> }))

import { apiRequest, ApiError } from "@/lib/auth"
import CaseDetailPage from "./page"

const mockApi = vi.mocked(apiRequest)
let currentCase: Case
let patchError: ApiError | null
let failedAlert: string | null

beforeEach(() => {
  mocks.role = "analyst"
  mocks.id = "CASE-001"
  currentCase = { ...sampleCase }
  patchError = null
  failedAlert = null
  mockApi.mockReset()
  mockApi.mockImplementation(async (endpoint, options) => {
    if (options?.method === "PATCH") {
      if (patchError) throw patchError
      currentCase = { ...currentCase, ...JSON.parse(options.body as string) }
      return currentCase
    }
    if (endpoint.includes("/events?")) return sampleEvents
    if (endpoint.includes("/alerts/")) {
      const id = endpoint.split("/").pop()
      if (id === failedAlert) throw new ApiError(404, "Not found")
      return { alert_id: id, title: `Alarm ${id}`, severity: "high", amount: 2500, currency: "TRY" }
    }
    return currentCase
  })
})

async function openPage() {
  render(<CaseDetailPage />)
  await screen.findByRole("heading", { name: "Transfer incelemesi" })
  await screen.findByText("İnceleme başlatıldı")
  return userEvent.setup()
}

function eventCalls() {
  return mockApi.mock.calls.filter(([endpoint]) => endpoint.includes("/events?"))
}

describe("Vaka detayı", () => {
  it("yükleme durumunu gösterir", () => {
    mockApi.mockImplementation(() => new Promise(() => {}))
    render(<CaseDetailPage />)
    expect(screen.getByRole("status")).toHaveTextContent("Vaka yükleniyor...")
  })

  it("özeti, alarmları, timeline ve İstanbul saatini gösterir", async () => {
    await openPage()
    const summary = screen.getByRole("region", { name: "Transfer incelemesi" })
    expect(summary).toHaveTextContent("CASE-001")
    expect(summary).toHaveTextContent("150.000 TRY")
    expect(summary).toHaveTextContent("SLA İhlali")
    expect(summary).toHaveTextContent("16.10.2026 00:30")
    expect(summary).toHaveTextContent("13.10.2026 00:30")
    expect(await screen.findByText("Alarm ALT-1")).toBeInTheDocument()
    expect(screen.getByText("Alarm ALT-2")).toBeInTheDocument()
    const timeline = screen.getByRole("region", { name: "İşlem geçmişi" })
    expect(timeline).toHaveTextContent("analyst1")
    expect(timeline).toHaveTextContent("new → investigating")
    expect(timeline).toHaveTextContent("13.10.2026 00:30")
    expect(screen.getByRole("link", { name: "Vaka listesine dön" })).toHaveAttribute("href", "/cases")
    expect(mockApi).toHaveBeenCalledWith("/api/v1/cases/CASE-001")
  })

  it("404 için vaka bulunamadı ve listeye dönüşü gösterir", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(404, "Not found"))
    render(<CaseDetailPage />)
    expect(await screen.findByRole("alert")).toHaveTextContent("Vaka bulunamadı.")
    expect(screen.getByRole("link", { name: "Vaka listesine dön" })).toHaveAttribute("href", "/cases")
  })

  it("yükleme hatasından sonra tekrar dener", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(0, "Network error"))
    render(<CaseDetailPage />)
    expect(await screen.findByRole("alert")).toHaveTextContent("Sunucuya ulaşılamıyor.")
    await userEvent.click(screen.getByRole("button", { name: "Tekrar dene" }))
    expect(await screen.findByRole("heading", { name: "Transfer incelemesi" })).toBeInTheDocument()
  })

  it("bir alarm yüklenemezse kimliğini korur, diğer bölümler çalışır", async () => {
    failedAlert = "ALT-2"
    await openPage()
    expect(await screen.findByText("Alarm ALT-1")).toBeInTheDocument()
    expect(screen.getByText("ALT-2")).toBeInTheDocument()
    expect(screen.queryByText("Alarm ALT-2")).toBeNull()
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("en fazla 20 alarmı ister ve kalan sayıyı gösterir", async () => {
    currentCase.alert_ids = Array.from({ length: 23 }, (_, index) => `ALT-${index + 1}`)
    currentCase.alert_count = 23
    await openPage()
    expect(await screen.findByText("+3 alarm daha")).toBeInTheDocument()
    expect(mockApi.mock.calls.filter(([endpoint]) => endpoint.includes("/alerts/"))).toHaveLength(20)
    expect(mockApi).not.toHaveBeenCalledWith("/api/v1/alerts/ALT-21")
  })

  it("alarmsız vakada boş durumu gösterir", async () => {
    currentCase.alert_ids = []
    await openPage()
    expect(await screen.findByText("Bağlı alarm yok.")).toBeInTheDocument()
  })

  it("viewer için hiçbir form ya da yazma düğmesi göstermez", async () => {
    mocks.role = "viewer"
    await openPage()
    expect(screen.queryByRole("form")).toBeNull()
    expect(screen.queryByRole("region", { name: "Vaka işlemleri" })).toBeNull()
    expect(screen.queryByRole("button", { name: /kaydet|Notu ekle/ })).toBeNull()
  })

  it("closed vakada durum formu yoktur ve çözüm açıklaması gösterilir", async () => {
    currentCase.status = "closed"
    currentCase.resolution = "İnceleme tamamlandı"
    await openPage()
    expect(screen.queryByRole("form", { name: "Durum değiştirme" })).toBeNull()
    expect(screen.getByText("İnceleme tamamlandı")).toBeInTheDocument()
  })

  it("çözümlenmiş vaka için yalnız kapatma ve yeniden açmayı sunar", async () => {
    currentCase.status = "resolved_true_positive"
    await openPage()
    const select = screen.getByLabelText("Yeni durum")
    expect(within(select).getAllByRole("option").map((option) => option.getAttribute("value")))
      .toEqual(["", "closed", "investigating"])
  })

  it("rota kimliği değişince önceki vaka verilerini taşımaz", async () => {
    const view = render(<CaseDetailPage />)
    await screen.findByRole("heading", { name: "Transfer incelemesi" })
    mocks.id = "CASE-002"
    mockApi.mockImplementation(() => new Promise(() => {}))
    view.rerender(<CaseDetailPage />)
    expect(screen.queryByRole("heading", { name: "Transfer incelemesi" })).toBeNull()
    expect(screen.getByRole("status")).toHaveTextContent("Vaka yükleniyor...")
    expect(mockApi).toHaveBeenLastCalledWith("/api/v1/cases/CASE-002")
  })
})

describe("Vaka mutasyonları", () => {
  it.each([
    ["durum", { status: "investigating" }, "Durumu kaydet"],
    ["öncelik", { priority: "P1" }, "Önceliği kaydet"],
    ["atama", { assigned_to: "analyst2", assigned_team: "AML" }, "Atamayı kaydet"],
    ["not", { note: "İnceleme notu" }, "Notu ekle"],
  ] as const)("%s PATCH sonrası özeti ve olayları yeniler", async (kind, patch, button) => {
    const user = await openPage()
    // Refresh must return to page 1 even when currently on page 2.
    mockApi.mockImplementationOnce(async () => ({ ...sampleEvents, total: 40 }))
    await user.selectOptions(screen.getByLabelText("Olay türü"), "note_added")
    await waitFor(() => expect(screen.getByRole("button", { name: "Sonraki" })).toBeEnabled())
    await user.click(screen.getByRole("button", { name: "Sonraki" }))
    await waitFor(() => expect(screen.getByText(/Sayfa 2/)).toBeInTheDocument())
    const before = eventCalls().length
    if (kind === "durum") await user.selectOptions(screen.getByLabelText("Yeni durum"), "investigating")
    if (kind === "öncelik") await user.selectOptions(screen.getByLabelText("Yeni öncelik"), "P1")
    if (kind === "atama") {
      await user.type(screen.getByLabelText("Kullanıcı adı"), "analyst2")
      await user.type(screen.getByLabelText("Takım (isteğe bağlı)"), "AML")
    }
    if (kind === "not") await user.type(screen.getByLabelText("Not"), "İnceleme notu")
    await user.click(screen.getByRole("button", { name: button }))
    expect(mockApi).toHaveBeenCalledWith("/api/v1/cases/CASE-001", {
      method: "PATCH", body: JSON.stringify(patch),
    })
    await waitFor(() => expect(eventCalls()).toHaveLength(before + 1))
    expect(eventCalls().at(-1)?.[0]).toBe(
      "/api/v1/cases/CASE-001/events?page=1&page_size=20&event_type=note_added",
    )
    const summary = screen.getByRole("region", { name: "Transfer incelemesi" })
    if (kind === "durum") expect(summary).toHaveTextContent("İnceleniyor")
    if (kind === "öncelik") expect(summary).toHaveTextContent("P1")
    if (kind === "atama") expect(summary).toHaveTextContent("analyst2")
    if (kind === "not") expect(screen.getByLabelText("Not")).toHaveValue("")
  })

  it.each(["resolved_true_positive", "resolved_false_positive"])(
    "%s için çözüm açıklamasını zorunlu tutar", async (status) => {
      const user = await openPage()
      await user.selectOptions(screen.getByLabelText("Yeni durum"), status)
      expect(screen.getByRole("button", { name: "Durumu kaydet" })).toBeDisabled()
      await user.type(screen.getByLabelText("Çözüm açıklaması"), "   ")
      expect(screen.getByRole("button", { name: "Durumu kaydet" })).toBeDisabled()
      await user.type(screen.getByLabelText("Çözüm açıklaması"), "İncelendi")
      await user.click(screen.getByRole("button", { name: "Durumu kaydet" }))
      expect(mockApi).toHaveBeenCalledWith("/api/v1/cases/CASE-001", {
        method: "PATCH", body: JSON.stringify({ status, resolution: "İncelendi" }),
      })
    },
  )

  it.each([
    [409, "invalid_status_transition", "Bu durum değişikliğine izin verilmiyor."],
    [422, "resolution_required", "Bu durum için çözüm açıklaması zorunlu."],
  ])("%s %s hatasında form değerlerini korur", async (status, code, message) => {
    const user = await openPage()
    patchError = new ApiError(status, "error", { code })
    await user.selectOptions(screen.getByLabelText("Yeni durum"), "resolved_true_positive")
    await user.type(screen.getByLabelText("Çözüm açıklaması"), "Analist açıklaması")
    const before = eventCalls().length
    await user.click(screen.getByRole("button", { name: "Durumu kaydet" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(message)
    expect(screen.getByLabelText("Yeni durum")).toHaveValue("resolved_true_positive")
    expect(screen.getByLabelText("Çözüm açıklaması")).toHaveValue("Analist açıklaması")
    expect(eventCalls()).toHaveLength(before)
    expect(screen.getByRole("button", { name: "Durumu kaydet" })).toBeEnabled()
  })

  it("çift tıklamada tek PATCH gönderir ve formu kilitler", async () => {
    const user = await openPage()
    await user.type(screen.getByLabelText("Not"), "Not")
    let resolve!: (value: Case) => void
    mockApi.mockReturnValueOnce(new Promise((done) => { resolve = done }))
    const button = screen.getByRole("button", { name: "Notu ekle" })
    act(() => { fireEvent.click(button); fireEvent.click(button) })
    expect(mockApi.mock.calls.filter(([, options]) => options?.method === "PATCH")).toHaveLength(1)
    expect(button).toBeDisabled()
    expect(screen.getByLabelText("Not")).toBeDisabled()
    await act(async () => { resolve(currentCase) })
    expect(screen.getByLabelText("Not")).toBeEnabled()
  })

  it("boş atama göndermez, takım boşken null veya tags göndermez", async () => {
    const user = await openPage()
    expect(screen.getByRole("button", { name: "Atamayı kaydet" })).toBeDisabled()
    await user.type(screen.getByLabelText("Kullanıcı adı"), "analyst2")
    await user.click(screen.getByRole("button", { name: "Atamayı kaydet" }))
    const patchCall = mockApi.mock.calls.find(([, options]) => options?.method === "PATCH")
    expect(JSON.parse(patchCall?.[1]?.body as string) as CaseUpdateRequest)
      .toEqual({ assigned_to: "analyst2" })
    expect(screen.getByLabelText("Not")).toHaveAttribute("maxlength", "5000")
  })
})
