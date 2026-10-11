import { describe, expect, it } from "vitest"
import { ApiError } from "./auth"
import { caseErrorCode, describeCaseError, linkedCaseId } from "./cases"

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
