import { beforeEach, describe, expect, it, vi } from "vitest"
import userEvent from "@testing-library/user-event"
import { render, screen, within } from "@testing-library/react"
import type { User } from "@/lib/auth"
import type { GraphData } from "@/lib/graph"

const mocks = vi.hoisted(() => ({ user: null as User | null }))
vi.mock("@/lib/auth", async (orig) => ({ ...(await orig()), apiRequest: vi.fn() }))
vi.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({
    user: mocks.user,
    isLoading: false,
    isAuthenticated: !!mocks.user,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}))
vi.mock("@/hooks/use-websocket", () => ({
  useWebSocket: () => ({ isConnected: false, alerts: [] }),
}))
// The force graph needs a canvas; the page test only checks what it is given.
vi.mock("@/components/dashboard/network-graph", () => ({
  NetworkGraph: ({ data, title }: { data: GraphData; title?: string }) => (
    <div data-testid="network-graph" aria-label={title}>
      {data.nodes.length} düğüm
    </div>
  ),
}))

import { apiRequest, ApiError } from "@/lib/auth"
import { config } from "@/lib/config"
import { mockGraph, realGraph, ring, RING_B } from "@/test/graph-fixtures"
import GraphPage from "./page"

const mockApi = vi.mocked(apiRequest)

beforeEach(() => {
  mocks.user = {
    user_id: "u1",
    username: "viewer",
    email: "viewer@example.com",
    full_name: "Demo viewer",
    role: "viewer",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
  }
  mockApi.mockReset()
})

describe("GraphPage", () => {
  it("says Neo4j is not running instead of showing sample data", async () => {
    mockApi.mockResolvedValueOnce(mockGraph)
    render(<GraphPage />)
    expect(await screen.findByText(/Neo4j\) bu ortamda çalışmıyor/)).toBeInTheDocument()
    expect(screen.queryByTestId("network-graph")).not.toBeInTheDocument()
    expect(mockApi).toHaveBeenCalledTimes(1)
  })

  it("shows the graph and rings to a viewer, and opens a ring account", async () => {
    mockApi.mockResolvedValueOnce(realGraph).mockResolvedValueOnce([ring])
    render(<GraphPage />)
    expect(await screen.findByLabelText("İşlem ağı (son 24 saat)")).toHaveTextContent("3 düğüm")
    const item = screen.getByRole("listitem", { name: "RING-0001" })
    expect(item).toHaveTextContent("Kritik")
    expect(within(item).getAllByRole("button")).toHaveLength(3)

    mockApi.mockResolvedValueOnce(realGraph)
    await userEvent.click(within(item).getByRole("button", { name: `${RING_B} komşuluğunu göster` }))
    expect(await screen.findByTestId("account-summary")).toHaveTextContent("3 hesap, 3 işlem")
    expect(mockApi.mock.calls[2][0]).toContain(`/graph/account/${RING_B}?depth=2`)
    expect(screen.getByLabelText("IBAN")).toHaveValue(RING_B)
  })

  it("shows empty states when there is no traffic", async () => {
    mockApi.mockResolvedValueOnce({ nodes: [], links: [], metadata: { is_mock: false } }).mockResolvedValueOnce([])
    render(<GraphPage />)
    expect(await screen.findByText("Son 24 saatte grafikte işlem yok.")).toBeInTheDocument()
    expect(screen.getByText("Döngüsel transfer bulunmadı.")).toBeInTheDocument()
  })

  it("validates the IBAN before calling the API", async () => {
    mockApi.mockResolvedValueOnce(mockGraph)
    render(<GraphPage />)
    await screen.findByText(/çalışmıyor/)
    await userEvent.type(screen.getByLabelText("IBAN"), "abc")
    await userEvent.click(screen.getByRole("button", { name: "Göster" }))
    expect(screen.getByRole("alert")).toHaveTextContent(/Geçerli bir IBAN/)
    expect(mockApi).toHaveBeenCalledTimes(1)
  })

  it("explains a missing account and a stopped graph database", async () => {
    mockApi.mockResolvedValueOnce(mockGraph)
    render(<GraphPage />)
    await screen.findByText(/çalışmıyor/)
    await userEvent.type(screen.getByLabelText("IBAN"), RING_B)

    mockApi.mockRejectedValueOnce(new ApiError(404, "Account not found"))
    await userEvent.click(screen.getByRole("button", { name: "Göster" }))
    expect(await screen.findByText(`${RING_B} için grafikte işlem bulunamadı.`)).toBeInTheDocument()

    mockApi.mockRejectedValueOnce(new ApiError(503, "Graph database not available"))
    await userEvent.click(screen.getByRole("button", { name: "Göster" }))
    expect(await screen.findByText(/hesap komşuluğu gösterilemiyor/)).toBeInTheDocument()
  })

  it("shows a readable error when the overview fails", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(403, "Forbidden"))
    render(<GraphPage />)
    expect(await screen.findByText("Bu işlem için yetkiniz yok.")).toBeInTheDocument()
  })

  it("is switched off by NEXT_PUBLIC_ENABLE_NETWORK_GRAPH=false", () => {
    const features = config.features as { enableNetworkGraph: boolean }
    features.enableNetworkGraph = false
    try {
      render(<GraphPage />)
      expect(screen.getByText("Ağ grafiği bu kurulumda kapalı.")).toBeInTheDocument()
      expect(mockApi).not.toHaveBeenCalled()
    } finally {
      features.enableNetworkGraph = true
    }
  })
})
