import { apiRequest, ApiError } from "./auth"
import { config } from "./config"
import type { MlEvidenceDetails, TopFeature } from "./ml"

// `POST /api/v1/risk/score` (docs/contracts/sprint4-ml-api.md §4.2). The request
// body is the API's `TransactionCreate`; the score is computed against the
// current account history without recording the transaction.

/** Category vocabularies of feature set fs-1 (contract §1). Others map to `unknown`. */
export const PAYMENT_TYPES = [
  "ach",
  "cash_deposit",
  "cash_withdrawal",
  "cheque",
  "credit_card",
  "cross_border",
  "debit_card",
] as const

export const CURRENCIES = [
  "AED", "ALL", "CHF", "EUR", "GBP", "INR", "JPY", "MAD", "MXN", "NGN", "PKR", "TRY", "USD",
] as const

export const COUNTRIES = [
  "AE", "AL", "AT", "CH", "DE", "ES", "FR", "GB", "IN", "IT", "JP", "MA", "MX", "NG", "NL",
  "PK", "TR", "US",
] as const

export const PAYMENT_TYPE_LABELS: Record<string, string> = {
  ach: "ACH transferi",
  cash_deposit: "Nakit yatırma",
  cash_withdrawal: "Nakit çekme",
  cheque: "Çek",
  credit_card: "Kredi kartı",
  cross_border: "Sınır ötesi",
  debit_card: "Banka kartı",
}

export interface ScoreForm {
  sender_iban: string
  sender_name: string
  receiver_iban: string
  receiver_name: string
  amount: string
  currency: string
  received_currency: string
  sender_country: string
  receiver_country: string
  payment_type: string
  /** `YYYY-MM-DDTHH:mm` from a datetime-local input, read as UTC. */
  timestamp: string
}

export interface RiskScoreResponse {
  transaction_id: string
  model_version: string
  feature_set_version: string
  score: number
  threshold: number
  is_fraud: boolean
  contribution_unit: string
  base_value: number
  top_features: TopFeature[]
  history_cold_start: boolean
  latency_ms: number
}

export type ScoreOutcome =
  | { kind: "scored"; result: RiskScoreResponse }
  | { kind: "model_unavailable"; reason: string | null }

/** Synthetic demo values (contract §1 example); never real customer data. */
export function defaultScoreForm(now: Date = new Date()): ScoreForm {
  return {
    sender_iban: "TR000000000000000000000001",
    sender_name: "Demo Gönderen",
    receiver_iban: "TR000000000000000000000002",
    receiver_name: "Demo Alıcı",
    amount: "25000",
    currency: "TRY",
    received_currency: "TRY",
    sender_country: "TR",
    receiver_country: "TR",
    payment_type: "cash_deposit",
    timestamp: now.toISOString().slice(0, 16),
  }
}

/** Client-side checks that mirror `TransactionCreate`; null when valid. */
export function validateScoreForm(form: ScoreForm): string | null {
  const iban = /^[A-Z]{2}[0-9A-Z]{13,32}$/
  if (!iban.test(form.sender_iban.trim())) return "Gönderen IBAN 15–34 karakter, ülke koduyla başlamalı."
  if (!iban.test(form.receiver_iban.trim())) return "Alıcı IBAN 15–34 karakter, ülke koduyla başlamalı."
  if (!form.sender_name.trim() || !form.receiver_name.trim()) return "Gönderen ve alıcı adı gerekli."
  const amount = Number(form.amount)
  if (!Number.isFinite(amount) || amount <= 0) return "Tutar sıfırdan büyük bir sayı olmalı."
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(form.timestamp)) return "İşlem zamanı geçersiz."
  return null
}

/** Request body for `TransactionCreate`; the timestamp is sent tz-aware (UTC). */
export function buildScoreRequest(form: ScoreForm): Record<string, unknown> {
  return {
    sender_iban: form.sender_iban.trim(),
    sender_name: form.sender_name.trim(),
    receiver_iban: form.receiver_iban.trim(),
    receiver_name: form.receiver_name.trim(),
    amount: Number(form.amount),
    currency: form.currency,
    received_currency: form.received_currency,
    sender_country: form.sender_country,
    receiver_country: form.receiver_country,
    payment_type: form.payment_type,
    timestamp: `${form.timestamp}:00Z`,
  }
}

/** 503 `model_not_loaded` becomes an outcome; every other failure is rethrown. */
export async function scoreTransaction(body: Record<string, unknown>): Promise<ScoreOutcome> {
  try {
    const result = await apiRequest<RiskScoreResponse>(config.endpoints.predict, {
      method: "POST",
      body: JSON.stringify(body),
    })
    return { kind: "scored", result }
  } catch (err) {
    if (err instanceof ApiError && err.status === 503) {
      const detail = typeof err.detail === "object" && err.detail !== null ? err.detail : {}
      const message = (detail as Record<string, unknown>).message
      return { kind: "model_unavailable", reason: typeof message === "string" ? message : null }
    }
    throw err
  }
}

/** The score in the shape the shared model-evaluation view reads. */
export function scoreToDetails(result: RiskScoreResponse): MlEvidenceDetails {
  return {
    model_version: result.model_version,
    feature_set_version: result.feature_set_version,
    score: result.score,
    threshold: result.threshold,
    contribution_unit: result.contribution_unit,
    base_value: result.base_value,
    top_features: result.top_features,
    history_cold_start: result.history_cold_start,
  }
}
