import { describe, expect, it, vi } from "vitest"
import userEvent from "@testing-library/user-event"
import { render, screen } from "@testing-library/react"

import { ApiError } from "@/lib/auth"

import {
  describeError,
  EmptyState,
  ErrorState,
  LoadingState,
} from "./request-state"

describe("describeError", () => {
  it("maps unauthorized to a session message", () => {
    expect(describeError(new ApiError(401, "Session expired"))).toBe(
      "Oturumunuz sona erdi."
    )
  })

  it("maps forbidden to a permission message", () => {
    expect(describeError(new ApiError(403, "Request failed (403)"))).toBe(
      "Bu işlem için yetkiniz yok."
    )
  })

  it("maps not_found to a missing record message", () => {
    expect(describeError(new ApiError(404, "Request failed (404)"))).toBe(
      "Kayıt bulunamadı."
    )
  })

  it("uses the backend message for conflict when present", () => {
    expect(describeError(new ApiError(409, "Alarm zaten bir vakaya bağlı"))).toBe(
      "Alarm zaten bir vakaya bağlı"
    )
  })

  it("falls back to a generic conflict message", () => {
    expect(describeError(new ApiError(409, "Request failed (409)"))).toBe(
      "Kayıt başka bir işlemle çakıştı."
    )
  })

  it("uses the backend message for validation when present", () => {
    expect(describeError(new ApiError(422, "Tutar negatif olamaz"))).toBe(
      "Tutar negatif olamaz"
    )
  })

  it("falls back to a generic validation message", () => {
    expect(describeError(new ApiError(422, "Request failed (422)"))).toBe(
      "Gönderilen bilgiler geçersiz."
    )
  })

  it("prefers the backend detail over the generic message", () => {
    expect(
      describeError(new ApiError(409, "Request failed (409)", "Vaka zaten kapalı"))
    ).toBe("Vaka zaten kapalı")
  })

  it("maps network errors to a connection message", () => {
    expect(describeError(new ApiError(0, "Network error"))).toBe(
      "Sunucuya ulaşılamıyor. Bağlantınızı kontrol edin."
    )
  })

  it("maps server errors to an unexpected message", () => {
    expect(describeError(new ApiError(500, "Request failed (500)"))).toBe(
      "Beklenmeyen bir hata oluştu."
    )
  })

  it("maps unknown errors to an unexpected message", () => {
    expect(describeError(new Error("boom"))).toBe(
      "Beklenmeyen bir hata oluştu."
    )
    expect(describeError("kablolu hata")).toBe(
      "Beklenmeyen bir hata oluştu."
    )
    expect(describeError(null)).toBe("Beklenmeyen bir hata oluştu.")
  })
})

describe("LoadingState", () => {
  it("shows the default label", () => {
    render(<LoadingState />)
    expect(screen.getByRole("status")).toHaveTextContent("Yükleniyor...")
  })

  it("shows a custom label", () => {
    render(<LoadingState label="Alarmlar yükleniyor..." />)
    expect(screen.getByRole("status")).toHaveTextContent("Alarmlar yükleniyor...")
  })
})

describe("ErrorState", () => {
  it("describes the error", () => {
    render(<ErrorState error={new ApiError(403, "Request failed (403)")} />)
    const alert = screen.getByRole("alert")
    expect(alert).toHaveTextContent("Bu işlem için yetkiniz yok.")
  })

  it("hides the retry button without onRetry", () => {
    render(<ErrorState error={new ApiError(500, "Request failed (500)")} />)
    expect(screen.queryByRole("button", { name: "Tekrar dene" })).not.toBeInTheDocument()
  })

  it("calls onRetry when the retry button is clicked", async () => {
    const onRetry = vi.fn()
    render(
      <ErrorState error={new ApiError(0, "Network error")} onRetry={onRetry} />
    )
    await userEvent.click(screen.getByRole("button", { name: "Tekrar dene" }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})

describe("EmptyState", () => {
  it("shows the message", () => {
    render(<EmptyState message="Alarm bulunamadı" />)
    expect(screen.getByText("Alarm bulunamadı")).toBeInTheDocument()
  })
})
