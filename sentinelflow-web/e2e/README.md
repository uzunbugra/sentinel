# Tarayıcı testleri (SF-404)

Playwright testleri gerçek API'ye ve web'in production build'ine karşı koşar.

| Dosya | Senaryo |
|---|---|
| `analyst-flow.spec.ts` | Analist girişi → alarm → "Vaka Oluştur" → vaka detayı → durum değişikliği → işlem geçmişinde `case_created`, `alert_linked_to_case`, `case_status_changed` |
| `viewer-permissions.spec.ts` | Viewer alarmı ve vakayı okur; "Vaka Oluştur", "Reddet" ve vaka işlemleri görünmez. API de viewer'ın `PATCH /cases`'ini 403 ile reddeder |
| `model-state.spec.ts` | Model yüklü değilken panodaki aktif model kartı "Yüklü model yok" der. `/ml/models` 500 döndüğünde kart hata ve "Tekrar dene" gösterir (bu hata Playwright route ile üretilir) |

## Test verisi

`scripts/e2e_seed.py` veriyi doğrudan veritabanına yazar:

- `users`: `e2e_analyst` ve `e2e_viewer` hesaplarını `E2E_PASSWORD` ile oluşturur. Hesaplar zaten varsa şifre, rol ve kilit durumu sıfırlanır. Bu adım her koşunun başında çalışır (`global-setup.ts`).
- `alert --tag`: Her test kendi kural alarmını benzersiz bir etiketle oluşturur.
- `cleanup --tag`: Test bitince, başarısız olsa bile, o etiketin alarmını, vakasını ve olaylarını siler.

Testler başka testlerin verisine güvenmez. Seed betiği yalnız adında `e2e` geçen bir veritabanına yazar (ör. `sentinelflow_e2e`). Böylece `.env` geliştirme veritabanını gösteriyorsa `e2e_` hesapları oraya yazılmaz, koşu baştan durur.

## Yerelde çalıştırmak

API modelsiz çalışmalı. `model-state.spec.ts` bunu `/system/health` ile kontrol eder. Web'in `NEXT_PUBLIC_API_URL`'i `E2E_API_URL` ile aynı olmalı (ikisinin de varsayılanı `http://127.0.0.1:8000`).

```bash
# 1. Ayrı bir PostgreSQL
docker run -d --name sf404-pg -e POSTGRES_USER=sentinelflow -e POSTGRES_PASSWORD=sf404_local \
  -e POSTGRES_DB=sentinelflow_e2e -p 55432:5432 postgres:16-alpine

# 2. Ortam (repo kökündeki .env bu değerleri ezmemeli)
export DATABASE_URL=postgresql+psycopg2://sentinelflow:sf404_local@localhost:55432/sentinelflow_e2e
export JWT_SECRET_KEY=$(openssl rand -hex 32)
export E2E_PASSWORD=E2e-$(openssl rand -hex 12)
export SENTINELFLOW_MODEL_DIR=build/e2e/no-model

# 3. Build ve test (sentinelflow-web içinde)
npx playwright install chromium
npm run build
npm run test:e2e
```

Windows'ta (PowerShell) 2. adım:

```powershell
$env:DATABASE_URL = 'postgresql+psycopg2://sentinelflow:sf404_local@localhost:55432/sentinelflow_e2e'
$env:JWT_SECRET_KEY = -join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })
$env:E2E_PASSWORD = 'E2e-' + [guid]::NewGuid().ToString('N').Substring(0, 24)
$env:SENTINELFLOW_MODEL_DIR = 'build/e2e/no-model'
```

API (`127.0.0.1:8000`) ve web (`127.0.0.1:3000`) çalışmıyorsa Playwright ikisini kendisi başlatır. Çalışıyorlarsa onları kullanır. Bu durumda açık API'nin de yukarıdaki test veritabanına bağlı olması gerekir; geliştirme API'si açıksa önce onu kapatın.

Python varsayılan olarak repo kökündeki `.venv`'den alınır (`.venv/bin/python` ya da Windows'ta `.venv/Scripts/python.exe`). Başka bir yorumlayıcı için `E2E_PYTHON` kullanın.

Başarısız testin trace'i, ekran görüntüsü ve videosu `test-results/` altında kalır:

```bash
npx playwright show-trace test-results/<test>/trace.zip
```

## CI

`ci.yml` → *E2E (Playwright)*: PostgreSQL servisi, modelsiz API (uvicorn), `npm run build` ve `next start`. JWT anahtarı ve test şifresi her koşuda yeniden üretilir. Retry yoktur, bu yüzden kararsız bir test job'u kırmızıya çevirir. Başarısız koşuda `e2e-results` artifact'ı trace, ekran görüntüsü, video, HTML raporu ve API/web loglarını içerir.
