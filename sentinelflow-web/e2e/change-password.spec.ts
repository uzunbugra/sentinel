import { test } from "@playwright/test"
import { API_URL, e2ePassword, USERS } from "./env"
import { expect, login } from "./fixtures"

// Scenario 6 (SF-524): a user changes their password from the header menu.
// The viewer's password is restored through the API afterwards so later
// tests (and later runs before global setup) can still sign in.

const NEW_PASSWORD = "Degisti-E2e-9"

test("viewer changes the password, signs in again with it, old one stops working", async ({
  page,
  request,
}) => {
  try {
    await login(page, "viewer")
    await page.getByRole("button", { name: "Parola değiştir" }).click()
    const dialog = page.getByRole("dialog", { name: "Parola değiştir" })

    await dialog.getByLabel("Mevcut parola").fill("Yanlis-Parola-1")
    await dialog.getByLabel("Yeni parola", { exact: true }).fill(NEW_PASSWORD)
    await dialog.getByLabel("Yeni parola (tekrar)").fill(NEW_PASSWORD)
    await dialog.getByRole("button", { name: "Parolayı değiştir" }).click()
    await expect(dialog.getByRole("alert")).toHaveText("Mevcut parola yanlış.")

    await dialog.getByLabel("Mevcut parola").fill(e2ePassword())
    await dialog.getByRole("button", { name: "Parolayı değiştir" }).click()
    await expect(dialog.getByRole("status")).toContainText("Parolanız değişti")
    await dialog.getByRole("button", { name: "Tekrar giriş yap" }).click()
    await expect(page).toHaveURL(/\/login$/)

    const old = await request.post(`${API_URL}/api/v1/auth/login`, {
      data: { username: USERS.viewer, password: e2ePassword() },
    })
    expect(old.status()).toBe(401)

    await page.getByPlaceholder("admin").fill(USERS.viewer)
    await page.getByPlaceholder("••••••••").fill(NEW_PASSWORD)
    await page.getByRole("button", { name: "Giriş Yap" }).click()
    await expect(page).toHaveURL(/\/dashboard$/)
  } finally {
    // Restore the seeded password whatever happened above.
    const signIn = await request.post(`${API_URL}/api/v1/auth/login`, {
      data: { username: USERS.viewer, password: NEW_PASSWORD },
    })
    if (signIn.ok()) {
      const token = (await signIn.json()).access_token
      const restored = await request.post(`${API_URL}/api/v1/auth/change-password`, {
        headers: { Authorization: `Bearer ${token}` },
        data: { current_password: NEW_PASSWORD, new_password: e2ePassword() },
      })
      expect(restored.ok(), await restored.text()).toBeTruthy()
    }
  }
})
