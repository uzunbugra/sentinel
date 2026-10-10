import { describe, expect, it, vi } from "vitest"
import userEvent from "@testing-library/user-event"
import { render, screen, waitFor } from "@testing-library/react"

vi.mock("@/lib/auth", async (orig) => ({ ...(await orig()), apiRequest: vi.fn() }))

import { apiRequest, ApiError } from "@/lib/auth"
import { config } from "@/lib/config"
import { AiChat } from "@/components/dashboard/ai-chat"

const mockApi = vi.mocked(apiRequest)

function renderChat() {
  return render(<AiChat />)
}

async function sendMessage(user: ReturnType<typeof userEvent.setup>, text: string) {
  const input = screen.getByPlaceholderText("Ask SentinelAI...")
  await user.type(input, text)
  await user.keyboard("{Enter}")
}

describe("AiChat", () => {
  it("başarılı yanıtı asistan mesajı olarak gösterir", async () => {
    mockApi.mockResolvedValueOnce({ response: "Şüpheli işlem görünüyor" })
    const user = userEvent.setup()

    renderChat()
    await sendMessage(user, "Bu işlem şüpheli mi?")

    expect(await screen.findByText("Şüpheli işlem görünüyor")).toBeInTheDocument()
    expect(screen.getByText("Bu işlem şüpheli mi?")).toBeInTheDocument()

    expect(mockApi).toHaveBeenCalledTimes(1)
    expect(mockApi).toHaveBeenCalledWith(config.endpoints.chat, {
      method: "POST",
      body: JSON.stringify({
        message: "Bu işlem şüpheli mi?",
        context: { amount: 150000, fraud_type: "whale_anomaly" },
      }),
    })
  })

  it("ağ hatasında Türkçe hata mesajı asistan balonunda görünür", async () => {
    mockApi.mockRejectedValueOnce(new ApiError(0, "Network error"))
    const user = userEvent.setup()

    const { container } = renderChat()
    await sendMessage(user, "Bağlantıyı test et")

    await waitFor(() => {
      expect(screen.getByText("Sunucuya ulaşılamıyor. Bağlantınızı kontrol edin.")).toBeInTheDocument()
    })

    expect(container.querySelector(".animate-bounce")).not.toBeInTheDocument()
  })
})
