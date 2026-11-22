"use client"

import { useState, type FormEvent } from "react"
import { Info, UserSearch } from "lucide-react"

import { Header } from "@/components/layout/header"
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/request-state"
import { useAuth } from "@/contexts/auth-context"
import { useWebSocket } from "@/hooks/use-websocket"
import { canWrite } from "@/lib/auth"
import { formatDateTime } from "@/lib/datetime"
import {
  KYC_EXAMPLES,
  label,
  MATCH_TYPE_LABELS,
  matchSource,
  riskBand,
  SCREENING_TYPE_LABELS,
  screenCustomer,
  validateKycName,
  type KycScreenResponse,
} from "@/lib/kyc"
import { formatNumber } from "@/lib/ml"
import { cn } from "@/lib/utils"

const inputClass =
  "w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-indigo-500 focus:outline-none"

type ScreenState =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "error"; error: unknown }
  | { phase: "done"; result: KycScreenResponse }

export default function KycPage() {
  const { isConnected } = useWebSocket()
  const { user } = useAuth()
  const [name, setName] = useState("")
  const [country, setCountry] = useState("")
  const [formError, setFormError] = useState<string | null>(null)
  const [state, setState] = useState<ScreenState>({ phase: "idle" })

  const run = async (query: string) => {
    const invalid = validateKycName(query)
    setFormError(invalid)
    if (invalid) return
    setState({ phase: "loading" })
    try {
      setState({ phase: "done", result: await screenCustomer(query, country) })
    } catch (error) {
      setState({ phase: "error", error })
    }
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    void run(name)
  }

  return (
    <div className="min-h-screen bg-zinc-950">
      <Header isConnected={isConnected} />
      <main className="mx-auto max-w-5xl space-y-6 p-4 lg:p-6">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-white">
            <UserSearch className="h-5 w-5 text-indigo-400" />
            Müşteri taraması (PEP ve yaptırım)
          </h1>
          <p
            role="note"
            className="mt-2 flex items-start gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200"
          >
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
            Tarama, uygulamadaki küçük örnek listelere karşı yapılır. Bu listeler OFAC, BM, AB
            veya MASAK gibi resmî listelere bağlı değildir ve gerçek bir uyum kararı için
            kullanılamaz.
          </p>
        </div>

        {!canWrite(user) ? (
          <p role="alert" className="rounded-lg border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-300">
            Müşteri taraması analist ve yönetici rolleri içindir. Hesabınız yalnız görüntüleme
            yetkisine sahip.
          </p>
        ) : (
          <>
            <form
              onSubmit={submit}
              aria-label="Müşteri taraması"
              noValidate
              className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-900/50 p-4"
            >
              <div className="grid gap-3 sm:grid-cols-[2fr_1fr_auto] sm:items-end">
                <label className="block space-y-1">
                  <span className="text-xs text-zinc-400">Ad soyad</span>
                  <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs text-zinc-400">Ülke (isteğe bağlı)</span>
                  <input className={inputClass} value={country} onChange={(e) => setCountry(e.target.value)} />
                </label>
                <button
                  type="submit"
                  disabled={state.phase === "loading"}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  Tara
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                Örnek adlar:
                {KYC_EXAMPLES.map((example) => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => {
                      setName(example)
                      void run(example)
                    }}
                    className="rounded border border-zinc-800 px-2 py-0.5 text-zinc-300 hover:bg-zinc-800"
                  >
                    {example}
                  </button>
                ))}
              </div>
              {formError && (
                <p role="alert" className="text-sm text-red-400">
                  {formError}
                </p>
              )}
            </form>

            <section aria-label="Tarama sonucu" className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
              <ScreenResult state={state} />
            </section>
          </>
        )}
      </main>
    </div>
  )
}

function ScreenResult({ state }: { state: ScreenState }) {
  if (state.phase === "idle") {
    return <p className="text-sm text-zinc-500">Sonuç, tarama yapıldığında burada görünür.</p>
  }
  if (state.phase === "loading") return <LoadingState label="Taranıyor..." />
  if (state.phase === "error") return <ErrorState error={state.error} />

  const { result } = state
  const band = riskBand(result)
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span
          data-testid="kyc-recommendation"
          className={cn(
            "rounded-full border px-3 py-1 text-sm font-medium",
            band === "high" && "border-red-500/30 bg-red-500/10 text-red-300",
            band === "medium" && "border-amber-500/30 bg-amber-500/10 text-amber-300",
            band === "clean" && "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
          )}
        >
          {result.recommendation || (result.has_matches ? "Eşleşme var" : "Tarama temiz")}
        </span>
        <span className="text-sm text-zinc-400">
          Risk skoru <span className="font-mono text-white">{formatNumber(result.risk_score, 0)}</span>/100
        </span>
        <span className="text-xs text-zinc-500">
          {result.screening_types.map((t) => label(SCREENING_TYPE_LABELS, t)).join(" + ")} ·{" "}
          {result.screened_at ? formatDateTime(result.screened_at) : "—"}
        </span>
      </div>

      {result.matches.length === 0 ? (
        <EmptyState message={`"${result.query_name}" için örnek listelerde eşleşme yok.`} />
      ) : (
        <table className="w-full text-sm">
          <caption className="sr-only">Eşleşmeler</caption>
          <thead>
            <tr className="text-left text-xs text-zinc-500">
              <th scope="col" className="py-1 font-normal">Eşleşen ad</th>
              <th scope="col" className="py-1 font-normal">Eşleşme türü</th>
              <th scope="col" className="py-1 font-normal">Liste</th>
              <th scope="col" className="py-1 text-right font-normal">Skor</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {result.matches.map((match) => (
              <tr key={`${match.screening_type}-${match.match_id}`}>
                <th scope="row" className="py-2 pr-2 text-left font-normal text-zinc-200">
                  {match.matched_name}
                  {typeof match.details.matched_alias === "string" && (
                    <span className="block text-xs text-zinc-500">takma ad: {match.details.matched_alias}</span>
                  )}
                  {typeof match.details.position === "string" && match.details.position && (
                    <span className="block text-xs text-zinc-500">{match.details.position}</span>
                  )}
                </th>
                <td className="py-2 text-zinc-300">{label(MATCH_TYPE_LABELS, match.match_type)}</td>
                <td className="py-2 text-zinc-300">{matchSource(match)}</td>
                <td className="py-2 text-right font-mono text-zinc-200">{formatNumber(match.match_score, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
