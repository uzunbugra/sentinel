# Sprint 4 Planı — Data/eğitim ve servis/backend ayrımı

Revizyon: 19 Ekim 2026. Data/eğitim Alper'e (@alper-tekin), servis/backend Kişi A'ya
(@uzunbugra) ayrıldı. SF-404 A'ya taşındı; SF-406 ortak iş olarak korundu.
Takvim yerine iş sırası ve kabul kapıları esas alınır. Önceki plan Git geçmişinde korunur.
Bu belge çalışma kapsamını tanımlar; geliştirme işlerinin tamamlandığını göstermez.

İncelenen kaynaklar:
- [Mevcut Sprint 4 planı](https://github.com/uzunbugra/sentinel/blob/codex/s4-plan/docs/SPRINT4_PLAN.md), `4d654ba` (GitHub dal ucu doğrulandı).
- [ML-01–09 issue'ları](https://github.com/uzunbugra/sentinel/issues?q=is%3Aissue+milestone%3A%22Sprint+4%22), #16–#24; 19 Ekim'de tamamı açık.
- `origin/develop` @ `d68b4e0`: veri/özellik/eğitim kodu ve CODEOWNERS.
- Alper'in paylaştığı dağılım görseli ve önceki SAML-D kararı (ortak hafıza).

## 1. Amaç ve sorumluluk

Tek veri sözleşmesi ve tek özellik tanımıyla eğitilen, ölçülen, versiyonlanan küçük
bir modeli API, detector ve risk motorunda kullanmak; sonucu alarm/vaka akışında göstermek.

- **Alper / B:** veri hazırlama, ortak özellik hesaplama, eğitim, değerlendirme,
  artifact üretimi ve model kartı; Docker/demo ve model ekranı.
- **Kişi A:** servis/backend, artifact'ın serviste yüklenmesi, API sözleşmesi,
  CI, release, Playwright ve entegrasyon dokümantasyonu.
- **Ortak:** mimari, model/özellik sözleşmesi, kalite hedefleri ve karşılıklı inceleme.

## 2. Revize backlog

Süreler kişi-gün tahminidir; tamamlanmış iş iddiası değildir.

| İş | Sahip | Gün | Teslim / kabul özeti |
|---|---|---:|---|
| SF-401 Release ve branch koruması | A | 0.5 | Mevcut release işi ve gerekli kontroller doğrulanır; yalnız eksikler tamamlanır. |
| SF-402 PostgreSQL CI | A | 0.5 | Gerçek PostgreSQL'de migration ve aynı alarmı eşzamanlı iki vakaya bağlama testi. |
| ML-01 ADR ve sözleşme koordinasyonu (#16) | A; karar ortak | 0.5 | SAML-D kaynağı, model ailesi, eşik politikası, sayısal hedefler, erken sözleşme notu. |
| ML-02 Veri seti ve zaman bölmesi (#17) | Alper | 1 | Tekrarlanabilir hazırlama, manifest, veri kartı, ayrık train/validation/test. |
| ML-03 Ortak özellik tanımı (#18) | Alper | 1.5 | Aynı batch/tekil hesaplama, feature_set_version, parity ve gelecek sızıntısı testi. |
| ML-04 Eğitim ve değerlendirme (#19) | Alper | 1.5 | Baseline + küçük ağaç modeli; validation'da eşik; kilitli testte nihai rapor. |
| ML-05 Artifact ve model kartı (#20) | Alper | 0.5 | Model + metadata + checksum; kaydet/yükle tahmin eşitliği, boyut bütçesi. |
| ML-06 Servis entegrasyonu (#21) | A | 1.5 | Üç giriş noktası aynı artifact/sözleşme; gerçek skor, açıklamalar, health ve hata davranışı. |
| ML-07 Eğitim workflow'u (#22) | A | 0.5 | Alper'in CLI'larını çağıran CI, rapor/artifact çıktısı ve doğrulanmış başarısız kalite kapısı. |
| ML-08 Kullanılmayan kod/bağımlılıklar (#23) | A | 0.5 | ML-06 sonrası güvenli temizlik; PyTorch çekirdekten ayrılır, önce/sonra imaj boyutu. |
| ML-09 Entegrasyon dokümanı (#24) | A | 0.5 | Eğitimden servise kullanım kılavuzu; Alper'in veri/model kartları ve raporuna bağlantılar. |
| SF-403 Docker ve demo | Alper | 1 | Ortam smoke, demo giriş ipucunun düzeltilmesi, demo adımları; finalde gerçek ML akışı. |
| SF-404 Playwright | A | 2 | Login→alarm→vaka→timeline akışı, yetki/hata senaryoları ve CI. |
| SF-405 Model bilgisi ve alarm açıklaması UI | Alper | 2 | İlk aşama fixture; finalde gerçek API'den model, skor, eşik, katkılar; boş/hata durumları. |
| SF-406 Node sürüm hizalaması | Alper + A | 0.5 | Alper web/Docker/package tarafı (0.25); A CI tarafı (0.25). Mevcut Node 22 ihtiyacı doğrulanır. |

Ana işler: Alper **7.75**, A **6.75** kişi-gün. Her kişiye ek **0.5 gün** ortak
sözleşme/inceleme/teslim payı: toplam **15.5 kişi-gün** (Alper 8.25, A 7.25).
Bu değerler efor tahminidir, takvim taahhüdü değildir. Veri/özellik/artifact zinciri
kritik bağımlılıktır; A bu teslimi beklerken servis hazırlığı, platform ve test işlerini yürütür.

SF-407 repository temizliği ve SF-408 ek metrik dashboard'u P2 kalır. SF-405 içindeki
aktif model özeti zorunludur; SF-408 için ayrı dashboard genişlemesi zorunlu değildir.

## 3. Başlangıçta dondurulacak sözleşme

A, `docs/contracts/sprint4-ml-api.md` belgesini yazar; Alper veri, özellik ve artifact
bölümlerini onaylar. Bu iş ML-06'nın sonuna bırakılmaz; ilk çalışma aşamasında yapılır.

1. **Veri:** alan adları/tipleri, zaman dilimi, hesap kimliği, eksik alanlar, izinli
   kategoriler. SAML-D kaynak/dönüşüm kimliği ve örnek işlem JSON'u.
2. **Özellik:** sıralı özellik listesi, dtype, varsayılanlar, `feature_set_version`,
   batch/tekil arayüz. Geçmiş kullanan özelliklerde pencere ve durum güncelleme sırası.
3. **Artifact:** model formatı, `model_version`, `feature_set_version`, `feature_names`,
   `threshold`, `dataset_id`, metrikler, eğitim zamanı, git SHA, kütüphane sürümleri,
   checksum; dağıtım yeri ve bozuk/uyumsuz artifact davranışı.
4. **API:** mevcut plandaki `GET /api/v1/ml/models`, `POST /api/v1/risk/score`, alarm
   evidence ve health yanıtları; kesin route'lar OpenAPI ile doğrulanır. Skor aralığı,
   eşik karşılaştırması, katkı değerinin anlamı ve `top_features` biçimi sabitlenir.
5. **Model yokken:** servis ayakta, health degraded; ML skoru uydurulmaz. ML skor
   endpoint'i için öneri 503; diğer kural motorlarının ve ingestion'ın nasıl devam
   edeceği ADR'de açıkça yazılır. UI model yok durumunu gösterir.
6. **Tek teslim örneği:** Alper örnek işlem dizisi + beklenen feature vektörleri ve
   metadata örneği verir. A loader/API fixture'ını, Alper UI fixture'ını bundan üretir.

Önemli: Aynı model sürümü, geçmişe bağlı özelliklerde tek başına aynı skoru garanti etmez.
İşlem geçmişinin sahibi, cold-start, duplicate ve sırası bozuk olay davranışı birlikte
kararlaştırılır. API ve detector aynı işlemi geçmişe iki kere yazmamalıdır. Bu state
altyapısı kapasiteyi aşıyorsa ilk modelin özellik kapsamı ADR'de daraltılır; servis
tarafında karşılığı olmayan geçmiş özellikleri eğitimde kullanılmaz.

## 4. Alper'in veri/eğitim teslim zinciri

### ML-02 — SAML-D'yi güvenilir eğitim girdisi yap

- Mevcut issue'daki CompetitionDatasetGenerator birincil kaynak önerisini önceki
  SAML-D kararıyla güncelle. Sentetik küçük fixture yalnız yazılım smoke testi içindir.
- Önceki dönüşüm dosyası ve betiğinin kalıcı konumunu, kaynak hash'ini ve tekrar
  üretilebilirliğini doğrula; geçici klasördeki dosyayı kalıcı teslim kabul etme.
- Hesap kimliklerini koru; yükleme sırasında rastgele IBAN/isim üretme.
- UK→Türkiye, GBP→TRY ve sabit x50 dönüşümünü veri kartında açıkla; bunları gerçek kur
  veya gerçek coğrafi veri olarak yorumlama. Ülke alanını şehir gibi kullanma.
- `is_laundering` hedef; `fraud_type` ve `laundering_type` yalnız raporlama etiketi,
  özellik girdisi değil. Kimlikler geçmiş hesaplama anahtarı olabilir, doğrudan model girdisi olmaz.
- Zaman sırasına göre böl; `max(train) < min(val)` ve `max(val) < min(test)` doğrulansın.
  Aynı zaman damgasındaki satırları bölme sınırında ayırma.
- Örnekleme gerekiyorsa strateji manifestte yazılsın. Validation/test doğal sınıf
  dağılımını korusun; train örneklemesi geçmiş özellikleri için gerekli olayları kaybettirmesin.

### ML-03 — Tek özellik motoru

- Özellik tanımının ve ortak hesaplama kodunun sahibi Alper; A ayrı hesaplama yazmaz.
- Geçmiş özellikleri yalnız mevcut işlemden önceki izinli olayları görür. Aynı zamanlı
  olaylar için deterministik sıra/pencere kuralı sözleşmede bulunur.
- Batch ve tekil akış aynı işlem dizisi/başlangıç durumu ile eşleşir.
- Sonradan eklenen gelecek olaylar önceki özellikleri değiştiremez.
- Train'de öğrenilen dönüşümler val/test'e yalnız uygulanır; etiketler geçmiş state'e girmez.

### ML-04/05 — Ölçülmüş ve yüklenebilir model

- Lojistik regresyon baseline ve LightGBM/XGBoost adayından biri. Başlangıç hedefi
  ≤200 ağaç, derinlik ≤6, artifact ≤5 MB; nihai model ailesi ML-01'de seçilir.
- Hiperparametre, kalibrasyon ve eşik yalnız train/validation ile seçilir. Kilitli test
  final değerlendirmede kullanılır; test sonucuna bakıp eşik tekrar ayarlanmaz.
- PR-AUC, ROC-AUC, precision/recall/F1, confusion matrix, tipoloji başına recall ve
  destek sayıları; baseline karşılaştırması ve p50/p95 gecikme raporlanır.
- p95 ≤5 ms hedefinin kapsamı ve donanımı yazılır; yalnız model predict ile tüm
  özellik hesaplama/açıklama/API süresi karıştırılmaz.
- Sayısal kalite hedefleri test açılmadan ADR'de sabitlenir. Hedef tutmazsa rapor
  saklanır ve model yayınlanmaz; sırf CI geçsin diye hedef düşürülmez.
- Alper paketleme/round-trip doğrulamasını teslim eder; A aynı formatın servis
  yükleyicisini ve uyumsuz artifact/health testlerini ML-06'da tamamlar.

## 5. Paralel çalışma ve bağımlılıklar

```text
Ortak ADR + veri/özellik/artifact/API sözleşmesi
  ├─ Alper: ML-02 → ML-03 → ML-04 → ML-05 ─────────────┐
  ├─ A: ML-06 servis iskeleti + fixture loader ────────┤
  ├─ A: SF-401/402, Playwright ve CI iskeleti           │
  └─ Alper: SF-405 fixture arayüzü                     │
                                                     ↓
                                    ML-06 gerçek artifact entegrasyonu
                                          ├─ ML-07 gerçek kalite kapısı
                                          ├─ ML-08 temizlik → ML-09
                                          └─ SF-405 gerçek API → SF-404 + SF-403 final demo
```

A, ML-04 bitmeden üç ensemble'ın çağrı noktalarını ayırmaya ve ortak servis
iskeletine başlayabilir. Ancak çalışan yolları model hazır olmadan bozan bir değişiklik
merge edilmez. ML-06'nın gerçek artifact ile kabul testi ML-05'e bağımlı kalır.
ML-07 iskeleti erken yazılır; final kabul ML-05 sonrasıdır (issue #22'deki bağımlılık).

SF-403 iki kontrol noktasıdır: önce ortam/analist akışı smoke, sonra gerçek artifact'la
işlem→ML alarmı→vaka→timeline. İlk smoke, yeni model demosunun tamamlandığı anlamına gelmez.
Fixture'lı Playwright testleri UI sözleşmesini doğrular; finalde en az bir gerçek
Docker/backend akışı da çalıştırılır.

## 6. Uygulama aşamaları ve geçiş kapıları

İşler aşağıdaki sırayla yürütülür. Bağımsız işler paralel başlayabilir; bağımlı işin
nihai kabulü önceki teslim doğrulandıktan sonra yapılır. Tarih netleştirme işi beklenmez.

| Aşama | Alper | Kişi A | Geçiş kapısı |
|---|---|---|---|
| 1 — Sözleşme ve temel | Ortak karar, ML-02, Docker ilk kontrolü | ML-01, SF-401/402, servis iskeleti | ADR, sözleşme, veri manifesti ve ortak fixture |
| 2 — Özellik ve hazırlık | ML-03; SF-405 fixture hazırlığı | ML-06 hazırlık, SF-404 iskelet, CI hazırlık | Parity/sızıntı testleri; eğitime hazır veri |
| 3 — Model teslimi | ML-04/05 | Servis loader/health testleri; artifact gelince ML-06 ve ML-07 kabulü | Değerlendirme raporu, yüklenebilir model, aynı sürümü kullanan servisler |
| 4 — Ürün entegrasyonu | SF-405 gerçek entegrasyon, SF-406 web tarafı | SF-404 gerçek akış, ML-08, SF-406 CI tarafı | UI ve uçtan uca testler; temiz çekirdek kurulum |
| 5 — Kapanış | SF-403 final demo ve belge; inceleme | ML-09, inceleme, CI/release doğrulama | §8 kapıları ve ortak demo tamam |

P2 işleri yalnız zorunlu işler tamamlandıktan sonra alınır. Veri sızıntısı, parity,
gerçek artifact entegrasyonu ve gerçek demo kapıları kapsam daraltılarak atlanmaz.

## 7. Dosya sahipliği ve PR sınırları

- Alper: dataset hazırlama/yükleme, ortak özellik modülleri, train/eval ve artifact
  paketleme, bunların testleri; data/model kartları ve raporlar; web ürün ekranları,
  demo dokümanı ve Docker/demo ayarları.
- A: model-serving/loader ve API, processor/detector, risk motoru, entegrasyon testleri,
  workflow'lar, release, Python bağımlılıkları, Playwright test/config, genel ML kılavuzu.
- `ml/**`, `tests/**`, `scripts/**`, `docs/**` topluca tek kişiye kapatılmaz; göreve ait
  somut dosya listesi PR açılmadan belirlenir. Önerilen yeni serving modülü A'nındır;
  ortak feature ve paketleme kodu Alper'indir.
- Playwright dosyaları web altında olsa da A yazar. `package*.json` ortak kesişiminde
  tek yazar Alper; A gereken test bağımlılıklarını bildirir. CI'yı A yazar.
- `api-schema.ts` A tarafından yalnız generator ile üretilir; Alper tüketir.
- ML-08 Alper'in aktif eğitim/özellik dosyalarını eşzamanlı düzenlemez; kaldırılacak
  dosyalar önce listelenir. `ml/__init__.py` gibi ortak girişler için tek yazar belirlenir.
- `origin/develop` CODEOWNERS iki kişiyi de içeriyor; bu inceleme kuralı dosya yazarlığı
  ile karıştırılmaz. Her PR diğer kişi tarafından incelenir.

Önerilen PR sırası: ortak ADR/sözleşme → Alper veri/özellik + A platform/servis hazırlığı
→ Alper model/artifact → A gerçek serving/CI → Alper model UI + A E2E → temizlik/docs/demo.
Her PR kendi ilgili testini taşır; tek büyük sprint PR'ı oluşturulmaz.

## 8. Sprint bitiş kapıları

- Veri ve model raporları yeniden üretilebilir; zaman bölmesi, leakage ve parity testleri yeşil.
- Sayısal model hedefleri sağlanmış; hedefler ve rapor aynı veri/sürümü tanımlıyor.
- API, detector ve risk motoru aynı model/feature sürümünü raporluyor; aynı feature
  girdisi aynı skoru veriyor. Yüklü model yoksa eğitilmemiş tahmin yapılmıyor.
- Gerçek alarm evidence'ında sürüm, skor, eşik ve anlamı tanımlanmış katkılar mevcut;
  UI bunları gerçek API'den gösteriyor.
- PostgreSQL concurrency testi, OpenAPI kontrolü ve ilgili kalite kapıları yeşil.
- En az 3 Playwright senaryosu; en az bir gerçek backend/Docker akışı ve belgeli demo.
- Çekirdek kurulum PyTorch gerektirmiyor; ML-08'in <500 satır şartı ve imaj boyutu raporu doğrulanmış.
- ML-07 hızlı mod gerçek model kalitesinin yerine geçmiyor: hızlı fixture smoke ile
  temsil edici veri üstündeki kalite değerlendirmesi ayrı raporlanıyor. Haftalık çalışma
  kilitli testle sürekli model seçimi yapmıyor; final test politikası korunuyor.

## 9. Issue eşlemesi ve revizyon kapsamı

Mevcut Sprint 4 milestone'u ve issue numaraları korunur; ikinci bir sprint açılmaz.

| Issue | Görev | Sorumlu |
|---|---|---|
| #16 | ML-01 ADR ve ortak sözleşme | A; karar ortak |
| #17 | ML-02 Veri hazırlama ve zaman bölmesi | Alper |
| #18 | ML-03 Ortak özellik motoru | Alper |
| #19 | ML-04 Eğitim ve değerlendirme | Alper |
| #20 | ML-05 Artifact ve model kartı | Alper |
| #21 | ML-06 Servis entegrasyonu | A |
| #22 | ML-07 Workflow | A |
| #23 | ML-08 Temizlik | A |
| #24 | ML-09 Dokümantasyon | A |

Revizyonla birincil veri kaynağı SAML-D olarak hizalanır. ML-05 paketlemeyi,
ML-06 servis yükleyicisini sahiplenir. ML-06 hazırlığı sözleşmeyle başlayabilir;
nihai kabul ML-05'e bağlıdır. ML-07 nihai kabul bağımlılığı ML-05 olarak korunur.
SF-404 A'ya, SF-403 demo dokümanı Alper'e aittir; SF-406 web/CI arasında paylaşılır.
Tamamlanmış işler yalnız test/teslim kanıtıyla işaretlenir.

## 10. A'nın servis/backend görevlerinin ayrıntılı kabulü

### ML-01 — Başlangıç kararı ve sözleşme

- A, ADR'yi ve §3 sözleşmesini yazar; Alper veri/model tarafını inceler.
- Model ailesi, ilk özellik kapsamı, veri erişimi/lisansı, artifact saklama yöntemi,
  hedef precision/recall ve eşik politikası bu görevin çıktısıdır. Bunlar planın
  tamamlanmasını bekleten sorular değil, ilk geliştirme görevinin kabul koşullarıdır.
- Kalite hedefleri veri dağılımı ve kullanım amacıyla gerekçelendirilir; test seti
  açılmadan kayda geçirilir. Eğitim smoke bütçesi ile tam eğitim bütçesi ayrı yazılır.
- Kabul: iki kişinin incelediği ADR ve örnek payload/metadata içeren sözleşme merge edilmiş.

### ML-06 — Ortak model servisi

- `FraudModelService` başlangıçta belirlenen artifact'ı yükler. API state, detector
  service ve risk motoru aynı uygulamayı ve aynı sürümlü paketi kullanır; farklı
  süreçlerin tek bir Python nesnesini paylaşması gerekmez.
- Loader checksum, model/özellik sürümü, özellik sırası ve gerekli metadata'yı
  doğrular. Geçersiz paket sessizce başka modele veya eğitilmemiş ensemble'a dönüşmez.
- Üç eski ensemble çağrısı ortak servise yönlendirilir; canlı trafikte kendiliğinden
  eğitim kaldırılır. Eski train endpoint'i kaldırılır/devre dışı bırakılır veya
  açıkça yetkilendirilmiş yeni akışa bağlanır; karar ve OpenAPI birlikte güncellenir.
- Açıklamalar gerçek model katkılarından üretilir. Katkı ölçeği (ör. log-odds),
  sıralama ve gösterilecek ilk N özellik sözleşmede yazılır; genel feature importance
  işlem özelindeki açıklama gibi sunulmaz.
- Kabul testleri: üç tüketicide sürüm eşitliği; aynı girdi/state ile skor eşitliği;
  bozuk/eksik/uyumsuz artifact; model yokken degraded; gerçek işlemden alarm evidence'ı.
- API yetkileri korunur; response değişiklikleri generator ile OpenAPI snapshot'ına işlenir.

### ML-07 — CI ve model kalite kapısı

- Workflow veri hazırlama, eğitim, değerlendirme ve paketleme için Alper'in tek
  giriş noktalarını çağırır; CI içine ikinci bir eğitim/özellik uygulaması yazılmaz.
- PR hızlı modunda deterministic veri fixture'ı, parity, paket round-trip ve smoke;
  model yayınlama kapısında temsil edici veriyle ADR hedefleri ve gerçek vektör gecikmesi.
- Haftalık tam çalışma için veri erişimi, cache, kaynak kimliği ve süre sınırı tanımlanır;
  kaynak yoksa başka veriyle başarılıymış gibi tamamlanmaz.
- Metrikler job özetine, rapor/model kartı/artifact sürümlü çıktıya yazılır. Hedef altı
  değerlendirme ile kapının kırmızı olduğu kontrollü bir testle gösterilir.
- Eski drift job'u yeni özelliklere uyarlanır veya gerekçesiyle devre dışı bırakılır;
  drift tetiklemeli otomatik eğitim bu sprintte eklenmez.

### ML-08/09 — Temizlik ve doğru dokümantasyon

- A, ML-06 sonrasında import/çağrı envanteri çıkarır; Alper yeni eğitim yolunun
  kullandığı dosyaları kontrol eder. Eski yarışma script'leri ve kullanılmayan ağır
  modüller kaldırılır veya çekirdekten bağımsız araştırma alanına taşınır.
- Python manifest/lockfile birlikte güncellenir; çekirdek kurulumda PyTorch bulunmaz.
  Kalan ML modülleri <500 satır kuralını sağlar; dosya bölme davranışı değiştirmez.
- Aynı build koşullarında Docker imaj boyutu önce/sonra ölçülür; temiz import,
  eğitim smoke, serving ve ilgili regression testleri geçer.
- `docs/ml/README.md` veri→özellik→model→artifact→servis akışını ve gerçek komutları
  anlatır. Eski ML/MLOps dokümanları ve README'deki ölçülmemiş iddialar düzeltilir.
- Kabul: diğer kişi dokümanı takip ederek eğitim, model yükleme ve skor üretimini
  tekrarlar; veri/model kartı ve raporlar doğru sürüme bağlıdır; changelog günceldir.

## 11. Platform, ürün ve demo görevlerinin ayrıntılı kabulü

### SF-401/402 — A: release ve PostgreSQL

- SF-401: mevcut planın `d8125d7` katkı commit'i ve `v2.2.0` release durumu önce
  kontrol edilir; zaten uygulanmış adımlar tekrarlanmaz. Eksikse develop/main
  eşitlemesi release PR'ıyla yapılır; paket/API sürümleri ve changelog tutarlı tutulur.
- `main`/`develop` için PR, bir karşı taraf onayı ve gerçek CI job adlarıyla gerekli
  kontroller etkin olmalıdır. Repository yetkisi yoksa ayarı yapacak yetkili ve
  uygulanacak kural listesi kaydedilir; aktif olmayan koruma tamamlandı sayılmaz.
- SF-402: geçici PostgreSQL üzerinde Alembic migration'ları ve birbirinden bağımsız
  transaction/session kullanan iki eşzamanlı istek test edilir. Sonuçta aynı alarm
  yalnız bir aktif vakaya bağlıdır; kaybeden isteğin hata/rollback davranışı tutarlıdır.

### SF-403 — Alper: Docker ve gerçek demo

- Postgres, Redis, Neo4j, Kafka, API ve web temiz kurulumla ayağa kaldırılır. Neo4j
  mimari sorunu önce yeniden üretilir; platform ayarı yalnız gerekli olduğunda yapılır.
- Admin seed adımı belgelenir; gerçek şifre repoya veya ekran görüntüsüne yazılmaz.
  Sabit demo giriş ipucu kaldırılır ya da gerçek geliştirme akışıyla uyumlu yapılır.
- İlk smoke mevcut analist akışını doğrular. Final smoke, ML-05/06 sonrası aynı
  artifact ile işlem→ML alarmı→vaka→timeline ve model açıklaması akışını doğrular.
- Demo işlemi, model sürümü ve beklenen sonuç tekrarlanabilir fixture olarak seçilir;
  gerçek modelin üretmediği alarm elle eklenerek ML demosu yapılmış sayılmaz.
- Kabul: `docs/SPRINT3_DEMO.md` kapanış adımları ve Sprint 4 ML demo adımları belgeli;
  diğer kişi temiz ortamda tekrar edebilir.

### SF-404 — A: tarayıcı testleri

- En az üç senaryo: başarılı login→alarm→vaka→timeline; viewer yazma yetkisi sınırı;
  model yok/hata durumunda doğru UI davranışı. Backend RBAC ayrıca API testleriyle korunur.
- Gerçek backend senaryosunda vaka durumu değiştirilir ve timeline olayı doğrulanır.
  Test verisi deterministik hazırlanır/temizlenir; başka testlerin verisine güvenilmez.
- Fixture testleri hızlı koşabilir; en az bir gerçek Docker/backend akışı CI'da
  çalışır. Hatalı koşuda trace/screenshot/log çıktıları teşhis için saklanır.
- Kabul: ilgili UI testleri ve gerçek akış yeşil; CI job'u başarısızlığı gizlemez.

### SF-405 — Alper: model ve açıklama ekranı

- Alarm detayında alarm üretildiği andaki `model_version`, skor, eşik ve top katkılar
  evidence'tan gösterilir. Bugünkü aktif model bilgisi eski alarmın yerine yazılmaz.
- Sistem/model alanında gerçek aktif model kartı özeti, eğitim zamanı, veri kimliği
  ve değerlendirme metrikleri gösterilir. Sıfır değer ile eksik değer ayrılır.
- Loading, empty, API error, model yok ve eski alarmda metadata yok durumları test edilir.
  Tarihler kullanıcı yerelinde, API timestamp'leri UTC sözleşmesiyle tutarlıdır.
- UI önce ortak fixture ile geliştirilir; gerçek OpenAPI ve backend yanıtıyla son
  entegrasyon yapılmadan iş kapanmaz. SF-408'deki ayrı dashboard kapsamı eklenmez.

### SF-406 — Ortak: Node sürüm tutarlılığı

- Alper web Dockerfile/package/lock ve yerel geliştirme dokümanını, A CI runtime'ını
  aynı desteklenen Node 22 çizgisine hizalar; mevcut durum uygunsa doğrulama yeterlidir.
- Kabul: temiz bağımlılık kurulumu, lint, TypeScript, unit test, production build
  ve Playwright aynı runtime çizgisinde çalışır.

## 12. Teslim paketi ve çalışma kuralları

| Teslim | Üreten | Devralan / doğrulayan |
|---|---|---|
| ADR ve API/artifact sözleşmesi | A | Alper |
| Kaynak/dönüşüm manifesti, split tanımı, veri kartı | Alper | A |
| Ortak feature kodu, sürümü ve parity fixture'ı | Alper | A |
| Eğitim/eval CLI, rapor, artifact, checksum ve model kartı | Alper | A: gerçek loader ile yükler |
| Servis entegrasyonu ve üretilmiş OpenAPI | A | Alper: gerçek UI entegrasyonu |
| Workflow, test sonuçları ve imaj boyutu raporu | A | Alper |
| Model ekranı ve demo belgesi | Alper | A: Playwright ve tekrar demo |
| Genel kullanım kılavuzu ve changelog | A | Alper |

- Her kişi güncel `origin/develop` tabanlı ayrı worktree/konu branch'inde çalışır.
  Branch örnekleri: `codex/s4-b-ml-data`, `codex/s4-b-ml-features`,
  `codex/s4-b-ml-model`, `codex/s4-a-ml-serving`, `codex/s4-a-e2e`.
- Başlangıçta çalışma ağacı/HEAD kontrol edilir, mevcut kullanıcı değişiklikleri korunur.
  Bağımlı PR merge edilince branch sahibi güncel develop'u alır ve ilgili kontrolleri tekrarlar.
- Sözleşme değişikliği gerekiyorsa sahibi örnek payload ve etkiyle CONTRACT-REQUEST
  açar; diğer alanın dosyalarını habersiz değiştirmez. Onaylı sözleşme birlikte güncellenir.
- Python için ilgili lint/type/test kapıları; web için lint/type/unit/build;
  entegrasyon için PostgreSQL, OpenAPI, parity ve E2E kontrolleri uygulanır.
- Her PR: bağlı iş ID'si, teslim, test kanıtı, model/API sürüm etkisi ve kalan
  bağımlılığı içerir. Model PR'ı değerlendirme raporunu da içerir.
- Sprint ancak §8 kapıları tamamlandığında kapanır; fixture'ın çalışması gerçek
  model entegrasyonunun veya gerçek backend demosunun yerine geçmez.

## 13. Sprint dışında

- GNN, sequence/temporal modeller ve federated learning'i yeniden etkinleştirme.
- Canlı trafikte eğitim, otomatik drift tetiklemeli retraining ve production Kubernetes.
- STR/MASAK raporlama, yeni tasarım sistemi veya kapsamlı dashboard yenilemesi.
- Eğitim veri setini sırf model eğitimi için üretim işlem tablosuna aktarma veya yeni
  veri tabanı şeması kurma; gerekli veri yükleme/dönüşüm bu sprintte offline kalır.
- P2 SF-407/408, zorunlu teslimlerin kabulünü etkilemez.
