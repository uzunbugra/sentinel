import { expect, login, openAlert, test } from "./fixtures"

// Scenario 1 (real backend): login → alert → case → status change → timeline.
test("analyst turns an alert into a case and the timeline records each step", async ({
  page,
  alert,
}) => {
  await login(page, "analyst")
  await openAlert(page, alert)

  await page.getByRole("button", { name: "Vaka Oluştur", exact: true }).click()
  const dialog = page.getByRole("dialog", { name: "Alarmı vakaya bağla" })
  await dialog.getByLabel("Başlık").fill(`SF-404 ${alert.tag}`)
  await dialog.getByRole("button", { name: "Vaka oluştur", exact: true }).click()
  await expect(dialog).toBeHidden()

  const caseLink = page.getByRole("link", { name: /^CASE-/ })
  await expect(caseLink).toBeVisible()
  const caseId = (await caseLink.textContent())!.trim()
  await caseLink.click()
  await expect(page).toHaveURL(new RegExp(`/cases/${caseId}$`))
  await expect(page.getByText(`SF-404 ${alert.tag}`)).toBeVisible()

  const timeline = page.getByRole("region", { name: "İşlem geçmişi" })
  await expect(timeline.getByRole("heading", { name: "Vaka oluşturuldu" })).toBeVisible()
  await expect(timeline.getByRole("heading", { name: "Alarm bağlandı" })).toBeVisible()
  await expect(timeline.getByText(`Alarm: ${alert.alertId}`)).toBeVisible()

  const statusForm = page.getByRole("form", { name: "Durum değiştirme" })
  await statusForm.getByLabel("Yeni durum").selectOption("investigating")
  await statusForm.getByRole("button", { name: "Durumu kaydet" }).click()

  const statusEvent = timeline.getByRole("listitem").filter({
    has: page.getByRole("heading", { name: "Durum değişti" }),
  })
  await expect(statusEvent).toBeVisible()
  await expect(statusEvent).toContainText("new → investigating")
  await expect(statusEvent).toContainText("e2e_analyst")
})
