import { BrainCircuit } from "lucide-react"

import {
  contributionUnitNote,
  extractModelEvaluation,
  featureLabel,
  formatNumber,
  formatSigned,
  isAboveThreshold,
  MISSING,
  type AlertEvidence,
} from "@/lib/ml"
import { cn } from "@/lib/utils"

interface ModelEvaluationProps {
  fraudType: string
  evidence: readonly AlertEvidence[] | null | undefined
}

/**
 * Model values recorded when the alert was raised (§4.5). It never reads the
 * active model, so a later model does not rewrite an old alert.
 */
export function ModelEvaluation({ fraudType, evidence }: ModelEvaluationProps) {
  const evaluation = extractModelEvaluation(fraudType, evidence)
  if (!evaluation) return null

  return (
    <section aria-labelledby="model-evaluation-title" className="space-y-3">
      <h3
        id="model-evaluation-title"
        className="flex items-center gap-2 text-sm font-semibold text-white"
      >
        <BrainCircuit className="h-4 w-4 text-blue-400" />
        Model değerlendirmesi
      </h3>

      {evaluation.kind === "legacy" ? (
        <p className="rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-xs text-zinc-400">
          Bu alarm model metadata&apos;sı kaydedilmeden önce üretildi; model sürümü, skor ve
          katkılar mevcut değil.
        </p>
      ) : (
        <MlDetails {...evaluation} />
      )}
    </section>
  )
}

function MlDetails({
  details,
  summary,
}: Extract<ReturnType<typeof extractModelEvaluation>, { kind: "ml" }>) {
  const above = isAboveThreshold(details.score, details.threshold)

  return (
    <div className="space-y-3">
      <dl>
        <dt className="text-xs text-zinc-500 block">Alarm anındaki model</dt>
        <dd className="text-sm text-zinc-300 font-mono break-all">
          {details.model_version ?? MISSING}
        </dd>
        <dd className="text-xs text-zinc-500">
          Özellik seti: <span className="font-mono">{details.feature_set_version ?? MISSING}</span>
        </dd>
      </dl>

      <dl className="grid grid-cols-2 gap-3">
        <div>
          <dt className="text-xs text-zinc-500">Skor</dt>
          <dd className="text-lg font-mono text-white">{formatNumber(details.score, 4)}</dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500">Eşik</dt>
          <dd className="text-lg font-mono text-white">{formatNumber(details.threshold, 4)}</dd>
        </div>
      </dl>

      <p
        data-testid="threshold-comparison"
        className={cn(
          "rounded border px-2 py-1 text-xs",
          above === true && "border-red-500/30 bg-red-500/10 text-red-300",
          above === false && "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
          above === null && "border-zinc-800 bg-zinc-900 text-zinc-400",
        )}
      >
        {above === null
          ? "Skor veya eşik kaydedilmemiş; karşılaştırma yapılamıyor."
          : above
            ? `Skor eşiğin üstünde (${formatNumber(details.score, 4)} ≥ ${formatNumber(details.threshold, 4)})`
            : `Skor eşiğin altında (${formatNumber(details.score, 4)} < ${formatNumber(details.threshold, 4)})`}
      </p>

      {summary && <p className="text-xs text-zinc-400">{summary}</p>}

      <div>
        <h4 className="text-xs text-zinc-500 mb-1">En etkili özellikler</h4>
        {details.top_features.length === 0 ? (
          <p className="text-xs text-zinc-500">Katkı kaydı yok.</p>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-zinc-500">
                <th scope="col" className="text-left font-normal py-1">Özellik</th>
                <th scope="col" className="text-right font-normal py-1">Değer</th>
                <th scope="col" className="text-right font-normal py-1">Katkı</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {details.top_features.map((f) => (
                <tr key={f.feature}>
                  <th scope="row" className="text-left font-normal py-1 pr-2 text-zinc-300">
                    {featureLabel(f.feature)}
                    <span className="block font-mono text-[10px] text-zinc-600">{f.feature}</span>
                  </th>
                  <td className="text-right font-mono text-zinc-300">{formatNumber(f.value)}</td>
                  <td
                    className={cn(
                      "text-right font-mono",
                      f.contribution === null
                        ? "text-zinc-500"
                        : f.contribution > 0
                          ? "text-red-300"
                          : f.contribution < 0
                            ? "text-emerald-300"
                            : "text-zinc-300",
                    )}
                  >
                    {formatSigned(f.contribution)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="mt-2 text-[11px] text-zinc-500">
          {contributionUnitNote(details.contribution_unit)}
          {details.base_value !== null && (
            <> Taban değer: <span className="font-mono">{formatSigned(details.base_value)}</span>.</>
          )}
        </p>
        {details.history_cold_start === true && (
          <p className="mt-1 text-[11px] text-amber-300">
            Hesapların geçmişi yoktu (cold start); geçmiş özellikleri varsayılan değerle hesaplandı.
          </p>
        )}
      </div>
    </div>
  )
}
