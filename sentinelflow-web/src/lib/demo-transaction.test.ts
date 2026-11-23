import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("./auth", async (orig) => ({ ...(await orig()), apiRequest: vi.fn() }))

import { apiRequest } from "./auth"
import { config } from "./config"
import {
  buildDemoTransaction,
  DEMO_RECEIVER,
  DEMO_SENDER,
  demoTransactionId,
  submitDemoTransaction,
} from "./demo-transaction"

const mockApi = vi.mocked(apiRequest)
beforeEach(() => mockApi.mockReset())

describe("demoTransactionId", () => {
  it("is DEMO- plus 16 hex characters", () => {
    expect(demoTransactionId()).toMatch(/^DEMO-[0-9a-f]{16}$/)
    expect(demoTransactionId(() => 0)).toBe("DEMO-0000000000000000")
  })
})

describe("buildDemoTransaction", () => {
  it("uses only the synthetic parties and the preset's categories", () => {
    const body = buildDemoTransaction("suspicious", 25000, "DEMO-1")
    expect(body).toEqual({
      transaction_id: "DEMO-1",
      sender_iban: DEMO_SENDER.iban,
      sender_name: DEMO_SENDER.name,
      receiver_iban: DEMO_RECEIVER.iban,
      receiver_name: DEMO_RECEIVER.name,
      description: "SentinelFlow demo işlemi (sentetik)",
      amount: 25000,
      currency: "TRY",
      received_currency: "USD",
      sender_country: "TR",
      receiver_country: "TR",
      payment_type: "cash_withdrawal",
    })
    expect(body).not.toHaveProperty("label")
  })

  it("keeps the entered amount", () => {
    expect(buildDemoTransaction("normal", 12.5, "DEMO-2")).toMatchObject({
      amount: 12.5,
      payment_type: "debit_card",
      received_currency: "TRY",
    })
  })
})

describe("submitDemoTransaction", () => {
  it("POSTs the body to /transactions", async () => {
    mockApi.mockResolvedValueOnce({ transaction_id: "DEMO-1" })
    await submitDemoTransaction({ amount: 1 })
    expect(mockApi).toHaveBeenCalledWith(config.endpoints.transactions, {
      method: "POST",
      body: JSON.stringify({ amount: 1 }),
    })
  })
})
