import { apiRequest } from "./auth"
import { config } from "./config"

// Demo transactions for live demos (SF-523): `POST /api/v1/transactions` with
// synthetic, clearly fake parties only. Unlike /risk/score this records the
// transaction in account history and may raise an alert, which then arrives on
// the live alert stream.

export type DemoPreset = "suspicious" | "normal"

interface PresetValues {
  label: string
  description: string
  amount: number
  currency: string
  received_currency: string
  sender_country: string
  receiver_country: string
  payment_type: string
}

/** The suspicious preset is the SPRINT4_DEMO.md §2 transaction. */
export const DEMO_PRESETS: Record<DemoPreset, PresetValues> = {
  suspicious: {
    label: "Şüpheli örnek",
    description: "Nakit çekme, ödeme TRY / alınan USD",
    amount: 25000,
    currency: "TRY",
    received_currency: "USD",
    sender_country: "TR",
    receiver_country: "TR",
    payment_type: "cash_withdrawal",
  },
  normal: {
    label: "Olağan örnek",
    description: "Banka kartı, aynı para birimi",
    amount: 350,
    currency: "TRY",
    received_currency: "TRY",
    sender_country: "TR",
    receiver_country: "TR",
    payment_type: "debit_card",
  },
}

export const DEMO_SENDER = { iban: "TR000000000000000000000001", name: "Demo Gönderen" }
export const DEMO_RECEIVER = { iban: "TR000000000000000000000002", name: "Demo Alıcı" }

export interface TransactionResult {
  transaction_id: string
  status: string
  message: string
  is_fraud: boolean
  fraud_score: number | null
  model_version: string | null
  alerts: { alert_id: string; severity?: string; title?: string }[] | null
  processing_time_ms: number
}

/** `DEMO-` + 16 hex characters: every submission is a new transaction. */
export function demoTransactionId(random: () => number = Math.random): string {
  let hex = ""
  for (let i = 0; i < 16; i++) hex += Math.floor(random() * 16).toString(16)
  return `DEMO-${hex}`
}

export function buildDemoTransaction(
  preset: DemoPreset,
  amount: number,
  transactionId: string = demoTransactionId(),
): Record<string, unknown> {
  const values = DEMO_PRESETS[preset]
  return {
    transaction_id: transactionId,
    sender_iban: DEMO_SENDER.iban,
    sender_name: DEMO_SENDER.name,
    receiver_iban: DEMO_RECEIVER.iban,
    receiver_name: DEMO_RECEIVER.name,
    description: "SentinelFlow demo işlemi (sentetik)",
    amount,
    currency: values.currency,
    received_currency: values.received_currency,
    sender_country: values.sender_country,
    receiver_country: values.receiver_country,
    payment_type: values.payment_type,
  }
}

export function submitDemoTransaction(body: Record<string, unknown>): Promise<TransactionResult> {
  return apiRequest<TransactionResult>(config.endpoints.transactions, {
    method: "POST",
    body: JSON.stringify(body),
  })
}
