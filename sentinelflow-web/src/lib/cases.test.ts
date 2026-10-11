import { beforeEach, describe, expect, it, vi } from "vitest"
import { apiRequest, ApiError } from "./auth"
import {
  allowedTransitions, caseErrorCode, describeCaseError, getCase,
  linkedCaseId, listCaseEvents, updateCase, type CaseStatus,
} from "./cases"
import { sampleCase, sampleEvents } from "@/test/case-fixtures"

vi.mock("./auth", async (original) => ({ ...(await original()), apiRequest: vi.fn() }))

describe("Vaka hataları", () => {
  it.each([
    null, undefined, new Error("error"), new ApiError(409, "error"),
    new ApiError(422, "error", []), new ApiError(409, "error", "code"),
    new ApiError(409, "error", { code: 123 }), new ApiError(409, "error", {}),
  ])("yapılandırılmamış hata için kod döndürmez: %s", (error) => {
    expect(caseErrorCode(error)).toBeNull()
    expect(linkedCaseId(error)).toBeNull()
  })

  it("yapılandırılmış hata kodunu ve bağlı vaka kimliğini okur", () => {
    const error = new ApiError(409, "Request failed (409)", { code: "alert_already_linked", case_id: "CASE-1" })
    expect(caseErrorCode(error)).toBe("alert_already_linked")
    expect(linkedCaseId(error)).toBe("CASE-1")
    expect(describeCaseError(error)).toBe("Bu alarm zaten CASE-1 vakasına bağlı.")
  })

  it.each([undefined, null, 123, ""])("geçersiz vaka kimliğini bağlantı olarak kullanmaz: %s", (caseId) => {
    const error = new ApiError(409, "Request failed (409)", { code: "alert_already_linked", case_id: caseId })
    expect(linkedCaseId(error)).toBeNull()
    expect(describeCaseError(error)).toBe("Bu alarm zaten bir vakaya bağlı.")
  })

  it.each([
    [new ApiError(409, "Request failed (409)", { code: "alert_dismissed" }), "Reddedilmiş alarm vakaya bağlanamaz."],
    [new ApiError(409, "Request failed (409)", { code: "case_not_open" }), "Seçilen vaka kapalı; alarm eklenemez."],
    [new ApiError(409, "Request failed (409)", { code: "unknown" }), "Kayıt başka bir işlemle çakıştı."],
    [new ApiError(422, "Request failed (422)", { code: "unknown" }), "Gönderilen bilgiler geçersiz."],
    [new ApiError(422, "Request failed (422)", [{ msg: "invalid" }]), "Gönderilen bilgiler geçersiz."],
    [new ApiError(403, "Forbidden"), "Bu işlem için yetkiniz yok."],
    [new ApiError(404, "Not found"), "Kayıt bulunamadı."],
    [new ApiError(0, "Network error"), "Sunucuya ulaşılamıyor. Bağlantınızı kontrol edin."],
    [new Error("error"), "Beklenmeyen bir hata oluştu."],
  ])("%s için Türkçe açıklama döndürür", (error, message) => {
    expect(describeCaseError(error)).toBe(message)
  })
})

describe("Vaka durum geçişleri", () => {
  const open: CaseStatus[] = ["new", "triage", "investigating", "escalated", "pending_info"]
  it.each(open)("%s için diğer açık ve tüm kapanış durumlarını sunar", (status) => {
    expect(allowedTransitions(status)).toEqual([
      ...open.filter((target) => target !== status),
      "resolved_true_positive", "resolved_false_positive", "closed",
    ])
  })
  it.each(["resolved_true_positive", "resolved_false_positive"] as const)(
    "%s yalnızca kapatılır veya yeniden açılır", (status) => {
      expect(allowedTransitions(status)).toEqual(["closed", "investigating"])
    },
  )
  it("closed son durumdur", () => {
    expect(allowedTransitions("closed")).toEqual([])
  })
})

describe("Vaka güncelleme hataları", () => {
  it.each([
    [409, "invalid_status_transition", "Bu durum değişikliğine izin verilmiyor."],
    [422, "resolution_required", "Bu durum için çözüm açıklaması zorunlu."],
    [422, "unsupported_field", "Bu alan bu ekrandan değiştirilemez."],
  ])("%s %s kodunu açıklar", (status, code, message) => {
    expect(describeCaseError(new ApiError(status, "error", { code }))).toBe(message)
  })
})

describe("Vaka detay API yardımcıları", () => {
  const mockApi = vi.mocked(apiRequest)
  beforeEach(() => {
    mockApi.mockReset()
  })

  it("vaka detayını yetkili istemciden alır", async () => {
    mockApi.mockResolvedValueOnce(sampleCase)
    expect(await getCase("CASE-001")).toEqual(sampleCase)
    expect(mockApi).toHaveBeenCalledWith("/api/v1/cases/CASE-001")
  })
  it("olay listesi için varsayılan sayfalama parametrelerini yollar", async () => {
    mockApi.mockResolvedValueOnce(sampleEvents)
    expect(await listCaseEvents("CASE-001")).toEqual(sampleEvents)
    expect(mockApi).toHaveBeenCalledWith("/api/v1/cases/CASE-001/events?page=1&page_size=20")
  })
  it("olay filtresi ve sayfalama parametrelerini yollar", async () => {
    mockApi.mockResolvedValueOnce(sampleEvents)
    await listCaseEvents("CASE-001", { page: 2, pageSize: 50, eventType: "note_added" })
    expect(mockApi).toHaveBeenCalledWith(
      "/api/v1/cases/CASE-001/events?page=2&page_size=50&event_type=note_added",
    )
  })
  it("yalnızca verilen PATCH alanlarını yollar ve güncel vakayı döndürür", async () => {
    mockApi.mockResolvedValueOnce(sampleCase)
    expect(await updateCase("CASE-001", { note: "İncele" })).toEqual(sampleCase)
    expect(mockApi).toHaveBeenCalledWith("/api/v1/cases/CASE-001", {
      method: "PATCH", body: JSON.stringify({ note: "İncele" }),
    })
  })
})
