import { test as base } from "@playwright/test"
import { API_URL } from "./env"
import { expect, login } from "./fixtures"

// Scenario 3: the dashboard's model card without a model and when the API fails.
// The e2e backend runs without a fraud model (playwright.config.ts).
const test = base

function modelCard(page: import("@playwright/test").Page) {
  return page.getByRole("region", { name: "aktif model" })
}

test("without a loaded model the dashboard says so and rule alerts keep working", async ({
  page,
  request,
}) => {
  const health = await (await request.get(`${API_URL}/api/v1/system/health`)).json()
  expect(health.components.ml_model.status, "the e2e API must run without a model").toBe(
    "degraded",
  )

  await login(page, "analyst")
  const card = modelCard(page)
  await expect(card.getByText("Yüklü model yok.")).toBeVisible()
  await expect(card.getByText("ML skorlaması kapalı; kural alarmları çalışmaya devam eder.")).toBeVisible()
})

test("a failing model endpoint shows an error with a retry that recovers", async ({ page }) => {
  // Fixture: only the browser's request fails; the backend itself is untouched.
  await page.route("**/api/v1/ml/models", (route) =>
    route.fulfill({ status: 500, json: { detail: "Internal Server Error" } }),
  )
  await login(page, "analyst")
  const card = modelCard(page)
  await expect(card.getByRole("alert")).toHaveText(/Beklenmeyen bir hata oluştu\./)

  await page.unroute("**/api/v1/ml/models")
  await card.getByRole("button", { name: "Tekrar dene" }).click()
  await expect(card.getByRole("alert")).toHaveCount(0)
  await expect(card.getByText("Yüklü model yok.")).toBeVisible()
})
