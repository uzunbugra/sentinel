import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import userEvent from "@testing-library/user-event"
import { render, screen, waitFor } from "@testing-library/react"

vi.mock("@/lib/auth", async (orig) => ({ ...(await orig()), apiRequest: vi.fn() }))

// Capture the props the graph stub receives so we can assert data flow.
const graphProps: { graphData?: { nodes: unknown[]; links: unknown[] } } = {}
vi.mock("next/dynamic", () => ({
  default: () => {
    const Stub = (props: Record<string, unknown>) => {
      graphProps.graphData = props.graphData as { nodes: unknown[]; links: unknown[] }
      return <div data-testid="force-graph-stub" />
    }
    return Stub
  },
}))

import { apiRequest, ApiError } from "@/lib/auth"
import { config } from "@/lib/config"
import { NetworkGraph } from "./network-graph"

const mockApi = vi.mocked(apiRequest)

/** Sample payload matching the component's GraphData interface. */
function sampleData() {
  return {
    nodes: [
      { id: "ACC0001", label: "Hesap 1", group: 2, amount_total: 5000, tx_count: 3 },
      {
        id: "ACC0002",
        label: "Hesap 2",
        group: 1,
        amount_total: 12000,
        tx_count: 5,
        is_fraud: true,
      },
      { id: "ACC0003", label: "Hesap 3", group: 0, amount_total: 700, tx_count: 1 },
    ],
    links: [
      { source: "ACC0001", target: "ACC0002", amount: 4200, is_fraud: true },
      { source: "ACC0002", target: "ACC0003", amount: 900 },
    ],
  }
}

beforeEach(() => {
  mockApi.mockReset()
  graphProps.graphData = undefined
  vi.stubGlobal("ResizeObserver", class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 800 })
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 600 })
})

afterEach(() => {
  vi.unstubAllGlobals()
  delete (HTMLElement.prototype as any).clientWidth
  delete (HTMLElement.prototype as any).clientHeight
})

describe("NetworkGraph", () => {
  it("fetches through the auth client and flows data to the graph", async () => {
    mockApi.mockResolvedValue(sampleData())

    render(<NetworkGraph />)

    expect(mockApi).toHaveBeenCalledWith(
      `${config.endpoints.graphData}?limit=100&hours=24&include_fraud_only=false`
    )

    expect(await screen.findByText("3 düğüm")).toBeInTheDocument()
    expect(screen.getByTestId("force-graph-stub")).toBeInTheDocument()

    await waitFor(() => {
      expect(graphProps.graphData?.nodes.length).toBe(3)
    })
    expect(graphProps.graphData?.links.length).toBe(2)
  })

  it("falls back to demo data on error and recovers via Tekrar dene", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(0, "Network error"))

    render(<NetworkGraph />)

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("Sunucuya ulaşılamıyor. Bağlantınızı kontrol edin.")
    expect(alert).toHaveTextContent("Demo verisi gösteriliyor.")
    expect(screen.getByText("30 düğüm")).toBeInTheDocument()
    expect(screen.getByTestId("force-graph-stub")).toBeInTheDocument()

    mockApi.mockResolvedValue(sampleData())
    await userEvent.click(screen.getByRole("button", { name: "Tekrar dene" }))

    expect(await screen.findByText("3 düğüm")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("shows the empty state when there is no data and skips the graph", async () => {
    mockApi.mockResolvedValue({ nodes: [], links: [] })

    render(<NetworkGraph />)

    expect(await screen.findByText("Henüz işlem verisi yok")).toBeInTheDocument()
    expect(screen.queryByTestId("force-graph-stub")).not.toBeInTheDocument()
    expect(graphProps.graphData).toBeUndefined()
  })
})
