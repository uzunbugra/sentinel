# SentinelFlow ML kılavuzu

ML tarafının tek kaynağı: sistemin veriden servise nasıl çalıştığı, modelin nasıl
yeniden eğitildiği ve servise nasıl alındığı. Kararlar ADR 0003'te
([`docs/adr/0003-ml-pipeline-v2.md`](../adr/0003-ml-pipeline-v2.md)), arayüzler
sözleşmede ([`docs/contracts/sprint4-ml-api.md`](../contracts/sprint4-ml-api.md)).

| Belge | İçerik |
|---|---|
| [Veri kartı](samld-data-card.md) | SAML-D kaynağı, lisans, dönüşüm, zaman bölmesi (ML-02) |
| [Model kartı](fraud-model-card.md) | Yayınlanan model, eşik, kilitli test sonuçları, sınırlar (ML-05) |
| [`reports/ml04/report.md`](../../reports/ml04/report.md) | Değerlendirme raporu: tüm hedefler, tipoloji recall'u, karışıklık matrisi (ML-04) |

## 1. Mimari

```
SAML-D CSV (Kaggle, v2)
  │  python -m sentinelflow.ml.samld_dataset          ml/samld_dataset.py (+ samld_split, samld_identity)
  ▼
data/samld/<dataset_id>/transactions.parquet + manifest.json      kanonik kayıt, train/validation/test bölmesi
  │  python -m sentinelflow.ml.training features      ml/features (fs-1, AccountHistory)
  ▼
features-fs-1.parquet (veri seti dizininde önbellek)
  │  … training select                                LightGBM + LR tabanı, eşik validation'da
  ▼
reports/ml04/selection.json  ──(commit)──►  … training evaluate-test   kilitli test, bir kez
  │                                            ▼
  │                                     reports/ml04/test-report.json, report.md
  │  … training package                       (yalnız tüm hedefler geçtiyse)
  ▼
models/fraud/<model_version>/   model.txt · metadata.json · model_card.md · SHA256SUMS
  │  SENTINELFLOW_MODEL_DIR (varsayılan models/fraud/current)
  ▼
ml/serving  build_scorer() ─┬─► API: GET /ml/models, POST /risk/score, POST /transactions
                            └─► Kafka detector: ENGINE 4, `ml_model` alarmı
```

- **Tek model:** LightGBM ikili sınıflandırıcı, `fs-1` özellik seti (15 özellik),
  kalibrasyon yok. Skor yalnız eşikle karşılaştırılır (model kartı §Kullanım).
- **Aynı özellik kodu:** eğitim (`build_features_batch`) ve servis
  (`AccountHistory.features_for`) aynı modülü kullanır; parity testleri
  `tests/test_ml_features.py` içinde.
- **Aynı model:** API ve detector `ml.serving.build_scorer()` ile aynı artifact'ı,
  aynı özellik setini ve aynı geçmiş kurallarını yükler
  (`tests/test_ml_detector.py::test_detector_and_api_serve_the_same_model`).
- **Açıklama:** her alarm LightGBM katkılarından (log-odds) ilk 5 özelliği taşır
  (sözleşme §4.5). SHAP kullanılmaz.
- **Durum süreç içindedir:** hesap geçmişi bellekte tutulur, yeniden başlatınca
  boştur (cold-start). Çok replikalı dağıtımda hesap bazlı tutarlılık yoktur (ADR 0003).

| Modül | Görev |
|---|---|
| `ml/samld_dataset.py`, `samld_split.py`, `samld_identity.py` | SAML-D → kanonik parquet, zaman bölmesi, görünen kimlikler |
| `ml/features/` | `fs-1` özellikleri; toplu (eğitim) ve akış (servis) yolu |
| `ml/training/` | `features` / `select` / `evaluate-test` / `package` CLI, metrikler, hedefler, artifact |
| `ml/serving/` | Artifact doğrulama ve yükleme, skor, alarm kanıtı (`evidence.py`) |
| `ml/ci.py` | CI için sentetik veri, kalite kapısı, servis gecikmesi ölçümü |

## 2. Kurulum

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Çekirdek kurulum LightGBM, scikit-learn, pandas ve pyarrow getirir; PyTorch, XGBoost,
CatBoost ve SHAP gerekmez (ML-08, CI bunu kontrol eder). Komutlar repo kökünden
çalıştırılır: eğitim kaydı git commit'ini okur ve `package` git dışı bir çalışmayı reddeder.

## 3. Modeli yeniden eğitmek

### 3.1 Veri

SAML-D sürüm 2'yi Kaggle'dan indirin (hesap gerekir; lisans CC BY-NC-SA 4.0, veri kartı §1).

```bash
python -m sentinelflow.ml.samld_dataset --source path/to/archive.zip --out data/samld
```

Çıktı `data/samld/<dataset_id>/`. Aynı CSV her zaman aynı `dataset_id`'yi
(`samld-e8dfe86cce3f`) ve aynı manifesti üretir. `data/` repoya girmez.

### 3.2 Özellikler, seçim, kilitli test, paket

```bash
DATASET=data/samld/samld-e8dfe86cce3f

python -m sentinelflow.ml.training features --dataset-dir $DATASET
python -m sentinelflow.ml.training select   --dataset-dir $DATASET
git add reports/ml04/selection.json && git commit -m "chore(ml): freeze model selection"
python -m sentinelflow.ml.training evaluate-test --dataset-dir $DATASET
python -m sentinelflow.ml.training package
```

| Adım | Ne yapar | Reddettiği durum |
|---|---|---|
| `features` | `fs-1` özelliklerini tüm olay akışı üzerinden, yalnız önceki olaylarla hesaplar ve önbelleğe yazar | Manifest yok / bozuk |
| `select` | Train'de LightGBM ve LR tabanını eğitir, validation'da eşiği seçer (precision ≥ 0.20 koşulunda en yüksek recall), `selection.json` yazar. Yayınlanan model için eğitim ~226 sn sürdü (donanım `selection.json` içinde) | Test seti zaten açılmış |
| `evaluate-test` | Test bölmesini **bir kez** açar (`test-opened.json`), ADR 0003 §7–§8 hedeflerini ölçer, `test-report.json` ve `report.md` yazar | `selection.json` commit'li değil ya da HEAD'den farklı; test daha önce açılmış; model dosyası seçimle uyuşmuyor |
| `package` | `models/fraud/<model_version>/` dizinini yazar (`model.txt`, `metadata.json`, `model_card.md`, `SHA256SUMS`) | Hedeflerden biri geçmedi; model test edilen model değil; seçimde git SHA yok |

Ara dosyalar `data/ml04/` altına yazılır (`--work-dir`). Kilitli test kuralı nedeniyle
`reports/ml04` yayınlanan modelin kaydıdır. Yeni bir eğitim turu başka bir
`--report-dir` (ve `--work-dir`) ile yapılır. Yeni model yayınlanacaksa raporu aynı PR'da
`reports/ml04`'ün yerine geçer, çünkü CI kalite kapısı o dizini kontrol eder (§5).

### 3.3 Kaggle olmadan hızlı deneme

CI'ın kullandığı sentetik veri aynı düzeni üretir ve tüm zinciri birkaç saniyede
çalıştırır. Sonuç yalnız boru hattını sınar, modeli değerlendirmez:

```bash
python -m sentinelflow.ml.ci synthetic --out build/ml-ci/samld --size fast
python -m sentinelflow.ml.training features --dataset-dir build/ml-ci/samld
python -m sentinelflow.ml.training select --dataset-dir build/ml-ci/samld \
  --work-dir build/ml-ci/work --report-dir build/ml-ci/report
python -m sentinelflow.ml.training evaluate-test --dataset-dir build/ml-ci/samld \
  --work-dir build/ml-ci/work --report-dir build/ml-ci/report --skip-commit-check
python -m sentinelflow.ml.training package \
  --work-dir build/ml-ci/work --report-dir build/ml-ci/report --out build/ml-ci/models
```

`--skip-commit-check` yalnız yerel denemeler içindir. Yayınlanacak bir model bu bayrakla
üretilmez.

## 4. Modeli servise almak

Servis modeli yalnız **açılışta** `SENTINELFLOW_MODEL_DIR` dizininden yükler. Varsayılan
değer `models/fraud/current`'tır (`config/settings.py`, `.env.example`).

```bash
# Yerel: current'ı yeni sürüme bağla (ya da .env içinde SENTINELFLOW_MODEL_DIR'i ayarla)
ln -sfn fraud-lgbm-20261030-0e0c647 models/fraud/current
# API ve detector'ı yeniden başlat; ikisi de aynı dizini okur
```

- **Docker:** `docker-compose.yml` `./models` dizinini API konteynerine salt okunur
  bağlar (`/app/models`). Artifact'ı `models/fraud/<model_version>/` altına koyup `current`
  bağlantısını güncelleyin, sonra `docker compose up -d api` çalıştırın.
  `SENTINELFLOW_MODEL_DIR` konteynerde `/app`'e göre çözülür.
- **Doğrulama:** `GET /api/v1/ml/models` → `status: "loaded"` ve beklenen
  `model_version`. `GET /api/v1/system/health` içinde `ml_model` bileşeni `healthy`.
  Detector açılışta `Fraud model loaded: <model_version>` loglar.
- **Yayın:** artifact repoya commit edilmez (`models/` ignore). Yayınlanan model
  `model-<model_version>` etiketli GitHub Release'e eklenir (ADR 0003 §9).
  CI koşularında artifact `ml-pipeline-<size>` adıyla Actions artifact'ı olarak indirilebilir.

**Model yoksa ya da artifact bozuksa** (ADR 0003 §10) servis yine ayağa kalkar ama
model yüklenmez, başka bir modele de düşmez:
- `ml_model` bileşeni `degraded` olur. `/ml/models` `not_loaded` ya da `invalid` döner
  ve sebebini yazar.
- `POST /risk/score` → `503 model_not_loaded`.
- `POST /transactions` işlemi kabul eder ama `fraud_score: null` döner.
- Kural motorları ve detector çalışmaya devam eder.

Hesap geçmişi model olmadan da kaydedilir; sonradan yüklenen model aynı geçmişi görür.

## 5. CI

| Workflow / job | Ne zaman | Ne yapar |
|---|---|---|
| `ci.yml` → *ML Model Tests* | Her PR | Çekirdek kurulumda `import torch`'un başarısız olduğunu kontrol eder, `tests/test_samld_dataset.py` ve `tests/test_ml_*.py` testlerini koşar |
| `ml-pipeline.yml` → *Quality Gate* | `ml/**`, `reports/ml04/**`, fixture veya workflow değişince; haftalık; elle | `reports/ml04` raporunu seçim SHA'sı ve `dataset_id` ile doğrular, hedefleri yeniden hesaplar. Hedef altındaki bir rapor workflow'u kırmızıya çevirir |
| `ml-pipeline.yml` → *Training Pipeline* | Aynı tetikleyiciler | Sentetik veri (`fast`, haftalık koşuda `full`) → features → select → evaluate-test → package → metrik özeti → servis gecikmesi. Çıktılar `ml-pipeline-<size>` artifact'ı olarak yüklenir |

Gerçek SAML-D CI'da kullanılmaz (lisans ve boyut). Gerçek modelin metrikleri commit'li
`reports/ml04` raporundan gelir.

## 6. Değerlendirme özeti

Yayınlanan model `fraud-lgbm-20261030-0e0c647`, kilitli test, 1.425.728 işlem,
1.697 pozitif (%0,12):

| Ölçüt | Değer | Hedef (ADR 0003) |
|---|---:|---|
| PR-AUC | 0,6152 | ≥ 0,40 |
| LR tabanına göre PR-AUC kazancı | 0,0628 → 0,6152 | ≥ %25 göreli |
| Precision / recall (validation eşiği 0,113) | 0,2457 / 0,6671 | ≥ 0,15 / ≥ 0,50 |
| En düşük tipoloji recall'u (destek ≥ 30) | 0,2245 (Cycle) | ≥ 0,20 |
| Artifact | 636.601 bayt | ≤ 5 MB |
| Tek satır predict + katkı, p95 | 1,13 ms (eğitim makinesi) | ≤ 5 ms |
| Ağaç / derinlik | 190 / 6 | ≤ 200 / ≤ 6 |

Her doğru alarma yaklaşık 3 yanlış alarm düşer (TP 1.132, FP 3.476). Tipoloji
dökümü ve karışıklık matrisi raporda, sınırlar model kartında.

### Ölçülen ve ölçülmeyen

- **Ölçüldü:** yukarıdaki tablo. Ayrıca CI runner'ında sentetik veriyle
  özellik + skor + kayıt gecikmesi (*Training Pipeline* özetinde; ilk koşuda predict +
  katkı p95 0,074 ms).
- **Ölçülmedi:** gerçek trafikte API içinden uçtan uca servis skoru (ADR hedefi p95 ≤
  30 ms), Kafka verimi ve uçtan uca alarm gecikmesi. Bu değerler için sayı verilmez.
