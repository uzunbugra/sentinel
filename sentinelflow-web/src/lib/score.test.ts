import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("./auth", async (orig) => ({ ...(await orig()), apiRequest: vi.fn() }))

import { apiRequest, ApiError } from "./auth"
import { config } from "./config"
import {
  buildScoreRequest,
  defaultScoreForm,
  scoreToDetails,
  scoreTransaction,
  validateScoreForm,
  type RiskScoreResponse,
} from "./score"

const mockApi = vi.mocked(apiRequest)

const scoreResponse: RiskScoreResponse = {
  transaction_id: "TXN-1",
  model_version: "fraud-lgbm-20261030-0e0c647",
  feature_set_version: "fs-1",
  score: 0.99867,
  threshold: 0.11301,
  is_fraud: true,
  contribution_unit: "log_odds",
  base_value: -3.2,
  top_features: [{ feature: "log_amount", value: 10.13, contribution: 2.4 }],
  history_cold_start: true,
  latency_ms: 1.234,
}

beforeEach(() => mockApi.mockReset())

describe("defaultScoreForm", () => {
  it("uses synthetic values and the current UTC minute", () => {
    const form = defaultScoreForm(new Date("2026-11-22T13:45:30Z"))
    expect(form.sender_iban).toBe("TR000000000000000000000001")
    expect(form.timestamp).toBe("2026-11-22T13:45")
    expect(validateScoreForm(form)).toBeNull()
  })
})

describe("validateScoreForm", () => {
  const base = defaultScoreForm(new Date("2026-11-22T13:45:00Z"))

  it.each([
    [{ sender_iban: "TR12" }, /Gönderen IBAN/],
    [{ receiver_iban: "x".repeat(40) }, /Alıcı IBAN/],
    [{ sender_name: "  " }, /adı gerekli/],
    [{ amount: "0" }, /Tutar/],
    [{ amount: "abc" }, /Tutar/],
    [{ timestamp: "" }, /zamanı/],
  ])("rejects %o", (patch, message) => {
    expect(validateScoreForm({ ...base, ...patch })).toMatch(message)
  })
})

describe("buildScoreRequest", () => {
  it("sends a numeric amount and a tz-aware UTC timestamp", () => {
    const body = buildScoreRequest({
      ...defaultScoreForm(new Date("2026-11-22T13:45:00Z")),
      sender_iban: "  TR000000000000000000000009 ",
      amount: "1500.5",
    })
    expect(body).toMatchObject({
      sender_iban: "TR000000000000000000000009",
      amount: 1500.5,
      timestamp: "2026-11-22T13:45:00Z",
      payment_type: "cash_deposit",
    })
  })
})

describe("scoreTransaction", () => {
  it("POSTs to risk/score and returns the result", async () => {
    mockApi.mockResolvedValueOnce(scoreResponse)
    const outcome = await scoreTransaction({ amount: 1 })
    expect(mockApi).toHaveBeenCalledWith(config.endpoints.predict, {
      method: "POST",
      body: JSON.stringify({ amount: 1 }),
    })
    expect(outcome).toEqual({ kind: "scored", result: scoreResponse })
  })

  it("maps 503 model_not_loaded to model_unavailable", async () => {
    mockApi.mockRejectedValueOnce(
      new ApiError(503, "Request failed (503)", {
        code: "model_not_loaded",
        message: "No valid fraud model is loaded",
        status: "not_loaded",
      }),
    )
    await expect(scoreTransaction({})).resolves.toEqual({
      kind: "model_unavailable",
      reason: "No valid fraud model is loaded",
    })
  })

  it("rethrows other errors", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(403, "Forbidden"))
    await expect(scoreTransaction({})).rejects.toMatchObject({ kind: "forbidden" })
  })
})

describe("scoreToDetails", () => {
  it("keeps every field the evaluation view reads", () => {
    expect(scoreToDetails(scoreResponse)).toEqual({
      model_version: "fraud-lgbm-20261030-0e0c647",
      feature_set_version: "fs-1",
      score: 0.99867,
      threshold: 0.11301,
      contribution_unit: "log_odds",
      base_value: -3.2,
      top_features: scoreResponse.top_features,
      history_cold_start: true,
    })
  })
})
