# SentinelFlow API Referansı

> Bu belge `v2.2.0` rota tablosundan üretilmiştir. Değişmez kaynak(lar):
> interaktif Swagger (`http://localhost:8000/docs`) ve üretilen sözleşmedir
> (`sentinelflow-web/src/lib/api-schema.ts`). Rota değiştirdikten sonra
> `python scripts/export_openapi.py` çalıştırıp sözleşmeyi commit edin;
> CI eskimiş şemayı reddeder.

## Kimlik Doğrulama

İki yöntem vardır:

1. **JWT Bearer** — `POST /api/v1/auth/login` ile alınan `access_token` her
   istekte `Authorization: Bearer <token>` başlığında gönderilir.
2. **X-API-Key** — yalnızca `POST /api/v1/transactions` servis-to-servis
   besleme (üretici/ingestor) içindir. Sunucu tarafında `SENTINELFLOW_API_KEY`
   tanımlıysa bu değer `X-API-Key` başlığından beklenir.

### Roller

| Rol | Yetki |
| --- | --- |
| `viewer` | Salt okunur: listeler, detay, istatistik |
| `analyst` | Soruşturma: alert dismiss, case yönetimi, KYC tarama, risk skorlama |
| `admin` | Tam yönetim (kullanıcı yönetimi gelecek sürümlerde) |

Aşağıdaki tabloda **Auth** sütunu gereken asgari rolü gösterir.

## Uç Noktalar

### System & Monitoring — herkese açık

| Method | Path | Açıklama | Auth |
| --- | --- | --- | --- |
| GET | `/` | Kök karşılama | — |
| GET | `/api/v1/system/health` | Sağlık kontrolü (`api`, `database`, `ml_model`); biri sağlıksızsa `degraded` | — |
| GET | `/api/v1/system/stats` | Sistem istatistikleri | — |
| GET | `/metrics` | Prometheus metrikleri | — |

### Authentication

| Method | Path | Açıklama | Auth |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/login` | Kullanıcı girişi, JWT verir | — |
| POST | `/api/v1/auth/register` | Yeni kullanıcı kaydı (bootstrap amaçlı; üretimde kapatılmalıdır) | — |
| POST | `/api/v1/auth/refresh` | Refresh token ile yeni erişim token'ı | — (refresh token gövdede) |
| GET | `/api/v1/auth/me` | Oturumdaki kullanıcı | JWT |
| POST | `/api/v1/auth/logout` | Oturumu kapatır (refresh token iptal) | JWT |
| POST | `/api/v1/auth/change-password` | Parola değiştirme | JWT |

### Transactions

| Method | Path | Açıklama | Auth |
| --- | --- | --- | --- |
| POST | `/api/v1/transactions` | Dolandırıcılık analizi için işlem gönderimi (gerçek zamanlı skorlama) | JWT **veya** `X-API-Key` |

### Alerts (`viewer`+)

| Method | Path | Açıklama | Auth |
| --- | --- | --- | --- |
| GET | `/api/v1/alerts` | Alert listesi (filtre/sayfalama) | viewer |
| GET | `/api/v1/alerts/stats` | Alert istatistikleri | viewer |
| GET | `/api/v1/alerts/{alert_id}` | Alert detayı (kanıt dahil; `ml_model` alarmında model sürümü ve ilk 5 katkı) | viewer |
| POST | `/api/v1/alerts/{alert_id}/dismiss` | Yanlış pozitif olarak kapat | analyst |
| POST | `/api/v1/alerts/{alert_id}/link-case/{case_id}` | **Deprecated** — `POST /api/v1/cases/{case_id}/alerts` ile aynı kurallar | analyst |

### Cases

| Method | Path | Açıklama | Auth |
| --- | --- | --- | --- |
| GET | `/api/v1/cases` | Case listesi | viewer |
| GET | `/api/v1/cases/stats` | Case istatistikleri | viewer |
| GET | `/api/v1/cases/{case_id}` | Case detayı | viewer |
| GET | `/api/v1/cases/{case_id}/events` | Audit timeline, en yeni önce (`page`, `page_size`, `event_type`) | viewer |
| POST | `/api/v1/cases` | Alarmlardan vaka oluştur — atomik, `201` | analyst |
| PATCH | `/api/v1/cases/{case_id}` | Durum / öncelik / atama / not / çözüm | analyst |
| POST | `/api/v1/cases/{case_id}/alerts` | Mevcut vakaya alarm bağla (`{"alert_id"}`, idempotent) | analyst |
| POST | `/api/v1/cases/{case_id}/assign` | Vakayı ata | analyst |
| POST | `/api/v1/cases/{case_id}/add-alert/{alert_id}` | **Deprecated** — `POST /cases/{case_id}/alerts` ile aynı | analyst |

Vaka iş akışının kuralları (durum geçişleri, SLA, `409`/`422` hata kodları, olay
türleri ve sıralaması) [`docs/contracts/sprint3-case-api.md`](contracts/sprint3-case-api.md)
içinde tanımlıdır. Tüm yazma işlemleri tek transaction'dır; hata olursa hiçbir
kayıt yazılmaz.

### Graph (Neo4j sorguları)

| Method | Path | Açıklama | Auth |
| --- | --- | --- | --- |
| GET | `/api/v1/graph/data` | Görselleştirme için işlem ağı grafiği | viewer |
| GET | `/api/v1/graph/rings` | Kara para halkaları (döngüsel akışlar) | viewer |
| GET | `/api/v1/graph/account/{iban}` | Hesap bazlı işlem komşuluğu | viewer |

### Chat (asistan)

| Method | Path | Açıklama | Auth |
| --- | --- | --- | --- |
| POST | `/api/v1/chat` | Sohbet yanıtı (fraud açıklaması vb.) | viewer |
| GET | `/api/v1/chat/suggestions` | Öneri sorular | viewer |
| GET | `/api/v1/chat/knowledge/{fraud_type}` | Fraud tipine göre bilgi kartı | viewer |

### Machine Learning

Sözleşme: `docs/contracts/sprint4-ml-api.md` §4, karar: ADR 0003. Model offline
eğitilir; API yalnız `SENTINELFLOW_MODEL_DIR` (varsayılan `models/fraud/current`)
altındaki artifact'i açılışta yükler. Model yoksa API çalışır, `ml_model` `degraded` olur.

| Method | Path | Açıklama | Auth |
| --- | --- | --- | --- |
| GET | `/api/v1/ml/models` | Aktif model ve metrikleri; her zaman `200`, `status` = `loaded` \| `not_loaded` \| `invalid` | viewer |
| GET | `/api/v1/ml/features` | Servis edilen özellik seti (`fs-1`, model girdi sırasıyla) | viewer |

### Risk Scoring

| Method | Path | Açıklama | Auth |
| --- | --- | --- | --- |
| POST | `/api/v1/risk/score` | Tek işlem skoru + log-odds katkıları; hesap geçmişini okur, yazmaz. Model yoksa `503 model_not_loaded` | analyst |
| GET | `/api/v1/risk/stats` | Skorlama sayaçları, ortalama gecikme ve hesap geçmişi sayaçları (`history`) | viewer |

`POST /api/v1/transactions` geçmişi kaydeden tek yoldur: `fraud_score` ve
`model_version` model yoksa `null` döner; skor eşiği geçerse `ml_model` alarmı
evidence içinde model sürümü, eşik ve ilk 5 katkıyla oluşturulur. Aynı işlem tekrar
gelirse mevcut alarm döner, yeniden yayınlanmaz. Geçmiş süreç içindedir: yeniden
başlatmadan sonra `risk/stats` → `history.recorded` 0'dır.

### KYC & Compliance

| Method | Path | Açıklama | Auth |
| --- | --- | --- | --- |
| POST | `/api/v1/kyc/screen` | Müşteri PEP & yaptırım listesi taraması | analyst |

### WebSocket

| Path | Açıklama |
| --- | --- |
| `ws://<host>:8000/ws/alerts` | Canlı alert yayını |

## Durum Kodları

| Kod | Anlam |
| --- | --- |
| `200/201` | Başarı |
| `401` | Kimlik yok/geçersiz (veya `X-API-Key` eksik/hatalı) |
| `403` | Rol yetkisiz (ör. viewer POST denemesi) |
| `404` | Kayıt yok |
| `422` | Gövde doğrulama hatası (Pydantic) |

## Örnek: Giriş ve Korumalı Çağrı

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "<user>", "password": "<password>"}' | jq -r .access_token)

curl -s http://localhost:8000/api/v1/alerts \
  -H "Authorization: Bearer $TOKEN"
```

## Örnek: Servis-to-Servis Besleme (X-API-Key)

```bash
curl -X POST http://localhost:8000/api/v1/transactions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SENTINELFLOW_API_KEY" \
  -d '{"sender_iban": "TR...", "receiver_iban": "TR...", "amount": 1500, "description": "kira"}'
```