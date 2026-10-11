"use client"

import { useRef, useState, type ReactNode } from "react"
import {
  allowedTransitions,
  describeCaseError,
  updateCase,
  type Case,
  type CasePriority,
  type CaseStatus,
  type CaseUpdateRequest,
} from "@/lib/cases"
import { statusConfig } from "./case-labels"

const fieldClass = "mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-900 p-2"

interface MutationFormProps {
  caseId: string
  title: string
  buttonLabel: string
  canSubmit: boolean
  patch: () => CaseUpdateRequest
  onUpdated: (item: Case) => void
  onSaved?: () => void
  children: ReactNode
}

function MutationForm({
  caseId, title, buttonLabel, canSubmit, patch, onUpdated, onSaved, children,
}: MutationFormProps) {
  const pending = useRef(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<unknown>(null)

  return (
    <form
      aria-label={title}
      aria-busy={sending}
      className="rounded-xl border border-zinc-800 p-4"
      onSubmit={async (event) => {
        event.preventDefault()
        if (pending.current || !canSubmit) return
        pending.current = true
        setSending(true)
        setError(null)
        try {
          const result = await updateCase(caseId, patch())
          onUpdated(result)
          onSaved?.()
        } catch (err) {
          setError(err)
        } finally {
          pending.current = false
          setSending(false)
        }
      }}
    >
      <fieldset disabled={sending} className="space-y-3 text-sm disabled:opacity-60">
        <legend className="mb-3 font-semibold text-white">{title}</legend>
        {children}
        <button
          type="submit"
          disabled={sending || !canSubmit}
          className="rounded-lg bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {sending ? "Kaydediliyor..." : buttonLabel}
        </button>
      </fieldset>
      {error !== null && <p role="alert" className="mt-3 text-sm text-red-400">
        {describeCaseError(error)}
      </p>}
    </form>
  )
}

type ActionProps = { item: Case; onUpdated: (item: Case) => void }

function StatusForm({ item, onUpdated }: ActionProps) {
  const [status, setStatus] = useState<CaseStatus | "">("")
  const [resolution, setResolution] = useState("")
  const transitions = allowedTransitions(item.status)
  const needsResolution = status === "resolved_true_positive" || status === "resolved_false_positive"
  if (!transitions.length) return null

  return (
    <MutationForm
      caseId={item.case_id}
      title="Durum değiştirme"
      buttonLabel="Durumu kaydet"
      canSubmit={!!status && transitions.includes(status) && (!needsResolution || !!resolution.trim())}
      patch={() => ({
        status: status as CaseStatus,
        ...(needsResolution ? { resolution: resolution.trim() } : {}),
      })}
      onUpdated={onUpdated}
    >
      <label className="block">
        Yeni durum
        <select
          className={fieldClass}
          value={status}
          onChange={(event) => setStatus(event.target.value as CaseStatus | "")}
          required
        >
          <option value="">Durum seçin</option>
          {transitions.map((target) => (
            <option key={target} value={target}>{statusConfig[target].label}</option>
          ))}
        </select>
      </label>
      {needsResolution && <label className="block">
        Çözüm açıklaması
        <textarea
          className={fieldClass}
          value={resolution}
          onChange={(event) => setResolution(event.target.value)}
          required
        />
      </label>}
    </MutationForm>
  )
}

function PriorityForm({ item, onUpdated }: ActionProps) {
  const [priority, setPriority] = useState<CasePriority>(item.priority)
  return (
    <MutationForm
      caseId={item.case_id}
      title="Öncelik değiştirme"
      buttonLabel="Önceliği kaydet"
      canSubmit={priority !== item.priority}
      patch={() => ({ priority })}
      onUpdated={onUpdated}
    >
      <label className="block">
        Yeni öncelik
        <select
          className={fieldClass}
          value={priority}
          onChange={(event) => setPriority(event.target.value as CasePriority)}
        >
          {["P1", "P2", "P3", "P4"].map((value) => <option key={value}>{value}</option>)}
        </select>
      </label>
    </MutationForm>
  )
}

function AssignmentForm({ item, onUpdated }: ActionProps) {
  const [username, setUsername] = useState(item.assigned_to ?? "")
  const [team, setTeam] = useState(item.assigned_team ?? "")
  return (
    <MutationForm
      caseId={item.case_id}
      title="Atama"
      buttonLabel="Atamayı kaydet"
      canSubmit={!!username.trim()}
      patch={() => ({
        assigned_to: username.trim(),
        ...(team.trim() ? { assigned_team: team.trim() } : {}),
      })}
      onUpdated={onUpdated}
    >
      <label className="block">
        Kullanıcı adı
        <input
          className={fieldClass}
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          required
        />
      </label>
      <label className="block">
        Takım (isteğe bağlı)
        <input
          className={fieldClass}
          value={team}
          onChange={(event) => setTeam(event.target.value)}
        />
      </label>
    </MutationForm>
  )
}

function NoteForm({ item, onUpdated }: ActionProps) {
  const [note, setNote] = useState("")
  return (
    <MutationForm
      caseId={item.case_id}
      title="Not ekleme"
      buttonLabel="Notu ekle"
      canSubmit={!!note.trim() && note.length <= 5000}
      patch={() => ({ note: note.trim() })}
      onUpdated={onUpdated}
      onSaved={() => setNote("")}
    >
      <label className="block">
        Not
        <textarea
          className={fieldClass}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={5000}
          required
        />
      </label>
      <p className="text-zinc-500">{note.length} / 5000</p>
    </MutationForm>
  )
}

export function CaseActions({ item, onUpdated }: ActionProps) {
  return (
    <section aria-label="Vaka işlemleri" className="space-y-4">
      <StatusForm key={item.status} item={item} onUpdated={onUpdated} />
      <PriorityForm key={item.priority} item={item} onUpdated={onUpdated} />
      <AssignmentForm
        key={`${item.assigned_to}:${item.assigned_team}`}
        item={item}
        onUpdated={onUpdated}
      />
      <NoteForm item={item} onUpdated={onUpdated} />
    </section>
  )
}
