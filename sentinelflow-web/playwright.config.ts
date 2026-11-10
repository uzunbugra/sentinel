// =============================================================================
// SentinelFlow - Browser tests (SF-404)
// =============================================================================
// Runs against a real API and the production web build. See e2e/README.md.
//
// The API and the web server are started here unless they are already running
// (CI starts them itself so their logs can be uploaded). The API must run
// without a fraud model: e2e/model-state.spec.ts checks that state.

import { defineConfig, devices } from "@playwright/test"
import { API_URL, BASE_URL, REPO_ROOT, PYTHON } from "./e2e/env"

const CI = !!process.env.CI

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  // One backend and one database for every test: run them one at a time.
  fullyParallel: false,
  workers: 1,
  // No retries: a flaky test fails the job instead of passing on a second try.
  retries: 0,
  forbidOnly: CI,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: CI
    ? [["list"], ["github"], ["html", { open: "never" }]]
    : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: BASE_URL,
    locale: "tr-TR",
    timezoneId: "Europe/Istanbul",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `"${PYTHON}" -m uvicorn sentinelflow.api.app:app --host 127.0.0.1 --port 8000`,
      cwd: REPO_ROOT,
      url: `${API_URL}/api/v1/system/health`,
      reuseExistingServer: true,
      timeout: 60_000,
      stdout: "pipe",
      env: { PYTHONPATH: "src" },
    },
    {
      command: "npm run start -- --hostname 127.0.0.1 --port 3000",
      url: BASE_URL,
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
})
