import { beforeEach, describe, expect, it, vi } from "vitest"
import userEvent from "@testing-library/user-event"
import { render, screen, within } from "@testing-library/react"

vi.mock("@/lib/auth", async (orig) => ({ ...(await orig()), apiRequest: vi.fn() }))

import { apiRequest, ApiError } from "@/lib/auth"
import { config } from "@/lib/config"
import { AiChat } from "@/components/dashboard/ai-chat"

const mockApi = vi.mocked(apiRequest)

beforeEach(() => mockApi.mockReset())

function log() {
  return screen.getByRole("log", { name: "Sohbet" })
}

async function sendMessage(text: string) {
  await userEvent.type(screen.getByLabelText("Mesaj"), text)
  await userEvent.keyboard("{Enter}")
}

describe("AiChat", () => {
  it("states that the assistant is rule-based and uses no LLM", () => {
    mockApi.mockResolvedValueOnce([])
    render(<AiChat />)
    expect(screen.getByRole("note")).toHaveTextContent(/Kural tabanlı/)
    expect(screen.getByRole("note")).toHaveTextContent(/LLM\) kullanmaz/)
  })

  it("loads suggested questions and sends one with a click", async () => {
    mockApi.mockResolvedValueOnce(["Döngüsel transfer nedir?", "MASAK bildirimi ne zaman yapılmalı?"])
    render(<AiChat />)
    expect(mockApi).toHaveBeenCalledWith(config.endpoints.chatSuggestions)
    const group = await screen.findByRole("group", { name: "Önerilen sorular" })

    mockApi.mockResolvedValueOnce({
      response: "**Circular Ring**\n\nParanın A → B → C → A şeklinde dolaşması.",
      suggestions: ["Diğer fraud türleri"],
    })
    await userEvent.click(within(group).getByRole("button", { name: "Döngüsel transfer nedir?" }))

    expect(await within(log()).findByText("Circular Ring")).toContainHTML("strong")
    expect(within(log()).getByText(/Paranın A → B/)).toBeInTheDocument()
    // The reply's own suggestions replace the starting ones.
    expect(screen.getByRole("button", { name: "Diğer fraud türleri" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Döngüsel transfer nedir?" })).not.toBeInTheDocument()
  })

  it("sends the typed message without any invented context", async () => {
    mockApi.mockResolvedValueOnce([]).mockResolvedValueOnce({ response: "Merhaba!" })
    render(<AiChat />)
    await sendMessage("  merhaba  ")

    expect(await within(log()).findByText("Merhaba!")).toBeInTheDocument()
    expect(within(log()).getByText("merhaba")).toBeInTheDocument()
    expect(mockApi).toHaveBeenLastCalledWith(config.endpoints.chat, {
      method: "POST",
      body: JSON.stringify({ message: "merhaba" }),
    })
    expect(screen.getByLabelText("Mesaj")).toHaveValue("")
  })

  it("keeps working when suggestions fail and shows a Turkish error on send failure", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(503, "down"))
    render(<AiChat />)
    expect(screen.queryByRole("group", { name: "Önerilen sorular" })).not.toBeInTheDocument()

    mockApi.mockRejectedValueOnce(new ApiError(0, "Network error"))
    await sendMessage("Bağlantıyı test et")
    expect(await within(log()).findByText("Sunucuya ulaşılamıyor. Bağlantınızı kontrol edin.")).toBeInTheDocument()
    expect(screen.queryByText("Yanıt hazırlanıyor...")).not.toBeInTheDocument()
  })

  it("does not send an empty message", async () => {
    mockApi.mockResolvedValueOnce([])
    render(<AiChat />)
    expect(screen.getByRole("button", { name: "Gönder" })).toBeDisabled()
    await sendMessage("   ")
    expect(mockApi).toHaveBeenCalledTimes(1)
  })
})
