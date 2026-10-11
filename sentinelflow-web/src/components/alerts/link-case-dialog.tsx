"use client"

import Link from "next/link"
import { useEffect, useRef, useState, type FormEvent } from "react"
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/request-state"
import {
  type Case, type CasePriority, createCaseFromAlert, describeCaseError,
  linkedCaseId, linkAlertToCase, listOpenCases,
} from "@/lib/cases"

interface LinkCaseDialogProps {
  alertId: string
  suggestedTitle: string
  onLinked: (caseId: string) => void
  onSuccess: () => void
  onClose: () => void
}

export function LinkCaseDialog({ alertId, suggestedTitle, onLinked, onSuccess, onClose }: LinkCaseDialogProps) {
  const [mode, setMode] = useState("new")
  const [title, setTitle] = useState(suggestedTitle)
  const [description, setDescription] = useState("")
  const [priority, setPriority] = useState<CasePriority>("P3")
  const [cases, setCases] = useState<Case[]>([])
  const [caseId, setCaseId] = useState("")
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState<unknown>(null)
  const [retry, setRetry] = useState(0)
  const [error, setError] = useState<unknown>(null)
  const [sending, setSending] = useState(false)
  const pending = useRef(false)
  const dialog = useRef<HTMLDivElement>(null)
  const conflictCaseId = linkedCaseId(error)

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    dialog.current?.focus()
    return () => { previous?.focus() }
  }, [])

  useEffect(() => {
    if (mode !== "existing") return
    let active = true
    setLoading(true)
    setListError(null)
    listOpenCases().then((items) => {
      if (active) setCases(items)
    }).catch((err: unknown) => {
      if (active) setListError(err)
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [mode, retry])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending.current || conflictCaseId || (mode === "new" ? !title.trim() : !caseId || loading || listError !== null)) return
    pending.current = true
    setSending(true)
    setError(null)
    try {
      const result = mode === "new"
        ? await createCaseFromAlert({ title: title.trim(), description, priority, alert_ids: [alertId] })
        : await linkAlertToCase(caseId, alertId)
      onLinked(result.case_id)
      onSuccess()
    } catch (err) {
      setError(err)
      const existingId = linkedCaseId(err)
      if (existingId) onLinked(existingId)
    } finally {
      pending.current = false
      setSending(false)
    }
  }

  const fieldClass = "w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-white"
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div ref={dialog} role="dialog" aria-modal="true" aria-labelledby="link-case-title" tabIndex={-1}
        className="max-h-[90vh] w-full max-w-lg overflow-auto rounded-xl border border-zinc-700 bg-zinc-900 p-6 text-zinc-300"
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.stopPropagation()
            if (!pending.current) onClose()
          }
          if (event.key === "Tab") {
            const controls = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href]')
            if (!controls?.length) { event.preventDefault(); return }
            const first = controls[0]
            const last = controls[controls.length - 1]
            if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) {
              event.preventDefault(); last.focus()
            } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog.current)) {
              event.preventDefault(); first.focus()
            }
          }
        }}>
        <h2 id="link-case-title" className="mb-4 text-lg font-bold text-white">Alarmı vakaya bağla</h2>
        <form onSubmit={submit} className="space-y-4" aria-busy={sending}>
          <fieldset disabled={sending || !!conflictCaseId} className="space-y-4 disabled:opacity-60">
            <legend className="sr-only">Vaka seçeneği</legend>
            <div className="flex gap-4">
              <label><input type="radio" name="case-mode" checked={mode === "new"} onChange={() => setMode("new")} /> Yeni vaka</label>
              <label><input type="radio" name="case-mode" checked={mode === "existing"} onChange={() => setMode("existing")} /> Mevcut vakaya bağla</label>
            </div>
            {mode === "new" ? <>
              <label className="block">Başlık<input className={fieldClass} value={title} onChange={(e) => setTitle(e.target.value)} required /></label>
              <label className="block">Öncelik<select className={fieldClass} value={priority} onChange={(e) => setPriority(e.target.value as CasePriority)}>
                {["P1", "P2", "P3", "P4"].map((value) => <option key={value}>{value}</option>)}
              </select></label>
              <label className="block">Açıklama (isteğe bağlı)<textarea className={fieldClass} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
            </> : loading ? <LoadingState label="Açık vakalar yükleniyor..." />
              : listError !== null ? <ErrorState error={listError} onRetry={() => setRetry((value) => value + 1)} />
              : cases.length === 0 ? <EmptyState message="Açık vaka bulunamadı." />
              : <label className="block">Açık vaka<select className={fieldClass} value={caseId} onChange={(e) => setCaseId(e.target.value)} required>
                <option value="">Vaka seçin</option>
                {cases.map((item) => <option key={item.case_id} value={item.case_id}>{item.case_id} — {item.title}</option>)}
              </select></label>}
          </fieldset>
          {error !== null && <div role="alert" className="text-sm text-red-400">
            <p>{describeCaseError(error)}</p>
            {conflictCaseId && <Link className="underline" href={`/cases/${conflictCaseId}`}>Vakayı aç: {conflictCaseId}</Link>}
          </div>}
          <div className="flex justify-end gap-3">
            <button type="button" disabled={sending} onClick={onClose} className="rounded-lg bg-zinc-800 px-4 py-2 disabled:opacity-50">Kapat</button>
            <button type="submit" disabled={sending || !!conflictCaseId || (mode === "new" ? !title.trim() : loading || listError !== null || !caseId || !cases.some((item) => item.case_id === caseId))}
              className="rounded-lg bg-blue-600 px-4 py-2 text-white disabled:opacity-50">
              {sending ? "Gönderiliyor..." : mode === "new" ? "Vaka oluştur" : "Alarmı bağla"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
