"use client"

import { useState, type FormEvent } from "react"
import Link from "next/link"
import { Send } from "lucide-react"

import { describeError } from "@/components/ui/request-state"
import { useAuth } from "@/contexts/auth-context"
import { canWrite } from "@/lib/auth"
import {
  buildDemoTransaction,
  DEMO_PRESETS,
  DEMO_RECEIVER,
  DEMO_SENDER,
  submitDemoTransaction,
  type DemoPreset,
  type TransactionResult,
} from "@/lib/demo-transaction"
import { formatNumber } from "@/lib/ml"
import { cn } from "@/lib/utils"

type FormState =
  | { phase: "idle" }
  | { phase: "sending" }
  | { phase: "done"; result: TransactionResult }
  | { phase: "error"; error: unknown }

/**
 * "Send a demo transaction" for live demos (SF-523). Shown to analysts and
 * admins; parties are fixed synthetic accounts. The API answers with the
 * model decision; a raised alert also arrives on the live alert stream.
 */
export function DemoTransactionForm() {
  const { user } = useAuth()
  const [preset, setPreset] = useState<DemoPreset>("suspicious")
  const [amount, setAmount] = useState(String(DEMO_PRESETS.suspicious.amount))
  const [state, setState] = useState<FormState>({ phase: "idle" })

  if (!canWrite(user)) return null

  const choose = (next: DemoPreset) => {
    setPreset(next)
    setAmount(String(DEMO_PRESETS[next].amount))
  }

  const parsedAmount = Number(amount)
  const amountValid = Number.isFinite(parsedAmount) && parsedAmount > 0

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!amountValid) return
    setState({ phase: "sending" })
    try {
      const result = await submitDemoTransaction(buildDemoTransaction(preset, parsedAmount))
      setState({ phase: "done", result })
    } catch (error) {
      setState({ phase: "error", error })
    }
  }

  return (
    <section
      aria-labelledby="demo-transaction-title"
      className="m-4 rounded-lg border border-line bg-base-2/60 p-4 space-y-3"
    >
      <div>
        <h2 id="demo-transaction-title" className="flex items-center gap-2 text-[13px] font-semibold text-ink">
          <Send className="w-3.5 h-3.5 text-signal" />
          Demo işlem gönder
        </h2>
        <p className="mt-1 text-[11px] text-muted">
          Yalnız sentetik hesaplar: {DEMO_SENDER.name} ({DEMO_SENDER.iban}) →{" "}
          {DEMO_RECEIVER.name} ({DEMO_RECEIVER.iban}). İşlem kaydedilir ve hesap geçmişine
          yazılır; model şüpheli bulursa alarm canlı akışa düşer.
        </p>
      </div>

      <form onSubmit={submit} aria-label="Demo işlem" className="flex flex-wrap items-end gap-3">
        <fieldset className="flex gap-2">
          <legend className="sr-only">Örnek</legend>
          {(Object.keys(DEMO_PRESETS) as DemoPreset[]).map((key) => (
            <label
              key={key}
              title={DEMO_PRESETS[key].description}
              className={cn(
                "cursor-pointer rounded-md border px-2.5 py-1.5 text-[12px]",
                preset === key ? "border-signal/60 bg-signal/10 text-ink" : "border-line text-muted",
              )}
            >
              <input
                type="radio"
                name="demo-preset"
                value={key}
                checked={preset === key}
                onChange={() => choose(key)}
                className="sr-only"
              />
              {DEMO_PRESETS[key].label}
            </label>
          ))}
        </fieldset>
        <label className="space-y-1">
          <span className="block text-[11px] text-muted">Tutar ({DEMO_PRESETS[preset].currency})</span>
          <input
            type="number"
            min="0"
            step="0.01"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            aria-invalid={!amountValid}
            className="w-32 rounded-md border border-line bg-base px-2 py-1.5 text-[12px] text-ink"
          />
        </label>
        <button
          type="submit"
          disabled={!amountValid || state.phase === "sending"}
          className="rounded-md bg-signal/20 border border-signal/40 px-3 py-1.5 text-[12px] font-medium text-ink hover:bg-signal/30 disabled:opacity-50"
        >
          {state.phase === "sending" ? "Gönderiliyor..." : "Gönder"}
        </button>
      </form>

      {!amountValid && (
        <p role="alert" className="text-[11px] text-alarm">
          Tutar sıfırdan büyük bir sayı olmalı.
        </p>
      )}
      <DemoResult state={state} />
    </section>
  )
}

function DemoResult({ state }: { state: FormState }) {
  if (state.phase === "error") {
    return (
      <p role="alert" className="text-[12px] text-alarm">
        {describeError(state.error)}
      </p>
    )
  }
  if (state.phase !== "done") return null

  const { result } = state
  const alertId = result.alerts?.[0]?.alert_id
  return (
    <div role="status" data-testid="demo-result" className="space-y-1 text-[12px]">
      <p className={result.is_fraud ? "text-alarm" : "text-signal"}>
        {result.is_fraud ? "Şüpheli: model alarm üretti." : "Temiz: eşiğin altında, alarm yok."}
      </p>
      <p className="font-mono text-muted">
        {result.transaction_id} · skor {formatNumber(result.fraud_score, 4)} ·{" "}
        {result.model_version ?? "model yüklü değil"} · {formatNumber(result.processing_time_ms, 1)} ms
      </p>
      {result.fraud_score === null && (
        <p className="text-amber">Model yüklü olmadığı için işlem skorlanmadı.</p>
      )}
      {alertId && (
        <p>
          Alarm <span className="font-mono">{alertId}</span> canlı akışa gönderildi.{" "}
          <Link href="/alerts" className="text-signal underline">
            Alarmlara git
          </Link>
        </p>
      )}
    </div>
  )
}
