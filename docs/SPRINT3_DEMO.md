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

Beklenen: `postgres`, `redis`, `zookeeper`, `kafka`, `neo4j`, `api`, `frontend`
konteynerleri `healthy` (kafka-ui ve redis-commander healthcheck tanımlamaz, `running`).
Temiz başlangıç için önce `docker compose --profile frontend down -v` (verileri siler).

### 3. Sağlık kontrolleri

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/system/health
docker compose exec postgres pg_isready -U sentinelflow -d sentinelflow
docker compose exec redis redis-cli ping
docker compose exec kafka kafka-broker-api-versions --bootstrap-server localhost:9092
Invoke-WebRequest http://localhost:7474 -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest http://localhost:3000/login -UseBasicParsing | Select-Object StatusCode
```

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

Docker imajında eğitilmiş model bulunmadığından `POST /api/v1/transactions` alarm
üretmez. Analist akışını göstermek için kural tabanlı tipte bir fixture alarm eklenir.
**Bu alarm ML demosu sayılmaz** (bkz. Sprint 4 planı §11, SF-403).

```powershell
docker compose exec api python -c "from sentinelflow.database.postgres import DatabaseSession; from sentinelflow.processor.alert_writer import create_alert_from_detection; from sentinelflow.repository import AlertRepository; s=DatabaseSession().__enter__(); a=AlertRepository(s).create(create_alert_from_detection('structuring','high',0.9,{'transaction_id':'TX-DEMO-S3-001','sender_iban':'TR000000000000000000000001','sender_name':'Demo Gonderen','receiver_iban':'TR000000000000000000000002','receiver_name':'Demo Alici','amount':49500,'currency':'TRY'},'Sprint 3 smoke fixture alarmi')); s.commit(); print(a.alert_id)"
```

Çıktıdaki `ALERT-...` kimliğini not alın.

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

Yeni bir fixture alarm ekleyip (Başlangıç §5, farklı `transaction_id`) mevcut vakaya bağlayın:

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
