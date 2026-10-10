import { AlertTriangle, Inbox, RefreshCw } from "lucide-react"

import { ApiError } from "@/lib/auth"

// -----------------------------------------------------------------------------
// Error descriptions
// -----------------------------------------------------------------------------

/** Generic message the auth client fills in when the backend sends no detail. */
const GENERIC_MESSAGE = /^Request failed \(\d+\)$/

/**
 * The backend message for conflict/validation errors, when it sent one.
 * `ApiError.detail` is the raw backend detail; `message` mirrors it when it is
 * a string and otherwise falls back to "Request failed (N)".
 */
function backendMessage(err: ApiError): string | null {
  if (typeof err.detail === "string" && err.detail.trim()) {
    return err.detail
  }
  const msg = err.message?.trim()
  if (msg && !GENERIC_MESSAGE.test(msg)) {
    return msg
  }
  return null
}

/** Human-readable Turkish message for an error thrown by `apiRequest`. */
export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.kind) {
      case "unauthorized":
        return "Oturumunuz sona erdi."
      case "forbidden":
        return "Bu işlem için yetkiniz yok."
      case "not_found":
        return "Kayıt bulunamadı."
      case "conflict":
        return backendMessage(err) ?? "Kayıt başka bir işlemle çakıştı."
      case "validation":
        return backendMessage(err) ?? "Gönderilen bilgiler geçersiz."
      case "network":
        return "Sunucuya ulaşılamıyor. Bağlantınızı kontrol edin."
      case "server":
        return "Beklenmeyen bir hata oluştu."
    }
  }
  return "Beklenmeyen bir hata oluştu."
}

// -----------------------------------------------------------------------------
// Shared request states
// -----------------------------------------------------------------------------

interface LoadingStateProps {
  label?: string
}

export function LoadingState({ label = "Yükleniyor..." }: LoadingStateProps) {
  return (
    <div
      role="status"
      className="flex flex-col items-center justify-center gap-3 p-8 text-zinc-500"
    >
      <RefreshCw className="h-8 w-8 animate-spin" />
      <p className="text-sm">{label}</p>
    </div>
  )
}

interface ErrorStateProps {
  error: unknown
  onRetry?: () => void
}

export function ErrorState({ error, onRetry }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center gap-3 p-8 text-center"
    >
      <AlertTriangle className="h-10 w-10 text-red-400" />
      <p className="text-sm text-zinc-300">{describeError(error)}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-lg border border-zinc-800 bg-zinc-800 px-4 py-1.5 text-sm text-zinc-300 transition-colors hover:bg-zinc-700 hover:text-white"
        >
          Tekrar dene
        </button>
      )}
    </div>
  )
}

interface EmptyStateProps {
  message: string
}

export function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 p-8 text-zinc-500">
      <Inbox className="h-10 w-10 opacity-50" />
      <p className="text-sm">{message}</p>
    </div>
  )
}
