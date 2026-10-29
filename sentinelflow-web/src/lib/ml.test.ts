import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("./auth", async (orig) => ({ ...(await orig()), apiRequest: vi.fn() }))

import { apiRequest, ApiError } from "./auth"
import { config } from "./config"
import {
  contributionUnitNote,
  extractModelEvaluation,
  fetchActiveModel,
  formatCount,
  formatNumber,
  formatSigned,
  isAboveThreshold,
  normalizeModelStatus,
} from "./ml"
import {
  legacyEnsembleEvidence,
  loadedModelResponse,
  mlEvidence,
  modelNotLoaded503Detail,
  notLoadedResponse,
  ruleEvidence,
} from "@/test/ml-fixtures"

const mockApi = vi.mocked(apiRequest)

beforeEach(() => {
  mockApi.mockReset()
})

describe("normalizeModelStatus", () => {
  it("yüklü modeli döndürür", () => {
    expect(normalizeModelStatus(loadedModelResponse)).toEqual({
      kind: "loaded",
      model: loadedModelResponse.model,
    })
  })

  it("not_loaded ve invalid durumlarını sebebiyle döndürür", () => {
    expect(normalizeModelStatus(notLoadedResponse)).toEqual({
      kind: "unavailable",
      status: "not_loaded",
      reason: "model directory not found: models/fraud/current",
    })
    expect(normalizeModelStatus({ status: "invalid", model: null, error: null })).toEqual({
      kind: "unavailable",
      status: "invalid",
      reason: null,
    })
  })

  it("sözleşme dışı (eski ensemble) gövdeyi unsupported sayar", () => {
    expect(normalizeModelStatus({ models: [], ensemble_ready: false })).toEqual({ kind: "unsupported" })
    expect(normalizeModelStatus(null)).toEqual({ kind: "unsupported" })
  })
})

describe("fetchActiveModel", () => {
  it("config'teki uca istek atar", async () => {
    mockApi.mockResolvedValueOnce(loadedModelResponse)
    await expect(fetchActiveModel()).resolves.toMatchObject({ kind: "loaded" })
    expect(mockApi).toHaveBeenCalledWith(config.endpoints.modelInfo)
    expect(config.endpoints.modelInfo).toBe("/api/v1/ml/models")
  })

  it("503 model_not_loaded cevabını model yok durumuna çevirir", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(503, "Request failed (503)", modelNotLoaded503Detail))
    await expect(fetchActiveModel()).resolves.toEqual({
      kind: "unavailable",
      status: "not_loaded",
      reason: "No valid fraud model is loaded",
    })
  })

  it("diğer hataları yeniden fırlatır", async () => {
    const err = new ApiError(500, "Request failed (500)")
    mockApi.mockRejectedValueOnce(err)
    await expect(fetchActiveModel()).rejects.toBe(err)
  })
})

describe("extractModelEvaluation", () => {
  it("ML evidence kaydını okur; sıfır ile eksik değeri ayırır", () => {
    const evaluation = extractModelEvaluation("ml_model", [ruleEvidence, mlEvidence])
    expect(evaluation?.kind).toBe("ml")
    if (evaluation?.kind !== "ml") return
    expect(evaluation.details).toMatchObject({
      model_version: "fraud-lgbm-20261105-a1b2c3d",
      score: 0.8123,
      threshold: 0.37,
      contribution_unit: "log_odds",
      base_value: -6.91,
      history_cold_start: false,
    })
    const byName = Object.fromEntries(evaluation.details.top_features.map((f) => [f.feature, f]))
    expect(byName.currency_mismatch).toEqual({ feature: "currency_mismatch", value: 0, contribution: 0 })
    expect(byName.sender_seconds_since_prev.value).toBeNull()
    expect(evaluation.summary).toBe("Model skoru 0.81 ≥ eşik 0.37")
  })

  it("eksik detay alanlarını null yapar, 0 uydurmaz", () => {
    const evaluation = extractModelEvaluation("ml_model", [
      { detector_type: "ml_model", details: { score: null, top_features: "bozuk" } },
    ])
    expect(evaluation).toEqual({
      kind: "ml",
      summary: null,
      details: {
        model_version: null,
        feature_set_version: null,
        score: null,
        threshold: null,
        contribution_unit: null,
        base_value: null,
        top_features: [],
        history_cold_start: null,
      },
    })
  })

  it("metadata'sız ML alarmını legacy sayar", () => {
    expect(extractModelEvaluation("ml_ensemble", [legacyEnsembleEvidence])).toEqual({ kind: "legacy" })
    expect(extractModelEvaluation("ml_model", undefined)).toEqual({ kind: "legacy" })
  })

  it("ML olmayan alarm için null döner", () => {
    expect(extractModelEvaluation("mule_account", [ruleEvidence])).toBeNull()
    expect(extractModelEvaluation("mule_account", undefined)).toBeNull()
  })
})

describe("yardımcılar", () => {
  it("eşik karşılaştırması score >= threshold kuralını izler", () => {
    expect(isAboveThreshold(0.37, 0.37)).toBe(true)
    expect(isAboveThreshold(0.36, 0.37)).toBe(false)
    expect(isAboveThreshold(null, 0.37)).toBeNull()
    expect(isAboveThreshold(0.5, null)).toBeNull()
  })

  it("sayı biçimleri sıfırı gösterir, eksiği tire ile gösterir", () => {
    expect(formatNumber(0)).toBe("0.00")
    expect(formatNumber(null)).toBe("—")
    expect(formatNumber(undefined)).toBe("—")
    expect(formatNumber(0.8123, 4)).toBe("0.8123")
    expect(formatSigned(2.31)).toBe("+2.31")
    expect(formatSigned(-0.18)).toBe("-0.18")
    expect(formatSigned(0)).toBe("0.00")
    expect(formatSigned(null)).toBe("—")
    expect(formatCount(0)).toBe("0")
    expect(formatCount(1425000)).toBe("1.425.000")
    expect(formatCount(null)).toBe("—")
  })

  it("katkı birimini sözleşmeye göre etiketler", () => {
    expect(contributionUnitNote("log_odds")).toMatch(/log-odds/)
    expect(contributionUnitNote("log_odds")).toMatch(/genel özellik önemi değildir/)
    expect(contributionUnitNote("shap")).toBe("Katkı birimi: shap")
    expect(contributionUnitNote(null)).toBe("Katkı birimi kaydedilmemiş.")
  })
})
