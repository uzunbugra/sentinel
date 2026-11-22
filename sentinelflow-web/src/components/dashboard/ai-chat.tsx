"use client"

import { Fragment, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react"
import { Bot, Info, Send } from "lucide-react"

import { config } from "@/lib/config"
import { apiRequest } from "@/lib/auth"
import { describeError } from "@/components/ui/request-state"
import { cn } from "@/lib/utils"

// SF-525: the backend assistant (src/sentinelflow/api/routes/chat.py) matches
// keywords against a fixed knowledge base. It is not an LLM and does not look
// at transactions or alerts, so the panel says so and sends no context.

interface ChatReply {
  response: string
  suggestions?: string[]
}

interface Message {
  role: "user" | "assistant"
  content: string
  error?: boolean
}

export const MAX_CHAT_MESSAGE = 1000

/** Render the backend's `**bold**` markers; everything else stays plain text. */
export function renderChatText(text: string): ReactNode {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <strong key={i} className="font-semibold text-ink">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  )
}

export function AiChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [input, setInput] = useState("")
  const [isTyping, setIsTyping] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let active = true
    apiRequest<string[]>(config.endpoints.chatSuggestions)
      .then((list) => {
        if (active) setSuggestions(list)
      })
      // Suggestions are optional; the panel still works without them.
      .catch(() => {})
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [messages, isTyping])

  const send = async (text: string) => {
    const message = text.trim()
    if (!message || isTyping) return
    setMessages((prev) => [...prev, { role: "user", content: message }])
    setInput("")
    setIsTyping(true)
    try {
      const data = await apiRequest<ChatReply>(config.endpoints.chat, {
        method: "POST",
        body: JSON.stringify({ message }),
      })
      setMessages((prev) => [...prev, { role: "assistant", content: data.response }])
      if (data.suggestions?.length) setSuggestions(data.suggestions)
    } catch (err) {
      setMessages((prev) => [...prev, { role: "assistant", content: describeError(err), error: true }])
    } finally {
      setIsTyping(false)
    }
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    void send(input)
  }

  return (
    <section aria-labelledby="ai-chat-title" className="m-4 space-y-3 rounded-lg border border-line bg-base-2/60 p-4">
      <div>
        <h2 id="ai-chat-title" className="flex items-center gap-2 text-[13px] font-semibold text-ink">
          <Bot className="h-3.5 w-3.5 text-signal" />
          Yardım asistanı
        </h2>
        <p role="note" className="mt-1 flex items-start gap-1.5 text-[11px] text-muted">
          <Info className="mt-0.5 h-3 w-3 shrink-0" />
          Kural tabanlı asistan: sorudaki anahtar kelimelere göre hazır bilgi tabanından yanıt verir.
          Yapay zekâ dil modeli (LLM) kullanmaz, işlemlere ve alarmlara bakmaz.
        </p>
      </div>

      <div
        ref={logRef}
        role="log"
        aria-label="Sohbet"
        aria-live="polite"
        className="h-56 space-y-2 overflow-y-auto rounded-md border border-line bg-base p-3"
      >
        {messages.length === 0 && !isTyping && (
          <p className="text-[12px] text-muted">
            Dolandırıcılık türleri, MASAK eşikleri veya tespit kuralları hakkında soru sorun.
          </p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
            <div
              data-role={msg.role}
              className={cn(
                "max-w-[85%] whitespace-pre-line rounded-md px-3 py-2 text-[12px]",
                msg.role === "user"
                  ? "border border-signal/40 bg-signal/20 text-ink"
                  : msg.error
                    ? "border border-alarm/40 text-alarm"
                    : "border border-line bg-base-2 text-ink",
              )}
            >
              {msg.role === "assistant" && !msg.error ? renderChatText(msg.content) : msg.content}
            </div>
          </div>
        ))}
        {isTyping && (
          <p role="status" className="text-[11px] text-muted">
            Yanıt hazırlanıyor...
          </p>
        )}
      </div>

      {suggestions.length > 0 && (
        <div className="flex flex-wrap gap-1.5" aria-label="Önerilen sorular" role="group">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              disabled={isTyping}
              onClick={() => void send(s)}
              className="rounded-md border border-line px-2 py-1 text-[11px] text-muted hover:text-ink disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={submit} className="flex items-center gap-2">
        <input
          type="text"
          aria-label="Mesaj"
          placeholder="Bir soru yazın..."
          maxLength={MAX_CHAT_MESSAGE}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="flex-1 rounded-md border border-line bg-base px-2 py-1.5 text-[12px] text-ink placeholder:text-muted"
        />
        <button
          type="submit"
          aria-label="Gönder"
          disabled={!input.trim() || isTyping}
          className="rounded-md border border-signal/40 bg-signal/20 p-2 text-ink hover:bg-signal/30 disabled:opacity-50"
        >
          <Send className="h-3.5 w-3.5" />
        </button>
      </form>
    </section>
  )
}
