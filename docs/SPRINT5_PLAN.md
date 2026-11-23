# Sprint 5 Planı — Yerel demo (Docker Compose + Tailscale Funnel) ve web özellikleri

**Tarih:** 23 Kasım – 11 Aralık 2026 (15 iş günü, öneri)
**Sorumlu:** Yusuf Eren Bozkurt (GitHub: `YusuffEren`)
**İnceleme:** Buğra Uzun (@uzunbugra), Alper Tekin (@alper-tekin)
**Plan tabanı:** `v2.3.0` (`main` @ `6fea58f`, 20 Kasım 2026)
**Sprint teması:** SentinelFlow'u mevcut Docker Compose kurulumuyla geliştiricinin bilgisayarında
çalıştırıp gerektiğinde Tailscale Funnel ile geçici bir HTTPS adresinden paylaşmak ve API'de olup
web'de arayüzü bulunmayan özellikleri web uygulamasına eklemek

> **Güncel durum (23 Kasım 2026):** Demo ortamı için **Oracle Cloud kullanılmıyor.** Ekip,
> uygulamayı geliştiricinin bilgisayarında Docker Compose ile çalıştırıp hocalarla
> [Tailscale Funnel](DEMO_TAILSCALE.md) üzerinden paylaşmaya karar verdi. Kararın gerekçesi
> ve her işin yeni durumu §12'dedir. Aşağıda Oracle'a özgü bölümler (§2'deki makine notları,
> §4'teki makine ve hesap kararları, SF-501/502/511/512, §10'daki Oracle riskleri) kayıt için
> korunmuştur ve **artık geçerli değildir**; her birinin başında bu belirtilir.

Bu belge çalışma kapsamını tanımlar; işlerin yapıldığını göstermez. Süreler kişi-gün
tahminidir.

## 1. Sprint hedefi

**Güncel hedefler (§12, Tailscale Funnel):**

1. `.\scripts\funnel.ps1` tek komutla yığını başlatır ve
   `https://<makine>.<tailnet>.ts.net` adresi geçerli sertifikayla açılır.
2. Demo hesabıyla giriş yapılır; alarm listesi, alarm detayındaki model açıklaması, alarmdan
   vaka oluşturma ve vaka zaman çizelgesi Funnel adresinde çalışır.
3. `GET /api/v1/ml/models` `status: loaded` ve `fraud-lgbm-20261030-0e0c647` döner.
4. Dışarıya yalnız Funnel'ın yönlendirdiği yerel ters vekil (127.0.0.1:8088) açılır;
   veritabanları ve yönetim arayüzleri yalnız `127.0.0.1`'de dinler, `/metrics`, `/docs` ve
   kayıt dışarıdan reddedilir.
5. Başlatma, hesap açma, kapatma ve sorun giderme adımları `docs/DEMO_TAILSCALE.md`'de
   yazılıdır ve ekipten ikinci bir kişi bu belgeyi takip edebilir.
6. Web uygulamasında işlem skorlama, müşteri taraması, demo işlem gönderme, parola
   değiştirme ve ağ grafiği ekranları Funnel adresinde çalışır.

<details>
<summary>İlk plan: Oracle Cloud hedefleri (artık geçerli değil)</summary>

1. `https://<alan-adı>` adresinde geçerli bir sertifikayla web uygulaması açılır.
2. Demo hesabıyla giriş yapılır; alarm listesi, alarm detayındaki model açıklaması, alarmdan
   vaka oluşturma ve vaka zaman çizelgesi canlıda çalışır.
3. `GET /api/v1/ml/models` canlıda `status: loaded` ve `fraud-lgbm-20261030-0e0c647` döner.
4. Makinede dışarıya yalnız 22 (SSH), 80 ve 443 portları açıktır; veritabanları ve yönetim
   arayüzleri internetten erişilemez.
5. Kurulum, güncelleme, yedekten geri dönme ve sürüm geri alma adımları bir runbook'ta
   yazılıdır ve ekipten ikinci bir kişi bu belgeyi takip edebilir.
6. Web uygulamasında işlem skorlama, müşteri taraması, demo işlem gönderme ve parola
   değiştirme ekranları çalışır; ağ grafiği ve para halkaları sayfası en az yerelde,
   Neo4j canlıya alındıysa canlıda çalışır.

</details>

## 2. Neden bu hedef ve mevcut durum

v2.3.0 ile Sprint 4 kapandı; sistem şu an yalnız geliştiricilerin bilgisayarlarında Docker
Compose ile çalışıyor. Canlı bir adres hem demo ve danışman değerlendirmesi hem de final
raporundaki sistem testleri için gerekli. Repoda canlıya almayı etkileyen durumlar:

- `docker-compose.yml` geliştirme için yazılmış: PostgreSQL (5432), Redis (6379), Kafka
  (9092, 29092), ZooKeeper (2181), Neo4j (7474, 7687), kafka-ui (8080), redis-commander
  (8081), API (8000) ve web (3000) portları tüm arayüzlere açılıyor. Canlıda bunlar dışarıya
  kapatılmalı.
- Web istemcisi API ve WebSocket adreslerini derleme anında pakete gömer
  (`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`; `sentinelflow-web/src/lib/config.ts`).
  Adres değişirse web imajı yeniden derlenmelidir.
- API, CORS için `CORS_ORIGINS` değişkenini okur (varsayılan `http://localhost:3000`).
- `POST /api/v1/auth/register` kimlik doğrulamasız açık; `docs/api.md` bunun üretimde
  kapatılması gerektiğini söylüyor, fakat kapatmak için bir ayar yok.
- Model dosyaları repoda değil; `docs/SPRINT4_DEMO.md` §1 modeli
  `model-fraud-lgbm-20261030-0e0c647` Release'inden indirip checksum doğrular.
- `scripts/seed_admin.py` yalnız **admin** rolünde hesap oluşturur; `register` yalnız viewer açar, rol değiştiren bir uç nokta yok, `scripts/e2e_seed.py` ise adında `e2e` olmayan veritabanını reddeder. Canlıda analist ve viewer demo hesabı açmanın hazır bir yolu yok.
- Şema API açılışında `Base.metadata.create_all` ile kurulur (`api/state.py`); bu eksik tabloları oluşturur ama var olan tabloyu değiştirmez. Yeni bir sürüm tablo değiştirirse güncelleme yolu (Alembic migration'ı) netleştirilmelidir.
- API'nin açılması Kafka ve Neo4j'ye bağlı değildir; ancak compose `NEO4J_PASSWORD` değişkeni boşsa başlamaz, Neo4j çalıştırılmasa da `.env`'de tanımlı olmalıdır.
- Web'de API'ye bağlanan graf ve sohbet bileşenleri (`components/dashboard/network-graph.tsx`, `ai-chat.tsx`) hiçbir sayfada kullanılmıyor; dashboard'daki grafik yalnız görsel. Neo4j'siz kurulumda web etkilenmez. `NEXT_PUBLIC_ENABLE_AUTH` okunur ve canlıda asla `false` yapılmamalıdır; `NEXT_PUBLIC_ENABLE_AI_CHAT` ve `NEXT_PUBLIC_ENABLE_NETWORK_GRAPH` tanımlı ama hiçbir yerde kullanılmıyor.
- API'de olup web'de arayüzü olmayan özellikler: ağ grafiği ve para halkaları (`/graph/data`, `/graph/rings`, `/graph/account/{iban}`), tek işlem risk skoru (`/risk/score`), müşteri PEP/yaptırım taraması (`/kyc/screen`), parola değiştirme (`/auth/change-password`), demo işlem gönderme (`/transactions`) ve kural tabanlı sohbet (`/chat`). Gereken paketler (`react-force-graph-2d` dahil) zaten `package.json`'da.
- *(Oracle'a özgü, artık geçerli değil — §12.)* API imajı linux/arm64 üzerinde derlenip ölçüldü (`docs/ml/ml08-image-size.md`), bu yüzden
  Oracle'ın ARM (Ampere A1) makineleri için temel uyumluluk var. Kafka, ZooKeeper, Neo4j ve
  yönetim arayüzü imajlarının arm64 desteği ayrıca doğrulanmalı.
- *(Oracle'a özgü, artık geçerli değil — §12.)* **Oracle Always Free belirsizliği:** Resmî belgelere göre bir Always Free makine 7 gün
  boyunca şu üç koşulu birlikte sağlarsa boşta sayılır ve geri alınabilir: 95. yüzdelik CPU
  kullanımı %20'nin altında, ağ kullanımı %20'nin altında ve (yalnız A1 makinelerde) bellek
  kullanımı %20'nin altında.
  Ayrıca topluluk kaynakları Ampere A1 ücretsiz kotasının 2026'da 4 OCPU / 24 GB'tan
  yaklaşık 2 OCPU / 12 GB'a düşürüldüğünü bildiriyor; bunun resmî duyurusu bulunamadı.
  Plan bu yüzden **12 GB belleğe sığacak** biçimde kurulur; güncel limit hesap açılınca
  konsoldan okunup SF-501 kaydına yazılır.

## 3. Kapasite ve çalışma modeli

- Teorik kapasite: 1 kişi × 15 gün = 15 kişi-gün. Planlanan: canlı ortam P0 8 kişi-gün + web P1 4.5 kişi-gün = 12.5 kişi-gün. Tampon: 2.5
  kişi-gün (Oracle kapasite sorunları, sertifika, ARM imaj uyumsuzlukları).
- Yusuf projeye bu sprintte katılıyor; ilk gün yerel kurulum ve okuma için ayrıldı (SF-500).
- Her iş ayrı branch ve küçük PR ile ilerler (hedef: PR başına ~400 net satırdan az).
  Branch örnekleri: `yusuf/s5-prod-compose`, `yusuf/s5-proxy`, `yusuf/s5-runbook`,
  `yusuf/s5-web-score`, `yusuf/s5-web-graph`.
- Oracle tarafında beklenen (kapasite, DNS, sertifika) günlerde web işleri yerelde ilerletilir.
- Her PR'ı Buğra veya Alper inceler (CODEOWNERS). Backend kodu değişen PR'larda Buğra'nın,
  `package*.json` değişen PR'larda Alper'in onayı gerekir.
- Sunucu üzerinde elle yapılan her değişiklik aynı gün runbook'a yazılır; "sadece sunucuda
  olan" ayar bırakılmaz.

## 4. Sprint başında verilecek kararlar

> **Güncel durum:** "Makine", "Alan adı", "Ödeme yöntemi riski" ve "Oracle hesabının sahibi"
> kararları Oracle Cloud içindi ve artık gerekmiyor. Yerine verilen karar: demo
> geliştiricinin bilgisayarında Docker Compose ile çalışır ve Tailscale Funnel ile paylaşılır;
> Tailscale hesabı Yusuf'ta (§12).

| Karar | Seçenekler | Öneri | Karar veren |
|---|---|---|---|
| Sprint süresi | 3 hafta (canlı ortam + web); 2 hafta canlı ortam, web işleri Sprint 6'ya | 3 hafta | Ekip |
| Alan adı | Ekibin kendi alanı; ücretsiz dinamik DNS alt alanı; IP tabanlı `sslip.io` adı | Elde alan adı varsa o; yoksa ücretsiz alt alan | Ekip |
| Makine | Ampere A1 Flex (ARM), konsolun gösterdiği ücretsiz limit içinde | 2 OCPU / 12 GB, Ubuntu 24.04 aarch64 | Yusuf, ekip onayı |
| Canlıdaki servisler | P0: PostgreSQL, Redis, API, web, ters vekil. P1: Kafka, ZooKeeper, Neo4j, detector | Önce P0; bellek ölçümü SF-503'te yeterse P1 | Ekip |
| Kayıt uç noktası | Ayarla kapatma (backend PR); ters vekilde engelleme (geçici) | İkisi: önce vekilde engel, sonra ayar | Buğra |
| Demo hesapları | Rol başına bir hesap (viewer, analyst, admin) | Parolalar ekip parola yöneticisinde; repoya, issue'ya, sohbete yazılmaz | Ekip |
| Ödeme yöntemi riski | Yalnız Always Free; kullandıkça öde hesabı | Yalnız Always Free; bütçe uyarısı açık | Ekip |
| Oracle hesabının sahibi | Hesabı kim açar, doğrulama kartı kimin | Hesabı açan kişi ekipte yazılı; yönetici erişimi en az iki kişide | Ekip |
| Ortak e-posta ve parola yöneticisi | Mevcut bir ekip adresi/kasası; yeni açılacak | Alan adı, sertifika uyarıları ve Oracle bildirimleri ortak adrese; sırlar ortak parola kasasında | Ekip |

## 5. Backlog

| İş | Öncelik | Gün | Teslim / kabul özeti |
|---|---|---:|---|
| SF-500 Yerel kurulum ve okuma | P0 | 1 | `SPRINT3_DEMO.md` başlangıcı ve `SPRINT4_DEMO.md` yerelde tekrarlanır; ADR 0002/0003 ve bu plan okunur; sorular issue'ya yazılır. |
| ~~SF-501 Oracle hesabı ve sanal makine~~ **İptal (§12)** | — | 0.5 | Ampere A1 makine, Ubuntu 24.04 aarch64, yalnız SSH anahtarıyla giriş, root girişi kapalı, otomatik güvenlik güncellemeleri açık, Docker Engine + Compose v2 kurulu, bütçe uyarısı tanımlı. Konsoldaki güncel ücretsiz limit kayda geçer. |
| ~~SF-502 Ağ ve güvenlik duvarı~~ **İptal (§12)** | — | 0.5 | Asıl bariyer VCN güvenlik listesidir: içeriye yalnız 22, 80, 443. Oracle'ın Ubuntu imajlarındaki iptables kurallarında 80/443 ayrıca açılır. Docker'ın yayınladığı portlar sunucudaki INPUT kurallarına (ör. ufw) takılmadan dışarı açılır; bu yüzden altyapı portları SF-503'te hiç yayınlanmaz. Dışarıdan port taramasıyla doğrulanır. |
| SF-503 Üretim compose override'ı *(sunucu için; kod repoda kalır, bu sprintin kabul şartı değil — §12)* | P2 | 1 | `deploy/compose.prod.yml`: Compose, override'daki `ports` listesini ana dosyadakine **ekler**, bu yüzden altyapı servislerinde `ports: !reset []` kullanılır (Compose v2.24 ve üstü). kafka-ui, redis-commander ve prometheus canlıda başlatılmaz; bellek sınırları, log döndürme, Neo4j ve Kafka heap ayarları. Kabul: `docker compose -f docker-compose.yml -f deploy/compose.prod.yml config` çıktısında ters vekil dışında yayınlanan port yok. Servislerin bellek kullanımı ölçülüp tabloya yazılır. |
| SF-504 Ters vekil ve HTTPS *(sunucu için; kod repoda kalır, bu sprintin kabul şartı değil — §12)* | P2 | 1 | Caddy (önerilen; otomatik Let's Encrypt): `/` → web, `/api/*` ve `/ws/*` → API, HTTP → HTTPS yönlendirme. `/metrics` ve isteğe bağlı `/docs` dışarıya kapalı. Önce Let's Encrypt staging ile denenir. |
| SF-505 Web'in canlı yapılandırması *(sunucu için; kod repoda kalır, bu sprintin kabul şartı değil — §12)* | P2 | 1 | Web imajı `NEXT_PUBLIC_API_URL=https://<alan>` ve `NEXT_PUBLIC_WS_URL=wss://<alan>` ile derlenir; `CORS_ORIGINS=https://<alan>`. Derlenmiş pakette `localhost`/`127.0.0.1` kalmaz. Giriş, oturum yenileme, çıkış, 401 sonrası giriş sayfasına dönüş, canlı alarm akışı (WebSocket) çalışır. `NEXT_PUBLIC_ENABLE_AUTH` tanımsız bırakılır (varsayılan açık); `false` yapılmaz. Kullanılmayan diğer iki bayrak SF-526'ya kadar eklenmez. |
| SF-506 Model, yönetici ve demo verisi | P0 | 1 | Model sunucuda `gh release download model-fraud-lgbm-20261030-0e0c647 -R uzunbugra/sentinel -D models/fraud/current` ve ardından o dizinde `sha256sum -c SHA256SUMS` ile alınır (`SPRINT4_DEMO.md` §1'in Linux karşılığı). Admin `seed_admin.py` ile (`SEED_ADMIN_*` değişkenleri). Analist ve viewer demo hesapları için `seed_admin.py`'ye rol seçeneği eklenir (`scripts/`, Buğra incelemesi) ya da eşdeğer küçük bir betik yazılır; elle SQL ile rol değiştirmek kalıcı çözüm sayılmaz. Yalnız sentetik demo işlemleri. `ml/models` `loaded` döner. |
| SF-507 Kayıt uç noktasını kapatma | P0 | 0.5 | Geçici: ters vekilde `POST /api/v1/auth/register` engellenir. Kalıcı: API'ye kaydı kapatan bir ortam değişkeni ve testi (backend PR, Buğra incelemesi). Canlıda kayıt denemesi reddedilir. |
| SF-508 Yedekleme ve geri yükleme *(sunucu için; kod repoda kalır, bu sprintin kabul şartı değil — §12)* | P2 | 0.5 | Günlük `pg_dump` (systemd timer veya cron), son 7 yedek makinede, haftalık kopya makine dışında (ör. Always Free Object Storage). Boş bir veritabanına bir kez geri yükleme denenir ve sonucu runbook'a yazılır. |
| SF-509 İzleme ve runbook *(sunucu için; kod repoda kalır, bu sprintin kabul şartı değil — §12)* | P2 | 0.5 | Dış sağlık kontrolü (`/api/v1/system/health`); disk ve bellek uyarısı; `deploy/README.md` runbook: sıfırdan kurulum, yeni sürüme geçiş (şema değişikliği varsa önce yedek; migration yolu Buğra ile netleştirilir), önceki sürüme dönüş, yedekten dönme, sırların nerede durduğu (değerleri değil). |
| SF-510 Canlı kabul testi *(Funnel adresine karşı — §12)* | P0 | 0.5 | §8'deki senaryo ekip bilgisayarından canlı adrese karşı çalıştırılır (`SPRINT4_DEMO.md` §2–3'teki PowerShell komutları `$api = 'https://<alan>/api/v1'` ile; sunucuda çalıştırılacaksa `pwsh` kurulur); sonuç, ekran görüntüleri (sır içermeyen) ve ölçülen yanıt süreleri issue'ya yazılır. |
| ~~SF-511 Kafka, Neo4j ve detector'ı canlıya alma~~ **Gerekmiyor (§12): yerelde zaten çalışıyor** | — | — (tampondan) | SF-503 ölçümü 12 GB'a sığdığını gösterirse: Kafka/ZooKeeper/Neo4j/detector dahili ağda; arm64 imajları doğrulanmış; `SPRINT4_DEMO.md` §4 canlıda tekrarlanır. |
| ~~SF-512 Elle tetiklenen dağıtım workflow'u~~ **Gerekmiyor (§12)** | — | — | `workflow_dispatch` ile SSH üzerinden dağıtım. Repo sırları (SSH anahtarı) yalnız repo yöneticisi (Buğra) tarafından eklenir. Bu sprintin kabul şartı değildir. |
| SF-520 Ağ grafiği ve para halkaları sayfası | P1 | 1.5 | Yeni `/graph` sayfası (viewer): hazır `components/dashboard/network-graph.tsx` bileşeni `GET /graph/data` ile; `GET /graph/rings` ile tespit edilen halkaların listesi; IBAN'a tıklayınca `GET /graph/account/{iban}` komşuluğu. Neo4j yokken veya boş grafikte anlaşılır boş/hata durumu. Canlıda görünmesi SF-511'e bağlı; geliştirme yerelde yapılır. |
| SF-521 İşlem skorlama aracı | P1 | 1 | Yeni `/score` sayfası (analyst): işlem alanları formu → `POST /risk/score`; skor, eşik, karar ve ilk 5 katkı mevcut `alerts/model-evaluation.tsx` görünümüyle. Hesap geçmişini değiştirmediği ekranda yazılır. Model yüklü değilse (503) açık mesaj. |
| SF-522 Müşteri taraması (KYC) sayfası | P1 | 1 | Yeni `/kyc` sayfası (analyst): ad ve ülke → `POST /kyc/screen`; eşleşme türü (tam, kısmi, bulanık, takma ad), liste ve skor. Listelerin örnek veri olduğu ve resmî listelere bağlı olmadığı ekranda açıkça yazılır. |
| SF-523 Demo işlem gönderme | P1 | 0.5 | Dashboard'da yalnız sentetik değerlerle "demo işlem gönder" formu (`POST /transactions`); sonuç ve oluşan alarm canlı akışta görünür. Böylece canlı demo PowerShell gerektirmez. Not: API bu uç noktayı her girişli kullanıcıya açıyor; form analyst ve admin'e gösterilir, sunucu tarafı kısıtlama gerekirse ayrı backend işi olarak Buğra'ya yazılır. |
| SF-524 Parola değiştirme | P1 | 0.5 | Başlıktaki kullanıcı menüsünden parola değiştirme (`POST /auth/change-password`); hata ve başarı durumları. Demo hesaplarının parolası canlıda değiştirilebilir olur. |
| SF-525 Sohbet asistanı paneli | P2 | 0.5 | Hazır `components/dashboard/ai-chat.tsx` dashboard'a eklenir (`/chat`, `/chat/suggestions`); asistanın kural tabanlı olduğu ve LLM kullanmadığı panelde yazılır. |
| SF-526 Kullanılmayan web kodunun temizliği | P2 | 0.5 | Hiçbir sayfada kullanılmayan bileşenler (`threat-map`, `leaflet-map` ve benzerleri) ya bir sayfaya bağlanır ya da kaldırılır; okunmayan `NEXT_PUBLIC_ENABLE_AI_CHAT` ve `NEXT_PUBLIC_ENABLE_NETWORK_GRAPH` bayrakları yeni sayfalara bağlanır veya silinir. Bağımlılık kaldırılacaksa Alper onayı. |

Canlı ortam P0 toplamı 8, web P1 toplamı 4.5 kişi-gün; tampon 2.5 kişi-gün. Sıra: önce canlı ortam P0, ardından web P1 (SF-521 → SF-523 → SF-524 → SF-522 → SF-520); SF-511 ve P2 işler ancak tampon kalırsa başlar.

Web işlerinin ortak kabulü: rol kontrolü (viewer analist eylemlerini görmez; API 403 dönerse anlaşılır mesaj), yükleniyor/boş/hata durumları mevcut `ui/request-state.tsx` ile, Vitest birim testleri ve en az skorlama ile demo işlem gönderme için birer Playwright senaryosu; `npm run lint`, `tsc`, `vitest` ve `next build` temiz; yeni sayfalar başlıktaki menüden erişilebilir.

## 6. Aşamalar ve geçiş kapıları

> **Güncel sıra (§12):** Hazırlık (SF-500) → web özellikleri (SF-520–526) → Funnel kurulumu
> (`deploy/funnel/`, `scripts/funnel.ps1`, SF-506/507) → kabul (SF-510, Funnel adresinde).
> Aşağıdaki 2–5. aşamalar Oracle sunucusu içindi ve artık uygulanmıyor.

1. **Hazırlık (SF-500).** Yerel kurulum çalışmadan sunucuya geçilmez.
2. **Makine ve ağ (SF-501, SF-502).** Kapı: SSH yalnız anahtarla; dışarıdan yalnız 22/80/443.
3. **Çekirdek servisler (SF-503, SF-506).** PostgreSQL, Redis, API ve web dahili ağda
   ayağa kalkar. Kapı: `system/health` sağlıklı, model `loaded`, dışarıya açık altyapı portu yok.
4. **Yayın (SF-504, SF-505, SF-507).** Kapı: `https://<alan>` geçerli sertifikayla açılır,
   giriş ve WebSocket çalışır, kayıt kapalı.
5. **İşletim (SF-508, SF-509).** Kapı: bir geri yükleme denemesi ve runbook incelemesi.
6. **Kabul (SF-510).**
7. **Web özellikleri (SF-520–524).** Her özellik ayrı PR; önce yerelde, birleştikten sonra canlıya
   yeni sürümle alınır. Kapı: §8'deki web maddeleri.
8. Tampon kalırsa SF-511, SF-525, SF-526.

Her aşamanın sonucu Sprint 5 milestone'undaki ilgili issue'ya kısa bir not olarak yazılır.

## 7. Dosya sahipliği ve PR sınırları

- **Yusuf yazar:** yeni `deploy/` dizini (`compose.prod.yml`, `Caddyfile`, yedek ve izleme
  betikleri, `README.md` runbook), `docs/SPRINT5_DEMO.md` (canlı demo adımları).
- **Yusuf yazar (web):** yeni sayfalar (`sentinelflow-web/src/app/{graph,score,kyc}/**`), bunlara ait
  bileşenler ve testler; başlık menüsüne bağlantılar. Mevcut ekranlarda (alerts, cases, dashboard)
  yapılan değişiklikler Alper onayıyla.
- **Yusuf, onayla yazar:** `sentinelflow-web/**` altında canlı yapılandırma için gereken
  diğer değişiklikler (Alper onayı); Playwright senaryoları (Buğra onayı); `package*.json` değişikliği gerekirse önce
  Alper'e sorulur. `src/sentinelflow/**` yalnız SF-507 kapsamında (Buğra onayı).
- **Değiştirilmez:** `docker-compose.yml` geliştirme dosyası olarak kalır; canlı farkları
  override dosyasında tutulur. Ana dosyada değişiklik gerekirse ayrı PR ve Buğra onayı.
  `.github/workflows/**` Buğra'nındır (SF-512 dahil).
- Her PR: bağlı iş ID'si, ne değiştiği, nasıl test edildiği (komut çıktısı veya ekran
  görüntüsü, sır içermeden) ve kalan bağımlılık.

## 8. Sprint bitiş kapıları

> **Güncel durum:** `https://<alan>` yerine Funnel adresi (`https://<makine>.<tailnet>.ts.net`)
> kullanılır. "Port taramasında yalnız 22/80/443" yerine: Funnel yalnız 8088'deki ters vekili
> açar ve tüm konteyner portları `127.0.0.1`'e bağlıdır. "Runbook incelemesi" yerine
> `docs/DEMO_TAILSCALE.md` incelenir. Ağ grafiği Funnel adresinde de çalışır, çünkü Neo4j
> yerelde açıktır. Diğer maddeler aynen geçerlidir.

- `https://<alan>` geçerli sertifikayla açılıyor; HTTP isteği HTTPS'e yönleniyor.
- Canlı senaryo: analist hesabıyla giriş → demo işlemi gönderilir → ML alarmı listede
  görünür → alarm detayında model sürümü, skor, eşik ve ilk 5 katkı → alarmdan vaka →
  vaka zaman çizelgesinde `case_created` ve `alert_linked_to_case`. Viewer hesabı aynı
  ekranları görür ama değişiklik yapamaz.
- `GET /api/v1/ml/models` → `loaded`, `fraud-lgbm-20261030-0e0c647`.
- Dışarıdan yapılan port taramasında yalnız 22, 80, 443 açık; `/metrics` dışarıdan erişilemiyor.
- Kayıt uç noktası canlıda reddediyor.
- Bir yedekten geri yükleme denendi ve süresi yazıldı.
- Runbook'u Buğra ve Alper inceledi; sunucuda runbook'ta olmayan elle yapılmış ayar yok.
- Repoda, issue'larda ve ekran görüntülerinde hiçbir sır (parola, anahtar, `.env` içeriği) yok.
- Canlıda: analist skorlama aracıyla bir işlemin skorunu, eşiğini ve ilk 5 katkısını görür;
  KYC ekranında örnek bir adı tarar; dashboard'dan demo işlem gönderir ve alarm canlı akışta
  görünür; parolasını değiştirir. Viewer bu eylemlerin düğmelerini görmez.
- Ağ grafiği sayfası yerelde (Neo4j açık) halka listesini ve hesap komşuluğunu gösterir;
  Neo4j canlıdaysa aynısı canlıda.
- Web kontrolleri (lint, tip, Vitest, build) ve yeni Playwright senaryoları CI'da yeşil.

## 9. Güvenlik kuralları

- `.env` yalnız sunucuda, `chmod 600`, repoya girmez. Canlı `JWT_SECRET_KEY`,
  `POSTGRES_PASSWORD`, `NEO4J_PASSWORD` yerel değerlerden farklı ve güçlü olur
  (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).
- Parolalar ve SSH anahtarları §4'te seçilen ortak parola kasasında tutulur; sohbetle paylaşılmaz.
- SSH: parola ile giriş ve root girişi kapalı; erişim yalnız ekip üyelerinin anahtarlarıyla.
- Redis yalnız dahili ağda; `REDIS_PASSWORD` desteği istemcilerde doğrulanırsa parola da açılır.
- Canlıda gerçek kişisel veri işlenmez; yalnız sentetik demo verisi (KVKK).
- Alan adı, sertifika ve Oracle bildirimleri §4'te seçilen ortak e-postaya gelir, tek kişiye bağlı kalmaz.

## 10. Riskler

> **Güncel durum:** Ampere A1 kapasitesi, ücretsiz kota, boşta makinenin geri alınması, ARM
> imajları ve beklenmeyen ücret riskleri Oracle içindi ve artık geçerli değil. Funnel ile
> gelen riskler §12'dedir.

| Risk | Etki | Önlem / Plan B |
|---|---|---|
| Ampere A1 kapasitesi bölgede yok ("out of capacity") | Makine açılamaz | Farklı müsaitlik alanı ve saatlerde tekrar; olmazsa ekip kararıyla başka ücretsiz/ucuz seçenek; o sürede yerel demo geçerli kalır. |
| Ücretsiz kota beklenenden düşük (12 GB veya altı) | Tüm servisler sığmaz | P0 profil (Kafka/Neo4j'siz); heap sınırları; SF-511 ertelenir. |
| Boşta kalan makinenin Oracle tarafından geri alınması (7 gün boyunca CPU, ağ ve bellek kullanımının üçü birden %20'nin altında) | Oracle uyarı e-postasından sonra makineyi durdurur; canlı adres kapanır | Demo trafiğinde CPU ve ağ büyük ihtimalle %20'nin altında kalır; makineyi koruyan koşul bellektir (12 GB'ta ~2,4 GB). Kafka ve Neo4j de çalışırsa (SF-511) bu sınır rahatça aşılır; yalnız P0 servislerle sınıra yakın kalabilir. İlk hafta Oracle Cloud Agent açılıp Monitoring'de üç ölçüm izlenir ve SF-509 kaydına yazılır. Yapay yük üreten betik kullanılmaz. Kullandıkça öde hesabına geçmenin geri almayı engellediği bildiriliyor ama resmî belgede doğrulanmadı; geçiş ekip kararıdır ve bütçe uyarısı şarttır. Her durumda runbook ile hızlı yeniden kurulum, makine dışında yedek ve uyarı e-postalarının ortak adrese gelmesi. |
| ARM'da çalışmayan imaj | Servis başlamaz | `docker manifest inspect` ile önceden kontrol; alternatif etiket veya arm64 destekli eşdeğer imaj (ayrı PR, onayla). |
| Let's Encrypt hız sınırı veya DNS hatası | Sertifika alınamaz | Önce staging ortamı; DNS kaydı doğrulandıktan sonra gerçek sertifika. |
| Beklenmeyen ücret | Maliyet | Yalnız Always Free kaynaklar; bütçe uyarısı; kaynak oluşturmadan önce "Always Free" etiketi kontrol edilir. |
| Web işleri canlı ortam işlerini geciktirir | Hedef 1–5 kaçar | Canlı ortam P0 önce; web işi yalnız Oracle tarafında beklenirken veya P0 bittikten sonra. |
| Graf sayfası Neo4j olmadan canlıda boş kalır | Demo eksik | Yerel kabul yeterli sayılır; canlı için SF-511 kararı. |
| Sır sızıntısı (ekran görüntüsü, log, commit) | Güvenlik | PR incelemesinde kontrol; sızarsa ilgili sır hemen değiştirilir ve olay issue'ya (değer yazmadan) not edilir. |

## 11. Sprint dışında

- Kubernetes, çok makineli kurulum, otomatik ölçekleme.
- Gerçek banka verisi veya gerçek müşteri hesabı.
- Backend'de karşılığı olmayan web özellikleri (ör. kullanıcı ve rol yönetimi ekranı; önce
  API gerekir). Canlıya alma sırasında bulunan web hataları issue olarak açılır, küçükse bu
  sprintte düzeltilir.
- Tasarım sisteminin yenilenmesi veya landing sayfasının yeniden yazılması.
- Model yeniden eğitimi veya yeni model sürümü.
- Final raporu için performans ölçümleri (uçtan uca gecikme, Kafka verimi) bu ortamda
  yapılabilir, fakat ölçüm planı ayrı bir işte tanımlanır.

## 12. Karar değişikliği: yerel demo ve Tailscale Funnel (23 Kasım 2026)

Demo ortamı için Oracle Cloud yerine şu yol seçildi: SentinelFlow mevcut Docker Compose
kurulumuyla geliştiricinin bilgisayarında çalışır; hocaların kendi cihazlarından açması
gerektiğinde Tailscale Funnel ile geçici bir HTTPS adresi paylaşılır
([`DEMO_TAILSCALE.md`](DEMO_TAILSCALE.md)).

- **Neden:** Sunucu, alan adı, sertifika, ödeme yöntemi ve Oracle Always Free'nin boşta
  makine geri alma riski (§10) ortadan kalkar; demo yalnız gerektiğinde açılır.
- **Yeni teslimler:** `deploy/funnel/compose.funnel.yml` (tüm portlar yalnız `127.0.0.1`,
  kayıt kapalı, tek giriş noktası Caddy `127.0.0.1:8088`), `deploy/funnel/Caddyfile`,
  `scripts/funnel.ps1` (başlat/durdur) ve web'in aynı-köken modu
  (`NEXT_PUBLIC_API_URL=same-origin`): aynı paket hem `localhost`'ta hem Funnel adresinde
  yeniden derlenmeden çalışır.
- **İşlerin durumu:**

  | İş | Yeni durum |
  |---|---|
  | SF-501, SF-502 (Oracle makinesi, güvenlik duvarı) | Gerekmiyor; Funnel yalnız tek bir yerel portu açar. |
  | SF-503, SF-504, SF-505, SF-508, SF-509 | Kod repoda kalır; ileride sunucuya geçilirse kullanılır. Bu sprintin kabul şartı değil. |
  | SF-506, SF-507 | Aynen geçerli: hesaplar seed betiğiyle açılır, kayıt Funnel kurulumunda da kapalı. |
  | SF-510 | Kabul testi Funnel adresine karşı yapılır (`SPRINT5_DEMO.md`, `<alan>` yerine Funnel adresi). |
  | SF-511 | Gerekmiyor; Kafka ve Neo4j yerel kurulumda zaten çalışıyor, ağ grafiği de veri gösterir. |
  | SF-512 | Gerekmiyor. |
  | SF-520–526 | Değişmedi. |

- **Funnel ile gelen riskler:**

  | Risk | Etki | Önlem |
  |---|---|---|
  | Demo sırasında bilgisayar uykuya geçer, kapanır veya ağ değişir | Adres açılmaz | Demo süresince uyku kapalı, şarj takılı; demodan önce `funnel.ps1` ile prova |
  | Funnel açıkken adres internette herkese açık | İzinsiz giriş denemesi | Funnel yalnız demo süresince açık; kayıt kapalı; `/metrics` ve `/docs` kapalı; demodan sonra `funnel.ps1 -Stop` |
  | Tailscale hesabı tek kişide | Yusuf yoksa demo açılamaz | Başka bir ekip üyesi kendi Tailscale hesabıyla aynı belgeyi izleyebilir |
  | Funnel bant genişliği sınırlı | Sayfalar yavaş açılır | Demo verisi küçük; ilk açılıştan önce prova |

- **Bitiş kapıları (§8) yerine:** Funnel adresi geçerli sertifikayla açılır; §8'deki analist
  ve viewer senaryosu bu adreste çalışır; `ml/models` `loaded` döner; `/metrics` ve kayıt
  dışarıdan reddedilir; aynı ağdaki başka bir cihazdan veritabanı ve yönetim portlarına
  erişilemez; demodan sonra `funnel.ps1 -Stop` ile adres kapanır.
