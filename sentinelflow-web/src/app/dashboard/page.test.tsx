import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, render, screen } from "@testing-library/react"
import type { HTMLAttributes, ReactNode } from "react"

// Sayula agir gorseller (3D kure, network grafigi, motion) stub'lanir; auth
// istemcinde sadece apiRequest mock'lanir (ApiError sinifi gercek kalir).
vi.mock("@/lib/auth", async (orig) => ({
  ...(await orig()),
  apiRequest: vi.fn(),
}))
const authMock = vi.hoisted(() => ({ role: "analyst" as "analyst" | "viewer" }))
vi.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({
    user: { full_name: "Demo", role: authMock.role },
    isAuthenticated: true,
    logout: vi.fn(),
  }),
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
// The chat panel calls its own endpoints and has its own tests.
vi.mock("@/components/dashboard/ai-chat", () => ({ AiChat: () => <section aria-label="Yardım asistanı" /> }))
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
import { loadedModelResponse } from "@/test/ml-fixtures"
import DashboardPage from "./page"

const mockApi = vi.mocked(apiRequest)

const REST_ALERT = {
  alert_id: "ALERT-REST00000001",
  fraud_type: "ml_model",
  severity: "critical",
  description: "Fraud model flagged the transaction",
  amount: 25000,
  currency: "TRY",
  detected_at: "2026-11-22T11:54:02Z",
}

// Aktif model karti /ml/models'i, alarm konsolu /alerts'i ayri ister;
// istatistik cevaplari sirayla verilir.
type StatsResult =
  | (typeof STATS & { alerts_created?: number; by_severity?: Record<string, number> })
  | Error

function routeApi(...statsResults: StatsResult[]) {
  mockApi.mockImplementation(async (endpoint: string) => {
    if (endpoint === config.endpoints.modelInfo) return loadedModelResponse
    if (endpoint.startsWith(`${config.endpoints.alerts}?`)) {
      return { alerts: alertsResult }
    }
    const next = statsResults.shift()
    if (next instanceof Error) throw next
    return next ?? new Promise(() => {})
  })
}

// Kucuk degerler: yerel bicimleme onemsenmez (42 -> "42", 125 sn -> "2m").
const STATS = {
  transactions_processed: 42,
  fraud_detected: 7,
  fraud_rate: 0.1,
  uptime_seconds: 125,
}

let alertsResult: unknown[] = []

beforeEach(() => {
  alertsResult = []
})

afterEach(() => {
  vi.useRealTimers()
})

describe("DashboardPage stats", () => {
  it("backend istatistiklerini stat kartlarinda gosterir", async () => {
    routeApi(STATS)

    render(<DashboardPage />)

    expect(await screen.findByText("42")).toBeInTheDocument()
    expect(screen.getByText("7")).toBeInTheDocument()
    expect(screen.getByText("2m")).toBeInTheDocument()
    expect(mockApi).toHaveBeenCalledWith(config.endpoints.stats)
  })

  it("polling hatasi onceki degerleri korur ve hata gostergesi cikar", async () => {
    vi.useFakeTimers()
    routeApi(STATS, new ApiError(0, "Network error"))

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

describe("DashboardPage gercek veri", () => {
  it("backend'e ulasilamazken uydurma sayi veya alarm gostermez", async () => {
    routeApi(new ApiError(0, "Network error"))

    render(<DashboardPage />)

    expect(await screen.findByRole("alert")).toBeInTheDocument()
    expect(screen.getAllByText("---")).toHaveLength(4)
    expect(screen.queryByText(/^ALERT-/)).not.toBeInTheDocument()
    expect(screen.queryByText("99.4%")).not.toBeInTheDocument()
    expect(screen.getByText("offline")).toBeInTheDocument()
  })

  it("son alarmlari REST'ten listeler ve kayitli alarm sayisini gosterir", async () => {
    alertsResult = [REST_ALERT]
    routeApi({ ...STATS, alerts_created: 3, by_severity: { critical: 2, low: 1 } })

    render(<DashboardPage />)

    expect(await screen.findByText("ALERT-REST00000001")).toBeInTheDocument()
    expect(screen.getByText("3")).toBeInTheDocument()
    expect(screen.getByText("kayitli alarm")).toBeInTheDocument()
    expect(mockApi).toHaveBeenCalledWith(
      `${config.endpoints.alerts}?page=1&page_size=12`,
    )
  })

  it("alarm yoksa bos durum gosterir", async () => {
    routeApi({ ...STATS, alerts_created: 0 })

    render(<DashboardPage />)

    expect(await screen.findByText("Henuz alarm yok")).toBeInTheDocument()
  })
})

describe("DashboardPage aktif model", () => {
  it("sistem panelinde aktif model ozetini gosterir", async () => {
    routeApi(STATS)

    render(<DashboardPage />)

    expect(await screen.findByText("fraud-lgbm-20261105-a1b2c3d")).toBeInTheDocument()
    expect(mockApi).toHaveBeenCalledWith(config.endpoints.modelInfo)
  })
})

describe("DashboardPage gezinme", () => {
  it("skorlama baglantisini analiste gosterir, viewer'a gostermez", async () => {
    routeApi(STATS)
    authMock.role = "analyst"
    const { unmount } = render(<DashboardPage />)
    expect(await screen.findByRole("link", { name: "Skorlama" })).toHaveAttribute("href", "/score")
    unmount()

    routeApi(STATS)
    authMock.role = "viewer"
    render(<DashboardPage />)
    expect(await screen.findByText("42")).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "Skorlama" })).not.toBeInTheDocument()
    authMock.role = "analyst"
  })
})

describe("DashboardPage bayraklar", () => {
  const features = config.features as { enableAiChat: boolean; enableNetworkGraph: boolean }
  afterEach(() => {
    features.enableAiChat = true
    features.enableNetworkGraph = true
  })

  it("yardim asistanini ve ag grafigi baglantisini bayraga gore gosterir", async () => {
    routeApi(STATS)
    const { unmount } = render(<DashboardPage />)
    expect(await screen.findByRole("region", { name: "Yardım asistanı" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Ağ grafiği" })).toHaveAttribute("href", "/graph")
    unmount()

    features.enableAiChat = false
    features.enableNetworkGraph = false
    routeApi(STATS)
    render(<DashboardPage />)
    expect(await screen.findByText("42")).toBeInTheDocument()
    expect(screen.queryByRole("region", { name: "Yardım asistanı" })).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "Ağ grafiği" })).not.toBeInTheDocument()
  })
})
