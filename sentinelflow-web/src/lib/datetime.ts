const dateFormatter = new Intl.DateTimeFormat("tr-TR", {
  timeZone: "Europe/Istanbul",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
})

const timeFormatter = new Intl.DateTimeFormat("tr-TR", {
  timeZone: "Europe/Istanbul",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
})

const clockFormatter = new Intl.DateTimeFormat("tr-TR", {
  timeZone: "Europe/Istanbul",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
})

function parseDate(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDate(iso: string | null | undefined): string {
  const date = parseDate(iso)
  return date ? dateFormatter.format(date) : "—"
}

export function formatDateTime(iso: string | null | undefined): string {
  const date = parseDate(iso)
  return date ? `${dateFormatter.format(date)} ${timeFormatter.format(date)}` : "—"
}

export function formatTime(iso: string | null | undefined): string {
  const date = parseDate(iso)
  return date ? clockFormatter.format(date) : "—"
}
