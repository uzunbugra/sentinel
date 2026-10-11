import { apiRequest, ApiError } from "./auth"
import { config } from "./config"
import { describeError } from "@/components/ui/request-state"

export type CasePriority = "P1" | "P2" | "P3" | "P4"
export type CaseStatus = "new" | "triage" | "investigating" | "escalated" | "pending_info"
  | "resolved_true_positive" | "resolved_false_positive" | "closed"

// Handwritten API types governed by docs/contracts/sprint3-case-api.md.
export interface Case {
  case_id: string
  title: string
  description: string
  status: CaseStatus
  priority: CasePriority
  primary_fraud_type: string | null
  fraud_types: string[]
  alert_ids: string[]
  alert_count: number
  total_amount: number
  max_severity: string
  avg_confidence: number
  involved_accounts: string[]
  involved_transactions: string[]
  assigned_to: string | null
  assigned_team: string | null
  tags: string[]
  created_at: string
  updated_at: string
  first_alert_at: string | null
  last_alert_at: string | null
  sla_due_at: string | null
  sla_breached: boolean
  resolution: string | null
  resolved_at: string | null
  resolved_by: string | null
}

export interface CaseCreateRequest {
  title: string
  description?: string
  alert_ids: [string, ...string[]]
  priority?: CasePriority
  tags?: string[]
  assigned_to?: string | null
  assigned_team?: string | null
}

export interface CaseErrorDetail {
  code: string
  message: string
  alert_id?: string
  case_id?: string
}

export function createCaseFromAlert(request: CaseCreateRequest): Promise<Case> {
  return apiRequest<Case>(config.endpoints.cases, {
    method: "POST", body: JSON.stringify(request),
  })
}

export function linkAlertToCase(caseId: string, alertId: string): Promise<Case> {
  return apiRequest<Case>(config.endpoints.caseAlerts(caseId), {
    method: "POST", body: JSON.stringify({ alert_id: alertId }),
  })
}

export interface OpenCaseList {
  cases: Case[]
  truncated: boolean
}

export async function listOpenCases(): Promise<OpenCaseList> {
  const cases: Case[] = []
  let total = 0
  for (let page = 1; page <= 5; page += 1) {
    const response = await apiRequest<{ cases: Case[]; total: number }>(
      `${config.endpoints.cases}?is_open=true&page_size=100&page=${page}`
    )
    cases.push(...response.cases)
    total = response.total ?? cases.length
    if (cases.length >= total || response.cases.length === 0) break
  }
  return { cases, truncated: cases.length === 500 && total > cases.length }
}

export function caseErrorCode(err: unknown): string | null {
  if (!(err instanceof ApiError) || !err.detail || typeof err.detail !== "object" || Array.isArray(err.detail)) return null
  return "code" in err.detail && typeof err.detail.code === "string" ? err.detail.code : null
}

export function linkedCaseId(err: unknown): string | null {
  if (caseErrorCode(err) !== "alert_already_linked" || !(err instanceof ApiError)) return null
  const detail = err.detail as Partial<CaseErrorDetail>
  return typeof detail.case_id === "string" && detail.case_id ? detail.case_id : null
}

export function describeCaseError(err: unknown): string {
  switch (caseErrorCode(err)) {
    case "alert_already_linked":
      return linkedCaseId(err) ? `Bu alarm zaten ${linkedCaseId(err)} vakasına bağlı.` : "Bu alarm zaten bir vakaya bağlı."
    case "alert_dismissed": return "Reddedilmiş alarm vakaya bağlanamaz."
    case "case_not_open": return "Seçilen vaka kapalı; alarm eklenemez."
    case "invalid_status_transition": return "Bu durum değişikliğine izin verilmiyor."
    case "resolution_required": return "Bu durum için çözüm açıklaması zorunlu."
    case "unsupported_field": return "Bu alan bu ekrandan değiştirilemez."
    default: return describeError(err)
  }
}

export type CaseEventType =
  | "case_created"
  | "alert_linked_to_case"
  | "case_status_changed"
  | "case_priority_changed"
  | "case_assigned"
  | "note_added"

export interface CaseEvent {
  event_id: string
  case_id: string
  event_type: CaseEventType
  actor: string
  actor_type: string
  description: string
  previous_value: string | null
  new_value: string | null
  alert_id: string | null
  created_at: string
}

export interface CaseEventListResponse {
  total: number
  page: number
  page_size: number
  events: CaseEvent[]
}

export interface CaseUpdateRequest {
  status?: CaseStatus
  priority?: CasePriority
  assigned_to?: string | null
  assigned_team?: string | null
  resolution?: string | null
  note?: string
}

export function getCase(id: string): Promise<Case> {
  return apiRequest<Case>(config.endpoints.caseDetail(id))
}

export function listCaseEvents(
  id: string,
  { page = 1, pageSize = 20, eventType }: {
    page?: number
    pageSize?: number
    eventType?: CaseEventType
  } = {},
): Promise<CaseEventListResponse> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (eventType) params.set("event_type", eventType)
  return apiRequest<CaseEventListResponse>(`${config.endpoints.caseEvents(id)}?${params}`)
}

export function updateCase(id: string, patch: CaseUpdateRequest): Promise<Case> {
  return apiRequest<Case>(config.endpoints.caseDetail(id), {
    method: "PATCH",
    body: JSON.stringify(patch),
  })
}

const openStatuses: CaseStatus[] = [
  "new", "triage", "investigating", "escalated", "pending_info",
]

export function allowedTransitions(status: CaseStatus): CaseStatus[] {
  if (status === "closed") return []
  if (status === "resolved_true_positive" || status === "resolved_false_positive") {
    return ["closed", "investigating"]
  }
  return [
    ...openStatuses.filter((target) => target !== status),
    "resolved_true_positive", "resolved_false_positive", "closed",
  ]
}
