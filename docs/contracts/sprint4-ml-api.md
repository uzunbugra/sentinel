# Sprint 4 — ML Veri, Özellik, Artifact ve API Sözleşmesi (ML-01)

**Sahip:** Kişi A (@uzunbugra) · **Onaylayan:** Alper (@alper-tekin) — §1–§3 veri/özellik/artifact
**Tüketiciler:** ML-02…ML-05 (Alper), ML-06/07 (A), SF-405 (Alper), SF-404 (A)
**Durum:** Sabitlendi (#26, Alper onayıyla) — değişiklikler CONTRACT-REQUEST ile · **Taban:** `develop` @ `d68b4e0`
**Karar kaydı:** [ADR 0003](../adr/0003-ml-pipeline-v2.md)

Bu not `docs/SPRINT4_PLAN.md` §3 gereğidir ve ML-06'nın sonuna bırakılmaz. Değişiklik
gerekiyorsa sahibi örnek payload ve etkisiyle `CONTRACT-REQUEST` issue'su açar; onaylanan
değişiklik bu dosyada birlikte güncellenir ve ilgili sürüm alanı artırılır.

## 1. Kanonik işlem kaydı (veri)

Eğitim veri seti (ML-02 parquet) ve servis tarafı tek bir kanonik kayda dönüşür. Özellik
modülü (ML-03) yalnız bu alanları okur.

| Alan | Tip | Zorunlu | Eğitim kaynağı (SAML-D) | Servis kaynağı (`TransactionCreate`) |
|---|---|---|---|---|
| `transaction_id` | string | ✅ | ML-02'de deterministik üretilir (satır sırası + `dataset_id`) | `transaction_id` (`with_defaults()` sonrası) |
| `timestamp` | datetime, **UTC**, tz-aware | ✅ | `Date` + `Time` | `timestamp` (yoksa alım anı, UTC) |
| `sender_account` | string (opak anahtar) | ✅ | `Sender_account` (değiştirilmeden, string) | `sender_iban` |
| `receiver_account` | string (opak anahtar) | ✅ | `Receiver_account` | `receiver_iban` |
| `amount` | float64, > 0, TRY | ✅ | `Amount` × 50 (GBP→TRY etiketli dönüşüm) | `amount` |
| `payment_currency` | string, ISO-4217 (kategori) | ✅ | `Payment_currency` (UK pounds→`TRY`, Turkish lira→`GBP`) | `currency` |
| `received_currency` | string, ISO-4217 (kategori) | — | `Received_currency` (aynı eşleme) | `received_currency` (yeni, opsiyonel; yoksa `payment_currency`) |
| `sender_country` | string, ISO-3166 alpha-2 | — | `Sender_bank_location` (UK→`TR`, Turkey→`GB`) | `sender_country` (yeni, opsiyonel; yoksa `TR`) |
| `receiver_country` | string, ISO-3166 alpha-2 | — | `Receiver_bank_location` (UK→`TR`, Turkey→`GB`) | `receiver_country` (yeni, opsiyonel; yoksa `TR`) |
| `payment_type` | string (kategori) | — | `Payment_type` | `payment_type` (yeni, opsiyonel; yoksa `unknown`) |
| `is_laundering` | int {0,1} | yalnız eğitim | `Is_laundering` | — |
| `laundering_type` | string | yalnız rapor | `Laundering_type` | — |
| `sender_iban`, `receiver_iban`, `sender_name`, `receiver_name` | string | yalnız görüntüleme | Hesap kimliğinden deterministik (ML-02) | — |
| `split` | `train` / `val` / `test` | yalnız eğitim | Kronolojik bölme (ML-02) | — |

Kurallar:

- Ülke alanları **ülke** kodudur; şehir alanlarıyla (`sender_city`) karıştırılmaz.
  UK ↔ Turkey ve UK pounds ↔ Turkish lira **yer değiştirir** (UK→`TR`, Turkey→`GB`;
  UK pounds→`TRY`, Turkish lira→`GBP`); eşleme bire birdir. Bu ve ×50 tutar ölçeği gerçek
  kur/coğrafya değildir; veri kartında belirtilir (ML-02).
- Görüntüleme alanları (`*_iban`, `*_name`) ve `split` hiçbir özelliğe girmez; geçmiş
  anahtarı yalnız `*_account`'tır.
- `is_laundering` ve `laundering_type` hiçbir özelliğe girmez; geçmiş state'e de yazılmaz.
- Kimlik alanları yalnız geçmiş anahtarıdır; doğrudan özellik değildir.
- Eksik opsiyonel alan → yukarıdaki varsayılan; bilinmeyen kategori → `unknown` kodu.
- Servise eklenecek 4 opsiyonel alan (`received_currency`, `sender_country`,
  `receiver_country`, `payment_type`) additive'dir; mevcut istemcileri bozmaz. ML-06'da
  `TransactionCreate`'e eklenir ve OpenAPI generator ile yansıtılır.

Örnek kanonik işlem (JSON gösterimi):

```json
{
  "transaction_id": "SAMLD-000000123",
  "timestamp": "2022-10-07T10:35:19+00:00",
  "sender_account": "8724731955",
  "receiver_account": "2769355426",
  "amount": 75029.50,
  "payment_currency": "TRY",
  "received_currency": "TRY",
  "sender_country": "TR",
  "receiver_country": "TR",
  "payment_type": "cash_deposit"
}
```

Kategori kelime dağarcıkları (ödeme tipi, para birimi, ülke) ve kodları ML-03'te
özellik modülünde sabit sıralı listeler olarak tanımlanır; servis kendi listesini tutmaz.
Kod `0` her zaman `unknown`; listeler yalnız yeni bir `feature_set_version` ile sona
eklenerek büyür, sıralama değişmez. Listeler ML-02'nin ürettiği değerleri
kapsar: ödeme tipi `ach, cash_deposit, cash_withdrawal, cheque, credit_card, cross_border,
debit_card`; para `AED, ALL, CHF, EUR, GBP, INR, JPY, MAD, MXN, NGN, PKR, TRY, USD`; ülke
`AE, AL, AT, CH, DE, ES, FR, GB, IN, IT, JP, MA, MX, NG, NL, PK, TR, US`. Kimlikler string, `timestamp` tz-aware olarak teslim edilir;
tz'siz zaman damgası `FeatureInputError` ile reddedilir.

## 2. Özellik seti

`feature_set_version = "fs-1"` (ML-03 ilk teslimi). Liste **sıralıdır**; model girdisi bu
sıradadır ve artifact'taki `feature_names` ile birebir eşleşmek zorundadır.

| # | Ad | dtype | Varsayılan / cold-start | Tanım |
|---|---|---|---|---|
| 1 | `log_amount` | float32 | — | `ln(1 + amount)` |
| 2 | `hour` | int8 | — | UTC saat (0–23) |
| 3 | `day_of_week` | int8 | — | 0=Pazartesi |
| 4 | `payment_type_code` | int8 (kategorik) | `unknown` kodu | Ödeme tipi kodu |
| 5 | `currency_mismatch` | int8 {0,1} | 0 | `payment_currency != received_currency` |
| 6 | `cross_border` | int8 {0,1} | 0 | `sender_country != receiver_country` |
| 7 | `sender_country_code` | int8 (kategorik) | `unknown` kodu | |
| 8 | `receiver_country_code` | int8 (kategorik) | `unknown` kodu | |
| 9 | `sender_tx_count_24h` | int32 | 0 | Gönderenin önceki 24 saatteki giden işlem sayısı |
| 10 | `sender_amount_sum_24h` | float32 | 0.0 | Aynı penceredeki tutar toplamı |
| 11 | `sender_unique_receivers_7d` | int32 | 0 | Gönderenin önceki 7 günde farklı alıcı sayısı |
| 12 | `receiver_tx_count_24h` | int32 | 0 | Alıcının önceki 24 saatteki gelen işlem sayısı |
| 13 | `receiver_unique_senders_7d` | int32 | 0 | Alıcının önceki 7 günde farklı gönderen sayısı |
| 14 | `pair_tx_count_7d` | int32 | 0 | Aynı gönderen→alıcı çiftinin önceki 7 gün işlem sayısı |
| 15 | `sender_seconds_since_prev` | float32 | `-1.0` (önceki işlem yok) | Gönderenin bir önceki işleminden bu yana saniye |

Geçmiş (state) kuralları — ADR 0003 §4:

- "Önceki" = `(timestamp, transaction_id)` sıralamasında mevcut işlemden **kesin önce**
  gelen olaylar; mevcut işlem kendi özelliğine girmez.
- Pencere: alt sınır **dahil** (`timestamp ≥ t − W`), üst sınır `(timestamp,
  transaction_id)` sırasında kesin önce. Böylece aynı zaman damgalı olaylar
  `transaction_id` sırasıyla birbirini görür. (`[t − W, t)` gösterimi bu anlamdadır.)
- Duplicate: aynı `(timestamp, transaction_id)` ile tekrar gelen işlem orijinalini görmez,
  bu yüzden orijinalle aynı vektörü alır; geçmişe ikinci kez yazılmaz. Kimlikler
  karşılaştırmada string olarak ele alınır. Kimlik kümesi sınırlıdır: kimlik, zamanı
  kaydedilen en son işlemden en çok 7 gün (`MAX_WINDOW_NS`) eskiyse tutulur. Daha eski
  bir işlem gönderen/alıcı hesabın saklanan olaylarıyla `(timestamp, transaction_id)`
  üzerinden karşılaştırılır; olay artık saklanmıyorsa hiçbir pencereye giremediği için
  tekrar yazılması özellikleri değiştirmez. Aynı kimliğin 7 günden sonra **farklı**
  hesaplarla yeniden kullanılması yeni işlem sayılır.
- `sender_seconds_since_prev` yalnız gönderenin **giden** işlemlerine bakar ve 7 günlük
  pencereyle sınırlı değildir.
- Arayüz (ML-03, Alper):

  ```python
  # sentinelflow.ml.features (ad ML-03'te kesinleşir)
  FEATURE_SET_VERSION: str
  FEATURE_NAMES: tuple[str, ...]
  def build_features_batch(df: pd.DataFrame) -> pd.DataFrame        # eğitim
  class AccountHistory:
      def features_for(self, tx: Mapping[str, Any]) -> np.ndarray    # okur, yazmaz
      def record(self, tx: Mapping[str, Any]) -> bool                # yazar; duplicate ise False
  ```

  Servis akışı: `vec = history.features_for(tx)` → skor → (yalnız ingestion yolunda)
  `history.record(tx)`. `risk/score` `record` çağırmaz.
- **Parity garantisi:** sıralı bir işlem dizisi için `build_features_batch` çıktısının
  her satırı, boş bir `AccountHistory` ile aynı diziyi sırayla `features_for` + `record`
  ederek elde edilen vektöre eşittir (float32 toleransı `1e-6`).
- **Gelecek sızıntısı testi:** diziye sonradan eklenen (daha geç zamanlı) olaylar önceki
  satırların vektörünü değiştirmez.

## 3. Artifact

Dizin: `models/fraud/<model_version>/`

```
model.txt        # LightGBM metin formatı (pickle yok)
metadata.json
model_card.md
SHA256SUMS       # model.txt ve metadata.json için
```

`model_version` biçimi: `fraud-lgbm-<YYYYMMDD>-<git_sha7>` (ör. `fraud-lgbm-20261105-a1b2c3d`).

`metadata.json` örneği:

```json
{
  "schema_version": 1,
  "model_version": "fraud-lgbm-20261105-a1b2c3d",
  "model_family": "lightgbm",
  "objective": "binary",
  "feature_set_version": "fs-1",
  "feature_names": ["log_amount", "hour", "day_of_week", "payment_type_code",
                    "currency_mismatch", "cross_border", "sender_country_code",
                    "receiver_country_code", "sender_tx_count_24h", "sender_amount_sum_24h",
                    "sender_unique_receivers_7d", "receiver_tx_count_24h",
                    "receiver_unique_senders_7d", "pair_tx_count_7d",
                    "sender_seconds_since_prev"],
  "categorical_features": ["payment_type_code", "sender_country_code", "receiver_country_code"],
  "threshold": 0.37,
  "calibration": null,
  "dataset_id": "samld-3f9a…",
  "metrics": {
    "split": "test",
    "pr_auc": 0.0, "roc_auc": 0.0,
    "precision": 0.0, "recall": 0.0, "f1": 0.0,
    "support_positive": 0, "support_total": 0,
    "baseline_pr_auc": 0.0
  },
  "trained_at": "2026-11-05T12:00:00+00:00",
  "git_sha": "a1b2c3d4e5f6…",
  "library_versions": {"python": "3.11.9", "lightgbm": "4.x.y", "numpy": "x.y.z"},
  "model_sha256": "…"
}
```

(Sayılar örnek yer tutucudur; gerçek değerler ML-04/05 raporundan gelir.)

Yükleme doğrulaması (ML-06, servis yükleyicisi) — herhangi biri tutmazsa model **yüklenmez**:

1. Dizin, `model.txt`, `metadata.json` mevcut; `SHA256SUMS` ve `model_sha256` eşleşiyor.
2. `schema_version` destekleniyor; zorunlu alanların hepsi var.
3. `feature_set_version` servisin import ettiği özellik modülününkiyle aynı.
4. `feature_names` servisteki `FEATURE_NAMES` ile aynı içerik ve **aynı sırada**;
   modelin kendi feature adları da aynı.
5. `0 < threshold < 1`.

Hata sebebi health `ml_model.message` alanına ve loga yazılır (§4.3).

## 4. API

Tüm uçlar `Authorization: Bearer <token>` ister (ingestion ayrıca `X-API-Key`). Tarihler
UTC, offset'li ISO-8601. Kesin şemalar ML-06'da OpenAPI generator ile
`sentinelflow-web/src/lib/api-schema.ts`'e yansır; bu bölüm ile fark olursa bu not güncellenir.

### 4.1 `GET /api/v1/ml/models` — aktif model (viewer+)

Model yüklü:

```json
{
  "status": "loaded",
  "model": {
    "model_version": "fraud-lgbm-20261105-a1b2c3d",
    "model_family": "lightgbm",
    "feature_set_version": "fs-1",
    "feature_names": ["log_amount", "…"],
    "threshold": 0.37,
    "dataset_id": "samld-3f9a…",
    "trained_at": "2026-11-05T12:00:00+00:00",
    "loaded_at": "2026-11-06T08:00:00+00:00",
    "metrics": {"split": "test", "pr_auc": 0.52, "roc_auc": 0.97, "precision": 0.21,
                "recall": 0.58, "f1": 0.31, "support_positive": 1234, "support_total": 1425000,
                "baseline_pr_auc": 0.30},
    "model_sha256": "…"
  },
  "error": null
}
```

Model yok / geçersiz (HTTP **200**, uç her zaman cevap verir):

```json
{ "status": "not_loaded", "model": null, "error": "model directory not found: models/fraud/current" }
```

`status` ∈ `loaded` | `not_loaded` | `invalid`. Metrikte değer yoksa `null` döner, `0` değil
(UI sıfır ile eksik değeri ayırır).

### 4.2 `POST /api/v1/risk/score` — tekil skor (analyst+)

İstek gövdesi `TransactionCreate` ile aynıdır (§1 servis kaynağı sütunu). Geçmişi okur,
yazmaz.

`200`:

```json
{
  "transaction_id": "TXN-A1B2C3D4E5F6",
  "model_version": "fraud-lgbm-20261105-a1b2c3d",
  "feature_set_version": "fs-1",
  "score": 0.8123,
  "threshold": 0.37,
  "is_fraud": true,
  "contribution_unit": "log_odds",
  "base_value": -6.91,
  "top_features": [
    {"feature": "sender_unique_receivers_7d", "value": 14.0, "contribution": 2.31},
    {"feature": "cross_border", "value": 1.0, "contribution": 1.12},
    {"feature": "log_amount", "value": 11.23, "contribution": 0.87},
    {"feature": "hour", "value": 3.0, "contribution": 0.41},
    {"feature": "sender_seconds_since_prev", "value": 42.0, "contribution": -0.18}
  ],
  "history_cold_start": false,
  "latency_ms": 2.4
}
```

Anlamlar:

- `score` ∈ `[0, 1]`: modelin olasılık çıktısı (kalibrasyon varsa kalibre). `is_fraud = score >= threshold`.
- `contribution`: işleme özel katkı, **log-odds** biriminde (LightGBM `pred_contrib`).
  Pozitif → riski artırır. `base_value + Σ(tüm özellik katkıları) = logit(ham skor)`.
- `top_features`: `|contribution|` büyükten küçüğe ilk **5** özellik; eşitlikte özellik adı
  alfabetik. Genel feature importance değildir.
- `history_cold_start`: gönderen ve alıcı hesap state'te **hiçbir yönde** (giden ya da
  gelen) kaydedilmemişse `true`.

`503` (model yok/geçersiz):

```json
{ "detail": { "code": "model_not_loaded", "message": "No valid fraud model is loaded", "status": "not_loaded" } }
```

`POST /api/v1/risk/batch` aynı öğe biçimini liste olarak döner; ML-06'da korunur ya da
kaldırılır (karar PR'da, OpenAPI ile birlikte). `GET /api/v1/risk/stats` gecikme/sayaç
döner, sözleşme dışıdır.

### 4.3 `GET /api/v1/system/health`

`components` içine `ml_model` eklenir; eski `ml_ensemble` anahtarı kaldırılır.

```json
{
  "status": "degraded",
  "components": {
    "api": {"name": "api", "status": "healthy"},
    "database": {"name": "database", "status": "healthy"},
    "ml_model": {
      "name": "ml_model",
      "status": "degraded",
      "message": "checksum mismatch for model.txt"
    }
  }
}
```

- `ml_model.status`: `healthy` (yüklü) | `degraded` (yok/geçersiz). Yüklüyken `message`
  `model_version` değerini taşır (`"fraud-lgbm-20261105-a1b2c3d"`).
- Genel `status`: veritabanı **veya** `ml_model` sağlıklı değilse `degraded`.

### 4.4 `POST /api/v1/transactions` — ingestion

`TransactionResponse` değişiklikleri (additive + bir nullable):

| Alan | Değişiklik |
|---|---|
| `fraud_score` | `float \| null` — model yoksa `null` (artık `0.0` uydurulmaz) |
| `model_version` | yeni, `string \| null` |
| `is_fraud` | model yoksa `false` (kural alarmları `alerts` içinde ayrıca gelir) |

Model `score >= threshold` dediğinde ML alarmı oluşturulur (§4.5). Severity:
`score >= 0.85` → `critical`, aksi `high` (mevcut davranış korunur).

### 4.5 ML alarmının `evidence` kaydı

Alarm `fraud_type = "ml_model"` (yeni enum değeri). Evidence listesinde bir öğe:

```json
{
  "detector_type": "ml_model",
  "detector_version": "fraud-lgbm-20261105-a1b2c3d",
  "confidence": 0.8123,
  "contribution": 1.0,
  "summary": "Model skoru 0.81 ≥ eşik 0.37",
  "details": {
    "model_version": "fraud-lgbm-20261105-a1b2c3d",
    "feature_set_version": "fs-1",
    "score": 0.8123,
    "threshold": 0.37,
    "contribution_unit": "log_odds",
    "base_value": -6.91,
    "top_features": [
      {"feature": "sender_unique_receivers_7d", "value": 14.0, "contribution": 2.31}
    ],
    "history_cold_start": false
  },
  "related_transactions": ["TXN-A1B2C3D4E5F6"]
}
```

- Değerler alarm **üretildiği andaki** modelden yazılır; sonradan aktif model değişse de
  eski alarm yeniden yazılmaz. UI açıklamayı evidence'tan okur, `/ml/models`'tan değil.
- Eski alarmlar (`fraud_type = "ml_ensemble"`) bu `details` alanlarını içermez; UI
  "metadata yok" durumunu gösterir (SF-405). `ml_model` etiketi frontend'e SF-405'te eklenir.

### 4.6 Kaldırılan uçlar

- `POST /api/v1/ml/train` ve `GET /api/v1/ml/train/status` kaldırılır; eğitim offline CLI
  ve CI ile yapılır (ADR 0003 §10). İstemci çağırırsa `404`.
- `/api/v1/ml/features` ve `/api/v1/ml/predict` (varsa) ML-06'da yeni özellik setine
  bağlanır veya kaldırılır; karar PR'da OpenAPI ile birlikte bildirilir.

## 5. Ortak fixture (tek teslim örneği)

`tests/fixtures/ml/` altında, ML-03 ile birlikte Alper teslim eder:

- `transactions.jsonl` — §1 biçiminde, aynı zamanlı ve aynı hesaplı olayları, cold-start'ı,
  duplicate `transaction_id`'yi, 24 sa / 7 gün sınırlarını ve bilinmeyen kategoriyi içeren
  sıralı dizi (ML-03 teslimi: 23 işlem).
- `expected_features.jsonl` — her işlem için `{transaction_id, features: [15 değer]}`.
- `metadata.example.json` — §3 biçiminde, gerçek modele bağlı olmayan örnek.

Kullanım: A loader/API testlerini ve `risk/score` fixture'ını; Alper SF-405 UI fixture'ını
bu dosyalardan üretir. Fixture değişirse iki tarafın testleri aynı PR'da güncellenir.

## 6. Açık noktalar (onayda kapatılacak)

- [x] Alper: §1 kategori listeleri ve UK ↔ Turkey / GBP ↔ TRY yer değiştirmesi (ML-02, #32);
      ML-03 listelerine `GB` ve `GBP` eklenir (#31).
- [ ] Alper: §1 SAML-D sütun eşlemesinin veri kartında doğrulanması (ML-02).
- [x] Alper: §2 geçmiş özellikleri ML-03'te tam kapsamla uygulandı (#31); pencere,
      duplicate ve cold-start yorumları §2'ye işlendi.
- [ ] Ortak: ADR 0003 §7 sayısal hedefler — test seti açılmadan onay.
- [ ] A (ML-06): `risk/batch`, `ml/features`, `ml/predict` uçlarının akıbeti.
