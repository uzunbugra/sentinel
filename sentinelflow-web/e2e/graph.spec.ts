import { test } from "@playwright/test"
import { expect, login } from "./fixtures"

// Scenario 8 (SF-520): the graph page against an API without Neo4j.

const A = "TR330006100519786457841326"
const B = "TR320010009999901234567890"
const C = "TR640001200123400000000001"

test("viewer opens the graph page; without Neo4j it says so instead of drawing sample data", async ({ page }) => {
  await login(page, "viewer")
  await page.getByRole("link", { name: "Ağ grafiği" }).click()
  await expect(page).toHaveURL(/\/graph$/)
  await expect(page.getByText("Graf veritabanı (Neo4j) bu ortamda çalışmıyor.")).toBeVisible()
  await expect(page.getByRole("heading", { name: /Tespit edilen para halkaları/ })).toHaveCount(0)

  await page.getByLabel("IBAN").fill(A)
  await page.getByRole("button", { name: "Göster" }).click()
  await expect(page.getByText(/hesap komşuluğu gösterilemiyor/)).toBeVisible()
})

test("with graph data, a ring account opens its neighbourhood", async ({ page }) => {
  const graph = {
    nodes: [A, B, C].map((id) => ({ id, label: id, group: 1, tx_count: 2 })),
    links: [
      { source: A, target: B, amount: 15000 },
      { source: B, target: C, amount: 14500 },
      { source: C, target: A, amount: 14000 },
    ],
    metadata: { is_mock: false },
  }
  await page.route("**/api/v1/graph/data*", (route) => route.fulfill({ json: graph }))
  await page.route("**/api/v1/graph/rings*", (route) =>
    route.fulfill({
      json: [
        {
          ring_id: "RING-0001",
          accounts: [A, B, C, A],
          total_amount: 43500,
          transaction_count: 3,
          detected_at: "2026-11-22T10:00:00Z",
          severity: "critical",
        },
      ],
    }),
  )
  await page.route("**/api/v1/graph/account/**", (route) => route.fulfill({ json: graph }))

  await login(page, "viewer")
  await page.goto("/graph")
  const ring = page.getByRole("listitem", { name: "RING-0001" })
  await expect(ring).toContainText("Kritik")
  await ring.getByRole("button", { name: `${B} komşuluğunu göster` }).click()
  await expect(page.getByTestId("account-summary")).toContainText("3 hesap, 3 işlem")
})
