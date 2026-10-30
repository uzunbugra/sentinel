import { beforeEach, describe, expect, it, vi } from "vitest"
import userEvent from "@testing-library/user-event"
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
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
import { legacyEnsembleEvidence, mlEvidence } from "@/test/ml-fixtures"
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

describe("Alarmdan vaka akışı", () => {
  const caseResponse = { case_id: "CASE-123", title: "İnceleme" }

  async function openDialog(alert = sampleAlert) {
    mocks.user = analyst
    mockApi.mockResolvedValueOnce({ ...listResponse, alerts: [alert] })
    render(<AlertsPage />)
    const user = userEvent.setup()
    await user.click(await screen.findByText("Ali Yılmaz → Ayşe Demir"))
    await user.click(screen.getByRole("button", { name: "Vaka Oluştur" }))
    return { user, dialog: within(screen.getByRole("dialog")) }
  }

  it("yeni vaka için doğru POST gövdesini gönderir, satır ve seçili alarmı günceller", async () => {
    const { user, dialog } = await openDialog()
    expect(dialog.getByLabelText("Başlık")).toHaveValue("Mule Hesap — Ali Yılmaz")
    await user.clear(dialog.getByLabelText("Başlık"))
    await user.type(dialog.getByLabelText("Başlık"), "  Transfer incelemesi  ")
    await user.selectOptions(dialog.getByLabelText("Öncelik"), "P2")
    await user.type(dialog.getByLabelText("Açıklama (isteğe bağlı)"), "İncelenecek")
    mockApi.mockResolvedValueOnce(caseResponse)
    await user.click(dialog.getByRole("button", { name: "Vaka oluştur" }))
    expect(mockApi).toHaveBeenLastCalledWith(config.endpoints.cases, {
      method: "POST",
      body: JSON.stringify({ title: "Transfer incelemesi", description: "İncelenecek", priority: "P2", alert_ids: ["alert-1"] }),
    })
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(screen.getByRole("link", { name: "CASE-123" })).toHaveAttribute("href", "/cases/CASE-123")
    // Reselecting reads the updated list item rather than selectedAlert state.
    await user.click(screen.getByText("Ali Yılmaz → Ayşe Demir"))
    expect(screen.getByRole("link", { name: "CASE-123" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Vaka Oluştur" })).toBeNull()
  })

  it("açık vakaları listeler ve seçilen vakaya alarmı bağlar", async () => {
    const { user, dialog } = await openDialog()
    mockApi.mockResolvedValueOnce({ cases: [caseResponse] })
    await user.click(dialog.getByLabelText("Mevcut vakaya bağla"))
    expect(mockApi).toHaveBeenLastCalledWith("/api/v1/cases?is_open=true&page_size=100&page=1")
    await user.selectOptions(await dialog.findByLabelText("Açık vaka"), "CASE-123")
    mockApi.mockResolvedValueOnce(caseResponse)
    await user.click(dialog.getByRole("button", { name: "Alarmı bağla" }))
    expect(mockApi).toHaveBeenLastCalledWith(config.endpoints.caseAlerts("CASE-123"), {
      method: "POST", body: JSON.stringify({ alert_id: "alert-1" }),
    })
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(screen.getByRole("link", { name: "CASE-123" })).toBeInTheDocument()
  })

  it("art arda iki gönderimde yalnızca tek POST başlatır", async () => {
    const { dialog } = await openDialog()
    let resolve!: (value: typeof caseResponse) => void
    mockApi.mockReturnValueOnce(new Promise((done) => { resolve = done }))
    const button = dialog.getByRole("button", { name: "Vaka oluştur" })
    act(() => { fireEvent.click(button); fireEvent.click(button) })
    expect(mockApi.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(1)
    expect(button).toBeDisabled()
    await act(async () => { resolve(caseResponse) })
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("409 alert_already_linked mesajını ve vaka bağlantısını gösterip alarmı günceller", async () => {
    const { user, dialog } = await openDialog()
    mockApi.mockRejectedValueOnce(new ApiError(409, "Request failed (409)", {
      code: "alert_already_linked", message: "Already linked", case_id: "CASE-456",
    }))
    await user.click(dialog.getByRole("button", { name: "Vaka oluştur" }))
    expect(dialog.getByRole("alert")).toHaveTextContent("Bu alarm zaten CASE-456 vakasına bağlı.")
    expect(dialog.getByRole("link")).toHaveAttribute("href", "/cases/CASE-456")
    expect(dialog.getByRole("button", { name: "Vaka oluştur" })).toBeDisabled()
    await user.click(dialog.getByRole("button", { name: "Kapat" }))
    await user.click(screen.getByText("Ali Yılmaz → Ayşe Demir"))
    expect(screen.getByRole("link", { name: "CASE-456" })).toHaveAttribute("href", "/cases/CASE-456")
    expect(screen.queryByRole("button", { name: "Vaka Oluştur" })).toBeNull()
  })

  it.each([
    [new ApiError(409, "Request failed (409)", { code: "alert_dismissed", message: "dismissed" }), "Reddedilmiş alarm vakaya bağlanamaz."],
    [new ApiError(409, "Request failed (409)", { code: "case_not_open", message: "closed" }), "Seçilen vaka kapalı; alarm eklenemez."],
    [new ApiError(422, "Request failed (422)", [{ msg: "invalid" }]), "Gönderilen bilgiler geçersiz."],
    [new ApiError(403, "Forbidden"), "Bu işlem için yetkiniz yok."],
    [new ApiError(404, "Not found"), "Kayıt bulunamadı."],
    [new ApiError(0, "Network error"), "Sunucuya ulaşılamıyor. Bağlantınızı kontrol edin."],
  ])("%s hatasında mesaj gösterir ve diyaloğu açık tutar", async (error, message) => {
    const { user, dialog } = await openDialog()
    mockApi.mockRejectedValueOnce(error)
    await user.click(dialog.getByRole("button", { name: "Vaka oluştur" }))
    expect(dialog.getByRole("alert")).toHaveTextContent(message)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(dialog.getByRole("button", { name: "Vaka oluştur" })).toBeEnabled()
  })

  it("reddedilmiş alarmda vaka düğmesini göstermez", async () => {
    mocks.user = analyst
    mockApi.mockResolvedValueOnce({ ...listResponse, alerts: [{ ...sampleAlert, is_dismissed: true }] })
    render(<AlertsPage />)
    await userEvent.setup().click(await screen.findByText("Ali Yılmaz → Ayşe Demir"))
    expect(screen.queryByRole("button", { name: "Vaka Oluştur" })).toBeNull()
  })

  it("boş veya yalnızca boşluk içeren başlık gönderilemez", async () => {
    const { user, dialog } = await openDialog()
    await user.clear(dialog.getByLabelText("Başlık"))
    expect(dialog.getByRole("button", { name: "Vaka oluştur" })).toBeDisabled()
    await user.type(dialog.getByLabelText("Başlık"), "   ")
    expect(dialog.getByRole("button", { name: "Vaka oluştur" })).toBeDisabled()
    fireEvent.submit(dialog.getByRole("button", { name: "Vaka oluştur" }).closest("form")!)
    expect(mockApi.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(0)
  })

  it("açık vaka yüklenirken ve liste boşken gönderimi engeller", async () => {
    const { user, dialog } = await openDialog()
    let resolve!: (value: { cases: [] }) => void
    mockApi.mockReturnValueOnce(new Promise((done) => { resolve = done }))
    await user.click(dialog.getByLabelText("Mevcut vakaya bağla"))
    expect(dialog.getByRole("status")).toHaveTextContent("Açık vakalar yükleniyor...")
    expect(dialog.getByRole("button", { name: "Alarmı bağla" })).toBeDisabled()
    await act(async () => { resolve({ cases: [] }) })
    expect(dialog.getByText("Açık vaka bulunamadı.")).toBeInTheDocument()
    expect(dialog.getByRole("button", { name: "Alarmı bağla" })).toBeDisabled()
  })

  it("açık vaka listesinin yükleme hatası tekrar denenebilir", async () => {
    const { user, dialog } = await openDialog()
    mockApi.mockRejectedValueOnce(new ApiError(0, "Network error"))
    await user.click(dialog.getByLabelText("Mevcut vakaya bağla"))
    expect(await dialog.findByRole("alert")).toHaveTextContent("Sunucuya ulaşılamıyor.")
    expect(dialog.getByRole("button", { name: "Alarmı bağla" })).toBeDisabled()
    mockApi.mockResolvedValueOnce({ cases: [caseResponse] })
    await user.click(dialog.getByRole("button", { name: "Tekrar dene" }))
    expect(await dialog.findByLabelText("Açık vaka")).toBeInTheDocument()
  })

  it("odak diyalog içinde kalır; Escape kapatır ve odağı açan düğmeye döndürür", async () => {
    const { user, dialog } = await openDialog()
    const modal = screen.getByRole("dialog")
    expect(modal).toHaveAttribute("aria-modal", "true")
    expect(modal).toHaveFocus()
    await user.tab({ shift: true })
    expect(dialog.getByRole("button", { name: "Vaka oluştur" })).toHaveFocus()
    await user.tab()
    expect(dialog.getByLabelText("Yeni vaka")).toHaveFocus()
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(screen.getByRole("button", { name: "Vaka Oluştur" })).toHaveFocus()
  })
})

describe("Alarmlar sayfası", () => {
  it("adlandırılmış filtrelerden Tab ve Enter ile alarm detayına ulaşılır", async () => {
    mockApi.mockResolvedValue(listResponse)
    render(<AlertsPage />)
    await screen.findByText("Ali Yılmaz → Ayşe Demir")
    const user = userEvent.setup()
    await user.tab()
    expect(screen.getByRole("combobox", { name: "Seviye filtresi" })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole("combobox", { name: "Tip filtresi" })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole("button", { name: "Yenile" })).toHaveFocus()
    await user.tab()
    const row = screen.getByRole("button", { name: /Ali Yılmaz → Ayşe Demir/ })
    expect(row).toHaveFocus()
    expect(row).toHaveAttribute("aria-pressed", "false")
    await user.keyboard("{Enter}")
    expect(screen.getByText("Alarm Detayı")).toBeInTheDocument()
    expect(row).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByText("Gönderen").tagName).toBe("DT")
    expect(screen.getByText("Ali Yılmaz").closest("dd")).not.toBeNull()
  })

  it("Space tuşu da alarm seçer", async () => {
    mockApi.mockResolvedValue(listResponse)
    render(<AlertsPage />)
    const row = await screen.findByRole("button", { name: /Ali Yılmaz → Ayşe Demir/ })
    row.focus()
    await userEvent.keyboard(" ")
    expect(row).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByText("Alarm Detayı")).toBeInTheDocument()
  })

  it("sayfalama gezinmesi adlandırılmıştır ve ilk sayfada önceki kilitlidir", async () => {
    mockApi.mockResolvedValue({ ...listResponse, total: 40 })
    render(<AlertsPage />)
    const nav = await screen.findByRole("navigation", { name: "Sayfalama" })
    expect(within(nav).getByRole("button", { name: "Önceki" })).toBeDisabled()
    expect(within(nav).getByRole("button", { name: "Sonraki" })).toBeEnabled()
  })

  it("alarm saatini ve detay tarihini İstanbul saatinde gösterir", async () => {
    mockApi.mockResolvedValue({
      ...listResponse,
      alerts: [{ ...sampleAlert, detected_at: "2026-10-12T21:30:05+00:00" }],
    })
    render(<AlertsPage />)
    expect(await screen.findByText("00:30:05")).toBeInTheDocument()
    await userEvent.click(screen.getByText("Ali Yılmaz → Ayşe Demir"))
    expect(screen.getByText("13.10.2026 00:30")).toBeInTheDocument()
  })

  it("ML alarmının detayında alarm anındaki model değerlendirmesini gösterir", async () => {
    mockApi.mockResolvedValue({
      ...listResponse,
      alerts: [{ ...sampleAlert, fraud_type: "ml_model", evidence: [mlEvidence] }],
    })
    render(<AlertsPage />)
    await userEvent.click(await screen.findByText("Ali Yılmaz → Ayşe Demir"))

    const section = screen.getByRole("region", { name: "Model değerlendirmesi" })
    expect(section).toHaveTextContent("fraud-lgbm-20261105-a1b2c3d")
    expect(section).toHaveTextContent("Skor eşiğin üstünde")
    expect(screen.getAllByText("ML Model").length).toBeGreaterThan(0)
    // Açıklama evidence'tan okunur; aktif model ucu çağrılmaz.
    expect(mockApi).not.toHaveBeenCalledWith(config.endpoints.modelInfo)
  })

  it("metadata'sız eski ML alarmında durum mesajı, kural alarmında bölüm yok", async () => {
    mockApi.mockResolvedValue({
      ...listResponse,
      total: 2,
      alerts: [
        { ...sampleAlert, fraud_type: "ml_ensemble", evidence: [legacyEnsembleEvidence] },
        { ...sampleAlert, alert_id: "alert-2", sender_name: "Can Kaya" },
      ],
    })
    render(<AlertsPage />)
    const user = userEvent.setup()
    await user.click(await screen.findByText("Ali Yılmaz → Ayşe Demir"))
    expect(screen.getByRole("region", { name: "Model değerlendirmesi" })).toHaveTextContent(
      "model metadata'sı kaydedilmeden önce üretildi",
    )
    await user.click(screen.getByText("Can Kaya → Ayşe Demir"))
    expect(screen.queryByRole("region", { name: "Model değerlendirmesi" })).toBeNull()
  })

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
