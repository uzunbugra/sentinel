import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, render, screen } from "@testing-library/react"
import type { HTMLAttributes, ReactNode } from "react"

// Sayula agir gorseller (3D kure, network grafigi, motion) stub'lanir; auth
// istemcinde sadece apiRequest mock'lanir (ApiError sinifi gercek kalir).
vi.mock("@/lib/auth", async (orig) => ({
  ...(await orig()),
  apiRequest: vi.fn(),
}))
vi.mock("@/hooks/use-websocket", () => ({
  useWebSocket: () => ({
    status: "disconnected",
    isConnected: false,
    alerts: [],
    reconnect: vi.fn(),
    reconnectAttempts: 0,
  }),
}))
vi.mock("next/dynamic", () => ({
  default: () => {
    const Stub = () => <div data-testid="dynamic-stub" />
    return Stub
  },
}))
vi.mock("@/components/landing/NetworkGraph", () => ({
  NetworkGraph: () => <div data-testid="network-graph-stub" />,
}))
vi.mock("motion/react", () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
  motion: {
    div: (props: Record<string, unknown>) => {
      // Animasyon prop'larini DOM'a tasimayacak sekilde ayikla.
      const domProps = { ...props }
      delete domProps.initial
      delete domProps.animate
      delete domProps.exit
      delete domProps.transition
      delete domProps.layout
      return <div {...(domProps as HTMLAttributes<HTMLDivElement>)} />
    },
  },
}))

import { apiRequest, ApiError } from "@/lib/auth"
import { config } from "@/lib/config"
import DashboardPage from "./page"

const mockApi = vi.mocked(apiRequest)

// Kucuk degerler: yerel bicimleme onemsenmez (42 -> "42", 125 sn -> "2m").
const STATS = {
  transactions_processed: 42,
  fraud_detected: 7,
  fraud_rate: 0.1,
  uptime_seconds: 125,
}

beforeEach(() => {
  // Demo hook'u window.matchMedia cagirir; prefers-reduced-motion acik
  // gibi dondurerek demo interval'in kurulmasini engelleriz.
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe("DashboardPage stats", () => {
  it("backend istatistiklerini stat kartlarinda gosterir", async () => {
    mockApi.mockResolvedValueOnce(STATS)

    render(<DashboardPage />)

    expect(await screen.findByText("42")).toBeInTheDocument()
    expect(screen.getByText("7")).toBeInTheDocument()
    expect(screen.getByText("2m")).toBeInTheDocument()
    expect(mockApi).toHaveBeenCalledWith(config.endpoints.stats)
  })

  it("polling hatasi onceki degerleri korur ve hata gostergesi cikar", async () => {
    vi.useFakeTimers()
    mockApi.mockResolvedValueOnce(STATS)
    mockApi.mockRejectedValueOnce(new ApiError(0, "Network error"))

    render(<DashboardPage />)

    // Ilk poll: microtask'leri flush et ve degerlerin geldiğini dogrula.
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.getByText("42")).toBeInTheDocument()
    expect(screen.getByText("7")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()

    // Yenileme araligi kadar ilerlet; bir sonraki poll hata dondurur.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(config.ui.statsRefreshInterval)
    })

    // Eski degerler ekranda kalmali.
    expect(screen.getByText("42")).toBeInTheDocument()
    expect(screen.getByText("7")).toBeInTheDocument()
    expect(screen.getByText("2m")).toBeInTheDocument()

    // Hata gostergesi Turkish aciklamayi icermeli.
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Sunucuya ulaşılamıyor. Bağlantınızı kontrol edin.",
    )
  })
})
