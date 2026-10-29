import type { AlertEvidence, ModelStatusResponse } from "@/lib/ml"

// Payloads copied from docs/contracts/sprint4-ml-api.md (§4.1, §4.5); numbers
// are the contract's placeholders, not a real model.

export const loadedModelResponse: ModelStatusResponse = {
  status: "loaded",
  model: {
    model_version: "fraud-lgbm-20261105-a1b2c3d",
    model_family: "lightgbm",
    feature_set_version: "fs-1",
    feature_names: ["log_amount", "hour"],
    threshold: 0.37,
    dataset_id: "samld-3f9a",
    trained_at: "2026-11-05T12:00:00+00:00",
    loaded_at: "2026-11-06T08:00:00+00:00",
    metrics: {
      split: "test",
      pr_auc: 0.52,
      roc_auc: 0.97,
      precision: 0.21,
      recall: 0.58,
      f1: 0.31,
      support_positive: 1234,
      support_total: 1425000,
      baseline_pr_auc: 0.3,
    },
    model_sha256: "0f1e2d",
  },
  error: null,
}

/** Same model with an unrecorded metric (null) next to a real zero. */
export const partialMetricsResponse: ModelStatusResponse = {
  ...loadedModelResponse,
  model: {
    ...loadedModelResponse.model!,
    metrics: { ...loadedModelResponse.model!.metrics!, pr_auc: null, recall: 0 },
  },
}

export const noMetricsResponse: ModelStatusResponse = {
  ...loadedModelResponse,
  model: { ...loadedModelResponse.model!, metrics: null },
}

export const notLoadedResponse: ModelStatusResponse = {
  status: "not_loaded",
  model: null,
  error: "model directory not found: models/fraud/current",
}

export const modelNotLoaded503Detail = {
  code: "model_not_loaded",
  message: "No valid fraud model is loaded",
  status: "not_loaded",
}

export const mlEvidence: AlertEvidence = {
  detector_type: "ml_model",
  detector_version: "fraud-lgbm-20261105-a1b2c3d",
  confidence: 0.8123,
  contribution: 1.0,
  summary: "Model skoru 0.81 ≥ eşik 0.37",
  details: {
    model_version: "fraud-lgbm-20261105-a1b2c3d",
    feature_set_version: "fs-1",
    score: 0.8123,
    threshold: 0.37,
    contribution_unit: "log_odds",
    base_value: -6.91,
    top_features: [
      { feature: "sender_unique_receivers_7d", value: 14.0, contribution: 2.31 },
      { feature: "cross_border", value: 1.0, contribution: 1.12 },
      { feature: "log_amount", value: 11.23, contribution: 0.87 },
      { feature: "currency_mismatch", value: 0, contribution: 0 },
      { feature: "sender_seconds_since_prev", value: null, contribution: -0.18 },
    ],
    history_cold_start: false,
  },
  related_transactions: ["TXN-A1B2C3D4E5F6"],
}

/** Evidence recorded with an older model than the one active today. */
export const olderModelEvidence: AlertEvidence = {
  ...mlEvidence,
  detector_version: "fraud-lgbm-20261020-0000aaa",
  details: {
    ...mlEvidence.details,
    model_version: "fraud-lgbm-20261020-0000aaa",
    score: 0.41,
    threshold: 0.45,
    top_features: [],
  },
}

/** Pre-Sprint 4 `ml_ensemble` alert: no model metadata in evidence. */
export const legacyEnsembleEvidence: AlertEvidence = {
  detector_type: "ml_ensemble",
  detector_version: "1.0.0",
  confidence: 0.9,
  contribution: 0.5,
  summary: "Ensemble oylaması",
  details: { votes: 3 },
}

export const ruleEvidence: AlertEvidence = {
  detector_type: "rule_engine",
  confidence: 0.8,
  summary: "Mule hesap kuralı",
  details: { rule: "mule" },
}
