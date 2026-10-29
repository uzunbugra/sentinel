import { beforeEach, describe, expect, it, vi } from "vitest"
import userEvent from "@testing-library/user-event"
import { render, screen, within } from "@testing-library/react"

vi.mock("@/lib/auth", async (orig) => ({ ...(await orig()), apiRequest: vi.fn() }))

import { apiRequest, ApiError } from "@/lib/auth"
import { config } from "@/lib/config"
import { ActiveModelCard } from "./active-model-card"
import {
  loadedModelResponse,
  modelNotLoaded503Detail,
  noMetricsResponse,
  notLoadedResponse,
  partialMetricsResponse,
} from "@/test/ml-fixtures"

const mockApi = vi.mocked(apiRequest)

function card() {
  return screen.getByRole("region", { name: "aktif model" })
}

function metric(label: string) {
  return screen.getByText(label, { selector: "dt" }).nextElementSibling!
}

beforeEach(() => {
  mockApi.mockReset()
})

describe("ActiveModelCard", () => {
  it("yüklenirken durum gösterir", () => {
    mockApi.mockReturnValueOnce(new Promise(() => {}))
    render(<ActiveModelCard />)
    expect(within(card()).getByRole("status")).toHaveTextContent("Model bilgisi yükleniyor...")
    expect(mockApi).toHaveBeenCalledWith(config.endpoints.modelInfo)
  })

  it("sürüm, İstanbul saatiyle eğitim zamanı, veri kimliği ve metrikleri gösterir", async () => {
    mockApi.mockResolvedValueOnce(loadedModelResponse)
    render(<ActiveModelCard />)

    expect(await screen.findByText("fraud-lgbm-20261105-a1b2c3d")).toBeInTheDocument()
    // 2026-11-05T12:00:00Z → İstanbul (UTC+3)
    expect(metric("Eğitim")).toHaveTextContent("05.11.2026 15:00 (İstanbul)")
    expect(metric("Veri kimliği")).toHaveTextContent("samld-3f9a")
    expect(metric("Eşik")).toHaveTextContent("0.3700")
    expect(metric("PR-AUC")).toHaveTextContent("0.52")
    expect(metric("Baz PR-AUC")).toHaveTextContent("0.30")
    expect(metric("Toplam örnek")).toHaveTextContent("1.425.000")
    expect(card()).toHaveTextContent("metrikler (test)")
  })

  it("eksik metriği tire, sıfır metriği 0 olarak gösterir", async () => {
    mockApi.mockResolvedValueOnce(partialMetricsResponse)
    render(<ActiveModelCard />)

    await screen.findByText("fraud-lgbm-20261105-a1b2c3d")
    expect(metric("PR-AUC")).toHaveTextContent("—")
    expect(metric("Duyarlılık")).toHaveTextContent("0.00")
  })

  it("metrik kaydı yoksa boş durum gösterir", async () => {
    mockApi.mockResolvedValueOnce(noMetricsResponse)
    render(<ActiveModelCard />)
    expect(await screen.findByText("Bu model için metrik kaydı yok.")).toBeInTheDocument()
  })

  it("200 not_loaded cevabında model yok durumunu sebebiyle gösterir", async () => {
    mockApi.mockResolvedValueOnce(notLoadedResponse)
    render(<ActiveModelCard />)
    expect(await screen.findByText("Yüklü model yok.")).toBeInTheDocument()
    expect(card()).toHaveTextContent("model directory not found: models/fraud/current")
    expect(card()).toHaveTextContent("kural alarmları çalışmaya devam eder")
  })

  it("invalid durumunu ayrı mesajla gösterir", async () => {
    mockApi.mockResolvedValueOnce({ status: "invalid", model: null, error: "checksum mismatch" })
    render(<ActiveModelCard />)
    expect(await screen.findByText("Model geçersiz; yüklenmedi.")).toBeInTheDocument()
  })

  it("503 cevabında model yok durumunu gösterir", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(503, "Request failed (503)", modelNotLoaded503Detail))
    render(<ActiveModelCard />)
    expect(await screen.findByText("Yüklü model yok.")).toBeInTheDocument()
    expect(card()).toHaveTextContent("No valid fraud model is loaded")
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("hata durumunu gösterir ve tekrar denemede yükler", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(0, "Network error"))
    render(<ActiveModelCard />)

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Sunucuya ulaşılamıyor. Bağlantınızı kontrol edin.",
    )
    mockApi.mockResolvedValueOnce(loadedModelResponse)
    await userEvent.setup().click(screen.getByRole("button", { name: "Tekrar dene" }))
    expect(await screen.findByText("fraud-lgbm-20261105-a1b2c3d")).toBeInTheDocument()
    expect(mockApi).toHaveBeenCalledTimes(2)
  })

  it("eski biçimdeki cevapta çökmeden bilgi verir", async () => {
    mockApi.mockResolvedValueOnce({ models: [], ensemble_ready: false })
    render(<ActiveModelCard />)
    expect(await screen.findByText(/henüz yeni biçimde vermiyor/)).toBeInTheDocument()
  })
})
