import { describe, expect, it } from "vitest"
import { formatDate, formatDateTime } from "./datetime"

describe("İstanbul tarih gösterimi", () => {
  it("UTC tarihini İstanbul'da ertesi günün saatiyle gösterir", () => {
    expect(formatDateTime("2026-10-12T21:30:00+00:00")).toBe("13.10.2026 00:30")
    expect(formatDate("2026-10-12T21:30:00+00:00")).toBe("13.10.2026")
  })

  it("offset ve Z biçimleri aynı an için aynı sonucu verir", () => {
    expect(formatDateTime("2026-10-13T00:30:00+03:00")).toBe("13.10.2026 00:30")
    expect(formatDateTime("2026-10-12T21:30:00Z")).toBe("13.10.2026 00:30")
  })

  it.each([null, undefined, "", "invalid-date"])("geçersiz girdi için tire: %s", (value) => {
    expect(formatDate(value)).toBe("—")
    expect(formatDateTime(value)).toBe("—")
  })
})
