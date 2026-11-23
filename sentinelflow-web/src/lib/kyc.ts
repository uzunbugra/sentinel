import { apiRequest } from "./auth"
import { config } from "./config"

// `POST /api/v1/kyc/screen` (SF-522). The backend screens against small demo
// PEP and sanctions lists in sentinelflow.kyc.screening; they are not tied to
// any official list (OFAC, UN, EU, MASAK).

export interface KycMatch {
  match_id: string
  matched_name: string
  query_name: string
  match_type: string
  match_score: number
  screening_type: string
  details: Record<string, unknown>
}

export interface KycScreenResponse {
  screening_id: string
  query_name: string
  screening_types: string[]
  has_matches: boolean
  matches_count: number
  matches: KycMatch[]
  risk_score: number
  recommendation: string
  screened_at: string
}

export const MATCH_TYPE_LABELS: Record<string, string> = {
  TAM_ESLESME: "Tam",
  KISMI_ESLESME: "Kısmi",
  BULANIK_ESLESME: "Bulanık",
  TAKMA_AD: "Takma ad",
}

export const SCREENING_TYPE_LABELS: Record<string, string> = {
  PEP: "PEP",
  YAPTIRIMLAR: "Yaptırım",
  OLUMSUZ_MEDYA: "Olumsuz medya",
  IZLEME_LISTESI: "İzleme listesi",
}

export const SANCTIONS_LIST_LABELS: Record<string, string> = {
  OFAC_SDN: "OFAC SDN (örnek)",
  AB_KONSOLIDE: "AB konsolide (örnek)",
  BM_KONSOLIDE: "BM konsolide (örnek)",
  INGILTERE: "Birleşik Krallık (örnek)",
  TURKIYE_MASAK: "MASAK (örnek)",
}

export const PEP_LEVEL_LABELS: Record<string, string> = {
  YURT_ICI_YUKSEK: "Yurt içi, yüksek",
  YURT_ICI_ORTA: "Yurt içi, orta",
  YURT_DISI_YUKSEK: "Yurt dışı, yüksek",
  YURT_DISI_ORTA: "Yurt dışı, orta",
  YAKIN_AILE: "Yakın aile",
  IS_ORTAGI: "İş ortağı",
}

/** Names in the demo lists (exact, partial, alias) and one clean name, as one-click examples. */
export const KYC_EXAMPLES = ["Ahmet Politikacı", "Ahmet Politika", "Banned Person", "Yasak Kişi", "Ayşe Temiz"]

export function label(map: Record<string, string>, value: unknown): string {
  if (typeof value !== "string" || !value) return "—"
  return map[value] ?? value
}

/** Which list the match came from: sanctions list name or PEP level. */
export function matchSource(match: KycMatch): string {
  if (match.screening_type === "YAPTIRIMLAR") return label(SANCTIONS_LIST_LABELS, match.details.list)
  if (match.screening_type === "PEP") return `PEP · ${label(PEP_LEVEL_LABELS, match.details.pep_level)}`
  return label(SCREENING_TYPE_LABELS, match.screening_type)
}

export type RiskBand = "high" | "medium" | "clean"

export function riskBand(result: KycScreenResponse): RiskBand {
  if (!result.has_matches) return "clean"
  // A sanctions hit blocks the transaction; a PEP hit asks for enhanced due diligence.
  return result.matches.some((m) => m.screening_type === "YAPTIRIMLAR") ? "high" : "medium"
}

export function validateKycName(name: string): string | null {
  const trimmed = name.trim()
  if (trimmed.length < 2) return "Ad en az 2 karakter olmalı."
  if (trimmed.length > 200) return "Ad en fazla 200 karakter olabilir."
  return null
}

export function screenCustomer(name: string, country: string): Promise<KycScreenResponse> {
  const body: Record<string, string> = { name: name.trim() }
  if (country.trim()) body.country = country.trim()
  return apiRequest<KycScreenResponse>(config.endpoints.kycScreen, {
    method: "POST",
    body: JSON.stringify(body),
  })
}
