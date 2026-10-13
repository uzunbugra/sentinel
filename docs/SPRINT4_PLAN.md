# Sprint 4 Planı — Tek, Eğitilmiş ve Ölçülmüş Fraud Modeli

**Tarih:** 15–28 Ekim 2026 (10 iş günü; 28 Ekim yarım gün, 29 Ekim tatil)
**Ekip:** 2 geliştirici — Kişi A: @uzunbugra · Kişi B: @alper-tekin
**Plan tabanı:** `origin/develop` @ `d68b4e0`
**Sprint teması:** Sprint 3 kapanışı + ML pipeline'ının baştan kurulması: tek veri sözleşmesi,
tek özellik tanımı, küçük ve eğitilmiş tek model, servislerin bu modeli gerçekten kullanması.

## 1. Sprint 3 kapanış durumu

Sprint 3'ün P0/P1/P2 işleri planlanan bitişten (23 Ekim) önce tamamlandı; kalan günler Sprint 4'e
aktarıldı.

| Ölçüt (Sprint 3 §11) | Durum |
|---|---|
| CI/CD ve ML Pipeline tamamen yeşil | ✅ `develop` push'ları ve haftalık ML çalıştırması yeşil (train → validate → benchmark → model card) |
| Açıklanmamış `pip-audit` bulgusu yok | ✅ istisnasız temiz |
| Alarmdan vaka oluşturma + timeline demo edilebilir | ⚠️ Kod ve testler hazır; **çalışan Docker yığınında uçtan uca demo yapılmadı** |
| Korumalı REST çağrılarının %100'ü ortak auth istemcisinden | ✅ korumalı uçlara çıplak `fetch` yok |
| Yeni vaka/audit kodunda ≥ %80 branch coverage | ✅ servis %98, kurallar ve repository'ler %100 |
| ≥ 4 kritik frontend senaryosu testli | ✅ 156 Vitest testi |
| Sprintte eklenen dosyaların hiçbiri 500 satırı aşmıyor | ✅ (`test_api_structure.py` `api/` için bunu CI'da zorluyor) |

**Sprint 3'ten kalanlar (Sprint 4 P0 kapısı, §4.1):**

1. `develop` → `main` release yapılmadı. `main`'de `develop`'ta olmayan bir commit var
   (`d8125d7`, README katkıda bulunanlar); release öncesi `develop`'a alınmalı.
2. Docker smoke testi ve uçtan uca demo yapılmadı (#13'te Neo4j `exec format error` raporlandı).
3. Giriş sayfasındaki sabit "Demo: admin / Admin123!" ipucu gerçek şifreyle eşleşmiyor (#13).
4. `develop` ve `main` için branch koruması yok; README "CI-gated" diyor ama zorlanmıyor.
5. Vaka akışındaki satır kilidi (eşzamanlı istek) gerçek PostgreSQL'de test edilmedi; CI'da
   PostgreSQL servisi yok.
6. Sprint 3 demo dokümanı (`docs/SPRINT3_DEMO.md`) yazılmadı.

## 2. Neden bu tema? — ML pipeline'ının bugünkü durumu

Kod incelemesinde (develop @ `d68b4e0`):

- **Eğitim ile servis birbirinden kopuk.** CI'daki ML Pipeline bir XGBoost modeli eğitip artifact
  olarak saklıyor, ama hiçbir servis bu modeli yüklemiyor.
- **Üç ayrı, eğitilmemiş ensemble.** `api/state.py`, `processor/detector/service.py` ve
  `api/risk_scoring/engine.py` her biri kendi IsolationForest + XGBoost + AutoEncoder (+ LightGBM /
  CatBoost) örneğini sıfırdan oluşturuyor. Gözetimli modeller hiç eğitilmediği için devre dışı
  kalıyor; skor fiilen canlı trafikte kendini eğiten bir IsolationForest'tan geliyor.
- **İki farklı özellik tanımı.** Servis `ml/feature_engine.py` (21 özellik, hesap geçmişi tutan
  durum bilgili motor), eğitim `ml/dataset_schema.py` (11 özellik) kullanıyor → train/serve skew.
- **Kullanılmayan ağır kod ve bağımlılıklar.** `gnn_model`, `temporal_model` hiçbir yerden
  çağrılmıyor; `advanced_*`, `graph_features`, `competition_dataset` 800–1060 satır.
  `torch` + `torch-geometric` çekirdek bağımlılıkta (kurulum ~2 GB).
- **Değerlendirme yok.** Tek metrik CI'daki rastgele bölünmüş test seti; zaman bazlı bölme,
  PR-AUC, eşik seçimi ve fraud türü bazında recall yok.

Hedef: tek bir veri sözleşmesi, tek bir özellik tanımı, küçük ve eğitilmiş tek bir model; API,
detector ve risk motorunun **aynı** versiyonlu artifact'ı yüklemesi.

## 3. Kapasite ve çalışma modeli

- Teorik kapasite `2 × 9.5 = 19` kişi-gün; planlanan 15, tampon 4.
- Sprint 3'teki kurallar geçerli: ayrı worktree/branch, tek yazar, `CONTRACT-REQUEST`, küçük PR,
  Conventional Commits, PR'ı diğer kişi inceler (`CODEOWNERS`).
- **Kişi A** (bu sprintte ML sahibi): `src/sentinelflow/ml/**`, `src/sentinelflow/mlops/**`,
  `src/sentinelflow/api/**` (ML servis ve uçları dahil), `processor/detector/**`, `tests/**`,
  `scripts/**`, `.github/workflows/**`, `pyproject.toml`, `docs/**`.
- **Kişi B**: `sentinelflow-web/**`, Docker/demo ortamı doğrulaması, tarayıcı testleri.
- ML işlerinin ayrıntılı görev listesi GitHub'da **Sprint 4** milestone'u altında, `ml` etiketiyle
  Kişi A'ya atanmış issue'lardır (§5).

## 4. Sprint backlog'u

### 4.1 P0 — Sprint 3 kapanışı (gün 1–2)

#### SF-401 — Release ve branch koruması (Kişi A, 0.5 gün)
- `main`'deki `d8125d7`'yi `develop`'a al; `develop` → `main` release PR'ı; `CHANGELOG.md`
  `[Unreleased]` → `[2.2.0] - 2026-10-xx`; sürüm `2.2.0` (`pyproject.toml`, `__version__`, API).
- `develop` ve `main` için branch koruması: PR zorunlu, CI'daki Lint/Tests/Security/Frontend işleri
  zorunlu kontrol, 1 onay.

**Kabul:** `main` = `develop` + release commit'i; `v2.2.0` tag'i; koruma kuralları aktif.

#### SF-402 — PostgreSQL entegrasyon testleri CI'da (Kişi A, 0.5 gün)
- CI `integration` işine PostgreSQL servisi; Alembic migration'ları gerçek veritabanında çalışır.
- Vaka akışı için eşzamanlı iki isteğin aynı alarmı iki vakaya bağlayamadığını gösteren
  `integration` işaretli test (row lock).

**Kabul:** Integration işi migration + eşzamanlılık testini PostgreSQL'e karşı koşar ve geçer.

#### SF-403 — Docker smoke ve demo (Kişi B, 1 gün)
- Repodaki `docker-compose.yml` ile tam yığın (Postgres, Redis, Neo4j, Kafka, API, web); #13'teki
  Neo4j sorunu repodaki imaj sürümüyle yeniden denenir, gerekiyorsa `CONTRACT-REQUEST` ile
  Kişi A'ya `platform:` sabitleme talebi.
- `seed_admin.py` ile admin; işlem gönderip ML alarmı üretme → alarmdan vaka → timeline akışı.
- Giriş sayfasındaki sabit demo ipucu kaldırılır ya da yalnızca geliştirme modunda gösterilir.
- `docs/SPRINT3_DEMO.md` için adımlar ve ekran görüntüleri (doküman Kişi A'ya PR açıklamasıyla iletilir).

**Kabul:** Temiz makinede README adımlarıyla demo akışı tekrarlanabilir.

### 4.2 P1 — ML pipeline'ı yeniden kurulumu (Kişi A, ~8 gün)

Ayrıntılı kabul kriterleri issue'lardadır; sıra bağımlılık sırasıdır.

| ID | İş | Gün |
|---|---|---|
| [ML-01](https://github.com/uzunbugra/sentinel/issues/16) (#16) | Hedef mimari ve veri seti kararı (ADR) | 0.5 |
| [ML-02](https://github.com/uzunbugra/sentinel/issues/17) (#17) | Tekrarlanabilir veri seti + zaman bazlı train/val/test bölmesi + veri kartı | 1 |
| [ML-03](https://github.com/uzunbugra/sentinel/issues/18) (#18) | Tek özellik tanımı: eğitim ve servis aynı kodu kullanır, parity testi | 1.5 |
| [ML-04](https://github.com/uzunbugra/sentinel/issues/19) (#19) | Küçük modeli eğit, eşik seç, değerlendirme raporu | 1.5 |
| [ML-05](https://github.com/uzunbugra/sentinel/issues/20) (#20) | Versiyonlu model artifact'ı + model kartı | 0.5 |
| [ML-06](https://github.com/uzunbugra/sentinel/issues/21) (#21) | Servis entegrasyonu: API, detector ve risk motoru aynı modeli yükler | 1.5 |
| [ML-07](https://github.com/uzunbugra/sentinel/issues/22) (#22) | ML Pipeline workflow'unun yeniden yazılması (kalite kapısı) | 0.5 |
| [ML-08](https://github.com/uzunbugra/sentinel/issues/23) (#23) | Kullanılmayan ML kodu ve ağır bağımlılıkların ayrılması | 0.5 |
| [ML-09](https://github.com/uzunbugra/sentinel/issues/24) (#24) | ML dokümantasyonu | 0.5 |

**Hedef model profili (ML-01'de kesinleşir):** gradient boosted trees (LightGBM veya XGBoost,
≤ 200 ağaç, derinlik ≤ 6) + karşılaştırma için lojistik regresyon taban modeli; artifact ≤ 5 MB;
tek işlem çıkarımı p95 ≤ 5 ms; PyTorch gerektirmez.

### 4.3 P1 — Kişi B

#### SF-404 — Uçtan uca tarayıcı testleri (Kişi B, 2 gün)
Playwright ile login → alarm listesi → alarmdan vaka → vaka detayı/timeline → durum değişikliği;
backend gerçek (Docker) veya sözleşme fixture'larıyla. CI'da çalıştırma Kişi A'dan `CONTRACT-REQUEST`.

#### SF-405 — Model bilgisi ve alarm açıklaması ekranı (Kişi B, 2 gün)
ML-06'nın sözleşmesine göre (§6): alarm detayında model versiyonu, skor, eşik ve en etkili
özellikler; ayarlar/sistem sayfasında aktif model kartı özeti. ML-06 birleşene kadar fixture ile.

#### SF-406 — Node 22 kararı (Kişi B, 0.5 gün)
`camera-controls` ve jest-dom'un yeni sürümleri Node ≥ 22 istiyor; `sentinelflow-web/Dockerfile`
güncellemesi (B) ve CI'daki `node-version` için `CONTRACT-REQUEST` (A).

### 4.4 P2 — Kapasite kalırsa

- **SF-407 (A):** `AlertRepository` ve diğer repository'lerdeki kullanılmayan async yolların temizliği.
- **SF-408 (B):** Dashboard'da model metrikleri (PR-AUC, eşik, son eğitim tarihi) kartı.

## 5. ML görev listesi (Kişi A) — GitHub issue'ları

Tümü **Sprint 4** milestone'u (#16–#24), `ml` etiketi, atanan @uzunbugra. Her issue'da kapsam, kabul
kriterleri ve bağımlılıklar yazılıdır. Önerilen branch'ler: `codex/s4-a-ml-<konu>`.

```text
ML-01 ─> ML-02 ─> ML-03 ─> ML-04 ─> ML-05 ─> ML-06 ─┐
                                    └─> ML-07       ├─> ML-09
                          ML-08 (ML-06'dan sonra) ──┘
```

## 6. API sözleşmesi el sıkışması (ML-06 ↔ SF-405)

Kişi A, ML-06'ya başlamadan `docs/contracts/sprint4-ml-api.md` notunu sabitler:

- `GET /api/v1/ml/models` — aktif model: `model_version`, `trained_at`, `feature_names`,
  `threshold`, değerlendirme metrikleri (PR-AUC, ROC-AUC, eşikteki precision/recall), veri seti
  kimliği.
- `POST /api/v1/risk/score` ve ML alarmları — `score`, `threshold`, `model_version`,
  `top_features` (ad, değer, katkı); alarm `evidence` içinde `detector_type = ml_ensemble`
  yerine model kimliği.
- Model yüklü değilse davranış (`503` mü, kural tabanlı geri dönüş mü) ve `GET /system/health`'te
  `ml_model` bileşeni.

Kişi B fixture'ları bu nottan hazırlar; `api-schema.ts` yalnızca generator ile güncellenir.

## 7. Günlere göre plan

| Gün | Kişi A | Kişi B |
|---|---|---|
| 1 — Per 15 Eki | SF-401 release + koruma; ML-01 ADR | SF-403 Docker yığını, Neo4j |
| 2 — Cum 16 Eki | SF-402 PostgreSQL CI; ML-02 başlangıç | SF-403 demo akışı + giriş ipucu |
| 3 — Pzt 19 Eki | ML-02 veri seti + bölme | SF-404 Playwright kurulumu |
| 4 — Sal 20 Eki | ML-03 özellik tanımı | SF-404 akış testleri |
| 5 — Çar 21 Eki | ML-03 parity testi; ML sözleşme notu (§6) | SF-405 fixture'larla ekran |
| 6 — Per 22 Eki | ML-04 eğitim + eşik | SF-405 |
| 7 — Cum 23 Eki | ML-04 rapor; ML-05 artifact + model kartı | SF-406 Node 22 |
| 8 — Pzt 26 Eki | ML-06 servis entegrasyonu | SF-405'i gerçek API'ye bağla |
| 9 — Sal 27 Eki | ML-06 + ML-07 workflow | Uçtan uca demo provası |
| 10 — Çar 28 Eki (½) | ML-08 temizlik, ML-09 doküman, release adayı | Sprint demo |

## 8. Definition of Done (Sprint 3'e ek olarak)

- Model değişikliği içeren PR'da değerlendirme raporu (veri seti kimliği, metrikler, eşik) PR
  açıklamasında yer alır.
- Eğitim tekrarlanabilir: aynı seed ve veri seti kimliği aynı metrikleri verir.
- Eğitim ve servis aynı özellik kodunu kullanır; parity testi CI'da koşar.
- Servisler modeli versiyonlu artifact'tan yükler; eğitilmemiş model ile skor üretilmez.

## 9. Sprint başarı ölçütleri

- `main`'de `v2.2.0`; `develop` ve `main` korumalı.
- Docker yığınında login → işlem → ML alarmı → vaka → timeline demosu.
- Tek model artifact'ı; API, detector ve risk motoru aynı `model_version`'ı raporlar.
- Zaman bazlı test setinde PR-AUC ve eşikteki precision/recall raporlanmış; ML-01'de belirlenen
  hedefler karşılanmış.
- Çekirdek kurulumda PyTorch yok; Docker imajı küçülmüş (önce/sonra boyutu raporlanır).
- En az 3 Playwright uçtan uca senaryosu.

## 10. Bilinçli olarak sprint dışında

- GNN, zamansal (sequence) modeller, federated learning'in yeniden etkinleştirilmesi.
- Gerçek zamanlı yeniden eğitim (online learning) ve otomatik drift tetiklemeli eğitim.
- STR/MASAK raporlama (park edilmiş compliance modülü).
- Kubernetes / production dağıtımı.
