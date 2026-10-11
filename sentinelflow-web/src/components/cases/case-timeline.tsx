"use client"

import { useEffect, useState } from "react"
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/request-state"
import { listCaseEvents, type CaseEventListResponse, type CaseEventType } from "@/lib/cases"
import { formatDateTime } from "@/lib/datetime"
import { eventLabels } from "./case-labels"

export function CaseTimeline({ caseId, revision }: { caseId: string; revision: number }) {
  const [query, setQuery] = useState({ page: 1, eventType: "", revision })
  const [data, setData] = useState<CaseEventListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)
  const [retry, setRetry] = useState(0)
  // A successful mutation resets pagination while preserving the selected filter.
  const page = query.revision === revision ? query.page : 1
  const eventType = query.eventType

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    listCaseEvents(caseId, {
      page,
      pageSize: 20,
      eventType: (eventType || undefined) as CaseEventType | undefined,
    }).then((response) => {
      if (active) setData(response)
    }).catch((err: unknown) => {
      if (active) setError(err)
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [caseId, page, eventType, revision, retry])

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / 20))
  return (
    <section aria-labelledby="case-timeline-title" className="min-w-0 rounded-xl border border-zinc-800 p-4">
      <h2 id="case-timeline-title" className="mb-3 text-lg font-semibold text-white">İşlem geçmişi</h2>
      <label className="block text-sm">
        Olay türü
        <select
          value={eventType}
          onChange={(event) => setQuery({ page: 1, eventType: event.target.value, revision })}
          className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-900 p-2"
        >
          <option value="">Tüm olaylar</option>
          {Object.entries(eventLabels).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>
      {loading ? <LoadingState label="İşlem geçmişi yükleniyor..." />
        : error !== null ? <ErrorState error={error} onRetry={() => setRetry((value) => value + 1)} />
        : !data?.events.length ? <EmptyState message="Henüz olay yok." />
        : <ol className="mt-4 space-y-4">
          {data.events.map((event) => (
            <li key={event.event_id} className="min-w-0 break-words border-l-2 border-blue-500 pl-3 text-sm">
              <h3 className="font-medium text-blue-400">{eventLabels[event.event_type] ?? event.event_type}</h3>
              <p>{event.actor} · {event.actor_type === "user" ? "Kullanıcı" : event.actor_type}</p>
              <p className="whitespace-pre-wrap">{event.description}</p>
              {(event.previous_value !== null || event.new_value !== null) && (
                <p className="text-zinc-400">{event.previous_value ?? "—"} → {event.new_value ?? "—"}</p>
              )}
              {event.alert_id && <p className="break-all">Alarm: {event.alert_id}</p>}
              <time dateTime={event.created_at} className="text-zinc-500">
                {formatDateTime(event.created_at)}
              </time>
            </li>
          ))}
        </ol>}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-sm">
        <p>Sayfa {page} / {totalPages}</p>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={loading || page <= 1}
            onClick={() => setQuery({ page: page - 1, eventType, revision })}
            className="rounded bg-zinc-800 px-3 py-2 disabled:opacity-50"
          >Önceki</button>
          <button
            type="button"
            disabled={loading || error !== null || page >= totalPages}
            onClick={() => setQuery({ page: page + 1, eventType, revision })}
            className="rounded bg-zinc-800 px-3 py-2 disabled:opacity-50"
          >Sonraki</button>
        </div>
      </div>
    </section>
  )
}
