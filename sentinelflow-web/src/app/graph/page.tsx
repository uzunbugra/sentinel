"use client"

import { useCallback, useEffect, useState, type FormEvent } from "react"
import { DatabaseZap, Info, Network } from "lucide-react"

import { NetworkGraph } from "@/components/dashboard/network-graph"
import { Header } from "@/components/layout/header"
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/request-state"
import { useWebSocket } from "@/hooks/use-websocket"
import { formatDateTime } from "@/lib/datetime"
import {
  fetchAccountNetwork,
  fetchGraphOverview,
  ringAccounts,
  shortIban,
  validateIban,
  type AccountNetwork,
  type FraudRing,
  type GraphOverview,
} from "@/lib/graph"
import { cn } from "@/lib/utils"

type Load<T> = { phase: "loading" } | { phase: "error"; error: unknown } | { phase: "done"; value: T }

const severityStyle: Record<string, string> = {
  critical: "border-red-500/30 bg-red-500/10 text-red-300",
  high: "border-orange-500/30 bg-orange-500/10 text-orange-300",
}

export default function GraphPage() {
  const { isConnected } = useWebSocket()
  const [overview, setOverview] = useState<Load<GraphOverview>>({ phase: "loading" })
  const [iban, setIban] = useState("")
  const [ibanError, setIbanError] = useState<string | null>(null)
  const [account, setAccount] = useState<{ iban: string; state: Load<AccountNetwork> } | null>(null)

  const loadOverview = useCallback(async () => {
    setOverview({ phase: "loading" })
    try {
      setOverview({ phase: "done", value: await fetchGraphOverview() })
    } catch (error) {
      setOverview({ phase: "error", error })
    }
  }, [])

  useEffect(() => {
    void loadOverview()
  }, [loadOverview])

  const openAccount = useCallback(async (target: string) => {
    const invalid = validateIban(target)
    setIbanError(invalid)
    if (invalid) return
    setIban(target)
    setAccount({ iban: target, state: { phase: "loading" } })
    try {
      const value = await fetchAccountNetwork(target)
      setAccount({ iban: target, state: { phase: "done", value } })
    } catch (error) {
      setAccount({ iban: target, state: { phase: "error", error } })
    }
  }, [])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    void openAccount(iban.trim())
  }

  return (
    <div className="min-h-screen bg-zinc-950">
      <Header isConnected={isConnected} />
      <main className="mx-auto max-w-7xl space-y-6 p-4 lg:p-6">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-white">
            <Network className="h-5 w-5 text-indigo-400" />
            Ağ grafiği ve para halkaları
          </h1>
          <p className="mt-1 flex items-start gap-1.5 text-sm text-zinc-400">
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
            Son 24 saatin işlem ağı ve Neo4j&apos;de bulunan döngüsel transferler (para
            halkaları). Bir halkadaki hesaba tıklayınca o hesabın iki adımlık komşuluğu açılır.
          </p>
        </div>

        <OverviewSection state={overview} onRetry={loadOverview} onAccount={openAccount} />

        <section aria-labelledby="account-title" className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <h2 id="account-title" className="text-sm font-semibold text-white">
            Hesap komşuluğu
          </h2>
          <form onSubmit={submit} noValidate aria-label="Hesap ara" className="flex flex-wrap items-end gap-2">
            <label className="flex-1 space-y-1">
              <span className="text-xs text-zinc-400">IBAN</span>
              <input
                value={iban}
                onChange={(e) => setIban(e.target.value.toUpperCase())}
                className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-sm text-zinc-200"
              />
            </label>
            <button type="submit" className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500">
              Göster
            </button>
          </form>
          {ibanError && (
            <p role="alert" className="text-sm text-red-400">
              {ibanError}
            </p>
          )}
          {account && <AccountResult iban={account.iban} state={account.state} />}
        </section>
      </main>
    </div>
  )
}

function OverviewSection({
  state,
  onRetry,
  onAccount,
}: {
  state: Load<GraphOverview>
  onRetry: () => void
  onAccount: (iban: string) => void
}) {
  if (state.phase === "loading") return <LoadingState label="Ağ yükleniyor..." />
  if (state.phase === "error") return <ErrorState error={state.error} onRetry={onRetry} />
  if (state.value.kind === "unavailable") return <GraphUnavailable onRetry={onRetry} />

  const { data, rings } = state.value
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="h-[460px] lg:col-span-2">
        {data.nodes.length === 0 ? (
          <div className="flex h-full items-center justify-center rounded-xl border border-zinc-800 bg-zinc-900/50">
            <EmptyState message="Son 24 saatte grafikte işlem yok." />
          </div>
        ) : (
          <NetworkGraph data={data} title="İşlem ağı (son 24 saat)" onRefresh={onRetry} />
        )}
      </div>
      <RingList rings={rings} onAccount={onAccount} />
    </div>
  )
}

function GraphUnavailable({ onRetry }: { onRetry: () => void }) {
  return (
    <div role="status" className="flex flex-col items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-900/50 p-8 text-center">
      <DatabaseZap className="h-10 w-10 text-amber-400" />
      <p className="text-sm text-zinc-200">Graf veritabanı (Neo4j) bu ortamda çalışmıyor.</p>
      <p className="max-w-lg text-xs text-zinc-500">
        Ağ grafiği ve para halkaları Neo4j&apos;deki işlemlerden hesaplanır. Örnek veri
        gösterilmez; Neo4j açılınca bu sayfa gerçek veriyle dolar.
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-lg border border-zinc-800 bg-zinc-800 px-4 py-1.5 text-sm text-zinc-300 hover:bg-zinc-700 hover:text-white"
      >
        Tekrar dene
      </button>
    </div>
  )
}

function RingList({ rings, onAccount }: { rings: FraudRing[]; onAccount: (iban: string) => void }) {
  return (
    <section aria-labelledby="rings-title" className="flex max-h-[460px] flex-col rounded-xl border border-zinc-800 bg-zinc-900/50">
      <h2 id="rings-title" className="border-b border-zinc-800 px-4 py-3 text-sm font-semibold text-white">
        Tespit edilen para halkaları ({rings.length})
      </h2>
      {rings.length === 0 ? (
        <EmptyState message="Döngüsel transfer bulunmadı." />
      ) : (
        <ul className="divide-y divide-zinc-800 overflow-y-auto">
          {rings.map((ring) => (
            <li key={ring.ring_id} className="space-y-2 p-4" aria-label={ring.ring_id}>
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-sm text-zinc-200">{ring.ring_id}</span>
                <span className={cn("rounded border px-2 py-0.5 text-xs", severityStyle[ring.severity] ?? "border-zinc-700 text-zinc-400")}>
                  {ring.severity === "critical" ? "Kritik" : ring.severity === "high" ? "Yüksek" : ring.severity}
                </span>
              </div>
              <p className="text-xs text-zinc-500">
                {ring.transaction_count} işlem ·{" "}
                {ring.total_amount.toLocaleString("tr-TR", { maximumFractionDigits: 0 })} toplam ·{" "}
                {formatDateTime(ring.detected_at)}
              </p>
              <div className="flex flex-wrap items-center gap-1">
                {ringAccounts(ring).map((iban, index) => (
                  <span key={iban} className="flex items-center gap-1">
                    {index > 0 && <span className="text-zinc-600">→</span>}
                    <button
                      type="button"
                      title={iban}
                      aria-label={`${iban} komşuluğunu göster`}
                      onClick={() => onAccount(iban)}
                      className="rounded border border-zinc-700 px-1.5 py-0.5 font-mono text-[11px] text-zinc-300 hover:bg-zinc-800"
                    >
                      {shortIban(iban)}
                    </button>
                  </span>
                ))}
                <span className="text-zinc-600">↺</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function AccountResult({ iban, state }: { iban: string; state: Load<AccountNetwork> }) {
  if (state.phase === "loading") return <LoadingState label="Komşuluk yükleniyor..." />
  if (state.phase === "error") return <ErrorState error={state.error} />
  if (state.value.kind === "not_found") {
    return <EmptyState message={`${iban} için grafikte işlem bulunamadı.`} />
  }
  if (state.value.kind === "unavailable") {
    return (
      <p role="status" className="text-sm text-amber-300">
        Graf veritabanı (Neo4j) çalışmadığı için hesap komşuluğu gösterilemiyor.
      </p>
    )
  }
  const { data } = state.value
  return (
    <div className="space-y-2">
      <p className="text-xs text-zinc-500" data-testid="account-summary">
        <span className="font-mono text-zinc-300">{iban}</span>: {data.nodes.length} hesap,{" "}
        {data.links.length} işlem (iki adıma kadar)
      </p>
      <div className="h-[380px]">
        <NetworkGraph data={data} title="Hesap komşuluğu" />
      </div>
    </div>
  )
}
