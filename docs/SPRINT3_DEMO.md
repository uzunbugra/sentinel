# Sprint 3 Demo Senaryosu

## Genel Bakış

Sprint 3, alarmdan vakaya uçtan uca analist iş akışını çalışır hale getirir
(`docs/SPRINT3_PLAN.md`):
- **JWT ile giriş** - Seed edilen yönetici veya analist hesabıyla
- **Alarm listesi ve detayı** - Yetkiye uygun inceleme, alarm kapatma (dismiss)
- **Vaka oluştur / bağla** - Alarmı yeni vakaya veya mevcut açık vakaya bağlama
- **Vaka detayı** - Durum, öncelik, atama ve not işlemleri
- **Zaman çizelgesi (audit)** - Her değişiklik için bir vaka olayı

Bu belge iki kontrol noktasından ilkidir (SF-403): mevcut analist akışının temiz
Docker kurulumunda doğrulanması. ML demosu ML-05/06 sonrasına bırakılmıştır (son bölüm).

---

## Başlangıç

### Ön koşullar

- Docker Desktop (Compose v2) çalışır durumda
- Node.js 22 (`>=22.12`, bkz. `sentinelflow-web/.nvmrc`) — yalnız web'i yerelde
  `npm run dev` ile çalıştıracaksanız gerekir; Docker imajı `node:22-alpine` kullanır.

### 1. Ortam değişkenlerini hazırla

```powershell
Copy-Item .env.example .env
```

`.env` içinde en az `POSTGRES_PASSWORD`, `NEO4J_PASSWORD` ve `JWT_SECRET_KEY`
doldurulmalıdır (compose bunlar boşsa başlamaz). Güçlü değer üretmek için:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`.env` repoya commit edilmez; içeriğini ekran görüntüsüne veya sohbete koymayın.

### 2. Servisleri temiz kurulumla başlat

```powershell
docker compose --profile frontend up -d --build
docker compose --profile frontend ps
```

Beklenen: `postgres`, `redis`, `zookeeper`, `kafka`, `neo4j`, `api`, `frontend`,
`redis-commander` konteynerleri `healthy`; `kafka-ui` healthcheck tanımlamaz (`Up`).
`neo4j-init` tek seferlik çalışır; başarılı sonuç `Exited (0)` olmalıdır
(`docker compose ps -a neo4j-init`). Neo4j `healthy` olması şemanın tamamlandığı
anlamına gelmez; init çıkışını ve aşağıdaki şema kontrollerini de doğrulayın.
Temiz başlangıç için önce `docker compose --profile frontend down -v` (verileri siler).
İlk build birkaç dakika sürer (smoke'ta ~16 dk, imaj indirmeleri dahil).

> **Neo4j `exec /usr/bin/tini: exec format error` ile yeniden başlıyorsa:** bu bir
> mimari sorunu değildir; Docker Desktop'un yerel imaj deposunda `neo4j` katmanı bozuk
> açılmıştır (konteyner içinde `/usr/bin/tini` 0 bayt). `docker pull` "up to date" der
> ve bozuk katmanı yeniden kullanır. Kontrol:
> `docker run --rm --entrypoint ls neo4j:5.15.0-community -la /usr/bin/tini`.
> Çözüm Docker Desktop → Troubleshoot → *Clean / Purge data* (tüm imaj ve volume'leri
> siler). Verileri korumak için geçici olarak aynı sürümün `neo4j:5.15.0-community-ubi8`
> imajı yerel bir compose override ile kullanılabilir; repodaki imaj değişmez.

### 3. Sağlık kontrolleri

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/system/health
docker compose exec postgres pg_isready -U sentinelflow -d sentinelflow
docker compose exec redis redis-cli ping
docker compose exec kafka kafka-broker-api-versions --bootstrap-server localhost:9092
Invoke-WebRequest http://localhost:7474 -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest http://localhost:3000/login -UseBasicParsing | Select-Object StatusCode
```

Neo4j şeması, kimlik doğrulamalı Bolt healthcheck'i başarılı olduktan sonra
`neo4j-init` tarafından otomatik uygulanır. Parola `.env` içindeki
`NEO4J_PASSWORD` değerinden gelir; aşağıdaki komutlarda ekrana yazılmaz:

```powershell
docker compose ps -a neo4j neo4j-init
docker compose logs neo4j-init
docker compose exec -T neo4j sh -c 'cypher-shell -u neo4j -p "$CYPHER_PASSWORD" --format plain "SHOW CONSTRAINTS YIELD name RETURN name ORDER BY name;"'
docker compose exec -T neo4j sh -c 'cypher-shell -u neo4j -p "$CYPHER_PASSWORD" --format plain "SHOW INDEXES YIELD name, type, state RETURN name, type, state ORDER BY name;"'
```

Beklenen: 3 uniqueness constraint, bunların 3 backing RANGE index'i, 5 açıkça
tanımlı RANGE index ve 2 varsayılan LOOKUP index (toplam 10 index, `ONLINE`).
İkinci `docker compose --profile frontend up -d` çalıştırması da başarılı olmalı;
`neo4j-init` yeniden çalışır ve `IF NOT EXISTS` sayesinde `Exited (0)` ile biter.
Şemayı ayrıca yeniden uygulamak için `docker compose run --rm neo4j-init` kullanın.

### 4. Yönetici hesabını oluştur (seed)

Sabit demo şifresi yoktur. İlk yönetici `scripts/seed_admin.py` ile oluşturulur ve
şifre ortamdan okunur. API konteynerinde çalıştırın:

```powershell
$env:SEED_ADMIN_PASSWORD = Read-Host "Yönetici şifresi"   # ekrana yazılmaz, repoya girmez
docker compose exec -e SEED_ADMIN_PASSWORD=$env:SEED_ADMIN_PASSWORD api python scripts/seed_admin.py --no-generate
```

- Varsayılanlar: kullanıcı `admin`, e-posta `admin@example.com`
  (`SEED_ADMIN_USERNAME`, `SEED_ADMIN_EMAIL` ile değiştirilebilir).
- `--no-generate` olmadan ve şifre verilmeden çalıştırılırsa script rastgele şifre
  üretir ve **log'a yazar**; paylaşılan ekranda bu yolu kullanmayın.
- Kullanıcı zaten varsa script hiçbir şeyi değiştirmeden çıkar (idempotent).

### 5. Demo alarmı (yalnız Sprint 3 smoke fixture'ı)

Sprint 3 akışında gerçek ML artifact'ı bağlı değildir. Analist akışını göstermek için
kural tabanlı tipte (`structuring`) fixture alarmlar doğrudan eklenir.
**Bu alarmlar ML demosu sayılmaz** (bkz. Sprint 4 planı §11, SF-403).

```powershell
$fixture = @'
import sys
from sentinelflow.database.postgres import DatabaseSession
from sentinelflow.processor.alert_writer import create_alert_from_detection
from sentinelflow.repository import AlertRepository
n = sys.argv[1]
tx = {"transaction_id": f"TX-DEMO-S3-{n}", "sender_iban": "TR000000000000000000000001",
      "sender_name": "Demo Gonderen", "receiver_iban": "TR000000000000000000000002",
      "receiver_name": "Demo Alici", "amount": 49500, "currency": "TRY"}
with DatabaseSession() as s:
    a = AlertRepository(s).create(create_alert_from_detection(
        "structuring", "high", 0.9, tx, "Sprint 3 smoke fixture alarmi"))
    s.commit()
    print(a.alert_id)
'@
$fixture | docker compose exec -T api python - 001   # <ALERT_ID>
$fixture | docker compose exec -T api python - 002   # <ALERT_ID_2>, Senaryo 4 için
```

Her çıktıdaki `ALERT-...` kimliğini not alın.

---

## Demo Senaryoları

### Senaryo 1: Giriş

1. http://localhost:3000 → oturum yoksa `/login` sayfasına yönlendirilir.
2. Seed adımındaki kullanıcı adı ve şifre ile giriş yapın.
3. Header'da kullanıcı adı ve rol (`admin`) görünür.

API ile (token sonraki senaryolarda kullanılır):

```powershell
$cred = Get-Credential -UserName admin -Message "SentinelFlow"
$body = @{ username = $cred.UserName; password = $cred.GetNetworkCredential().Password } | ConvertTo-Json
$tok = Invoke-RestMethod -Uri http://localhost:8000/api/v1/auth/login -Method POST -Body $body -ContentType "application/json"
$h = @{ Authorization = "Bearer $($tok.access_token)" }
Invoke-RestMethod -Uri http://localhost:8000/api/v1/auth/me -Headers $h
```

---

### Senaryo 2: Alarm listesi ve detayı

1. **Alarmlar** sayfası (http://localhost:3000/alerts): fixture alarm listede görünür.
2. Alarm detayında tutar, gönderen/alıcı ve kanıt alanları görünür.

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/alerts?page=1&page_size=20" -Headers $h
Invoke-RestMethod -Uri http://localhost:8000/api/v1/alerts/<ALERT_ID> -Headers $h
```

---

### Senaryo 3: Alarmdan vaka oluştur

1. Alarm satırındaki **Vaka Oluştur** ile yeni vaka açın.
2. Vakalar sayfasında yeni vaka `new` durumunda görünür.

```powershell
$body = @{ title = "Sprint 3 demo vakasi"; alert_ids = @("<ALERT_ID>"); priority = "P2" } | ConvertTo-Json
$case = Invoke-RestMethod -Uri http://localhost:8000/api/v1/cases -Method POST -Headers $h -Body $body -ContentType "application/json"
$case.case_id
```

Aynı alarmı ikinci bir açık vakaya bağlamak `409 Conflict` döner.

---

### Senaryo 4: Mevcut vakaya alarm bağla

Başlangıç §5'teki ikinci fixture alarmı mevcut vakaya bağlayın:

```powershell
$body = @{ alert_id = "<ALERT_ID_2>" } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8000/api/v1/cases/$($case.case_id)/alerts -Method POST -Headers $h -Body $body -ContentType "application/json"
```

İşlem idempotenttir: aynı alarmı tekrar bağlamak `200` döner.

---

### Senaryo 5: Vaka detayı — durum, atama, not

1. Vaka detay sayfası: http://localhost:3000/cases/<CASE_ID>
2. Durumu `investigating` yapın, kendinize atayın, bir not ekleyin.

```powershell
$body = @{ status = "investigating"; note = "Demo notu" } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8000/api/v1/cases/$($case.case_id) -Method PATCH -Headers $h -Body $body -ContentType "application/json"
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/cases/$($case.case_id)/assign?assigned_to=admin" -Method POST -Headers $h
```

---

### Senaryo 6: Zaman çizelgesi (audit)

1. Vaka detayındaki zaman çizelgesinde oluşturma, alarm bağlama, durum değişikliği,
   atama ve not olayları sırayla görünür.

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/cases/$($case.case_id)/events?page=1&page_size=20" -Headers $h
```

---

## Smoke sonucu (SF-403 ilk kontrol noktası, 2026-10-29)

Ortam: Windows 11, Docker Desktop 29.2.1 (Compose v5.1.0, linux/x86_64), temiz volume'ler,
`docker compose --profile frontend up -d --build` (exit 0).

| Kontrol | Sonuç |
|---------|-------|
| postgres / redis / zookeeper / kafka / redis-commander | `healthy`; `pg_isready` OK, `PONG`, broker API yanıt veriyor |
| neo4j | `healthy`; HTTP 7474 → 200, Bolt girişi OK, APOC 5.15.0 + GDS 2.6.9 yüklü (yerel bozuk imaj nedeniyle `-ubi8` varyantıyla, yukarıdaki nota bakın) |
| api | `healthy`; `/api/v1/system/health` → 200 |
| frontend | `healthy`; `/login` → 200; korumalı sayfa `/login`'e yönlendiriyor; production build'de demo ipucu yok |
| Admin seed | Kullanıcı oluşturuldu; ikinci çalıştırma "already exists, skipping" |
| Token olmadan `GET /alerts` | 401 |
| Login → `/auth/me` | 200 / 200 (`role=admin`) |
| Alarm listesi / detayı | 200 / 200 |
| Vaka oluştur | 201 (`status=new`); aynı alarmla ikinci vaka 409 |
| Mevcut vakaya alarm bağla | 200; tekrar bağlama 200 (idempotent) |
| Durum + not / atama / vaka detayı | 200 / 200 / 200 (`investigating`, 2 alarm) |
| Timeline | 200, 6 olay: `case_created`, 2× `alert_linked_to_case`, `case_status_changed`, `note_added`, `case_assigned` |

Akış API üzerinden doğrulandı. Tarayıcıda yalnız login sayfası ve yönlendirme
kontrol edildi; giriş sonrası UI senaryosu SF-404 Playwright testlerine bırakıldı.

---

## Sprint 3 vs Sprint 2 Karşılaştırması

| Özellik | Sprint 2 | Sprint 3 |
|---------|----------|----------|
| Alerts/Cases istemcisi | Doğrudan `fetch` | `fetchWithAuth` (JWT) |
| Vaka Oluştur düğmesi | İşlevsiz | Alarmdan vaka açar |
| Alarm bağlama | Yok | Yeni/mevcut vakaya, çakışma kontrollü |
| Vaka detayı | Yok | Durum, atama, not |
| Audit timeline | Yalnız backend | Vaka detay ekranında |
| Demo girişi | Sabit ipucu | Seed akışı, sabit şifre yok |

---

## Sprint 4 ML Demosu (yer tutucu — ML-05/06 sonrası)

> Bu bölüm ML-05/06 tamamlanıp gerçek model artifact'ı API'ye bağlandıktan sonra
> doldurulacak. Elle eklenen fixture alarm ML demosu sayılmaz.

Doldurulacaklar:
- Demo işlemi (tekrarlanabilir fixture), model sürümü ve beklenen skor/sonuç
- İşlem → ML alarmı → vaka → timeline akışı
- Alarm detayında `model_version`, skor, eşik ve top katkılar (SF-405)
- Sistem/model ekranında aktif model kartı özeti

---

## Bilinen notlar

- `prometheus` yalnız `--profile monitoring` ile, `frontend` yalnız `--profile frontend` ile başlar.
- Web `NEXT_PUBLIC_*` değerleri build sırasında gömülür; değiştirince `--build` gerekir.
- İlk smoke'ta eksik olan Neo4j şeması SF-403 takibinde `neo4j-init` servisiyle
  düzeltildi; `/docker-entrypoint-initdb.d` bağlaması kaldırıldı. Bellek ayarları
  Neo4j 5 `server.memory.*` adlarını kullanır; `dbms.security.procedures.*`
  izin ayarları Neo4j 5'te geçerlidir.
