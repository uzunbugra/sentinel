import { randomBytes } from "node:crypto"
import { test as base, expect, type APIRequestContext, type Page } from "@playwright/test"
import { API_URL, e2ePassword, USERS } from "./env"
import { seed } from "./seed"

export type Role = keyof typeof USERS

export interface SeededAlert {
  tag: string
  alertId: string
  senderName: string
}

/** Logs in through the login form and waits for the dashboard. */
export async function login(page: Page, role: Role): Promise<void> {
  await page.goto("/login")
  await page.getByPlaceholder("admin").fill(USERS[role])
  await page.getByPlaceholder("••••••••").fill(e2ePassword())
  await page.getByRole("button", { name: "Giriş Yap" }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
}

/** An access token for direct API calls (test setup and RBAC checks). */
export async function apiToken(request: APIRequestContext, role: Role): Promise<string> {
  const res = await request.post(`${API_URL}/api/v1/auth/login`, {
    data: { username: USERS[role], password: e2ePassword() },
  })
  expect(res.ok(), await res.text()).toBeTruthy()
  return (await res.json()).access_token
}

/** Opens the alerts page and selects the given alert. */
export async function openAlert(page: Page, alert: SeededAlert): Promise<void> {
  await page.goto("/alerts")
  await page.getByRole("button").filter({ hasText: alert.senderName }).click()
  await expect(page.getByText(alert.alertId, { exact: true })).toBeVisible()
}

export const test = base.extend<{ alert: SeededAlert }>({
  // Each test gets its own alert; its alert, case and events are removed afterwards.
  alert: async ({}, use, testInfo) => {
    const tag = `w${testInfo.workerIndex}-${Date.now().toString(36)}-${randomBytes(3).toString("hex")}`
    const created = seed<{ alert_id: string; sender_name: string }>("alert", "--tag", tag)
    try {
      await use({ tag, alertId: created.alert_id, senderName: created.sender_name })
    } finally {
      seed("cleanup", "--tag", tag)
    }
  },
})

export { expect }
