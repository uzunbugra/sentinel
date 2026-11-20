"use client"

import { useCallback, useEffect, useState } from "react"
import { BrainCircuit } from "lucide-react"

import { describeError } from "@/components/ui/request-state"
import { formatDateTime } from "@/lib/datetime"
import {
  fetchActiveModel,
  formatCount,
  formatNumber,
  MISSING,
  type ActiveModelState,
  type ModelMetrics,
} from "@/lib/ml"
import { cn } from "@/lib/utils"

type CardState =
  | { phase: "loading" }
  | { phase: "error"; error: unknown }
  | { phase: "done"; result: ActiveModelState }

const METRIC_ROWS: { key: keyof Omit<ModelMetrics, "split">; label: string; count?: boolean }[] = [
  { key: "pr_auc", label: "PR-AUC" },
  { key: "baseline_pr_auc", label: "Baz PR-AUC" },
  { key: "roc_auc", label: "ROC-AUC" },
  { key: "precision", label: "Kesinlik" },
  { key: "recall", label: "Duyarlılık" },
  { key: "f1", label: "F1" },
  { key: "support_positive", label: "Pozitif örnek", count: true },
  { key: "support_total", label: "Toplam örnek", count: true },
]

/** Summary of today's active fraud model (`GET /ml/models`). */
export function ActiveModelCard() {
  const [state, setState] = useState<CardState>({ phase: "loading" })

  const load = useCallback(async () => {
    setState({ phase: "loading" })
    try {
      setState({ phase: "done", result: await fetchActiveModel() })
    } catch (error) {
      setState({ phase: "error", error })
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <section
      aria-labelledby="active-model-title"
      className="col-span-2 rounded-lg border border-line bg-base/60 p-3"
    >
      <div className="flex items-center justify-between mb-2.5">
        <h2
          id="active-model-title"
          className="text-[10px] font-mono uppercase tracking-wider text-muted"
        >
          aktif model
        </h2>
        <BrainCircuit className="w-3.5 h-3.5 text-signal" />
      </div>
      <CardBody state={state} onRetry={load} />
    </section>
  )
}

function CardBody({ state, onRetry }: { state: CardState; onRetry: () => void }) {
  if (state.phase === "loading") {
    return (
      <p role="status" className="text-[11px] text-muted">
        Model bilgisi yükleniyor...
      </p>
    )
  }
  if (state.phase === "error") {
    return (
      <div role="alert" className="flex items-center justify-between gap-2">
        <span className="text-[11px] text-alarm">{describeError(state.error)}</span>
        <RetryButton onRetry={onRetry} />
      </div>
    )
  }

  const { result } = state
  if (result.kind === "unsupported") {
    return (
      <p className="text-[11px] text-muted">
        Sunucu model özetini henüz yeni biçimde vermiyor.
      </p>
    )
  }
  if (result.kind === "unavailable") {
    return (
      <div className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-amber">
            {result.status === "invalid" ? "Model geçersiz; yüklenmedi." : "Yüklü model yok."}
          </span>
          <RetryButton onRetry={onRetry} />
        </div>
        <p className="text-[10px] text-muted">
          ML skorlaması kapalı; kural alarmları çalışmaya devam eder.
        </p>
        {result.reason && (
          <p className="text-[10px] font-mono text-muted/70 break-all">{result.reason}</p>
        )}
      </div>
    )
  }

  const { model } = result
  return (
    <div className="space-y-2.5">
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[11px]">
        <dt className="text-muted">Sürüm</dt>
        <dd className="font-mono text-ink break-all">{model.model_version}</dd>
        <dt className="text-muted">Eğitim</dt>
        <dd className="font-mono text-ink">{formatDateTime(model.trained_at)} (İstanbul)</dd>
        <dt className="text-muted">Veri kimliği</dt>
        <dd className="font-mono text-ink break-all">{model.dataset_id || MISSING}</dd>
        <dt className="text-muted">Eşik</dt>
        <dd className="font-mono text-ink">{formatNumber(model.threshold, 4)}</dd>
        <dt className="text-muted">Özellik seti</dt>
        <dd className="font-mono text-ink">{model.feature_set_version}</dd>
      </dl>
      <Metrics metrics={model.metrics} />
    </div>
  )
}

function Metrics({ metrics }: { metrics: ModelMetrics | null }) {
  if (!metrics) {
    return <p className="text-[11px] text-muted">Bu model için metrik kaydı yok.</p>
  }
  return (
    <div>
      <div className="text-[10px] font-mono uppercase tracking-wider text-muted/70 mb-1">
        metrikler {metrics.split ? `(${metrics.split})` : ""}
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
        {METRIC_ROWS.map(({ key, label, count }) => {
          const value = metrics[key]
          return (
            <div key={key} className="flex items-center justify-between gap-2">
              <dt className="text-muted">{label}</dt>
              <dd className={cn("font-mono tabular-nums", value === null ? "text-muted/50" : "text-ink")}>
                {count ? formatCount(value) : formatNumber(value)}
              </dd>
            </div>
          )
        })}
      </dl>
    </div>
  )
}

function RetryButton({ onRetry }: { onRetry: () => void }) {
  return (
    <button
      type="button"
      onClick={onRetry}
      className="text-[10px] font-mono text-signal hover:text-ink transition-colors"
    >
      Tekrar dene
    </button>
  )
}
