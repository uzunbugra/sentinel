import { test } from "@playwright/test"
import { expect, login } from "./fixtures"

// Scenario 9 (SF-525): the rule-based assistant on the dashboard, real API.

test("viewer asks the rule-based assistant from the dashboard", async ({ page }) => {
  await login(page, "viewer")
  const panel = page.getByRole("region", { name: "Yardım asistanı" })
  await expect(panel.getByRole("note")).toContainText("LLM) kullanmaz")

  await panel.getByRole("group", { name: "Önerilen sorular" }).getByRole("button", { name: "Döngüsel transfer nedir?" }).click()
  const log = panel.getByRole("log", { name: "Sohbet" })
  await expect(log).toContainText("A → B → C → A")
  await expect(log.locator("strong").first()).toBeVisible()

  await panel.getByLabel("Mesaj").fill("MASAK eşiği ne kadar?")
  await panel.getByRole("button", { name: "Gönder" }).click()
  await expect(log).toContainText("75.000 TL")
})
