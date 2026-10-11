import { AlertTriangle, CheckCircle, Clock, XCircle, type LucideIcon } from "lucide-react"
import type { CaseEventType, CasePriority, CaseStatus } from "@/lib/cases"

export const statusConfig: Record<CaseStatus, {
  label: string
  color: string
  icon: LucideIcon
}> = {
  new: {
    label: "Yeni", color: "bg-blue-500/10 text-blue-400 border-blue-500/20", icon: AlertTriangle,
  },
  triage: {
    label: "Triage", color: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20", icon: AlertTriangle,
  },
  investigating: {
    label: "İnceleniyor", color: "bg-orange-500/10 text-orange-400 border-orange-500/20", icon: Clock,
  },
  escalated: {
    label: "Üst Seviye", color: "bg-red-500/10 text-red-400 border-red-500/20", icon: AlertTriangle,
  },
  pending_info: {
    label: "Bilgi Bekleniyor", color: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20", icon: Clock,
  },
  resolved_true_positive: {
    label: "Doğru Tespit", color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20", icon: CheckCircle,
  },
  resolved_false_positive: {
    label: "Yanlış Alarm", color: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20", icon: XCircle,
  },
  closed: {
    label: "Kapatıldı", color: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20", icon: CheckCircle,
  },
}

export const priorityColors: Record<CasePriority, string> = {
  P1: "bg-red-500/20 text-red-400",
  P2: "bg-orange-500/20 text-orange-400",
  P3: "bg-yellow-500/20 text-yellow-400",
  P4: "bg-zinc-500/20 text-zinc-400",
}

export const eventLabels: Record<CaseEventType, string> = {
  case_created: "Vaka oluşturuldu",
  alert_linked_to_case: "Alarm bağlandı",
  alert_unlinked_from_case: "Alarm başka vakaya taşındı",
  case_status_changed: "Durum değişti",
  case_priority_changed: "Öncelik değişti",
  case_resolution_updated: "Çözüm güncellendi",
  case_assigned: "Vaka atandı",
  note_added: "Not eklendi",
}
