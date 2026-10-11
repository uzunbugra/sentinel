"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useEffect, useState } from "react"
import { Header } from "@/components/layout/header"
import { ErrorState, LoadingState } from "@/components/ui/request-state"
import { CaseSummary } from "@/components/cases/case-summary"
import { CaseAlerts } from "@/components/cases/case-alerts"
import { CaseTimeline } from "@/components/cases/case-timeline"
import { CaseActions } from "@/components/cases/case-actions"
import { useAuth } from "@/contexts/auth-context"
import { useWebSocket } from "@/hooks/use-websocket"
import { ApiError, canWrite } from "@/lib/auth"
import { getCase, type Case } from "@/lib/cases"

function CaseDetail({ id }: { id: string }) {
  const { user } = useAuth()
  const { isConnected } = useWebSocket()
  const [item, setItem] = useState<Case | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)
  const [retry, setRetry] = useState(0)
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    getCase(id).then((response) => {
      if (active) setItem(response)
    }).catch((err: unknown) => {
      if (active) setError(err)
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [id, retry])

  function onUpdated(updated: Case) {
    setItem(updated)
    setRevision((value) => value + 1)
  }

  return (
    <div className={
      "min-h-screen bg-[#09090B] text-zinc-300 " +
      "[&>header]:h-auto [&>header]:min-h-14 [&>header]:flex-wrap " +
      "[&>header]:gap-3 [&>header]:p-4 [&>header>div]:flex-wrap " +
      "[&>header>div]:gap-3 [&>header_nav]:flex-wrap"
    }>
      <Header isConnected={isConnected} />
      <main className="mx-auto w-full max-w-7xl p-4 sm:p-6">
        <Link href="/cases" className="mb-4 inline-block text-blue-400 underline">
          Vaka listesine dön
        </Link>
        {loading ? <LoadingState label="Vaka yükleniyor..." />
          : error instanceof ApiError && error.status === 404 ? (
            <p role="alert" className="py-6 text-zinc-300">Vaka bulunamadı.</p>
          ) : error !== null ? (
            <ErrorState error={error} onRetry={() => setRetry((value) => value + 1)} />
          ) : item && (
            <div className="grid min-w-0 grid-cols-1 items-start gap-6 lg:grid-cols-2">
              <div className="min-w-0 space-y-4">
                <CaseSummary item={item} />
                <CaseAlerts alertIds={item.alert_ids} />
                {canWrite(user) && <CaseActions item={item} onUpdated={onUpdated} />}
              </div>
              <CaseTimeline caseId={id} revision={revision} />
            </div>
          )}
      </main>
    </div>
  )
}

export default function CaseDetailPage() {
  const { case_id: caseId } = useParams<{ case_id: string }>()
  return <CaseDetail key={caseId} id={caseId} />
}
