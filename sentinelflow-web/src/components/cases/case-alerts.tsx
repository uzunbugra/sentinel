"use client"

import { useEffect, useState } from "react"
import { apiRequest } from "@/lib/auth"
import { config } from "@/lib/config"
import { EmptyState, LoadingState } from "@/components/ui/request-state"

interface LinkedAlert {
  alert_id: string
  title: string
  severity: string
  amount: number
  currency: string
}

export function CaseAlerts({ alertIds }: { alertIds: string[] }) {
  const [items, setItems] = useState<(LinkedAlert | null)[]>([])
  const [loading, setLoading] = useState(true)

  // Every PATCH returns a fresh `alert_ids` array; key on its content so the
  // alerts are only refetched when the linked set actually changes.
  const shownIds = alertIds.slice(0, 20).join(",")

  useEffect(() => {
    let active = true
    setLoading(true)
    const ids = shownIds ? shownIds.split(",") : []
    Promise.allSettled(ids.map((id) =>
      apiRequest<LinkedAlert>(config.endpoints.alertDetail(id))
    )).then((results) => {
      if (!active) return
      setItems(results.map((result) => result.status === "fulfilled" ? result.value : null))
      setLoading(false)
    })
    return () => { active = false }
  }, [shownIds])

  return (
    <section aria-labelledby="linked-alerts-title" className="rounded-xl border border-zinc-800 p-4">
      <h2 id="linked-alerts-title" className="text-lg font-semibold text-white">Bağlı alarmlar</h2>
      {loading ? <LoadingState label="Alarmlar yükleniyor..." />
        : alertIds.length === 0 ? <EmptyState message="Bağlı alarm yok." />
        : <ul className="divide-y divide-zinc-800">
          {alertIds.slice(0, 20).map((id, index) => (
            <li key={id} className="break-words py-3 text-sm">
              <p className="break-all font-mono text-zinc-400">{id}</p>
              {items[index] && <>
                <p>{items[index].title}</p>
                <p>{items[index].severity.toUpperCase()} · {items[index].amount.toLocaleString("tr-TR")} {items[index].currency}</p>
              </>}
            </li>
          ))}
        </ul>}
      {alertIds.length > 20 && <p className="mt-2 text-sm">+{alertIds.length - 20} alarm daha</p>}
    </section>
  )
}
