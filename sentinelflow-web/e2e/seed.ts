import { execFileSync } from "node:child_process"
import path from "node:path"
import { PYTHON, REPO_ROOT } from "./env"

/** Runs scripts/e2e_seed.py and returns the JSON it prints on its last line. */
export function seed<T = Record<string, unknown>>(...args: string[]): T {
  const output = execFileSync(PYTHON, [path.join("scripts", "e2e_seed.py"), ...args], {
    cwd: REPO_ROOT,
    env: { ...process.env, PYTHONPATH: "src" },
    encoding: "utf-8",
    stdio: ["ignore", "pipe", "pipe"],
  })
  const lines = output.trim().split("\n")
  return JSON.parse(lines[lines.length - 1]) as T
}
