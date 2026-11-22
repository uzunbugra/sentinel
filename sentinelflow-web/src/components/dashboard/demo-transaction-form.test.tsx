import { beforeEach, describe, expect, it, vi } from "vitest"
import userEvent from "@testing-library/user-event"
import { render, screen } from "@testing-library/react"

const mocks = vi.hoisted(() => ({ role: "analyst" as string }))
vi.mock("@/lib/auth", async (orig) => ({ ...(await orig()), apiRequest: vi.fn() }))
vi.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({ user: { full_name: "Demo", role: mocks.role }, isAuthenticated: true }),
}))

import { apiRequest, ApiError } from "@/lib/auth"
import { DemoTransactionForm } from "./demo-transaction-form"

const mockApi = vi.mocked(apiRequest)

const fraudResult = {
  transaction_id: "DEMO-abc",
  status: "analyzed",
  message: "Fraud detected!",
  is_fraud: true,
  fraud_score: 0.99867,
  model_version: "fraud-lgbm-20261030-0e0c647",
  alerts: [{ alert_id: "ALT-123" }],
  processing_time_ms: 4.2,
}

beforeEach(() => {
  mocks.role = "analyst"
  mockApi.mockReset()
})

function sentBody() {
  const [, options] = mockApi.mock.calls[0]
  return JSON.parse(options!.body as string)
}

describe("DemoTransactionForm", () => {
  it("is not rendered for a viewer", () => {
    mocks.role = "viewer"
    const { container } = render(<DemoTransactionForm />)
    expect(container).toBeEmptyDOMElement()
  })

  it("sends the suspicious preset and shows the alert it raised", async () => {
    mockApi.mockResolvedValueOnce(fraudResult)
    render(<DemoTransactionForm />)
    await userEvent.click(screen.getByRole("button", { name: "Gönder" }))

    expect(sentBody()).toMatchObject({
      sender_iban: "TR000000000000000000000001",
      amount: 25000,
      payment_type: "cash_withdrawal",
    })
    expect(sentBody().transaction_id).toMatch(/^DEMO-/)
    const result = await screen.findByTestId("demo-result")
    expect(result).toHaveTextContent("Şüpheli: model alarm üretti.")
    expect(result).toHaveTextContent("0.9987")
    expect(result).toHaveTextContent("ALT-123")
  })

  it("switches preset and amount", async () => {
    mockApi.mockResolvedValueOnce({ ...fraudResult, is_fraud: false, alerts: null, fraud_score: 0.01 })
    render(<DemoTransactionForm />)
    await userEvent.click(screen.getByText("Olağan örnek"))
    const amount = screen.getByRole("spinbutton")
    expect(amount).toHaveValue(350)
    await userEvent.clear(amount)
    await userEvent.type(amount, "99")
    await userEvent.click(screen.getByRole("button", { name: "Gönder" }))
    expect(sentBody()).toMatchObject({ amount: 99, payment_type: "debit_card" })
    expect(await screen.findByTestId("demo-result")).toHaveTextContent("Temiz")
  })

  it("says the transaction was not scored when no model is loaded", async () => {
    mockApi.mockResolvedValueOnce({
      ...fraudResult,
      is_fraud: false,
      fraud_score: null,
      model_version: null,
      alerts: null,
    })
    render(<DemoTransactionForm />)
    await userEvent.click(screen.getByRole("button", { name: "Gönder" }))
    expect(await screen.findByText(/Model yüklü olmadığı için/)).toBeInTheDocument()
  })

  it("blocks an invalid amount", async () => {
    render(<DemoTransactionForm />)
    await userEvent.clear(screen.getByRole("spinbutton"))
    expect(screen.getByRole("button", { name: "Gönder" })).toBeDisabled()
    expect(screen.getByRole("alert")).toHaveTextContent(/Tutar/)
  })

  it("shows a readable message on 403", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(403, "Forbidden"))
    render(<DemoTransactionForm />)
    await userEvent.click(screen.getByRole("button", { name: "Gönder" }))
    expect(await screen.findByText("Bu işlem için yetkiniz yok.")).toBeInTheDocument()
  })
})
