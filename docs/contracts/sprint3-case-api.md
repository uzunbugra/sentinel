# Sprint 3 — Vaka API Sözleşmesi (SF-304)

**Sahip:** Kişi A · **Tüketici:** Kişi B (SF-305, SF-306) · **Durum:** Sabitlendi, uygulamaya başlandı
**Taban:** `develop` @ `2527b3d`

Bu not, `docs/SPRINT3_PLAN.md` §8 "API sözleşmesi el sıkışması" gereğidir. Kişi B frontend
fixture'larını bu nota göre hazırlar; backend birleşince `sentinelflow-web/src/lib/api-schema.ts`
generator ile yenilenir ve fixture ile gerçek şema arasındaki fark kaldırılır.

## 1. Genel kurallar

- Tüm uçlar `Authorization: Bearer <access_token>` ister. Token yok/geçersiz → `401`.
- **Yetki matrisi**

  | İşlem | viewer | analyst | admin |
  |---|---|---|---|
  | `GET` liste / detay / istatistik / olaylar | ✅ | ✅ | ✅ |
  | `POST` / `PATCH` (oluşturma, bağlama, durum, atama, not) | `403` | ✅ | ✅ |

- **Tarih formatı:** API her zaman UTC döner, offset'li ISO-8601 olarak:
  `"2026-10-12T09:15:02.123456+00:00"` (`new Date(...)` doğrudan okur).
  Europe/Istanbul dönüşümü frontend'dedir.
- **Hata gövdesi:** `401/403/404` için FastAPI varsayılanı `{"detail": "<mesaj>"}`.
  `409` ve iş kuralı kaynaklı `422` için yapılandırılmış gövde:

  ```json
  { "detail": { "code": "alert_already_linked", "message": "…", "alert_id": "ALT-…", "case_id": "CASE-…" } }
  ```
  Pydantic doğrulama hataları (`422`) FastAPI'nin standart liste formatındadır.
- **Atomiklik:** Her yazma isteği tek transaction'dır. Hata olursa vaka, alarm ve olay
  kayıtlarının hiçbiri yazılmaz (rollback).

## 2. Enum değerleri

| Enum | Değerler |
|---|---|
| `CaseStatus` (açık) | `new`, `triage`, `investigating`, `escalated`, `pending_info` |
| `CaseStatus` (kapalı) | `resolved_true_positive`, `resolved_false_positive`, `closed` |
| `CasePriority` | `P1`, `P2`, `P3`, `P4` |
| `EventType` (bu sprintte yazılanlar) | `case_created`, `alert_linked_to_case`, `case_status_changed`, `case_priority_changed`, `case_assigned`, `note_added` |

**Durum geçişleri**

| Mevcut | İzin verilen yeni durum |
|---|---|
| herhangi bir açık durum | başka bir açık durum, `resolved_true_positive`, `resolved_false_positive`, `closed` |
| `resolved_true_positive` / `resolved_false_positive` | `closed`, `investigating` (yeniden açma) |
| `closed` | — (son durum) |

Aynı duruma "geçiş" değişiklik sayılmaz (olay yazılmaz). Geçersiz geçiş → `409 invalid_status_transition`.
`resolved_*` durumuna geçerken `resolution` zorunludur → yoksa `422 resolution_required`.

## 3. Uçlar

### 3.1 `POST /api/v1/cases` — alarmdan vaka oluştur (tek istek, atomik)

İstek:
```json
{
  "title": "Döngüsel transfer halkası",
  "description": "",
  "alert_ids": ["ALT-1A2B3C", "ALT-4D5E6F"],
  "priority": "P2",
  "tags": ["ring"],
  "assigned_to": null,
  "assigned_team": null
}
```
- `alert_ids` en az 1 eleman; tekrar eden kimlikler tekilleştirilir.
- Yanıt **`201 Created`** → tam `Case` nesnesi (mevcut `GET /cases/{id}` ile aynı şema;
  `alert_ids`, `alert_count`, `total_amount`, `max_severity`, `sla_due_at` … dolu gelir).
- **SLA:** `sla_due_at = created_at + süre(priority)`; süreler `P1` 4 saat, `P2` 24 saat,
  `P3` 72 saat, `P4` 168 saat. Öncelik değişirse `created_at` üzerinden yeniden hesaplanır.
  `sla_breached`, vaka açıkken `now > sla_due_at` ise okuma anında `true` döner.
- Yazılan olaylar (bu sırayla): `case_created`, ardından her alarm için `alert_linked_to_case`.
  `actor` = isteği yapan kullanıcı adı, `actor_type` = `user`.

| Durum | `code` | Ne zaman |
|---|---|---|
| `201` | — | Başarılı |
| `404` | — | Alarmlardan biri yok (`detail` eksik kimlikleri listeler) |
| `409` | `alert_already_linked` | Alarm zaten **açık** bir vakaya bağlı (`case_id` o vakayı gösterir) |
| `409` | `alert_dismissed` | Alarm yanlış pozitif olarak kapatılmış |
| `422` | — | Gövde doğrulama hatası (boş `title`, boş `alert_ids` …) |

**Çift tıklama / tekrar gönderim:** İkinci istek `409 alert_already_linked` alır ve `case_id`
ilk istekte oluşan vakayı gösterir. Frontend bu durumda o vakanın detayına yönlendirebilir;
böylece duplicate vaka oluşmaz. Kapalı (`resolved_*`/`closed`) bir vakaya bağlı alarm yeni
bir vakaya bağlanabilir.

### 3.2 `POST /api/v1/cases/{case_id}/alerts` — mevcut vakaya alarm bağla

İstek: `{ "alert_id": "ALT-1A2B3C" }` → Yanıt `200` + güncellenmiş `Case`.

| Durum | `code` | Ne zaman |
|---|---|---|
| `200` | — | Bağlandı; `alert_linked_to_case` yazıldı |
| `200` | — | Alarm zaten bu vakada (idempotent, yeni olay **yazılmaz**) |
| `404` | — | Vaka veya alarm yok |
| `409` | `alert_already_linked` | Alarm başka bir açık vakada |
| `409` | `alert_dismissed` | Alarm kapatılmış |
| `409` | `case_not_open` | Vaka kapalı durumda |

Eski `POST /api/v1/cases/{case_id}/add-alert/{alert_id}` aynı kuralları uygular, OpenAPI'de
`deprecated` işaretlidir; yeni kodda kullanılmamalıdır.

### 3.3 `PATCH /api/v1/cases/{case_id}` — durum / öncelik / atama / not

İstek (tüm alanlar isteğe bağlı, sadece gönderilenler değişir):
```json
{
  "status": "investigating",
  "priority": "P1",
  "assigned_to": "analyst1",
  "assigned_team": "AML",
  "resolution": null,
  "note": "Gönderen hesap 3 gün önce açılmış."
}
```
`tags` bu uçta desteklenmez; gönderilirse `422 unsupported_field`.

Yanıt `200` + güncel `Case`. Değişen her alan için bir olay yazılır, sabit sırayla:
`case_status_changed` → `case_priority_changed` → `case_assigned` → `note_added`.
Değişmeyen alan için olay yazılmaz. Hatalar: `404`, `409 invalid_status_transition`,
`422 resolution_required`, `422 unsupported_field`, `422` gövde doğrulama.

`POST /api/v1/cases/{case_id}/assign?assigned_to=…` mevcut haliyle kalır (aynı olayı yazar).

### 3.4 `GET /api/v1/cases/{case_id}/events` — audit timeline

Sorgu: `page` (≥1, varsayılan 1), `page_size` (1–100, varsayılan 50), `event_type` (opsiyonel,
yukarıdaki `EventType` değerlerinden biri; geçersiz değer → `422`).

Yanıt `200`:
```json
{
  "total": 3,
  "page": 1,
  "page_size": 50,
  "events": [
    {
      "event_id": "EVT-…",
      "case_id": "CASE-…",
      "event_type": "note_added",
      "actor": "analyst1",
      "actor_type": "user",
      "description": "Gönderen hesap 3 gün önce açılmış.",
      "previous_value": null,
      "new_value": null,
      "alert_id": null,
      "created_at": "2026-10-12T09:15:02.123456+00:00"
    }
  ]
}
```
- **Sıralama:** en yeni önce (`created_at` azalan). Aynı istekte yazılan olaylar yazılış
  sırasını korur (ör. `case_created` her zaman kendi `alert_linked_to_case` olaylarından
  önce gelir, listede onlardan sonra görünür).
- Vaka yoksa `404` (eskiden boş liste dönüyordu).
- `ip_address` / `user_agent` yanıtta yer almaz.

## 4. Bilinçli olarak kapsam dışı

- Atamayı kaldırma (`assigned_to: null` "değişiklik yok" anlamına gelir).
- Etiket değişikliği (`PATCH` ile `tags`, `tag_added` / `tag_removed` olayları).
- Vakadan alarm çıkarma.
