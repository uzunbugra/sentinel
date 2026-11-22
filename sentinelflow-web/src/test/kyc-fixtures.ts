import type { KycScreenResponse } from "@/lib/kyc"

// Shapes taken from the real API (POST /api/v1/kyc/screen against the demo lists).

export const pepExact: KycScreenResponse = {
  screening_id: "SCR-1",
  query_name: "Ahmet Politikacı",
  screening_types: ["PEP", "YAPTIRIMLAR"],
  has_matches: true,
  matches_count: 1,
  matches: [
    {
      match_id: "PEP-00001",
      matched_name: "Ahmet Politikacı",
      query_name: "Ahmet Politikacı",
      match_type: "TAM_ESLESME",
      match_score: 100,
      screening_type: "PEP",
      details: {
        pep_level: "YURT_ICI_YUKSEK",
        position: "Eski Bakan",
        country: "Türkiye",
        active: true,
        related_pep: null,
      },
    },
  ],
  risk_score: 100,
  recommendation: "EDD gerekli - PEP tespit edildi",
  screened_at: "2026-11-22T15:00:00+00:00",
}

export const sanctionsAlias: KycScreenResponse = {
  screening_id: "SCR-2",
  query_name: "Banned Person",
  screening_types: ["PEP", "YAPTIRIMLAR"],
  has_matches: true,
  matches_count: 1,
  matches: [
    {
      match_id: "SAN-00002",
      matched_name: "Yasak Kişi",
      query_name: "Banned Person",
      match_type: "TAM_ESLESME",
      match_score: 100,
      screening_type: "YAPTIRIMLAR",
      details: {
        list: "OFAC_SDN",
        reason: "Money laundering",
        added_date: "2020-01-15",
        country: "Unknown",
        matched_alias: "Banned Person",
      },
    },
  ],
  risk_score: 100,
  recommendation: "İŞLEM YAPILAMAZ - Yaptırım eşleşmesi",
  screened_at: "2026-11-22T15:00:00+00:00",
}

export const clean: KycScreenResponse = {
  screening_id: "SCR-3",
  query_name: "Ayşe Temiz",
  screening_types: ["PEP", "YAPTIRIMLAR"],
  has_matches: false,
  matches_count: 0,
  matches: [],
  risk_score: 0,
  recommendation: "Tarama temiz",
  screened_at: "2026-11-22T15:00:00+00:00",
}
