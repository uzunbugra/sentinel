import { test } from "@playwright/test"
import { API_URL } from "./env"
import { apiToken, expect, login } from "./fixtures"

// Scenario 7 (SF-522): customer screening against the real API's demo lists.

test("analyst screens an alias of a sanctioned name and a clean name", async ({ page }) => {
  await login(page, "analyst")
  await page.getByRole("link", { name: "Müşteri taraması" }).click()
  await expect(page).toHaveURL(/\/kyc$/)
  await expect(page.getByRole("note")).toContainText("resmî listelere bağlı değildir")

  await page.getByLabel("Ad soyad").fill("Banned Person")
  await page.getByRole("button", { name: "Tara" }).click()
  const result = page.getByRole("region", { name: "Tarama sonucu" })
  await expect(result.getByTestId("kyc-recommendation")).toContainText("İŞLEM YAPILAMAZ")
  const row = result.getByRole("row", { name: /Yasak Kişi/ })
  await expect(row).toContainText("takma ad: Banned Person")
  await expect(row).toContainText("OFAC SDN (örnek)")

  await page.getByRole("button", { name: "Ayşe Temiz" }).click()
  await expect(result.getByTestId("kyc-recommendation")).toHaveText("Tarama temiz")
})

test("viewer gets no screening form and the API refuses the viewer", async ({ page, request }) => {
  await login(page, "viewer")
  await expect(page.getByRole("link", { name: "Müşteri taraması" })).toHaveCount(0)
  await page.goto("/kyc")
  await expect(page.getByRole("button", { name: "Tara" })).toHaveCount(0)

  const viewer = await apiToken(request, "viewer")
  const res = await request.post(`${API_URL}/api/v1/kyc/screen`, {
    headers: { Authorization: `Bearer ${viewer}` },
    data: { name: "Banned Person" },
  })
  expect(res.status()).toBe(403)
})
