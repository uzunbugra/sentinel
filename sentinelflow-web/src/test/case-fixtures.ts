import type { Case, CaseEvent, CaseEventListResponse } from "@/lib/cases"

export const sampleCase: Case = {
  case_id: "CASE-001",
  title: "Transfer incelemesi",
  description: "Şüpheli transfer zinciri",
  status: "new",
  priority: "P3",
  primary_fraud_type: "circular_ring",
  fraud_types: ["circular_ring"],
  alert_ids: ["ALT-1", "ALT-2"],
  alert_count: 2,
  total_amount: 150000,
  max_severity: "high",
  avg_confidence: 0.9,
  involved_accounts: [],
  involved_transactions: [],
  assigned_to: null,
  assigned_team: null,
  tags: [],
  created_at: "2026-10-12T21:30:00+00:00",
  updated_at: "2026-10-12T21:30:00+00:00",
  first_alert_at: null,
  last_alert_at: null,
  sla_due_at: "2026-10-15T21:30:00+00:00",
  sla_breached: true,
  resolution: null,
  resolved_at: null,
  resolved_by: null,
}

export const sampleEvent: CaseEvent = {
  event_id: "EVT-001",
  case_id: sampleCase.case_id,
  event_type: "case_status_changed",
  actor: "analyst1",
  actor_type: "user",
  description: "İnceleme başlatıldı",
  previous_value: "new",
  new_value: "investigating",
  alert_id: null,
  created_at: "2026-10-12T21:30:00+00:00",
}

export const sampleEvents: CaseEventListResponse = {
  total: 1,
  page: 1,
  page_size: 20,
  events: [sampleEvent],
}
