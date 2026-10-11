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

export async function listOpenCases(): Promise<Case[]> {
  const response = await apiRequest<{ cases: Case[] }>(
    `${config.endpoints.cases}?is_open=true&page_size=100`
  )
  return response.cases
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
    default: return describeError(err)
  }
}
