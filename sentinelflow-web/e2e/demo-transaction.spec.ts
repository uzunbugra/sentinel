import { test } from "@playwright/test"
import { expect, login } from "./fixtures"

// Scenario 5 (SF-523): the dashboard's demo transaction form against the real
// API. The e2e API runs without a model, so the transaction is recorded but
// not scored; the fraud path (alert id in the result) is drawn from a routed
// response with the API's shape.

test("analyst sends a demo transaction; without a model it is recorded unscored", async ({
  page,
}) => {
  await login(page, "analyst")
  const form = page.getByRole("region", { name: "Demo işlem gönder" })
  await expect(form.getByText(/Yalnız sentetik hesaplar/)).toBeVisible()

  const response = page.waitForResponse("**/api/v1/transactions")
  await form.getByRole("button", { name: "Gönder" }).click()
  const res = await response
  expect(res.status()).toBe(200)
  const body = res.request().postDataJSON()
  expect(body.transaction_id).toMatch(/^DEMO-[0-9a-f]{16}$/)
  expect(body.sender_iban).toBe("TR000000000000000000000001")

  const result = form.getByTestId("demo-result")
  await expect(result).toContainText(body.transaction_id)
  await expect(result).toContainText("Model yüklü olmadığı için işlem skorlanmadı.")
})

test("a fraud result names the alert and links to the alert list", async ({ page }) => {
  await page.route("**/api/v1/transactions", (route) =>
    route.fulfill({
      status: 200,
      json: {
        transaction_id: "DEMO-e2e",
        status: "analyzed",
        message: "Fraud detected!",
        is_fraud: true,
        fraud_score: 0.99867,
        model_version: "fraud-lgbm-20261030-0e0c647",
        alerts: [{ alert_id: "ALT-E2E-DEMO" }],
        processing_time_ms: 3.1,
      },
    }),
  )
  await login(page, "analyst")
  const form = page.getByRole("region", { name: "Demo işlem gönder" })
  await form.getByRole("button", { name: "Gönder" }).click()
  await expect(form.getByTestId("demo-result")).toContainText("ALT-E2E-DEMO")
  await form.getByRole("link", { name: "Alarmlara git" }).click()
  await expect(page).toHaveURL(/\/alerts$/)
})

test("viewer does not see the demo transaction form", async ({ page }) => {
  await login(page, "viewer")
  await expect(page.getByRole("region", { name: "aktif model" })).toBeVisible()
  await expect(page.getByRole("region", { name: "Demo işlem gönder" })).toHaveCount(0)
})
