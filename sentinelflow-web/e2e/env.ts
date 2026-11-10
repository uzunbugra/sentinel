import { existsSync } from "node:fs"
import path from "node:path"

/** Repository root (the web app lives in `sentinelflow-web/`). */
export const REPO_ROOT = path.resolve(__dirname, "..", "..")

export const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000"
/** Must match NEXT_PUBLIC_API_URL of the web build (default http://127.0.0.1:8000). */
export const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000"

// The virtualenv layout differs on Windows (Scripts/python.exe) and elsewhere (bin/python).
const venvPython = [
  path.join(REPO_ROOT, ".venv", "bin", "python"),
  path.join(REPO_ROOT, ".venv", "Scripts", "python.exe"),
].find((candidate) => existsSync(candidate))
/** Python with the sentinelflow package; it runs the API and scripts/e2e_seed.py. */
export const PYTHON = process.env.E2E_PYTHON ?? venvPython ?? "python"

export const USERS = {
  analyst: "e2e_analyst",
  viewer: "e2e_viewer",
} as const

export function e2ePassword(): string {
  const password = process.env.E2E_PASSWORD
  if (!password) {
    throw new Error("E2E_PASSWORD is not set (the e2e users' password, see e2e/README.md)")
  }
  return password
}
