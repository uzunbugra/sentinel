"use client"

// =============================================================================
// SentinelFlow — SOC Dashboard (canli izleme ekrani)
// =============================================================================
// Landing sayfasinin tasarim diliyle tutarli. Sayilar ve alarm akisi yalniz
// API'den (REST + WebSocket) gelir; backend'e ulasilamazsa uydurma deger
// gosterilmez. Graf ve kure animasyonlari temsili olarak etiketlenir.
// =============================================================================

import { useEffect, useMemo, useState } from "react"
import dynamic from "next/dynamic"
import {
  Activity,
  ShieldAlert,
  CreditCard,
  Bell,
  ArrowLeft,
  CircleDot,
} from "lucide-react"
import Link from "next/link"
import { AnimatePresence, motion } from "motion/react"

import { useWebSocket } from "@/hooks/use-websocket"
import { formatTime } from "@/lib/datetime"
import { config } from "@/lib/config"
import { apiRequest } from "@/lib/auth"
import { describeError } from "@/components/ui/request-state"
import { cn } from "@/lib/utils"
import { fraudLabel, type Alert3D } from "@/components/3d/types"
import { SEVERITY_META } from "@/lib/landing-data"
import { NetworkGraph } from "@/components/landing/NetworkGraph"
import { ActiveModelCard } from "@/components/dashboard/active-model-card"

const GlobeScene = dynamic(() => import("@/components/3d/GlobeScene"), {
  ssr: false,
  loading: () => <PanelLoader label="Kure yukleniyor..." />,
})

function PanelLoader({ label }: { label: string }) {
  return (
    <div className="w-full h-full flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="w-7 h-7 border-2 border-signal/30 border-t-signal rounded-full animate-spin" />
        <span className="text-[10px] font-mono text-muted tracking-wider uppercase">
          {label}
        </span>
      </div>
    </div>
  )
}

// --- Backend istatistikleri (/api/v1/system/stats) ---------------------------
interface Stats {
  transactions_processed: number
  fraud_detected: number
  fraud_rate: number
  uptime_seconds: number
  alerts_created?: number
  by_severity?: Record<string, number>
}

// --- Alarm akisi (REST ilk yukleme + WebSocket) -------------------------------
type Severity = "critical" | "high" | "medium" | "low"

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"]

const SEV_META: Record<Severity, { label: string; color: string }> = {
  ...SEVERITY_META,
  low: { label: "Low", color: "#7d8ba1" },
}

interface AlertRowData {
  id: string
  ts: string
  engine: string
  severity: Severity
  detail: string
  amount: string
}

interface AlertsResponse {
  alerts: Alert3D[]
}

const ALERT_LIMIT = 12

function toSeverity(value: unknown): Severity {
  const s = String(value).toLowerCase()
  return (SEVERITIES as string[]).includes(s) ? (s as Severity) : "medium"
}

function toRow(a: Alert3D): AlertRowData {
  return {
    id: a.alert_id,
    ts: formatTime(a.detected_at),
    engine: a.fraud_type,
    severity: toSeverity(a.severity),
    detail: a.description || fraudLabel(a.fraud_type),
    amount: new Intl.NumberFormat("tr-TR", {
      style: "currency",
      currency: a.currency || "TRY",
      maximumFractionDigits: 0,
    }).format(a.amount ?? 0),
  }
}

/** WebSocket alarmlari once; ayni alarm REST'ten de geldiyse bir kez gosterilir. */
function mergeAlerts(live: Alert3D[], recent: Alert3D[]): AlertRowData[] {
  const seen = new Set<string>()
  const rows: AlertRowData[] = []
  for (const a of [...live, ...recent]) {
    if (!a?.alert_id || seen.has(a.alert_id)) continue
    seen.add(a.alert_id)
    rows.push(toRow(a))
    if (rows.length === ALERT_LIMIT) break
  }
  return rows
}

// --- Stat karti (landing temasiyla uyumlu) ----------------------------------
function StatCard({
  title,
  value,
  icon: Icon,
  accent,
  sub,
}: {
  title: string
  value: string | number
  icon: React.ComponentType<{ className?: string }>
  accent: "signal" | "alarm"
  sub: string
}) {
  const isPlaceholder = value === "---"
  return (
    <div className="rounded-lg border border-line bg-base-2/60 backdrop-blur-sm px-4 py-3.5">
      <div className="flex items-center justify-between mb-2.5">
        <span className="text-[10px] font-mono uppercase tracking-wider text-muted">
          {title}
        </span>
        <Icon
          className={cn(
            "w-3.5 h-3.5",
            accent === "alarm" ? "text-alarm" : "text-signal",
          )}
        />
      </div>
      <div
        className={cn(
          "font-mono tabular-nums text-xl font-semibold",
          isPlaceholder
            ? "text-muted/50"
            : accent === "alarm"
              ? "text-alarm"
              : "text-ink",
        )}
      >
        {value}
      </div>
      <div className="mt-1.5 text-[10px] text-muted/70">{sub}</div>
    </div>
  )
}

// --- Alert satiri -----------------------------------------------------------
function AlertRow({ a }: { a: AlertRowData }) {
  const sev = SEV_META[a.severity]
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
      className="grid grid-cols-[auto_1fr_auto] gap-3 items-center px-3 py-2.5 rounded-md hover:bg-signal/5 transition-colors border-b border-line/50"
    >
      <div className="flex items-center gap-2 min-w-0">
        <span
          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
          style={{ background: sev.color, boxShadow: `0 0 6px ${sev.color}` }}
        />
        <span className="text-[10px] font-mono text-muted tabular-nums">
          {a.ts}
        </span>
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span style={{ color: sev.color }} className="text-[11px] font-mono">
            {a.id}
          </span>
          <span className="text-[10px] text-muted/70 font-mono">
            {a.engine}
          </span>
        </div>
        <div className="text-[11px] text-ink/80 truncate font-mono mt-0.5">
          {a.detail}
        </div>
      </div>
      <span
        className="font-mono text-[12px] tabular-nums flex-shrink-0"
        style={{ color: sev.color }}
      >
        {a.amount}
      </span>
    </motion.div>
  )
}

const MOTORS = [
  { n: "Circular Ring", t: "Neo4j" },
  { n: "Impossible Travel", t: "Redis Geo" },
  { n: "NLP Blacklist", t: "scikit-learn" },
  { n: "ML Fraud Model", t: "LightGBM" },
]

export default function DashboardPage() {
  const { isConnected, alerts: wsAlerts } = useWebSocket()
  const isLive = isConnected

  const [stats, setStats] = useState<Stats>({
    transactions_processed: 0,
    fraud_detected: 0,
    fraud_rate: 0,
    uptime_seconds: 0,
  })
  const [recentAlerts, setRecentAlerts] = useState<Alert3D[]>([])
  const [alertsLoaded, setAlertsLoaded] = useState(false)
  const [backendUp, setBackendUp] = useState(false)
  const [statsError, setStatsError] = useState<unknown>(null)

  useEffect(() => {
    let alive = true
    const fetchStats = async () => {
      try {
        const data = await apiRequest<Stats>(config.endpoints.stats)
        if (!alive) return
        setStats(data)
        setBackendUp(true)
        setStatsError(null)
      } catch (err) {
        // Polling hatasi onceki istatistikleri silmez; sadece hata gosterilir.
        if (alive) setStatsError(err)
      }
    }
    fetchStats()
    const iv = setInterval(fetchStats, config.ui.statsRefreshInterval)
    return () => {
      alive = false
      clearInterval(iv)
    }
  }, [])

  // Son alarmlar acilista ve kayitli alarm sayisi degistikce REST'ten okunur;
  // WebSocket bagli degilken de liste guncel kalir.
  const alertsCreated = stats.alerts_created
  useEffect(() => {
    let alive = true
    apiRequest<AlertsResponse>(
      `${config.endpoints.alerts}?page=1&page_size=${ALERT_LIMIT}`,
    )
      .then((data) => {
        if (!alive) return
        setRecentAlerts(data.alerts ?? [])
        setAlertsLoaded(true)
      })
      .catch(() => {
        // Hata basliktaki istatistik gostergesinde zaten gorunur.
      })
    return () => {
      alive = false
    }
  }, [alertsCreated])

  const placeholder = "---"
  const txValue = backendUp
    ? stats.transactions_processed.toLocaleString()
    : placeholder
  const fraudValue = backendUp ? stats.fraud_detected.toLocaleString() : placeholder
  const alertsValue =
    backendUp && stats.alerts_created !== undefined
      ? stats.alerts_created.toLocaleString()
      : placeholder
  const uptimeValue = backendUp
    ? `${Math.floor(stats.uptime_seconds / 60)}m`
    : placeholder

  const alertList = useMemo(
    () => mergeAlerts(wsAlerts as Alert3D[], recentAlerts),
    [wsAlerts, recentAlerts],
  )

  return (
    <div className="min-h-screen flex flex-col bg-base text-ink">
      <DashboardHeader
        isLive={isLive}
        backendUp={backendUp}
        statsError={statsError}
      />
      <DashboardBody
        txValue={txValue}
        fraudValue={fraudValue}
        alertsValue={alertsValue}
        uptimeValue={uptimeValue}
        backendUp={backendUp}
        alertList={alertList}
        alertsLoaded={alertsLoaded}
        bySeverity={backendUp ? stats.by_severity : undefined}
        motors={MOTORS}
      />
    </div>
  )
}

function DashboardHeader({
  isLive,
  backendUp,
  statsError,
}: {
  isLive: boolean
  backendUp: boolean
  statsError: unknown
}) {
  return (
    <header className="sticky top-0 z-40 h-14 border-b border-line bg-base/80 backdrop-blur-md flex items-center justify-between px-5">
      <div className="flex items-center gap-4">
        <Link
          href="/"
          className="flex items-center gap-2 text-muted hover:text-signal transition-colors text-[13px]"
        >
          <ArrowLeft className="w-4 h-4" />
          Landing
        </Link>
        <span className="h-4 w-px bg-line" />
        <span className="font-display font-semibold text-[14px]">
          Sentinel<span className="text-signal">Flow</span>
        </span>
        <span className="text-[10px] font-mono text-muted/60 uppercase tracking-wider">
          {"// soc console"}
        </span>
      </div>
      <div className="flex items-center gap-3">
        {statsError !== null && (
          <span
            role="alert"
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-alarm/40 bg-alarm/10"
          >
            <ShieldAlert className="w-3 h-3 text-alarm" />
            <span className="text-[10px] font-mono text-alarm">
              {describeError(statsError)}
            </span>
          </span>
        )}
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-md border border-line bg-base-2/60">
          <span
            className={cn(
              "w-1.5 h-1.5 rounded-full",
              isLive
                ? "bg-signal animate-subtle-pulse"
                : "bg-amber animate-subtle-pulse",
            )}
          />
          <span className="text-[10px] font-mono uppercase tracking-wider text-muted">
            {isLive ? "live" : backendUp ? "rest" : "offline"}
          </span>
        </div>
        <Link
          href="/alerts"
          className="text-[12px] text-muted hover:text-ink transition-colors"
        >
          Alarmlar
        </Link>
        <Link
          href="/cases"
          className="text-[12px] text-muted hover:text-ink transition-colors"
        >
          Vakalar
        </Link>
      </div>
    </header>
  )
}

function DashboardBody({
  txValue,
  fraudValue,
  alertsValue,
  uptimeValue,
  backendUp,
  alertList,
  alertsLoaded,
  bySeverity,
  motors,
}: {
  txValue: string
  fraudValue: string
  alertsValue: string
  uptimeValue: string
  backendUp: boolean
  alertList: AlertRowData[]
  alertsLoaded: boolean
  bySeverity?: Record<string, number>
  motors: { n: string; t: string }[]
}) {
  return (
    <main className="flex-1 overflow-y-auto">
      <GraphStatsSection
        txValue={txValue}
        fraudValue={fraudValue}
        alertsValue={alertsValue}
        uptimeValue={uptimeValue}
        backendUp={backendUp}
        motors={motors}
      />
      <AlertConsoleSection
        alertList={alertList}
        alertsLoaded={alertsLoaded}
        bySeverity={bySeverity}
      />
    </main>
  )
}

function GraphStatsSection({
  txValue,
  fraudValue,
  alertsValue,
  uptimeValue,
  backendUp,
  motors,
}: {
  txValue: string
  fraudValue: string
  alertsValue: string
  uptimeValue: string
  backendUp: boolean
  motors: { n: string; t: string }[]
}) {
  return (
    <section className="relative grid grid-cols-1 lg:grid-cols-3 gap-px bg-line border-b border-line">
      <div className="lg:col-span-2 relative h-[340px] sm:h-[400px] bg-base-2/40 overflow-hidden">
        <NetworkGraph
          className="absolute inset-0 w-full h-full opacity-90"
          nodeCount={14}
          ringIntervalMs={4800}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-base via-transparent to-transparent" />
        <div className="absolute top-4 left-4 flex items-center gap-2">
          <CircleDot className="w-3.5 h-3.5 text-signal" />
          <span className="text-[11px] font-mono uppercase tracking-wider text-signal">
            transaction graph {"// temsili gorsel"}
          </span>
        </div>
        <div className="absolute top-4 right-4 px-2.5 py-1 rounded-md border border-line bg-base/70 backdrop-blur-sm">
          <span className="text-[9px] font-mono text-muted/70 uppercase tracking-wider">
            kirmizi = aklama halkasi
          </span>
        </div>
        <div className="absolute bottom-4 left-4 right-4">
          <p className="text-[10px] font-mono text-muted/70 uppercase tracking-wider">
            animasyon gercek islem verisini gostermez
          </p>
        </div>
      </div>

      <div className="bg-base-2/40 p-4 grid grid-cols-2 gap-3 content-start">
        <StatCard
          title="Islem"
          value={txValue}
          icon={CreditCard}
          accent="signal"
          sub={backendUp ? "api acilisindan beri" : "veri yok"}
        />
        <StatCard
          title="Dolandiricilik"
          value={fraudValue}
          icon={ShieldAlert}
          accent="alarm"
          sub={backendUp ? "tespit edildi" : "veri yok"}
        />
        <StatCard
          title="Alarm"
          value={alertsValue}
          icon={Bell}
          accent="signal"
          sub={backendUp ? "kayitli alarm" : "veri yok"}
        />
        <StatCard
          title="Calisma"
          value={uptimeValue}
          icon={Activity}
          accent="signal"
          sub="sistem sagligi"
        />

        <div className="col-span-2 rounded-lg border border-line bg-base/60 p-3">
          <div className="text-[10px] font-mono uppercase tracking-wider text-muted mb-2.5">
            tespit motorlari
          </div>
          <div className="space-y-1.5">
            {motors.map((m) => (
              <div
                key={m.n}
                className="flex items-center justify-between text-[11px]"
              >
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-signal animate-subtle-pulse" />
                  <span className="text-ink/90">{m.n}</span>
                </div>
                <span className="font-mono text-muted text-[10px]">{m.t}</span>
              </div>
            ))}
          </div>
        </div>

        <ActiveModelCard />
      </div>
    </section>
  )
}

function AlertConsoleSection({
  alertList,
  alertsLoaded,
  bySeverity,
}: {
  alertList: AlertRowData[]
  alertsLoaded: boolean
  bySeverity?: Record<string, number>
}) {
  // Dagilim tum kayitli alarmlardan (system/stats) hesaplanir; stats yoksa
  // listedeki son alarmlardan.
  const counts = Object.fromEntries(
    SEVERITIES.map((s) => [
      s,
      bySeverity
        ? (bySeverity[s] ?? 0)
        : alertList.filter((a) => a.severity === s).length,
    ]),
  ) as Record<Severity, number>
  const total = SEVERITIES.reduce((sum, s) => sum + counts[s], 0)
  return (
    <section className="grid grid-cols-1 lg:grid-cols-5 gap-px bg-line border-b border-line">
      <div className="lg:col-span-3 bg-base-2/30 p-4">
        <div className="rounded-lg border border-line bg-[#080b11] overflow-hidden">
          <div className="flex items-center justify-between px-4 h-9 border-b border-line bg-base-2/80">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-signal animate-subtle-pulse" />
              <span className="text-[10px] font-mono uppercase tracking-wider text-muted">
                live_alerts {"// ws://sentinelflow"}
              </span>
            </div>
            <span className="text-[10px] font-mono text-signal">
              son {alertList.length}
            </span>
          </div>
          <div className="px-2 py-2 h-[420px] overflow-y-auto">
            {alertList.length === 0 ? (
              <p className="px-3 py-6 text-center text-[11px] font-mono text-muted">
                {alertsLoaded ? "Henuz alarm yok" : "Alarmlar yukleniyor..."}
              </p>
            ) : (
              <AnimatePresence initial={false}>
                {alertList.map((a) => (
                  <AlertRow key={a.id} a={a} />
                ))}
              </AnimatePresence>
            )}
          </div>
        </div>
      </div>

      <div className="lg:col-span-2 bg-base-2/30 p-4 flex flex-col gap-4">
        <div className="rounded-lg border border-line bg-base/60 overflow-hidden flex-1 min-h-[260px] relative">
          <div className="flex items-center justify-between px-4 h-9 border-b border-line">
            <span className="text-[10px] font-mono uppercase tracking-wider text-muted">
              cografi aktivite {"// kaydir + zoomla"}
            </span>
            <span className="text-[10px] font-mono text-muted">temsili</span>
          </div>
          <div className="h-[calc(100%-36px)] relative">
            <GlobeScene />
          </div>
          {/* lejant */}
          <div className="absolute bottom-2 left-2 flex flex-col gap-1 px-2.5 py-2 rounded-md border border-line bg-base/80 backdrop-blur-sm">
            <div className="flex items-center gap-1.5 text-[9px] font-mono">
              <span className="w-2 h-0.5 bg-signal/40" />
              <span className="text-muted">normal transfer</span>
            </div>
            <div className="flex items-center gap-1.5 text-[9px] font-mono">
              <span className="w-2 h-0.5 bg-amber/60" />
              <span className="text-muted">supheli</span>
            </div>
            <div className="flex items-center gap-1.5 text-[9px] font-mono">
              <span className="w-2 h-0.5 bg-alarm animate-subtle-pulse" />
              <span className="text-alarm">imkansiz seyahat</span>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-line bg-base/60 p-3">
          <div className="text-[10px] font-mono uppercase tracking-wider text-muted mb-2.5">
            siddet dagilimi
          </div>
          <div className="space-y-2">
            {SEVERITIES.map((s) => {
              const sev = SEV_META[s]
              const count = counts[s]
              const pct = total ? Math.round((count / total) * 100) : 0
              return (
                <div key={s}>
                  <div className="flex items-center justify-between text-[11px] mb-1">
                    <span style={{ color: sev.color }}>{sev.label}</span>
                    <span className="font-mono text-muted">{count}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-line overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${pct}%`,
                        background: sev.color,
                        boxShadow: `0 0 8px ${sev.color}80`,
                      }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </section>
  )
}
