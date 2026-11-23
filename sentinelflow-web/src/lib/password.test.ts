import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("./auth", async (orig) => ({ ...(await orig()), apiRequest: vi.fn() }))

import { apiRequest, ApiError } from "./auth"
import {
  CHANGE_PASSWORD_ENDPOINT,
  changePassword,
  describePasswordError,
  passwordRuleErrors,
  validatePasswordForm,
} from "./password"

const mockApi = vi.mocked(apiRequest)
beforeEach(() => mockApi.mockReset())

describe("passwordRuleErrors", () => {
  it("mirrors the backend rules", () => {
    expect(passwordRuleErrors("Yenisifre1")).toEqual([])
    expect(passwordRuleErrors("Kisa1")).toEqual(["En az 8 karakter olmalı."])
    expect(passwordRuleErrors("kucukharf1")).toEqual(["En az bir büyük harf içermeli."])
    expect(passwordRuleErrors("Rakamsizparola")).toEqual(["En az bir rakam içermeli."])
    expect(passwordRuleErrors("Şifre1234")).toEqual([])
  })
})

describe("validatePasswordForm", () => {
  const ok = { current: "Eskisifre1", next: "Yenisifre1", confirm: "Yenisifre1" }

  it("accepts a valid form", () => {
    expect(validatePasswordForm(ok)).toBeNull()
  })

  it.each([
    [{ current: "" }, /Mevcut parolanızı/],
    [{ next: "kisa", confirm: "kisa" }, /Yeni parola: en az 8/],
    [{ confirm: "Baskasi1" }, /tekrarı aynı değil/],
    [{ next: "Eskisifre1", confirm: "Eskisifre1" }, /farklı olmalı/],
  ])("rejects %o", (patch, message) => {
    expect(validatePasswordForm({ ...ok, ...patch })).toMatch(message)
  })
})

describe("changePassword", () => {
  it("POSTs current and new password", async () => {
    mockApi.mockResolvedValueOnce({ message: "Password changed successfully" })
    await changePassword("Eskisifre1", "Yenisifre1")
    expect(mockApi).toHaveBeenCalledWith(CHANGE_PASSWORD_ENDPOINT, {
      method: "POST",
      body: JSON.stringify({ current_password: "Eskisifre1", new_password: "Yenisifre1" }),
    })
  })
})

describe("describePasswordError", () => {
  it("translates a wrong current password and a rule violation", () => {
    expect(describePasswordError(new ApiError(400, "Invalid current password", "Invalid current password"))).toBe(
      "Mevcut parola yanlış.",
    )
    expect(describePasswordError(new ApiError(422, "Request failed (422)", []))).toMatch(/kurallara/)
    expect(describePasswordError(new ApiError(500, "x"))).toBeNull()
  })
})
