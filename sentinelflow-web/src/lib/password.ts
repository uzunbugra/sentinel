import { apiRequest, ApiError } from "./auth"

// `POST /api/v1/auth/change-password` (SF-524). The backend rules
// (PasswordChangeRequest): at least 8 characters, one uppercase letter and
// one digit. On success every refresh token of the user is revoked, so the
// session cannot be renewed and the user signs in again.

export const CHANGE_PASSWORD_ENDPOINT = "/api/v1/auth/change-password"

export interface PasswordForm {
  current: string
  next: string
  confirm: string
}

/** Turkish rule violations for the new password, in the backend's order. */
export function passwordRuleErrors(password: string): string[] {
  const errors: string[] = []
  if (password.length < 8) errors.push("En az 8 karakter olmalı.")
  if (!/[A-ZÇĞİÖŞÜ]/.test(password)) errors.push("En az bir büyük harf içermeli.")
  if (!/\d/.test(password)) errors.push("En az bir rakam içermeli.")
  return errors
}

/** First problem with the form, or null when it can be sent. */
export function validatePasswordForm(form: PasswordForm): string | null {
  if (!form.current) return "Mevcut parolanızı girin."
  const rule = passwordRuleErrors(form.next)[0]
  if (rule) return `Yeni parola: ${rule.charAt(0).toLocaleLowerCase("tr-TR")}${rule.slice(1)}`
  if (form.next !== form.confirm) return "Yeni parola ile tekrarı aynı değil."
  if (form.next === form.current) return "Yeni parola mevcut paroladan farklı olmalı."
  return null
}

export async function changePassword(current: string, next: string): Promise<void> {
  await apiRequest<{ message: string }>(CHANGE_PASSWORD_ENDPOINT, {
    method: "POST",
    body: JSON.stringify({ current_password: current, new_password: next }),
  })
}

/**
 * Message for a failed change. The backend answers 400 "Invalid current
 * password" for a wrong current password; other errors fall back to the
 * caller's generic description.
 */
export function describePasswordError(err: unknown): string | null {
  if (err instanceof ApiError && err.status === 400 && err.detail === "Invalid current password") {
    return "Mevcut parola yanlış."
  }
  if (err instanceof ApiError && err.status === 422) {
    return "Yeni parola kurallara uymuyor (en az 8 karakter, bir büyük harf, bir rakam)."
  }
  return null
}
