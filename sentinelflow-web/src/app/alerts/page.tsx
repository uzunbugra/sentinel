"use client"

import { useEffect, useState, useCallback } from "react"
import Link from "next/link"
import { LinkCaseDialog } from "@/components/alerts/link-case-dialog"
import { keyboardFocusWithin } from "@/components/ui/keyboard-focus"
import { Header } from "@/components/layout/header"
import { useWebSocket } from "@/hooks/use-websocket"
import { 
  ShieldAlert, 
  RefreshCw, 
  ChevronRight,
  Clock,
  MapPin,
  TrendingUp,
  Eye,
  XCircle,
  Link as LinkIcon
} from "lucide-react"
import { formatDateTime, formatTime } from "@/lib/datetime"
import { cn } from "@/lib/utils"
import { apiRequest, canWrite } from "@/lib/auth"
import { useAuth } from "@/contexts/auth-context"
import {
  LoadingState,
  ErrorState,
  EmptyState,
  describeError,
} from "@/components/ui/request-state"

interface Alert {
  alert_id: string
  fraud_type: string
  severity: string
  confidence: number
  transaction_id: string
  sender_iban: string
  sender_name: string
  sender_city: string
  receiver_iban: string
  receiver_name: string
  receiver_city: string
  amount: number
  currency: string
  title: string
  description: string
  detected_at: string
  is_dismissed: boolean
  case_id: string | null
}

interface AlertsResponse {
  total: number
  page: number
  page_size: number
  alerts: Alert[]
}

import { config } from "@/lib/config"

const severityColors: Record<string, string> = {
  low: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  medium: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  high: "bg-orange-500/10 text-orange-400 border-orange-500/20",
  critical: "bg-red-500/10 text-red-400 border-red-500/20",
}

const fraudTypeLabels: Record<string, string> = {
  circular_ring: "Döngüsel Transfer",
  impossible_travel: "İmkansız Seyahat",
  blacklist_keyword: "Kara Liste",
  mule_account: "Mule Hesap",
  structuring: "Yapılandırma",
  velocity_anomaly: "Hız Anomalisi",
  ml_ensemble: "ML Tespit",
  compliance_violation: "Uyum İhlali",
}

export default function AlertsPage() {
  const { isConnected, alerts: wsAlerts } = useWebSocket()
  const { user } = useAuth()
  
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState<unknown>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  
  // Filters
  const [severityFilter, setSeverityFilter] = useState<string | null>(null)
  const [fraudTypeFilter, setFraudTypeFilter] = useState<string | null>(null)
  
  // Selected alert for detail view
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null)
  const [dismissError, setDismissError] = useState<unknown>(null)
  const [caseAlert, setCaseAlert] = useState<Alert | null>(null)

  const handleCaseLinked = (alertId: string, caseId: string) => {
    setAlerts((prev) => prev.map((alert) => alert.alert_id === alertId ? { ...alert, case_id: caseId } : alert))
    setSelectedAlert((prev) => prev?.alert_id === alertId ? { ...prev, case_id: caseId } : prev)
  }
  
  const fetchAlerts = useCallback(async () => {
    setLoading(true)
    setListError(null)
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: pageSize.toString(),
      })
      
      if (severityFilter) params.append("severity", severityFilter)
      if (fraudTypeFilter) params.append("fraud_type", fraudTypeFilter)
      
      const data = await apiRequest<AlertsResponse>(`${config.endpoints.alerts}?${params}`)
      setAlerts(data.alerts)
      setTotal(data.total)
    } catch (e) {
      setListError(e)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, severityFilter, fraudTypeFilter])
  
  useEffect(() => {
    fetchAlerts()
  }, [fetchAlerts])
  
  // Merge WebSocket alerts
  useEffect(() => {
    if (wsAlerts.length > 0 && page === 1) {
      const newAlerts = wsAlerts.filter(
        (wa) => !alerts.find((a) => a.alert_id === wa.alert_id)
      )
      if (newAlerts.length > 0) {
        setAlerts((prev) => {
          const wsMapped: Alert[] = newAlerts.map((wa) => ({
            alert_id: wa.alert_id,
            fraud_type: wa.fraud_type,
            severity: wa.severity,
            confidence: wa.confidence,
            transaction_id: wa.alert_id,
            sender_iban: wa.sender_iban || "",
            sender_name: "",
            sender_city: "",
            receiver_iban: wa.receiver_iban || "",
            receiver_name: "",
            receiver_city: "",
            amount: wa.amount,
            currency: "TRY",
            title: wa.fraud_type,
            description: wa.description,
            detected_at: wa.detected_at,
            is_dismissed: false,
            case_id: null,
          }))
          return [...wsMapped, ...prev].slice(0, pageSize)
        })
        setTotal((prevCount) => prevCount + newAlerts.length)
      }
    }
  }, [wsAlerts, page, alerts, pageSize])
  
  const handleDismiss = async (alertId: string) => {
    setDismissError(null)
    try {
      await apiRequest(config.endpoints.alertDismiss(alertId), { method: "POST" })
      setAlerts((prev) =>
        prev.map((a) =>
          a.alert_id === alertId ? { ...a, is_dismissed: true } : a
        )
      )
      if (selectedAlert?.alert_id === alertId) {
        setSelectedAlert({ ...selectedAlert, is_dismissed: true })
      }
    } catch (e) {
      setDismissError(e)
    }
  }
  
  const totalPages = Math.ceil(total / pageSize)
  
  return (
    <div className={cn("min-h-screen lg:h-screen flex flex-col bg-[#09090B]", keyboardFocusWithin)}>
      <Header isConnected={isConnected} />
      
      <main className="flex-1 max-lg:min-w-0 p-6 lg:overflow-hidden">
        <div className="lg:h-full flex flex-col gap-4">
          {/* Title and actions */}
          <div className="flex flex-wrap items-center justify-between gap-3 lg:flex-nowrap lg:gap-0">
            <div className="flex items-center gap-3">
              <ShieldAlert className="h-6 w-6 text-red-400" />
              <h1 className="text-2xl font-bold text-white">Alarmlar</h1>
              <span className="px-2 py-0.5 text-sm bg-zinc-800 text-zinc-400 rounded-full">
                {total} toplam
              </span>
            </div>
            
            <div className="flex max-lg:min-w-0 flex-wrap items-center gap-3 lg:flex-nowrap">
              {/* Severity filter */}
              <select
                aria-label="Seviye filtresi"
                value={severityFilter || ""}
                onChange={(e) => setSeverityFilter(e.target.value || null)}
                className="bg-zinc-900 border border-zinc-800 text-zinc-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Tüm Seviyeler</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
              
              {/* Fraud type filter */}
              <select
                aria-label="Tip filtresi"
                value={fraudTypeFilter || ""}
                onChange={(e) => setFraudTypeFilter(e.target.value || null)}
                className="bg-zinc-900 border border-zinc-800 text-zinc-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Tüm Tipler</option>
                {Object.entries(fraudTypeLabels).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
              
              <button
                aria-label="Yenile"
                disabled={loading}
                onClick={fetchAlerts}
                className="p-2 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-400 hover:text-white transition-colors disabled:cursor-not-allowed"
              >
                <RefreshCw className={cn("h-5 w-5", loading && "animate-spin")} />
              </button>
            </div>
          </div>
          
          {/* Content */}
          <div className="flex flex-col gap-4 lg:flex-1 lg:flex-row lg:min-h-0">
            {/* Alert list */}
            <div className="max-lg:min-w-0 lg:flex-1 bg-zinc-900/50 border border-zinc-800 rounded-xl overflow-hidden flex flex-col">
              <div className="lg:flex-1 lg:overflow-auto">
                {loading && alerts.length === 0 ? (
                  <LoadingState label="Alarmlar yükleniyor..." />
                ) : listError && alerts.length === 0 ? (
                  <ErrorState error={listError} onRetry={fetchAlerts} />
                ) : alerts.length === 0 ? (
                  <EmptyState message="Alarm bulunamadı" />
                ) : (
                  <div className="divide-y divide-zinc-800">
                    {alerts.map((alert) => (
                      <div
                        key={alert.alert_id}
                        role="button"
                        tabIndex={0}
                        aria-pressed={selectedAlert?.alert_id === alert.alert_id}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault()
                            setSelectedAlert(alert)
                          }
                        }}
                        onClick={() => setSelectedAlert(alert)}
                        className={cn(
                          "p-4 cursor-pointer transition-colors hover:bg-zinc-800/50",
                          selectedAlert?.alert_id === alert.alert_id && "bg-zinc-800/80",
                          alert.is_dismissed && "opacity-50"
                        )}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="flex max-lg:flex-wrap items-center gap-2 mb-1">
                              <span className={cn(
                                "px-2 py-0.5 text-xs font-medium rounded border",
                                severityColors[alert.severity]
                              )}>
                                {alert.severity.toUpperCase()}
                              </span>
                              <span className="text-xs text-zinc-500">
                                {fraudTypeLabels[alert.fraud_type] || alert.fraud_type}
                              </span>
                              {alert.is_dismissed && (
                                <span className="text-xs text-zinc-600">
                                  (Dismissed)
                                </span>
                              )}
                            </div>
                            
                            <p className="text-sm text-white font-medium truncate">
                              {alert.sender_name} → {alert.receiver_name}
                            </p>
                            
                            <div className="flex max-lg:flex-wrap items-center gap-4 mt-1 text-xs text-zinc-500">
                              <span className="flex items-center gap-1">
                                <TrendingUp className="h-3 w-3" />
                                {(alert.confidence * 100).toFixed(0)}%
                              </span>
                              <span className="font-mono">
                                {alert.amount.toLocaleString("tr-TR")} {alert.currency}
                              </span>
                              <span className="flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {formatTime(alert.detected_at)}
                              </span>
                            </div>
                          </div>
                          
                          <ChevronRight className="h-5 w-5 text-zinc-600 flex-shrink-0" />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              
              {/* Pagination */}
              {totalPages > 1 && (
                <nav aria-label="Sayfalama" className="flex max-lg:flex-wrap items-center justify-between gap-y-2 px-4 py-3 border-t border-zinc-800 bg-zinc-900/80">
                  <span className="text-sm text-zinc-500">
                    Sayfa {page} / {totalPages}
                  </span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page === 1}
                      className="px-3 py-1.5 text-sm bg-zinc-800 text-zinc-300 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Önceki
                    </button>
                    <button
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                      disabled={page === totalPages}
                      className="px-3 py-1.5 text-sm bg-zinc-800 text-zinc-300 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Sonraki
                    </button>
                  </div>
                </nav>
              )}
            </div>
            
            {/* Alert detail panel */}
            <div className="w-full lg:w-96 max-lg:break-words bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 lg:overflow-auto">
              {selectedAlert ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h2 className="text-lg font-bold text-white">Alarm Detayı</h2>
                    <span className={cn(
                      "px-2 py-0.5 text-xs font-medium rounded border",
                      severityColors[selectedAlert.severity]
                    )}>
                      {selectedAlert.severity.toUpperCase()}
                    </span>
                  </div>
                  
                  <div className="space-y-3">
                    <dl>
                      <dt className="text-xs text-zinc-500 block">Alarm ID</dt>
                      <dd className="text-sm text-zinc-300 font-mono">{selectedAlert.alert_id}</dd>
                    </dl>
                    
                    <dl>
                      <dt className="text-xs text-zinc-500 block">Tip</dt>
                      <dd className="text-sm text-white">
                        {fraudTypeLabels[selectedAlert.fraud_type] || selectedAlert.fraud_type}
                      </dd>
                    </dl>
                    
                    <dl>
                      <dt className="text-xs text-zinc-500 block">Güven Skoru</dt>
                      <dd className="flex items-center gap-2">
                        <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-gradient-to-r from-yellow-500 to-red-500"
                            style={{ width: `${selectedAlert.confidence * 100}%` }}
                          />
                        </div>
                        <span className="text-sm text-white font-mono">
                          {(selectedAlert.confidence * 100).toFixed(1)}%
                        </span>
                      </dd>
                    </dl>
                    
                    <hr className="border-zinc-800" />
                    
                    <dl>
                      <dt className="text-xs text-zinc-500 block">Gönderen</dt>
                      <dd>
                        <p className="text-sm text-white">{selectedAlert.sender_name}</p>
                        <p className="text-xs text-zinc-500 font-mono">{selectedAlert.sender_iban}</p>
                        {selectedAlert.sender_city && (
                          <p className="text-xs text-zinc-500 flex items-center gap-1 mt-1">
                            <MapPin className="h-3 w-3" />
                            {selectedAlert.sender_city}
                          </p>
                        )}
                      </dd>
                    </dl>
                    
                    <dl>
                      <dt className="text-xs text-zinc-500 block">Alıcı</dt>
                      <dd>
                        <p className="text-sm text-white">{selectedAlert.receiver_name}</p>
                        <p className="text-xs text-zinc-500 font-mono">{selectedAlert.receiver_iban}</p>
                        {selectedAlert.receiver_city && (
                          <p className="text-xs text-zinc-500 flex items-center gap-1 mt-1">
                            <MapPin className="h-3 w-3" />
                            {selectedAlert.receiver_city}
                          </p>
                        )}
                      </dd>
                    </dl>
                    
                    <dl>
                      <dt className="text-xs text-zinc-500 block">Tutar</dt>
                      <dd className="text-xl font-bold text-white">
                        {selectedAlert.amount.toLocaleString("tr-TR")} {selectedAlert.currency}
                      </dd>
                    </dl>
                    
                    <dl>
                      <dt className="text-xs text-zinc-500 block">Tespit Zamanı</dt>
                      <dd className="text-sm text-zinc-300">
                        {formatDateTime(selectedAlert.detected_at)}
                      </dd>
                    </dl>
                    
                    {selectedAlert.description && (
                      <dl>
                        <dt className="text-xs text-zinc-500 block">Açıklama</dt>
                        <dd className="text-sm text-zinc-400">{selectedAlert.description}</dd>
                      </dl>
                    )}
                    
                    <hr className="border-zinc-800" />
                    
                    {/* Actions */}
                    <div className="flex flex-col gap-2">
                      {dismissError !== null && (
                        <p className="text-center text-xs text-red-400">
                          {describeError(dismissError)}
                        </p>
                      )}
                      
                      {!selectedAlert.is_dismissed && canWrite(user) && (
                        <button
                          onClick={() => handleDismiss(selectedAlert.alert_id)}
                          className="flex items-center justify-center gap-2 w-full py-2 bg-zinc-800 text-zinc-300 rounded-lg hover:bg-zinc-700 transition-colors"
                        >
                          <XCircle className="h-4 w-4" />
                          Reddet (False Positive)
                        </button>
                      )}
                      
                      {!selectedAlert.case_id && !selectedAlert.is_dismissed && canWrite(user) && (
                        <button onClick={() => setCaseAlert(selectedAlert)} className="flex items-center justify-center gap-2 w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 transition-colors">
                          <LinkIcon className="h-4 w-4" />
                          Vaka Oluştur
                        </button>
                      )}
                      
                      {selectedAlert.case_id && (
                        <p className="text-center text-sm text-zinc-500">
                          Bağlı Vaka: <Link className="text-blue-400 underline" href={`/cases/${selectedAlert.case_id}`}>{selectedAlert.case_id}</Link>
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-zinc-500">
                  <Eye className="h-12 w-12 mb-3 opacity-50" />
                  <p>Detay görmek için alarm seçin</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
      {caseAlert && <LinkCaseDialog
        key={caseAlert.alert_id}
        alertId={caseAlert.alert_id}
        suggestedTitle={`${fraudTypeLabels[caseAlert.fraud_type] || caseAlert.fraud_type} — ${caseAlert.sender_name || caseAlert.alert_id}`}
        onLinked={(caseId) => handleCaseLinked(caseAlert.alert_id, caseId)}
        onSuccess={() => setCaseAlert(null)}
        onClose={() => setCaseAlert(null)}
      />}
    </div>
  )
}
