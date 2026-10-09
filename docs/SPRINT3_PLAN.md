# Sprint 3 Planı — Güvenilir Analist Vaka Akışı

**Tarih:** 12–23 Ekim 2026 (10 iş günü)  
**Ekip:** 2 geliştirici  
**Plan tabanı:** `origin/develop` / `6e68986`  
**Sprint teması:** Stabilizasyon + alarmdan vakaya uçtan uca analist iş akışı

## 1. Sprint hedefi

Sprint sonunda bir analist:

1. JWT ile giriş yapabilmeli,
2. yetkisine uygun biçimde alarmları listeleyip inceleyebilmeli,
3. bir alarmı yeni veya mevcut vakaya bağlayabilmeli,
4. vaka detayında durum, atama ve not işlemlerini yapabilmeli,
5. tüm değişiklikleri zaman çizelgesi/audit geçmişinde görebilmeli.

Bu akış backend, frontend ve entegrasyon testleriyle doğrulanmalı; `develop` dalındaki
CI/CD ve ML Pipeline kontrolleri tamamen yeşil olmalıdır.

## 2. Neden bu hedef?

Güncel depo incelemesinde:

- `develop`, `main` dalından ileride ve çalışan çekirdek özellikleri koruyup bağlı
  olmayan modülleri yeniden geliştirilmek üzere park etmiş durumda.
- Son CI çalışmasında unit, integration, frontend ve ML model testleri başarılı;
  güvenlik taraması bağımlılık açıkları nedeniyle başarısız.
- ML Pipeline, veri üreticisinin artık sağlamadığı `user_id` kolonunu beklediği için
  veri doğrulama adımında başarısız.
- Backend veri rotaları JWT/RBAC korumalı olmasına rağmen Alerts ve Cases sayfaları
  doğrudan `fetch` kullanıyor; mevcut `fetchWithAuth` istemcisi bu akışlara bağlı değil.
- Backend'de vaka olayları endpoint'i hazır, fakat frontend'de vaka detay/audit
  timeline ekranı yok.
- Alerts ekranındaki **Vaka Oluştur** düğmesi işlevsiz.
- İlk modülerleştirme tamamlanmış olsa da birçok kaynak dosya hâlâ 500 satırın üzerinde.

Bu nedenle sprint, yeni ve bağımsız bir özellik yığını eklemek yerine mevcut ürünün
en değerli yarım kalmış kullanıcı akışını çalışır hale getirir.

## 3. Kapasite ve çalışma modeli

- Toplam teorik kapasite: `2 kişi × 10 gün = 20 kişi-gün`.
- Planlanan geliştirme kapasitesi: 16 kişi-gün.
- Tampon: 4 kişi-gün; inceleme, entegrasyon, beklenmeyen CI ve bağımlılık işleri.
- Her iş tek sahibinde kalır; diğer kişi PR inceleyicisidir.
- Aynı dosyada eş zamanlı çalışma yapılmaz.
- Kişi A ve Kişi B aynı checkout üzerinde çalışmaz; her biri ayrı Git worktree ve
  ayrı branch kullanır.
- Coding agent'a görev verilirken bu doküman, kişinin rolü, izinli dosya alanı ve
  yasaklı dosya alanı prompt içinde açıkça belirtilir.
- Küçük ve bağımsız PR'lar tercih edilir; hedef PR başına en fazla yaklaşık 400 net satırdır.

## 4. Konu bazlı iş bölümü

### Kişi A — Platform, backend ve API sözleşmesi

Sahip olduğu alanlar:

- `.github/workflows/`
- `pyproject.toml`
- `src/sentinelflow/api/`
- `src/sentinelflow/auth/`
- `src/sentinelflow/repository/`
- `src/sentinelflow/database/`
- `tests/`
- `sentinelflow-web/src/lib/api-schema.ts` üretimi

Ana sorumluluğu: CI kapılarını düzeltmek, vaka API'sini atomik ve tipli hale
getirmek, RBAC ve audit kayıtlarını backend testleriyle güvenceye almak.

### Kişi B — Frontend, kullanıcı akışı ve tarayıcı testleri

Sahip olduğu alanlar:

- `sentinelflow-web/src/app/`
- `sentinelflow-web/src/components/`
- `sentinelflow-web/src/contexts/`
- `sentinelflow-web/src/hooks/`
- `sentinelflow-web/src/lib/auth.ts`
- yeni frontend test dosyaları ve test konfigürasyonu

Ana sorumluluğu: tüm korumalı istekleri ortak auth istemcisine geçirmek, alarmdan
vakaya akışı ve vaka audit timeline ekranını tamamlamak, kullanıcı durumlarını
test etmek.

### Ortak fakat tek yazarlı dosyalar

| Dosya/alan | Sprint sahibi | Kural |
|---|---|---|
| `sentinelflow-web/src/lib/config.ts` | Kişi B | Endpoint isimlerini Kişi A ile sözleşme görüşmesinden sonra ekler. |
| `sentinelflow-web/src/lib/api-schema.ts` | Kişi A | Yalnızca generator ile güncellenir; elle düzenlenmez. |
| `CHANGELOG.md`, `README.md`, `docs/` | Entegrasyon gününde Kişi A | Kişi B değişiklik notlarını PR açıklamasına yazar. |
| `package.json`, `package-lock.json` | Kişi B | Mevcut kullanıcı değişikliği ayrıştırılmadan üzerine yazılmaz. |

### Kesin çalışma sınırları

İki coding agent aynı anda çalışırken aşağıdaki sınırlar zorunludur:

| Alan | Yazma yetkisi | Diğer kişinin davranışı |
|---|---|---|
| `.github/workflows/**`, `pyproject.toml` | Yalnızca Kişi A | Sadece okuyabilir; değişiklik isteğini Kişi A'ya iletir. |
| `src/sentinelflow/**`, `tests/**`, `alembic/**` | Yalnızca Kişi A | Backend dosyasına geçici/mock düzeltme commit etmez. |
| `sentinelflow-web/src/app/**`, `components/**`, `contexts/**`, `hooks/**` | Yalnızca Kişi B | Sadece okuyabilir. |
| `sentinelflow-web/src/lib/auth.ts`, `config.ts` | Yalnızca Kişi B | Endpoint ihtiyacını sözleşme notuyla bildirir. |
| `sentinelflow-web/src/lib/api-schema.ts` | Yalnızca Kişi A | Elle düzenlemez; üretilen değişikliği kendi branch'ine entegrasyon sırasında alır. |
| `sentinelflow-web/package*.json` | Yalnızca Kişi B | Kişi A frontend bağımlılığı eklemez. |
| `README.md`, `CHANGELOG.md`, `docs/**` | Sprint boyunca plan dosyası hariç Kişi A | Kişi B doküman girdisini PR açıklamasına yazar. |

Bir görev bu sınırı aşmayı gerektirirse agent kendiliğinden diğer alana girmez. İhtiyacı
`CONTRACT-REQUEST` başlığıyla kısa bir not olarak bildirir ve kendi alanında fixture,
interface veya adapter üzerinden ilerler.

## 5. Sprint backlog'u

### P0 — Önce çözülmesi gereken kapılar

#### SF-301 — ML Pipeline veri sözleşmesini düzelt (Kişi A, 0.5 gün)

İş:

- Workflow doğrulamasını gerçek veri sözleşmesine uyarla (`sender_iban` /
  `receiver_iban`; artık üretilmeyen `user_id` değil).
- Kolon adlarını tek bir sabit veya şema kaynağından kontrol et.
- Yanlış kolon, dtype ve boş veri durumları için hızlı test ekle.

Kabul kriterleri:

- Data Validation işi geçer.
- Üretilen örnekte işlem kimliği, gönderen/alıcı IBAN, tutar, zaman ve fraud etiketi
  doğrulanır.
- Şema değişirse test anlamlı bir hata mesajıyla kırılır.

#### SF-302 — Güvenlik taramasını gerçekten yeşile getir (Kişi A, 1.5 gün)

İş:

- `pip-audit` bulgularını sınıflandır; `python-jose`/`ecdsa` zincirini aktif
  bakımı olan bir JWT kütüphanesine taşı.
- Düzeltilebilir transitif açıklar için minimum güvenli sürümleri tanımla.
- Auth testlerini token üretme, doğrulama, süre aşımı, bozuk imza ve refresh akışı
  için çalıştır.
- İstisna gerekirse yalnızca CVE kimliği, gerekçe ve son kullanma tarihi olan
  dar kapsamlı bir kayıt kullan; genel `continue-on-error` ekleme.

Kabul kriterleri:

- Security Scan işi geçer.
- JWT/RBAC davranışı değişmez.
- Audit çıktısında açıklanmamış açık kalmaz.

#### SF-303 — Frontend auth taşıma katmanı (Kişi B, 1.5 gün)

İş:

- Alerts, Cases, Dashboard, Graph ve Chat içindeki korumalı REST çağrılarını ortak
  istemci üzerinden geçir.
- Tek seferlik refresh + yeniden deneme davranışını koru; ikinci 401'de oturumu
  temizleyip login'e yönlendir.
- Loading, 401/403, ağ hatası ve boş sonuç durumlarını kullanıcıya göster.
- Geliştirme varsayılanını backend'in güvenlik modeliyle uyumlu hale getir; auth'u
  sessizce kapatan varsayılan bırakma.

Kabul kriterleri:

- Korumalı endpoint'lere çıplak `fetch` kalmaz.
- Viewer yazma işlemi göremez veya tetikleyemez; Analyst gerekli aksiyonları görür.
- Token yenileme döngüye girmez.

### P1 — Sprintin ürün çıktısı

#### SF-304 — Vaka API sözleşmesini tamamla (Kişi A, 2 gün)

İş:

- Vaka oluşturma ve alarma bağlama işlemini tek, atomik servis akışı olarak tanımla.
- Case event listesi için sözlük yerine Pydantic response modelleri kullan.
- Event actor, tür, zaman, açıklama ve ilgili alert alanlarını sözleşmede netleştir.
- Geçersiz durum geçişi, bulunamayan alarm/vaka, çift bağlama ve transaction rollback
  senaryolarını ele al.
- Viewer/Analyst/Admin yetki matrisini API testleriyle sabitle.
- OpenAPI snapshot'ını generator ile yenile.

Kabul kriterleri:

- Tek istekle alarmdan vaka oluşturulabilir ve `case_created` + `alert_linked`
  olayları yazılır.
- Kısmi hata durumunda vaka, alert ve event verileri yarım kalmaz.
- Aynı alarm iki aktif vakaya bağlanamaz.
- API sözleşme kontrolü geçer.

#### SF-305 — Alarmdan vakaya kullanıcı akışı (Kişi B, 2 gün)

İş:

- İşlevsiz **Vaka Oluştur** düğmesini gerçek API'ye bağla.
- Yeni vaka oluşturma ve mevcut vakaya bağlama seçeneklerini sun.
- Başarı sonrası alert state'ini güncelle ve vaka detayına geçiş ver.
- 409/422/403 ve ağ hatalarını anlaşılır mesajlarla göster.
- Yalnızca Analyst/Admin rollerine yazma aksiyonlarını göster.

Kabul kriterleri:

- Bir alert yeni vakaya veya seçilen mevcut vakaya bağlanabilir.
- Çift tıklama/tekrar gönderim duplicate vaka üretmez.
- Başarı ve hata durumları testlidir.

#### SF-306 — Vaka detay ve audit timeline ekranı (Kişi B, 2.5 gün)

İş:

- `/cases/[case_id]` detay sayfası oluştur.
- Vaka özeti, bağlı alarmlar, atanan kişi/takım, durum, öncelik ve SLA bilgisini göster.
- `/cases/{case_id}/events` verisini zaman çizelgesi olarak göster; sayfalama ve
  event type filtresi ekle.
- Analyst/Admin için durum değiştirme, atama ve not ekleme aksiyonlarını bağla.
- Mobil/dar ekran ve loading/empty/error durumlarını kapsa.

Kabul kriterleri:

- Liste satırından vaka detayına gidilebilir.
- Her mutasyon sonrasında timeline yeni olayı yeniden yükler.
- Viewer ekranı salt okunurdur.
- Tarihler Europe/Istanbul kullanıcı yerelinde tutarlı gösterilir; API UTC tutar.

#### SF-307 — Backend vaka/audit testleri (Kişi A, 1.5 gün)

İş:

- Repository ve route seviyesinde başarılı akış, rollback, pagination ve RBAC
  senaryolarını test et.
- Case event sıralamasını ve filtrelemeyi doğrula.
- OpenAPI response şemalarının testini ekle.

Kabul kriterleri:

- Yeni backend davranışlarının branch coverage'ı en az %80'dir.
- Global coverage mevcut %45 kapısının altına düşmez.
- Testler dış servislere ihtiyaç duymadan unit seviyesinde çalışır; gerçek PostgreSQL
  gerektiren senaryolar integration marker kullanır.

#### SF-308 — Frontend test temeli ve kritik akış testleri (Kişi B, 1.5 gün)

İş:

- Hafif bir test koşucusu ve DOM test altyapısı ekle.
- Auth refresh, role görünürlüğü, vaka oluşturma ve audit timeline durumlarını test et.
- Network cevaplarını deterministik mock'la; gerçek backend'e bağımlı frontend unit
  testi oluşturma.

Kabul kriterleri:

- `npm test` CI'da çalışır.
- En az auth istemcisi ve iki kritik kullanıcı akışı testlidir.
- `npm run lint`, `tsc --noEmit`, test ve production build geçer.

### P2 — Kapasite kalırsa

#### SF-309 — Modülerleştirme Faz 2 (Kişi A, en fazla 1 gün)

Yalnızca P0 ve P1 tamamlandıysa `api/app.py` içindeki router/websocket/lifecycle
sorumluluklarını ayır. Bu sprintte geniş ML/MLOps dosyalarına girme; bunlar ayrı bir
teknik sprint olarak planlanmalı.

Kabul kriterleri:

- Her yeni elle yazılmış modül 500 satırın altında.
- Public import yolları ve OpenAPI çıktısı korunur.

#### SF-310 — Erişilebilirlik ve küçük ekran düzeltmeleri (Kişi B, en fazla 1 gün)

Form label'ları, klavye odağı, modal focus trap, buton disabled durumları ve dar ekran
timeline düzeni iyileştirilir.

## 6. Günlere göre paralel çalışma planı

| Gün | Kişi A | Kişi B | Ortak çıktı |
|---|---|---|---|
| 1 — Pzt 12 Eki | SF-301; güvenlik bulgularını kesinleştir | SF-303 için korumalı çağrı envanteri ve test altyapısı spike | 45 dk API sözleşme toplantısı; endpoint/payload kararları |
| 2 — Sal 13 Eki | SF-302 JWT bağımlılık geçişi | SF-303 ortak auth istemcisi ve hata modeli | P0 PR'ları karşılıklı inceleme |
| 3 — Çar 14 Eki | SF-302 testleri ve Security Scan | Alerts/Cases auth taşıması, role guard'ları | P0 tamam; CI ara kapısı tamamen yeşil |
| 4 — Per 15 Eki | SF-304 response modelleri ve servis sınırı | SF-305 yeni/mevcut vaka UX'i | Öğlen payload örnekleriyle contract check |
| 5 — Cum 16 Eki | SF-304 atomik işlem/rollback | SF-305 API entegrasyonu ve durumlar | İlk demo: login → alert → case |
| 6 — Pzt 19 Eki | SF-307 route/repository testleri | SF-306 vaka detay iskeleti ve veri yükleme | OpenAPI snapshot dondurulur |
| 7 — Sal 20 Eki | SF-307 RBAC, pagination, event tests | SF-306 timeline + filtre + aksiyonlar | Karşılıklı PR inceleme |
| 8 — Çar 21 Eki | Entegrasyon kusurları; schema sahibi | SF-308 frontend akış testleri | Tam uçtan uca demo provası |
| 9 — Per 22 Eki | P2 SF-309 veya hata düzeltme | P2 SF-310 veya hata düzeltme | Regression, Docker smoke, dokümantasyon |
| 10 — Cum 23 Eki | Release adayı ve değişiklik notu | UX son kontrol ve demo verisi | CI yeşil, sprint demo, retro |

## 7. Bağımlılık sırası

```text
SF-301 ─┐
        ├──> CI yeşil ara kapısı
SF-302 ─┘

SF-303 ───────────────> SF-305 ───────┐
                                      ├──> Uçtan uca analist akışı
SF-304 ─> SF-307 ─────> SF-306 ───────┘

SF-308, SF-305 ve SF-306 ile paralel ilerler.
SF-309/SF-310 yalnızca bütün P0 ve P1 işler bittikten sonra başlar.
```

## 8. Branch ve birleşme düzeni

### Ayrı çalışma alanları

Sprint başında tek bir kişi `origin/develop` dalını günceller ve iki bağımsız worktree
oluşturur. Her iki branch de aynı commit'ten başlamalıdır:

```bash
git fetch origin
git worktree add ../sentinelflow-s3-a -b codex/s3-a-ci-security origin/develop
git worktree add ../sentinelflow-s3-b -b codex/s3-b-auth-client origin/develop
```

- Kişi A yalnızca `sentinelflow-s3-a` worktree'sinde çalışır.
- Kişi B yalnızca `sentinelflow-s3-b` worktree'sinde çalışır.
- Agent'lar ana checkout'a veya birbirlerinin worktree'sine yazmaz.
- Sprint başlangıcında var olan uncommitted değişiklikler worktree'lere taşınmaz.
- Her agent işe başlamadan `git status --short --branch` ve `git rev-parse HEAD`
  çıktısını kaydeder.
- İlk PR birleşince aynı worktree içinde güncel `origin/develop` tabanlı bir sonraki
  konu branch'ine geçilir; worktree başına aynı anda yalnızca bir aktif görev bulunur.

### Branch/PR dilimleri

Uzun süre yaşayan tek bir büyük branch yerine aşağıdaki sırayla küçük branch/PR'lar
kullanılır:

| Sıra | Branch | Sahip | İçerik | Birleşme önkoşulu |
|---|---|---|---|---|
| 1 | `codex/s3-a-ci-security` | A | SF-301, SF-302 | Python testleri + iki CI workflow'u |
| 2 | `codex/s3-b-auth-client` | B | SF-303 | Frontend lint/type/test/build |
| 3 | `codex/s3-a-case-api` | A | SF-304, SF-307 | API tests + OpenAPI check |
| 4 | `codex/s3-b-case-ui` | B | SF-305, SF-306, SF-308 | A'nın case API PR'ı birleştikten sonra güncel `develop` üzerine rebase |
| 5 | `codex/s3-integration` | A | Yalnız entegrasyon kusurları ve docs | Tüm P0/P1 PR'ları birleşmiş olmalı |

Kişi A ve B'nin P0 branch'leri paralel ilerleyebilir. Case API ve Case UI geliştirmesi
de paralel başlayabilir; ancak UI branch'i merge edilmeden önce güncel `develop`
üzerine alınmalı ve üretilmiş API sözleşmesiyle yeniden doğrulanmalıdır.

### API sözleşmesi el sıkışması

Kişi A, SF-304 kodlamasına başlamadan aşağıdakileri küçük bir sözleşme notunda sabitler:

- endpoint ve HTTP method,
- request/response JSON örnekleri,
- status code'lar (`200/201/403/404/409/422`),
- enum değerleri,
- idempotency/duplicate davranışı,
- event sıralaması ve tarih formatı.

Kişi B bu sözleşmeye göre frontend fixture'ı oluşturur. Backend PR'ı birleşince Kişi A
OpenAPI snapshot'ını üretir; Kişi B branch'ini günceller ve fixture ile gerçek şema
arasındaki farkı kaldırır. `api-schema.ts` üzerinde iki taraflı manuel düzenleme yapılmaz.

### Commit kuralları

- Her commit tek amaçlı ve çalışır durumda olmalıdır.
- Conventional Commits kullanılır: `fix(ci): ...`, `fix(auth): ...`,
  `feat(cases): ...`, `test(cases): ...`, `feat(web): ...`.
- Agent her commit öncesi yalnızca kendi değişikliklerini stage eder; `git add .` veya
  `git add -A` kullanmaz.
- Başkasına ait değişikliği amend, revert, reset veya format etmez.
- Generated dosya, onu üreten kaynak değişiklikle aynı commit'te yer alır.
- Dependency manifest ve lockfile aynı commit'te olmalıdır.
- Sırf çakışmayı azaltmak için testleri sonraki toplu commit'e bırakma; davranış ve
  ilgili test mümkünse aynı commit'te olmalıdır.
- Önerilen commit akışı:

```text
Kişi A
fix(ml-ci): align dataset validation with transaction schema
fix(auth): replace vulnerable jwt dependency
feat(cases): add atomic alert-to-case workflow
test(cases): cover audit events rollback and rbac

Kişi B
fix(web-auth): route protected requests through auth client
feat(web-cases): connect alert to case workflow
feat(web-cases): add case detail audit timeline
test(web): cover auth refresh and case workflows
```

### Günlük senkronizasyon ve çakışma önleme

- Her sabah iki kişi son birleşmiş `origin/develop` commit'ini paylaşır.
- Açık PR varken diğer kişinin branch'i doğrudan cherry-pick edilmez; ihtiyaç varsa
  sözleşme fixture'ı kullanılır.
- Bir PR birleşince, ona bağımlı branch sahibi `git fetch origin` sonrası kendi
  branch'ini `origin/develop` üzerine rebase eder ve tüm kalite kapılarını yeniden çalıştırır.
- Rebase yalnızca branch sahibi tarafından yapılır; coding agent diğer kişinin
  branch history'sini force-push etmez.
- Aynı dosyada beklenmedik ihtiyaç oluşursa iş durdurulur, dosya için tek sahip
  belirlenir ve diğer taraf adapter/fixture üzerinden bekler.
- Her PR diğer kişi tarafından incelenir. Büyük refactor ile davranış değişikliği aynı
  PR'a konmaz.

## 9. Coding agent çalışma protokolü

Her coding agent'a görev başlamadan aşağıdaki ortak talimat verilmelidir:

```text
Bu sprintte iki coding agent paralel çalışıyor. Yalnızca sana atanan worktree,
branch ve dosya alanlarında değişiklik yap. İşe başlamadan git status ve HEAD'i
kontrol et. Kullanıcıya veya diğer agente ait mevcut değişiklikleri koru.

Diğer kişinin sahip olduğu dosyalara yazma, onları formatlama, stage etme, amend
veya revert etme. Alanın dışında değişiklik gerekiyorsa kodlama; CONTRACT-REQUEST
olarak endpoint/payload/dosya ihtiyacını bildir ve kendi tarafında fixture veya
adapter ile ilerle.

Her commit tek amaçlı olsun. Sadece ilgili dosyaları açık isimleriyle stage et;
git add . kullanma. Commit öncesinde rolüne ait testleri çalıştır. Commit SHA'sını,
değişen dosyaları ve test sonucunu raporla. Push veya merge yetkin ayrıca
verilmediyse yalnızca yerel commit oluştur.
```

### Kişi A coding agent başlangıç prompt'u

```text
Rolün: Sprint 3 Kişi A — platform, backend ve API sözleşmesi.
Başlangıç dalın: origin/develop. Ayrı worktree/branch: codex/s3-a-<konu>.
Plan: docs/SPRINT3_PLAN.md; önce tamamen oku.

Yazabileceğin alanlar: .github/workflows/**, pyproject.toml,
src/sentinelflow/**, tests/**, alembic/** ve generator ile üretilen
sentinelflow-web/src/lib/api-schema.ts.

Yazamayacağın alanlar: sentinelflow-web/src/app/**, components/**, contexts/**,
hooks/**, lib/auth.ts, lib/config.ts ve package*.json.

Frontend ihtiyacı doğarsa frontend kodunu değiştirme; CONTRACT-REQUEST bırak.
Önce P0 CI/security işlerini bitir, sonra vaka API ve audit testlerine geç.
OpenAPI dosyasını elle düzenleme. Her davranış değişikliğini testiyle commit et.
```

### Kişi B coding agent başlangıç prompt'u

```text
Rolün: Sprint 3 Kişi B — frontend auth ve analist vaka kullanıcı akışı.
Başlangıç dalın: origin/develop. Ayrı worktree/branch: codex/s3-b-<konu>.
Plan: docs/SPRINT3_PLAN.md; önce tamamen oku.

Yazabileceğin alanlar: sentinelflow-web/src/app/**, components/**, contexts/**,
hooks/**, lib/auth.ts, lib/config.ts, frontend testleri ve package*.json.

Yazamayacağın alanlar: src/sentinelflow/**, tests/**, alembic/**,
.github/workflows/**, pyproject.toml ve lib/api-schema.ts.

Backend eksikse backend'e geçici route ekleme; CONTRACT-REQUEST bırak ve üzerinde
anlaşılan JSON fixture/interface ile ilerle. Mevcut package-lock değişikliğini
ezme. Önce ortak auth istemcisini tamamla, sonra alarmdan vakaya ve audit timeline
akışına geç. Her kullanıcı davranışını ilgili frontend testiyle commit et.
```

### Agent görev bitiş raporu

Her agent her PR/iş dilimi sonunda şu formatta rapor verir:

```text
Branch / HEAD:
Tamamlanan iş:
Değişen dosyalar:
Oluşturulan commit(ler):
Çalıştırılan testler ve sonuçları:
API/şema etkisi:
CONTRACT-REQUEST veya kalan bağımlılık:
Diğer agentın rebase etmesi gereken commit/PR:
```

## 10. Definition of Done

Bir iş ancak aşağıdakilerin tamamı sağlandığında biter:

- Kabul kriterleri otomatik testlerle veya tekrarlanabilir smoke adımıyla kanıtlandı.
- Python: Black, Ruff, MyPy ve ilgili Pytest paketleri geçti.
- Frontend: ESLint, TypeScript, testler ve production build geçti.
- API değiştiyse OpenAPI snapshot güncel.
- RBAC ve hata durumları test edildi; secret veya kişisel veri loglanmıyor.
- Kullanıcıya görünen loading, empty, success ve error durumları mevcut.
- Dokümantasyon/davranış farkı varsa README veya ilgili docs güncellendi.
- PR küçük, tek konulu ve diğer ekip üyesi tarafından incelenmiş.

## 11. Sprint başarı ölçütleri

- GitHub'da CI/CD Pipeline ve ML Pipeline tamamen yeşil.
- Açıklanmamış `pip-audit` bulgusu yok.
- Alarmdan vaka oluşturma ve vaka timeline görüntüleme demo edilebilir.
- Korumalı frontend REST çağrılarının %100'ü ortak auth istemcisinden geçer.
- Yeni vaka/audit backend kodunda en az %80 branch coverage.
- En az 4 kritik frontend senaryosu otomatik testlidir.
- Sprintte eklenen elle yazılmış yeni dosyaların hiçbiri 500 satırı aşmaz.

## 12. Bilinçli olarak sprint dışında

- Park edilmiş compliance/MASAK motorunun tamamını geri getirmek.
- E-posta/SMS bildirim altyapısı.
- Kubernetes/production deployment.
- GNN, federated learning veya geniş MLOps yeniden yazımı.
- Tüm 500+ satırlık ML dosyalarını aynı sprintte bölmek.
- Yeni tasarım sistemi veya landing page yenilemesi.

Bu konular değerli olsa da iki kişilik sprintte analist akışını ve stabilizasyonu
riske atar. Bir sonraki sprint için önerilen tema, çalışan vaka/audit verisi üzerine
**STR/MASAK raporlama** veya ayrı bir **ML/MLOps modülerleştirme** sprintidir.
