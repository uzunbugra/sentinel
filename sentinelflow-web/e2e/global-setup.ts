import { e2ePassword } from "./env"
import { seed } from "./seed"

/** Creates (or resets) the analyst and viewer accounts every test logs in with. */
export default function globalSetup(): void {
  e2ePassword()
  seed("users")
}
