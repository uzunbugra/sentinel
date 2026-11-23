"use client"

import { useState, type FormEvent, type ReactNode } from "react"
import { Calculator, Info } from "lucide-react"

import { MlDetails } from "@/components/alerts/model-evaluation"
import { Header } from "@/components/layout/header"
import { ErrorState, LoadingState } from "@/components/ui/request-state"
import { useAuth } from "@/contexts/auth-context"
import { useWebSocket } from "@/hooks/use-websocket"
import { canWrite } from "@/lib/auth"
import { formatNumber } from "@/lib/ml"
import {
  buildScoreRequest,
  COUNTRIES,
  CURRENCIES,
  defaultScoreForm,
  PAYMENT_TYPE_LABELS,
  PAYMENT_TYPES,
  scoreTransaction,
  scoreToDetails,
  validateScoreForm,
  type ScoreForm,
  type ScoreOutcome,
} from "@/lib/score"

const inputClass =
  "w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-indigo-500 focus:outline-none"

export default function ScorePage() {
  const { isConnected } = useWebSocket()
  const { user } = useAuth()
  const [form, setForm] = useState<ScoreForm>(() => defaultScoreForm())
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [requestError, setRequestError] = useState<unknown>(null)
  const [outcome, setOutcome] = useState<ScoreOutcome | null>(null)

  const allowed = canWrite(user)

  const update = (field: keyof ScoreForm) => (value: string) =>
    setForm((prev) => ({ ...prev, [field]: value }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const invalid = validateScoreForm(form)
    setFormError(invalid)
    if (invalid) return
    setSubmitting(true)
    setRequestError(null)
    setOutcome(null)
    try {
      setOutcome(await scoreTransaction(buildScoreRequest(form)))
    } catch (err) {
      setRequestError(err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950">
      <Header isConnected={isConnected} />
      <main className="mx-auto max-w-6xl space-y-6 p-4 lg:p-6">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-white">
            <Calculator className="h-5 w-5 text-indigo-400" />
            İşlem skorlama
          </h1>
          <p className="mt-1 flex items-start gap-1.5 text-sm text-zinc-400">
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
            Bu araç işlemi yalnız skorlar: işlem kaydedilmez, alarm üretilmez ve hesap geçmişi
            değişmez. Geçmiş özellikleri o anki hesap geçmişinden okunur.
          </p>
        </div>

        {!allowed ? (
          <p
            role="alert"
            className="rounded-lg border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-300"
          >
            İşlem skorlama analist ve yönetici rolleri içindir. Hesabınız yalnız görüntüleme
            yetkisine sahip.
          </p>
        ) : (
          <div className="grid gap-6 lg:grid-cols-2">
            <form
              onSubmit={submit}
              aria-label="Skorlanacak işlem"
              className="space-y-4 rounded-xl border border-zinc-800 bg-zinc-900/50 p-4"
              noValidate
            >
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Gönderen IBAN">
                  <input className={inputClass} value={form.sender_iban} onChange={(e) => update("sender_iban")(e.target.value)} />
                </Field>
                <Field label="Gönderen adı">
                  <input className={inputClass} value={form.sender_name} onChange={(e) => update("sender_name")(e.target.value)} />
                </Field>
                <Field label="Alıcı IBAN">
                  <input className={inputClass} value={form.receiver_iban} onChange={(e) => update("receiver_iban")(e.target.value)} />
                </Field>
                <Field label="Alıcı adı">
                  <input className={inputClass} value={form.receiver_name} onChange={(e) => update("receiver_name")(e.target.value)} />
                </Field>
                <Field label="Tutar">
                  <input className={inputClass} type="number" min="0" step="0.01" inputMode="decimal" value={form.amount} onChange={(e) => update("amount")(e.target.value)} />
                </Field>
                <Field label="İşlem zamanı (UTC)">
                  <input className={inputClass} type="datetime-local" value={form.timestamp} onChange={(e) => update("timestamp")(e.target.value)} />
                </Field>
                <Field label="Ödeme para birimi">
                  <Select value={form.currency} options={CURRENCIES} onChange={update("currency")} />
                </Field>
                <Field label="Alınan para birimi">
                  <Select value={form.received_currency} options={CURRENCIES} onChange={update("received_currency")} />
                </Field>
                <Field label="Gönderen ülke">
                  <Select value={form.sender_country} options={COUNTRIES} onChange={update("sender_country")} />
                </Field>
                <Field label="Alıcı ülke">
                  <Select value={form.receiver_country} options={COUNTRIES} onChange={update("receiver_country")} />
                </Field>
                <Field label="Ödeme tipi">
                  <Select
                    value={form.payment_type}
                    options={PAYMENT_TYPES}
                    labels={PAYMENT_TYPE_LABELS}
                    onChange={update("payment_type")}
                  />
                </Field>
              </div>

              {formError && (
                <p role="alert" className="text-sm text-red-400">
                  {formError}
                </p>
              )}

              <button
                type="submit"
                disabled={submitting}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
              >
                {submitting ? "Skorlanıyor..." : "Skorla"}
              </button>
            </form>

            <section
              aria-label="Skor sonucu"
              className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4"
            >
              <ScoreResult submitting={submitting} error={requestError} outcome={outcome} />
            </section>
          </div>
        )}
      </main>
    </div>
  )
}

function ScoreResult({
  submitting,
  error,
  outcome,
}: {
  submitting: boolean
  error: unknown
  outcome: ScoreOutcome | null
}) {
  if (submitting) return <LoadingState label="Skorlanıyor..." />
  if (error) return <ErrorState error={error} />
  if (!outcome) {
    return <p className="text-sm text-zinc-500">Sonuç, işlem skorlandığında burada görünür.</p>
  }
  if (outcome.kind === "model_unavailable") {
    return (
      <div role="alert" className="space-y-1 text-sm">
        <p className="font-medium text-amber-300">Model yüklü değil; işlem skorlanamadı.</p>
        <p className="text-zinc-400">
          API geçerli bir dolandırıcılık modeli yüklemeden çalışıyor. Model paketi kurulunca
          tekrar deneyin.
          {outcome.reason && <> Sunucu mesajı: {outcome.reason}</>}
        </p>
      </div>
    )
  }

  const { result } = outcome
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span
          data-testid="score-decision"
          className={
            result.is_fraud
              ? "rounded-full border border-red-500/30 bg-red-500/10 px-3 py-1 text-sm font-medium text-red-300"
              : "rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-sm font-medium text-emerald-300"
          }
        >
          {result.is_fraud ? "Karar: şüpheli (alarm eşiğini aşıyor)" : "Karar: eşiğin altında"}
        </span>
        <span className="text-xs text-zinc-500">
          Yanıt süresi {formatNumber(result.latency_ms, 1)} ms
        </span>
      </div>
      <MlDetails details={scoreToDetails(result)} summary={null} modelLabel="Skorlayan model" />
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs text-zinc-400">{label}</span>
      {children}
    </label>
  )
}

function Select({
  value,
  options,
  labels,
  onChange,
}: {
  value: string
  options: readonly string[]
  labels?: Record<string, string>
  onChange: (value: string) => void
}) {
  return (
    <select className={inputClass} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((option) => (
        <option key={option} value={option}>
          {labels?.[option] ?? option}
        </option>
      ))}
    </select>
  )
}
