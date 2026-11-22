"use client"

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react"
import { KeyRound } from "lucide-react"

import { keyboardFocusWithin } from "@/components/ui/keyboard-focus"
import { describeError } from "@/components/ui/request-state"
import { useAuth } from "@/contexts/auth-context"
import {
  changePassword,
  describePasswordError,
  passwordRuleErrors,
  validatePasswordForm,
  type PasswordForm,
} from "@/lib/password"

const EMPTY: PasswordForm = { current: "", next: "", confirm: "" }

/** Opens the password dialog; placed in the user menu of both headers. */
export function ChangePasswordButton({ className }: { className?: string }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={
          className ??
          "p-1.5 text-zinc-500 hover:text-white hover:bg-zinc-800 rounded-lg transition-colors"
        }
        title="Parola değiştir"
        aria-label="Parola değiştir"
      >
        <KeyRound className="w-4 h-4" />
      </button>
      {open && <ChangePasswordDialog onClose={() => setOpen(false)} />}
    </>
  )
}

export function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const { logout } = useAuth()
  const [form, setForm] = useState<PasswordForm>(EMPTY)
  const [formError, setFormError] = useState<string | null>(null)
  const [requestError, setRequestError] = useState<unknown>(null)
  const [sending, setSending] = useState(false)
  const [done, setDone] = useState(false)
  const dialog = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    dialog.current?.focus()
    return () => previous?.focus()
  }, [])

  const set = (field: keyof PasswordForm) => (value: string) =>
    setForm((prev) => ({ ...prev, [field]: value }))

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape" && !sending) {
      event.stopPropagation()
      onClose()
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const invalid = validatePasswordForm(form)
    setFormError(invalid)
    if (invalid || sending) return
    setSending(true)
    setRequestError(null)
    try {
      await changePassword(form.current, form.next)
      setForm(EMPTY)
      setDone(true)
    } catch (err) {
      setRequestError(err)
    } finally {
      setSending(false)
    }
  }

  const rules = passwordRuleErrors(form.next)
  const fieldClass = "w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-white"

  return (
    <div className={"fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 " + keyboardFocusWithin}>
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="change-password-title"
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className="w-full max-w-md rounded-xl border border-zinc-700 bg-zinc-900 p-6 text-zinc-300"
      >
        <h2 id="change-password-title" className="mb-4 text-lg font-semibold text-white">
          Parola değiştir
        </h2>

        {done ? (
          <div className="space-y-4">
            <p role="status" className="text-sm text-emerald-300">
              Parolanız değişti. Diğer oturumlarınız kapatıldı; güvenlik için yeni parolanızla
              tekrar giriş yapın.
            </p>
            <button
              type="button"
              onClick={() => void logout()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
            >
              Tekrar giriş yap
            </button>
          </div>
        ) : (
          <form onSubmit={submit} noValidate className="space-y-3" aria-label="Parola değiştirme">
            <label className="block space-y-1">
              <span className="text-xs text-zinc-400">Mevcut parola</span>
              <input
                type="password"
                autoComplete="current-password"
                className={fieldClass}
                value={form.current}
                onChange={(e) => set("current")(e.target.value)}
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs text-zinc-400">Yeni parola</span>
              <input
                type="password"
                autoComplete="new-password"
                aria-describedby="password-rules"
                className={fieldClass}
                value={form.next}
                onChange={(e) => set("next")(e.target.value)}
              />
            </label>
            <ul id="password-rules" className="space-y-0.5 text-[11px]">
              {["En az 8 karakter olmalı.", "En az bir büyük harf içermeli.", "En az bir rakam içermeli."].map(
                (rule) => (
                  <li key={rule} className={form.next && !rules.includes(rule) ? "text-emerald-400" : "text-zinc-500"}>
                    {rule}
                  </li>
                ),
              )}
            </ul>
            <label className="block space-y-1">
              <span className="text-xs text-zinc-400">Yeni parola (tekrar)</span>
              <input
                type="password"
                autoComplete="new-password"
                className={fieldClass}
                value={form.confirm}
                onChange={(e) => set("confirm")(e.target.value)}
              />
            </label>

            {(formError || requestError !== null) && (
              <p role="alert" className="text-sm text-red-400">
                {formError ?? describePasswordError(requestError) ?? describeError(requestError)}
              </p>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                disabled={sending}
                className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800"
              >
                Vazgeç
              </button>
              <button
                type="submit"
                disabled={sending}
                aria-busy={sending}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                {sending ? "Kaydediliyor..." : "Parolayı değiştir"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
