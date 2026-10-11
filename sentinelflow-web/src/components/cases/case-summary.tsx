import type { Case } from "@/lib/cases"
import { formatDateTime } from "@/lib/datetime"
import { priorityColors, statusConfig } from "./case-labels"

export function CaseSummary({ item }: { item: Case }) {
  return (
    <section aria-labelledby="case-summary-title" className="rounded-xl border border-zinc-800 p-4">
      <h1 id="case-summary-title" className="break-words text-xl font-bold text-white">
        {item.title}
      </h1>
      <p className="my-2 break-all font-mono text-sm">{item.case_id}</p>
      <div className="mb-4 flex flex-wrap gap-2">
        <span className={`rounded border px-2 py-1 text-sm ${statusConfig[item.status].color}`}>
          {statusConfig[item.status].label}
        </span>
        <span className={`rounded px-2 py-1 text-sm ${priorityColors[item.priority]}`}>
          {item.priority}
        </span>
        {item.sla_breached && <span className="text-red-400">SLA İhlali</span>}
      </div>
      {item.description && <p className="mb-4 whitespace-pre-wrap break-words">{item.description}</p>}
      <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
        {[
          ["SLA son zamanı", formatDateTime(item.sla_due_at)],
          ["Atanan kişi", item.assigned_to || "—"],
          ["Atanan takım", item.assigned_team || "—"],
          ["Toplam tutar", `${item.total_amount.toLocaleString("tr-TR")} TRY`],
          ["Alarm sayısı", String(item.alert_count)],
          ["Oluşturulma", formatDateTime(item.created_at)],
          ["Güncellenme", formatDateTime(item.updated_at)],
        ].map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="text-zinc-500">{label}</dt>
            <dd className="break-words text-zinc-200">{value}</dd>
          </div>
        ))}
      </dl>
      {item.resolution && (
        <div className="mt-4">
          <h2 className="font-medium">Çözüm açıklaması</h2>
          <p className="whitespace-pre-wrap break-words text-sm">{item.resolution}</p>
        </div>
      )}
    </section>
  )
}
