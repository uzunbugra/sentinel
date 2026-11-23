// Alarm tiplerinin arayuzde gosterilen Turkce adlari. Alarm listesi ve vaka
// detayi ayni adlari kullanir; backend'in sakladigi Ingilizce `title`
// ("Ml Model Detected" gibi) gosterilmez.
export const fraudTypeLabels: Record<string, string> = {
  circular_ring: "Döngüsel Transfer",
  impossible_travel: "İmkansız Seyahat",
  blacklist_keyword: "Kara Liste",
  mule_account: "Mule Hesap",
  structuring: "Yapılandırma",
  velocity_anomaly: "Hız Anomalisi",
  ml_model: "ML Model",
  ml_ensemble: "ML Tespit",
  compliance_violation: "Uyum İhlali",
}

export function fraudTypeLabel(type: string | null | undefined): string {
  if (!type) return "Bilinmeyen tip"
  return fraudTypeLabels[type] ?? type
}
