import { API_URL } from "./env"
import { apiToken, expect, login, openAlert, test } from "./fixtures"

// Scenario 2 (real backend): a viewer reads alerts and cases but sees no write action.
test("viewer can read an alert and its case but gets no write actions", async ({
  page,
  request,
  alert,
}) => {
  // The case is prepared through the API as the analyst; the viewer only reads it.
  const analyst = await apiToken(request, "analyst")
  const created = await request.post(`${API_URL}/api/v1/cases`, {
    headers: { Authorization: `Bearer ${analyst}` },
    data: { title: `SF-404 viewer ${alert.tag}`, alert_ids: [alert.alertId] },
  })
  expect(created.ok(), await created.text()).toBeTruthy()
  const caseId: string = (await created.json()).case_id

  await login(page, "viewer")
  await openAlert(page, alert)
  await expect(page.getByRole("button", { name: "Vaka Oluştur", exact: true })).toHaveCount(0)
  await expect(page.getByRole("button", { name: /Reddet/ })).toHaveCount(0)

  await page.getByRole("link", { name: caseId }).click()
  await expect(page).toHaveURL(new RegExp(`/cases/${caseId}$`))
  await expect(page.getByText(`SF-404 viewer ${alert.tag}`)).toBeVisible()
  const timeline = page.getByRole("region", { name: "İşlem geçmişi" })
  await expect(timeline.getByRole("heading", { name: "Vaka oluşturuldu" })).toBeVisible()
  await expect(page.getByRole("region", { name: "Vaka işlemleri" })).toHaveCount(0)
  await expect(page.getByRole("form", { name: "Durum değiştirme" })).toHaveCount(0)

  // The hidden buttons are not the only guard: the API refuses the viewer too.
  const viewer = await apiToken(request, "viewer")
  const patched = await request.patch(`${API_URL}/api/v1/cases/${caseId}`, {
    headers: { Authorization: `Bearer ${viewer}` },
    data: { status: "investigating" },
  })
  expect(patched.status()).toBe(403)
})
