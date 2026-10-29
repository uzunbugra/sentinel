import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { AlertFeed } from "./alert-feed"

afterEach(() => { vi.useRealTimers() })

describe("Alarm akışı tarihleri", () => {
  it("eski alarm tarihini İstanbul gününe çevirir ve göreli metinleri korur", () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-10-14T22:00:00Z"))
    const alert = {
      alert_id: "ALT-1", fraud_type: "circular_ring", severity: "high" as const,
      confidence: 0.9, amount: 100, detected_at: "2026-10-12T21:30:00+00:00",
    }
    render(<AlertFeed alerts={[
      alert,
      { ...alert, alert_id: "ALT-2", detected_at: "2026-10-14T21:55:00Z" },
      { ...alert, alert_id: "ALT-3", detected_at: "2026-10-14T21:59:50Z" },
    ]} />)
    expect(screen.getByText("13.10.2026")).toBeInTheDocument()
    expect(screen.getByText("5m ago")).toBeInTheDocument()
    expect(screen.getByText("Just now")).toBeInTheDocument()
  })
})
