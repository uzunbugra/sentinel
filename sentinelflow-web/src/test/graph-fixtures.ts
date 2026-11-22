import type { FraudRing, GraphData } from "@/lib/graph"

export const RING_A = "TR330006100519786457841326"
export const RING_B = "TR320010009999901234567890"
export const RING_C = "TR640001200123400000000001"

export const realGraph: GraphData = {
  nodes: [
    { id: RING_A, label: RING_A, group: 1, tx_count: 2 },
    { id: RING_B, label: RING_B, group: 1, tx_count: 2 },
    { id: RING_C, label: RING_C, group: 2, tx_count: 2 },
  ],
  links: [
    { source: RING_A, target: RING_B, amount: 15000 },
    { source: RING_B, target: RING_C, amount: 14500 },
    { source: RING_C, target: RING_A, amount: 14000 },
  ],
  metadata: { is_mock: false, node_count: 3, edge_count: 3 },
}

export const mockGraph: GraphData = { nodes: realGraph.nodes, links: realGraph.links, metadata: { is_mock: true } }

export const ring: FraudRing = {
  ring_id: "RING-0001",
  accounts: [RING_A, RING_B, RING_C, RING_A],
  total_amount: 43500,
  transaction_count: 3,
  detected_at: "2026-11-22T10:00:00Z",
  severity: "critical",
}
