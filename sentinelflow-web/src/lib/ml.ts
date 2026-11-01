import { apiRequest, ApiError } from "./auth"
import { config } from "./config"

// Handwritten API types governed by docs/contracts/sprint4-ml-api.md (§4.1, §4.5).
// api-schema.ts holds the OpenAPI object, not TS types; ml.contract.test.ts
// checks these against it.

export type ModelLoadStatus = "loaded" | "not_loaded" | "invalid"

/** Every numeric metric may be null; null means "not recorded", never 0. */
export interface ModelMetrics {
  split: string | null
  pr_auc: number | null
  roc_auc: number | null
  precision: number | null
  recall: number | null
  f1: number | null
  support_positive: number | null
  support_total: number | null
  baseline_pr_auc: number | null
}

export interface ActiveModel {
  model_version: string
  model_family: string
  feature_set_version: string
  feature_names: string[]
  threshold: number
  dataset_id: string
  trained_at: string
  loaded_at: string
  metrics: ModelMetrics | null
  model_sha256: string
}

export interface ModelStatusResponse {
  status: ModelLoadStatus
  model: ActiveModel | null
  error: string | null
}

/** Normalized result of `GET /ml/models` for the UI. */
export type ActiveModelState =
  | { kind: "loaded"; model: ActiveModel }
  | { kind: "unavailable"; status: "not_loaded" | "invalid"; reason: string | null }
  | { kind: "unsupported" }

export interface TopFeature {
  feature: string
  value: number | null
  contribution: number | null
}

export interface MlEvidenceDetails {
  model_version: string | null
  feature_set_version: string | null
  score: number | null
  threshold: number | null
  contribution_unit: string | null
  base_value: number | null
  top_features: TopFeature[]
  history_cold_start: boolean | null
}

/** Subset of the alert `Evidence` schema the UI reads. */
export interface AlertEvidence {
  detector_type: string
  detector_version?: string
  confidence?: number
  contribution?: number
  summary?: string
  details?: Record<string, unknown>
  related_transactions?: string[]
}

/**
 * What the alert detail can say about the model at alert time.
 * - `ml`: the alert carries the §4.5 ML evidence record.
 * - `legacy`: an ML alert without that record (old `ml_ensemble` alerts).
 * - `null`: not an ML alert.
 */
export type ModelEvaluation =
  | { kind: "ml"; details: MlEvidenceDetails; summary: string | null }
  | { kind: "legacy" }
  | null

export const ML_FRAUD_TYPES = ["ml_model", "ml_ensemble"] as const
const ML_DETECTOR = "ml_model"
const LOAD_STATUSES: readonly string[] = ["loaded", "not_loaded", "invalid"]

// -----------------------------------------------------------------------------
// Active model
// -----------------------------------------------------------------------------

export function normalizeModelStatus(body: unknown): ActiveModelState {
  if (!isRecord(body) || typeof body.status !== "string" || !LOAD_STATUSES.includes(body.status)) {
    return { kind: "unsupported" }
  }
  const reason = typeof body.error === "string" ? body.error : null
  if (body.status === "loaded" && isRecord(body.model)) {
    return { kind: "loaded", model: body.model as unknown as ActiveModel }
  }
  return {
    kind: "unavailable",
    status: body.status === "invalid" ? "invalid" : "not_loaded",
    reason,
  }
}

/**
 * The contract answers 200 with `status: not_loaded` when no model is loaded;
 * a 503 `model_not_loaded` (the `risk/score` shape) is treated the same way.
 * Every other failure is rethrown for the caller's error state.
 */
export async function fetchActiveModel(): Promise<ActiveModelState> {
  try {
    const body = await apiRequest<unknown>(config.endpoints.modelInfo)
    return normalizeModelStatus(body)
  } catch (err) {
    if (err instanceof ApiError && err.status === 503) {
      const detail = isRecord(err.detail) ? err.detail : {}
      return {
        kind: "unavailable",
        status: detail.status === "invalid" ? "invalid" : "not_loaded",
        reason: typeof detail.message === "string" ? detail.message : null,
      }
    }
    throw err
  }
}

// -----------------------------------------------------------------------------
// Alert evidence
// -----------------------------------------------------------------------------

/** Reads the model evaluation recorded when the alert was raised. */
export function extractModelEvaluation(
  fraudType: string,
  evidence: readonly AlertEvidence[] | null | undefined,
): ModelEvaluation {
  const item = (evidence ?? []).find(
    (e) => e.detector_type === ML_DETECTOR && isRecord(e.details) && "score" in e.details,
  )
  if (item && isRecord(item.details)) {
    return {
      kind: "ml",
      details: parseMlDetails(item.details),
      summary: item.summary?.trim() ? item.summary : null,
    }
  }
  const isMlAlert =
    (ML_FRAUD_TYPES as readonly string[]).includes(fraudType) ||
    (evidence ?? []).some((e) => (ML_FRAUD_TYPES as readonly string[]).includes(e.detector_type))
  return isMlAlert ? { kind: "legacy" } : null
}

function parseMlDetails(d: Record<string, unknown>): MlEvidenceDetails {
  const features = Array.isArray(d.top_features) ? d.top_features : []
  return {
    model_version: str(d.model_version),
    feature_set_version: str(d.feature_set_version),
    score: num(d.score),
    threshold: num(d.threshold),
    contribution_unit: str(d.contribution_unit),
    base_value: num(d.base_value),
    top_features: features.filter(isRecord).map((f) => ({
      feature: str(f.feature) ?? "—",
      value: num(f.value),
      contribution: num(f.contribution),
    })),
    history_cold_start: typeof d.history_cold_start === "boolean" ? d.history_cold_start : null,
  }
}

/** `score >= threshold` per §4.2; null when either side is missing. */
export function isAboveThreshold(score: number | null, threshold: number | null): boolean | null {
  if (score === null || threshold === null) return null
  return score >= threshold
}

// -----------------------------------------------------------------------------
// Labels and formatting
// -----------------------------------------------------------------------------

export const MISSING = "—"

export const FEATURE_LABELS: Record<string, string> = {
  log_amount: "Tutar (log)",
  hour: "Saat (UTC)",
  day_of_week: "Haftanın günü",
  payment_type_code: "Ödeme tipi",
  currency_mismatch: "Para birimi uyuşmazlığı",
  cross_border: "Sınır ötesi",
  sender_country_code: "Gönderen ülke",
  receiver_country_code: "Alıcı ülke",
  sender_tx_count_24h: "Gönderen işlem sayısı (24 sa)",
  sender_amount_sum_24h: "Gönderen tutar toplamı (24 sa)",
  sender_unique_receivers_7d: "Gönderenin farklı alıcıları (7 gün)",
  receiver_tx_count_24h: "Alıcı işlem sayısı (24 sa)",
  receiver_unique_senders_7d: "Alıcının farklı gönderenleri (7 gün)",
  pair_tx_count_7d: "Aynı çift işlem sayısı (7 gün)",
  sender_seconds_since_prev: "Önceki işlemden geçen süre (sn)",
}

export function featureLabel(name: string): string {
  return FEATURE_LABELS[name] ?? name
}

const CONTRIBUTION_UNITS: Record<string, string> = {
  log_odds:
    "Katkılar log-odds birimindedir ve bu işleme özeldir (genel özellik önemi değildir). Pozitif değer riski artırır, negatif değer azaltır.",
}

export function contributionUnitNote(unit: string | null): string {
  if (!unit) return "Katkı birimi kaydedilmemiş."
  return CONTRIBUTION_UNITS[unit] ?? `Katkı birimi: ${unit}`
}

/** Fixed-precision number; null stays visibly missing so 0 is never implied. */
export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return MISSING
  return value.toFixed(digits)
}

export function formatSigned(value: number | null | undefined, digits = 2): string {
  const text = formatNumber(value, digits)
  if (text === MISSING || value === null || value === undefined) return text
  return value > 0 ? `+${text}` : text
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return MISSING
  return value.toLocaleString("tr-TR")
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null
}
