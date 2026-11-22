import { apiRequest, ApiError } from "./auth"
import { config } from "./config"

// Graph endpoints (SF-520), backed by Neo4j (src/sentinelflow/api/routes/graph.py).
//
// Without Neo4j the backend does not fail: /graph/data answers random sample
// data with `metadata.is_mock: true`, and /graph/rings answers random sample
// rings with no marker at all. The page must never present those as real, so
// the data call decides: when it is mock, Neo4j is treated as unavailable and
// the rings are not requested. /graph/account/{iban} answers 503 instead.

export interface GraphNode {
  id: string
  label: string
  group: number
  amount_total?: number
  tx_count?: number
  city?: string | null
  is_fraud?: boolean
}

export interface GraphEdge {
  source: string
  target: string
  amount: number
  timestamp?: string
  color?: string
  is_fraud?: boolean
}

export interface GraphData {
  nodes: GraphNode[]
  links: GraphEdge[]
  metadata?: Record<string, unknown>
}

export interface FraudRing {
  ring_id: string
  accounts: string[]
  total_amount: number
  transaction_count: number
  detected_at: string
  severity: string
}

export type GraphOverview =
  | { kind: "ok"; data: GraphData; rings: FraudRing[] }
  | { kind: "unavailable" }

export type AccountNetwork =
  | { kind: "ok"; data: GraphData }
  | { kind: "not_found" }
  | { kind: "unavailable" }

export function isMockGraph(data: GraphData): boolean {
  return data.metadata?.is_mock === true
}

export async function fetchGraphOverview(hours = 24, limit = 100): Promise<GraphOverview> {
  const params = new URLSearchParams({ limit: String(limit), hours: String(hours) })
  const data = await apiRequest<GraphData>(`${config.endpoints.graphData}?${params}`)
  if (isMockGraph(data)) return { kind: "unavailable" }
  const rings = await apiRequest<FraudRing[]>(config.endpoints.graphRings)
  return { kind: "ok", data, rings }
}

export async function fetchAccountNetwork(iban: string, depth = 2): Promise<AccountNetwork> {
  const params = new URLSearchParams({ depth: String(depth) })
  try {
    const data = await apiRequest<GraphData>(
      `${config.endpoints.graphAccount(encodeURIComponent(iban.trim()))}?${params}`,
    )
    return { kind: "ok", data }
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return { kind: "not_found" }
    if (err instanceof ApiError && err.status === 503) return { kind: "unavailable" }
    throw err
  }
}

/** A ring path repeats its first account at the end; list each account once. */
export function ringAccounts(ring: FraudRing): string[] {
  return Array.from(new Set(ring.accounts))
}

export function shortIban(iban: string): string {
  return iban.length > 14 ? `${iban.slice(0, 8)}…${iban.slice(-4)}` : iban
}

export function validateIban(iban: string): string | null {
  return /^[A-Z]{2}[0-9A-Z]{13,32}$/.test(iban.trim()) ? null : "Geçerli bir IBAN girin (ör. TR…)."
}
