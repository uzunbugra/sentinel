import { test } from "@playwright/test"
import { API_URL } from "./env"
import { apiToken, expect, login } from "./fixtures"

// Scenario 4 (SF-521): the transaction scoring tool. The e2e API runs without a
// fraud model, so the real backend answers 503; the scored view is drawn from
// a routed response with the contract's shape.

const scored = {
  transaction_id: "TXN-E2E-SCORE",
  model_version: "fraud-lgbm-20261030-0e0c647",
  feature_set_version: "fs-1",
  score: 0.99867,
  threshold: 0.11301,
  is_fraud: true,
  contribution_unit: "log_odds",
  base_value: -3.2,
  top_features: [
    { feature: "log_amount", value: 10.13, contribution: 2.4 },
    { feature: "payment_type_code", value: 2, contribution: 1.1 },
    { feature: "hour", value: 13, contribution: -0.2 },
    { feature: "cross_border", value: 0, contribution: -0.1 },
    { feature: "sender_seconds_since_prev", value: -1, contribution: 0.05 },
  ],
  history_cold_start: true,
  latency_ms: 1.2,
}

test("analyst opens scoring from the header; without a model the page says so", async ({
  page,
}) => {
  await login(page, "analyst")
  // Login lands on the dashboard, whose own header carries the link.
  await page.getByRole("link", { name: "Skorlama" }).click()
  await expect(page).toHaveURL(/\/score$/)
  await expect(page.getByText(/hesap geçmişi\s+değişmez/)).toBeVisible()

  await page.getByRole("button", { name: "Skorla" }).click()
  await expect(page.getByText("Model yüklü değil; işlem skorlanamadı.")).toBeVisible()
})

test("a scored transaction shows decision, score, threshold and five contributions", async ({
  page,
}) => {
  await page.route("**/api/v1/risk/score", (route) => route.fulfill({ status: 200, json: scored }))
  await login(page, "analyst")
  await page.goto("/score")
  await page.getByRole("button", { name: "Skorla" }).click()

  const result = page.getByRole("region", { name: "Skor sonucu" })
  await expect(result.getByTestId("score-decision")).toHaveText(/şüpheli/)
  await expect(result.getByText("0.9987", { exact: true })).toBeVisible()
  await expect(result.getByText("0.1130", { exact: true })).toBeVisible()
  await expect(result.getByRole("row")).toHaveCount(6) // header + top 5
})

test("viewer has no scoring link or form, and the API refuses the viewer", async ({
  page,
  request,
}) => {
  await login(page, "viewer")
  await expect(page.getByRole("link", { name: "Skorlama" })).toHaveCount(0)
  await page.goto("/score")
  await expect(page.getByRole("button", { name: "Skorla" })).toHaveCount(0)
  await expect(page.getByText(/analist ve yönetici rolleri içindir/)).toBeVisible()

  const viewer = await apiToken(request, "viewer")
  const res = await request.post(`${API_URL}/api/v1/risk/score`, {
    headers: { Authorization: `Bearer ${viewer}` },
    data: {
      sender_iban: "TR000000000000000000000001",
      sender_name: "Demo Gönderen",
      receiver_iban: "TR000000000000000000000002",
      receiver_name: "Demo Alıcı",
      amount: 100,
    },
  })
  expect(res.status()).toBe(403)
})
