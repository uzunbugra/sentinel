# ADR 0003: ML pipeline v2 — tek veri sözleşmesi, tek model, tek servis

- Durum: kabul edildi (accepted) — #26, Alper onayıyla, 2026-10-29
- Tarih: 2026-10-29
- Sahip: Kişi A (@uzunbugra) · Ortak karar: Alper (@alper-tekin)
- İlgili: issue #16 (ML-01), `docs/SPRINT4_PLAN.md` §3, §10,
  sözleşme [`docs/contracts/sprint4-ml-api.md`](../contracts/sprint4-ml-api.md)

## Bağlam

`develop` @ `d68b4e0` itibarıyla:

- `api/state.py`, `processor/detector/service.py` ve `api/risk_scoring/engine.py` üç
  ayrı ve **eğitilmemiş** ensemble kuruyor (IsolationForest + XGBoost + AutoEncoder,
  risk motorunda ek olarak LightGBM/CatBoost). Skor fiilen canlı trafikte kendini
  eğiten IsolationForest'tan geliyor; CI'da eğitilen XGBoost hiçbir servis tarafından
  yüklenmiyor.
- Servis `ml/feature_engine.py` (21 özellik), eğitim `ml/dataset_schema.py` (11 özellik)
  kullanıyor; iki tanım birbirini tutmuyor. Eğitim verisi `CompetitionDatasetGenerator`
  ile rastgele üretiliyor.
- `pyproject.toml` çekirdek bağımlılıklarında `torch`, `torch-geometric`, `catboost`,
  `shap` var; ölçülmemiş performans iddiaları README'de duruyor.

Bu ADR, ML-02…ML-09'un dayandığı kararları test seti açılmadan sabitler.

## Karar

### 1. Kapsam

- Tek bir denetimli ikili sınıflandırıcı (aklama / değil) eğitilir ve **aynı artifact**
  API ingestion, detector servisi ve risk skoru uç noktası tarafından kullanılır.
- Kapsam dışı (bu sprintte yeniden etkinleştirilmez): GNN, sequence/temporal modeller,
  federated learning, AutoEncoder/IsolationForest ensemble'ı, canlı trafikte eğitim,
  drift tetiklemeli otomatik yeniden eğitim. Kod ML-08'de çekirdekten ayrılır.
- Kural motorları (graph, geo, blacklist, compliance) bu karardan etkilenmez; ML skoru
  onların yerine geçmez, yanlarında ayrı bir alarm kaynağıdır.

### 2. Veri seti

- **Birincil kaynak: SAML-D** (Oztas vd., 2023, sentetik AML işlem veri seti; Kaggle
  üzerinden dağıtılır). Hesap kimlikleri, zaman, tutar, ödeme tipi, para birimleri,
  banka konumları, `Is_laundering` ve `Laundering_type` alanlarını içerir.
- Önceki ekip kararıyla yapılan dönüşüm korunur ve **etiketli bir dönüşüm** olarak
  belgelenir: UK ↔ Türkiye konum ve GBP ↔ TRY para birimi yer değiştirmesi (bire bir)
  ve sabit ×50 tutar ölçeği. Bunlar gerçek kur/coğrafya değildir; konum alanı **ülke**
  olarak kalır, şehir gibi kullanılmaz.
- Hesap kimlikleri korunur; yüklemede rastgele IBAN/isim üretilmez. Görüntüleme için
  IBAN/isim hesap kimliğinden deterministik türetilebilir; bunlar özellik değildir.
  Kimlikler yalnız geçmiş (state) anahtarıdır, doğrudan model girdisi değildir.
- `is_laundering` hedeftir. `laundering_type`/`fraud_type` yalnız raporlama etiketidir
  (tipoloji başına recall); özellik girdisi olamaz.
- **Kimlik ve tekrar üretilebilirlik (ML-02 çıktısı, Alper):** ham dosyanın SHA-256'sı,
  dönüşüm betiğinin sürümü (`transform_version`), split/örnekleme parametreleri ve seed
  → `dataset_id`. Ham veri repoya girmez; kalıcı erişim yöntemi (Kaggle sürüm referansı
  + hash doğrulaması) veri kartında yazılır. Geçici klasördeki dönüşüm çıktısı teslim
  sayılmaz.
- **Lisans:** veri setinin Kaggle sayfasındaki lisans metni ML-02'de veri kartına
  birebir aktarılır ve bitirme projesi kullanımına uygunluğu orada teyit edilir. Lisans
  dağıtıma izin vermiyorsa ham/dönüştürülmüş veri CI cache'i dışında paylaşılmaz.
- Küçük deterministik sentetik fixture yalnız yazılım smoke testi (parity, round-trip,
  workflow) içindir; kalite metriği bu fixture'dan raporlanmaz.

### 3. Zaman bölmesi

- Train / validation / test zamana göre ayrıktır: `max(train) < min(val)` ve
  `max(val) < min(test)`. Aynı zaman damgasındaki satırlar sınırda bölünmez.
- Önerilen oran: kronolojik %70 / %15 / %15 (ML-02'de manifestte sabitlenir).
- Validation ve test doğal sınıf dağılımını korur. Train'de negatif alt örnekleme
  yapılırsa yalnız **etiketli satır** seçiminde uygulanır; geçmiş özellikleri tüm
  olay akışından hesaplanır (örneklenen satırlar state'i bozmaz).
- **Kilitli test:** test seti yalnız final değerlendirmede bir kez açılır. Hiperparametre,
  kalibrasyon ve eşik yalnız train/validation ile seçilir; test sonucuna göre eşik
  yeniden ayarlanmaz.

### 4. Özellik kapsamı ve state

- Özellik tanımının ve hesaplama kodunun tek sahibi Alper'dir (ML-03). Servis aynı
  modülü çağırır; A ikinci bir hesaplama yazmaz. Her değişiklik `feature_set_version`
  artırır.
- İlk model için **dar ve servis tarafında karşılığı olan** bir kapsam seçilir:
  1. İşlem anı: log tutar, saat, haftanın günü, ödeme tipi, para birimi uyuşmazlığı,
     sınır ötesi (gönderen/alıcı ülke farklı), gönderen/alıcı ülke kodu.
  2. Hesap geçmişi (yalnız mevcut işlemden **önceki** olaylar): gönderenin son 24 saat
     işlem sayısı ve tutar toplamı, gönderenin son 7 gün farklı alıcı sayısı, alıcının
     son 24 saat gelen işlem sayısı, alıcının son 7 gün farklı gönderen sayısı,
     gönderen→alıcı çiftinin son 7 gün işlem sayısı, gönderenin önceki işleminden bu
     yana geçen süre.
  Kesin liste, dtype ve varsayılanlar sözleşme §2'de; ML-03 bu listeyi daraltabilir,
  genişletme sözleşme değişikliğidir.
- **Deterministik sıra:** olaylar `(timestamp, transaction_id)` ile sıralanır; aynı
  zamanlı olaylar bu sıraya göre birbirini görür. Batch (eğitim) ve tekil (servis)
  hesaplama aynı sırayı kullanır.
- **State sahipliği:** hesap geçmişi süreç içi (in-memory) bir `AccountHistory`
  nesnesinde tutulur. Geçmişe yalnız **ingestion yolu** yazar: API'de
  `POST /api/v1/transactions`, Kafka dağıtımında detector. Bir dağıtımda yalnız biri
  ingestion yapar; aynı işlem iki kez yazılmaz. `POST /api/v1/risk/score` geçmişi
  **okur, yazmaz** (what-if skoru).
- **Cold-start:** geçmişi olmayan hesapta sayaçlar 0, "önceki işlemden beri süre"
  sözleşmedeki varsayılan değeri alır. Servis yeniden başladığında state boştur; bu
  bilinen bir sınırlamadır ve health'te raporlanır. Kalıcı state (Redis vb.) bu
  sprintin dışındadır.
- **Duplicate:** `transaction_id` daha önce görülmüşse işlem skorlanır ama geçmişe
  ikinci kez yazılmaz.
- **Sırası bozuk olay:** hesabın son olayından eski bir işlem gelirse mevcut state ile
  skorlanır ve geçmişe eklenir; bu durum batch ile tam parity'yi bozabilir, sayacı
  health/metrics'te tutulur. Parity testleri sıralı akış üzerinden yapılır.
- Aynı model sürümü + aynı feature vektörü → aynı skor garantisi verilir. Aynı ham
  işlem için aynı skor ancak aynı state ile garanti edilir.

### 5. Model ailesi

- **Servis edilen model: LightGBM** (gradient boosted trees, ikili `binary` hedef).
  Gerekçe: dengesiz tablo verisinde güçlü taban, küçük metin artifact (pickle yok),
  tek satır tahmininde milisaniye altı gecikme ve `pred_contrib=True` ile işleme özel
  log-odds katkıları — ayrı `shap` bağımlılığı gerekmez. Başlangıç sınırları:
  ≤200 ağaç, `max_depth` ≤6.
- **Taban model: lojistik regresyon** (standartlaştırılmış aynı özellikler, sınıf
  ağırlıklı). Yalnız karşılaştırma için raporlanır, servis edilmez.
- XGBoost ikinci aday olarak yalnız ML-04'te gerekçeyle seçilebilir; seçilirse aynı
  sözleşme (metin JSON formatı, `pred_contribs`) geçerlidir. CatBoost ve PyTorch
  çekirdekten çıkar (ML-08).

### 6. Eşik politikası

- Eşik **validation** setinde seçilir: precision ≥ **0.20** koşulunu sağlayan eşikler
  arasından recall'u en yüksek olan. Hiçbir eşik koşulu sağlamıyorsa model
  yayınlanmaz.
- Skor, LightGBM'in olasılık çıktısıdır (`[0, 1]`); `is_fraud = score >= threshold`.
  Kalibrasyon (isotonic/Platt) yapılırsa validation'ın ayrı bir parçasında öğrenilir ve
  artifact'a dahil edilir; eşik kalibre skora uygulanır.
- Eşik artifact metadata'sına yazılır; servis eşiği koddan veya ortam değişkeninden
  almaz.

### 7. Hedef metrikler (kilitli test setinde)

SAML-D'de pozitif oranı ‰1 civarındadır; rastgele sınıflandırıcının PR-AUC'u bu orana
eşittir. Bu yüzden ROC-AUC tek başına kabul ölçütü değildir.

| Metrik | Hedef | Not |
|---|---|---|
| PR-AUC | ≥ **0.40** | Ana ölçüt |
| PR-AUC, taban modele göre | ≥ **%25** göreli iyileşme | LightGBM LR'yi geçmeli |
| Validation'da seçilen eşikte precision | ≥ **0.15** | Validation'da 0.20 ile seçilir; teste kayma payı |
| Aynı eşikte recall | ≥ **0.50** | |
| Tipoloji başına recall | Destek ≥ 30 olan her şüpheli tipolojide ≥ **0.20** | Raporlanır, destek sayısıyla birlikte |
| ROC-AUC | raporlanır | Kabul ölçütü değil |

Hedefler test açılmadan bu ADR'nin `accepted` olmasıyla kilitlenir. Hedef tutmazsa
rapor saklanır, model yayınlanmaz; hedef sırf CI geçsin diye düşürülmez. Değişiklik
yeni bir ADR revizyonu ve gerekçe ister.

### 8. Bütçeler

| Bütçe | Değer | Kapsam |
|---|---|---|
| Artifact boyutu | ≤ 5 MB | Model + metadata + model kartı |
| Tek işlem model çıkarımı | p95 ≤ 5 ms | Yalnız `predict` + katkı, hazır vektörle, CI runner'ında (ubuntu-latest, 2 vCPU) |
| Tek işlem uçtan uca servis skoru | p95 ≤ 30 ms | Özellik + state okuma + model + açıklama, API süreci içinde ölçülür; ayrı raporlanır |
| CI hızlı mod (PR) | ≤ 5 dk | Deterministik fixture, smoke + parity + round-trip |
| Tam eğitim (haftalık / yayın) | ≤ 60 dk | Temsil edici SAML-D, tek runner |

### 9. Artifact ve dağıtım

- Format: `models/fraud/<model_version>/` dizini — `model.txt` (LightGBM metin
  formatı), `metadata.json`, `model_card.md`, `SHA256SUMS`. Pickle kullanılmaz.
- `metadata.json` alanları sözleşme §3'te; checksum, `model_version`,
  `feature_set_version`, `feature_names` (sıralı), `threshold`, `dataset_id`,
  metrikler, eğitim zamanı, git SHA ve kütüphane sürümleri zorunludur.
- Saklama: artifact repoya commit edilmez (`models/` zaten ignore). PR koşularında
  GitHub Actions artifact'ı; yayınlanan modeller `model-<model_version>` etiketli
  GitHub Release eki olarak saklanır. Servis yolu `SENTINELFLOW_MODEL_DIR` ayarından
  okunur (`config/settings.py`), Docker'da volume ile bağlanır.
- Bozuk / eksik / uyumsuz artifact: servis ayağa kalkar, model **yüklenmez**, health
  `degraded`; başka bir modele veya eğitilmemiş modele düşülmez.

### 10. Model yokken davranış

- API ayakta, `/api/v1/system/health` genel durumu `degraded`, `ml_model` bileşeni
  sebebiyle birlikte raporlanır.
- `POST /api/v1/risk/score` → `503` (`model_not_loaded`).
- `POST /api/v1/transactions` işlemi kabul eder ve kural motorları çalışmaya devam eder;
  yanıtta ML skoru `null` döner, ML alarmı üretilmez. Skor uydurulmaz.
- Detector Kafka akışını tüketmeye devam eder; ML adımını atlar ve sayacını artırır.
- `POST /api/v1/ml/train` kaldırılır; eğitim yalnız offline CLI ve CI workflow'u ile
  yapılır (ML-04/ML-07).
- UI model yok durumunu gösterir (SF-405).

## Sonuçlar

- Üç eski ensemble ve canlı eğitim kaldırılır (ML-06); `/api/v1/risk/score` ve
  `/api/v1/ml/models` yanıtları değişir — breaking change, OpenAPI generator ile
  yansıtılır, frontend SF-405'te uyum sağlar.
- Yeni `fraud_type`/`detector_type` değeri `ml_model` eklenir; eski alarmlardaki
  `ml_ensemble` okunabilir kalır.
- Süreç içi state yüzünden yeniden başlatma sonrası geçmiş özellikleri soğuk başlar;
  çok replikalı dağıtımda hesap bazlı tutarlılık bu sprintte garanti edilmez.
- Çekirdek kurulum PyTorch/CatBoost/SHAP gerektirmez (ML-08); imaj küçülür.

## Değerlendirilen alternatifler

- **Mevcut ensemble'ı eğitip korumak:** üç ayrı yükleme yolu, AutoEncoder için PyTorch
  ve ölçülemeyen ağırlıklı oylama gerektirir; reddedildi.
- **XGBoost'u birincil model yapmak:** kabul edilebilir; LightGBM daha küçük artifact
  ve daha basit kategorik işleme nedeniyle seçildi. ML-04'te gerekçeyle değişebilir.
- **SHAP TreeExplainer:** aynı log-odds katkılarını verir ama ağır bağımlılıktır;
  modelin yerleşik katkı çıktısı tercih edildi.
- **Redis'te paylaşılan hesap state'i:** çok replikayı çözer ama altyapı ve parity
  testlerini büyütür; Sprint 4 kapasitesini aşar, sonraya bırakıldı.
- **CompetitionDatasetGenerator ile eğitim:** etiketler üreticinin kurallarını
  ezberletir, gerçekçi değerlendirme vermez; yalnız smoke fixture'ı olarak kalır.
