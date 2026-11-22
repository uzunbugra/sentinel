# SentinelFlow canlı ortam runbook'u

Sprint 5 (`docs/SPRINT5_PLAN.md`) canlı ortamının kurulum, güncelleme, geri alma, yedekten
dönme ve izleme adımları. Hedef: ekipten ikinci bir kişi yalnız bu belgeyle makineyi sıfırdan
kurabilsin. Sunucuda elle yapılan her değişiklik aynı gün buraya yazılır (plan §3).

> **Sırlar bu belgeye, issue'lara, commit'lere ve ekran görüntülerine yazılmaz.** Aşağıda
> yalnız sırların *nerede* durduğu yazılıdır, değerleri değil.

## İçindekiler

1. [Dosyalar ve sırlar](#1-dosyalar-ve-sırlar)
2. [Sıfırdan kurulum](#2-sıfırdan-kurulum)
3. [Bellek bütçesi](#3-bellek-bütçesi)
4. [Yeni sürüme geçiş](#4-yeni-sürüme-geçiş)
5. [Önceki sürüme dönüş](#5-önceki-sürüme-dönüş)
6. [Yedekleme ve yedekten dönme](#6-yedekleme-ve-yedekten-dönme)
7. [İzleme](#7-izleme)
8. [Sorun giderme](#8-sorun-giderme)
9. [Açık konular](#9-açık-konular)

Tüm komutlar sunucuda, `/opt/sentinelflow` (repo kökü) içinde çalıştırılır. Kısaltma:

```bash
alias dc='docker compose -f docker-compose.yml -f deploy/compose.prod.yml'
```

## 1. Dosyalar ve sırlar

| Yol | Ne | Kim yazar |
|---|---|---|
| `deploy/compose.prod.yml` | Üretim override'ı: hiçbir servis port yayınlamaz, yalnız `caddy` 80/443 (SF-503, SF-504) | repo |
| `deploy/Caddyfile` | Ters vekil, HTTPS, `/metrics`–`/docs` kapalı, kayıt engeli (SF-504, SF-507) | repo |
| `deploy/check_ports.py` | Derlenmiş compose yapılandırmasında yasak port var mı (SF-503 kabulü) | repo |
| `deploy/backup/` | `pg_backup.sh`, `pg_restore.sh` (SF-508) | repo |
| `deploy/monitor/healthcheck.sh` | Sağlık, disk, bellek kontrolü (SF-509) | repo |
| `deploy/systemd/` | Yedek ve sağlık kontrolü zamanlayıcıları | repo |
| `/opt/sentinelflow/.env` | Uygulama sırları ve alan adı; `chmod 600`, sahibi `root` | sunucuda |
| `/etc/sentinelflow/backup.env` | `OCI_BUCKET` vb. (sır içermez) | sunucuda |
| `/etc/sentinelflow/healthcheck.env` | `SENTINELFLOW_DOMAIN`, `ALERT_WEBHOOK_URL` | sunucuda |
| `models/fraud/current/` | Model paketi (Release'den; repoda yok) | sunucuda |
| `/var/backups/sentinelflow/` | Son 7 günlük yedek | timer |
| Docker volume'ları | `sentinelflow-postgres-data`, `sentinelflow-caddy-data` (sertifikalar) … | Docker |

**Sırların yeri:** `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, `NEO4J_PASSWORD`,
`SENTINELFLOW_API_KEY`, demo hesap parolaları, SSH anahtarları ve `ALERT_WEBHOOK_URL` ekibin
ortak parola kasasında (plan §4) tutulur. Sunucuda yalnız `.env` ve
`/etc/sentinelflow/healthcheck.env` içinde bulunurlar. Canlı değerler yerel değerlerden farklı
ve güçlü olur:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 2. Sıfırdan kurulum

Ön koşul: SF-501 (Ampere A1, Ubuntu 24.04 aarch64, yalnız anahtarla SSH, root girişi kapalı,
otomatik güvenlik güncellemeleri, Docker Engine + Compose **v2.24 veya üstü**) ve SF-502
(VCN güvenlik listesi ve iptables'ta yalnız 22/80/443). `docker compose version` ile sürümü
doğrulayın; `!reset` etiketi daha eski sürümlerde çalışmaz.

### 2.1 Kod

```bash
sudo mkdir -p /opt/sentinelflow && sudo chown "$USER" /opt/sentinelflow
git clone https://github.com/uzunbugra/sentinel.git /opt/sentinelflow
cd /opt/sentinelflow
git checkout v2.3.0        # her zaman bir sürüm etiketi; main değil
```

### 2.2 `.env`

`.env.example`'dan başlayın ve en az şunları doldurun (değerler parola kasasından):

| Değişken | Değer |
|---|---|
| `POSTGRES_PASSWORD`, `NEO4J_PASSWORD`, `JWT_SECRET_KEY` | Güçlü, yerelden farklı. Neo4j çalışmasa da `NEO4J_PASSWORD` tanımlı olmalı (compose şartı). |
| `SENTINELFLOW_DOMAIN` | Alan adı, ör. `sentinel.example.org` (plan §4 kararı) |
| `ACME_EMAIL` | Ortak ekip adresi (sertifika uyarıları) |
| `ACME_CA` | İlk denemede `https://acme-staging-v02.api.letsencrypt.org/directory`; sonra satırı silin |
| `CORS_ORIGINS` | `https://<alan>` |
| `NEXT_PUBLIC_API_URL` | `https://<alan>` (web imajına derleme anında gömülür) |
| `NEXT_PUBLIC_WS_URL` | `wss://<alan>` |

`NEXT_PUBLIC_ENABLE_AUTH` tanımlanmaz (varsayılan açık); canlıda asla `false` yapılmaz.
`SENTINELFLOW_REGISTRATION_ENABLED=false` override dosyasında sabittir, `.env`'e gerekmez.

```bash
sudo chown root:root .env && sudo chmod 600 .env
```

### 2.3 Model paketi

```bash
gh release download model-fraud-lgbm-20261030-0e0c647 -R uzunbugra/sentinel -D models/fraud/current
(cd models/fraud/current && sha256sum -c SHA256SUMS)
```

Dört dosyanın hepsi `OK` olmalı.

### 2.4 Port kontrolü ve başlatma

```bash
dc --profile streaming --profile graph config --format json | python3 deploy/check_ports.py
# beklenen: "OK: no published ports except the reverse proxy (80/443)"

dc up -d --build
dc ps
```

Varsayılan olarak yalnız P0 servisler başlar: `postgres`, `redis`, `api`, `frontend`,
`caddy`. Kafka/ZooKeeper (`--profile streaming`) ve Neo4j (`--profile graph`) SF-511 kararıyla
açılır; açılırsa sonraki her `dc` komutuna aynı `--profile` bayrakları eklenir.
`kafka-ui`, `redis-commander`, `prometheus` canlıda hiç başlatılmaz (`dev-tools` profili).

### 2.5 Hesaplar (SF-506)

Kayıt uç noktası canlıda kapalıdır (#93); hesaplar yalnız seed betiğiyle açılır.
Kullanıcı adları varsayılan olarak rolün adıdır (`admin`, `analyst`, `viewer`);
`SEED_ADMIN_USERNAME` ile değiştirilebilir. Parolalar kasadan,
komut satırına değil ortam değişkenine verilir (`read -s` geçmişe yazmaz):

```bash
read -rs SEED_ADMIN_PASSWORD && export SEED_ADMIN_PASSWORD
dc exec -T -e SEED_ADMIN_PASSWORD api python scripts/seed_admin.py --no-generate
# analyst ve viewer demo hesapları (#94); her birinde parolayı yeniden okuyun:
dc exec -T -e SEED_ADMIN_PASSWORD api python scripts/seed_admin.py --role analyst --no-generate
dc exec -T -e SEED_ADMIN_PASSWORD api python scripts/seed_admin.py --role viewer --no-generate
unset SEED_ADMIN_PASSWORD
```

Betik var olan bir kullanıcıyı değiştirmez; tekrar çalıştırmak güvenlidir. Yalnız sentetik
demo işlemleri gönderilir.

### 2.6 Doğrulama

Ekip bilgisayarından:

```bash
curl -sI http://<alan>/ | head -1                       # 308 → https
curl -s https://<alan>/api/v1/system/health              # "status":"healthy"
curl -s -o /dev/null -w '%{http_code}\n' https://<alan>/metrics                       # 404
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://<alan>/api/v1/auth/register  # 403
nmap -Pn -p 1-65535 <sunucu-ip>                          # yalnız 22, 80, 443 açık
```

`GET /api/v1/ml/models` (analist token'ıyla) `status: loaded` ve
`fraud-lgbm-20261030-0e0c647` dönmelidir.

Web paketinde yerel adres kalmadığını doğrulayın (SF-505):

```bash
dc exec frontend sh -c "grep -rlE 'localhost:8000|127\.0\.0\.1' .next || echo temiz"
```

Staging sertifikasıyla her şey çalışınca `.env`'den `ACME_CA` satırını silin ve
`dc up -d caddy` ile gerçek sertifikayı alın. Let's Encrypt üretim CA'sının haftalık sınırı
olduğu için denemeler staging'de yapılır.

### 2.7 Zamanlayıcılar

```bash
sudo mkdir -p /etc/sentinelflow
printf 'SENTINELFLOW_DOMAIN=<alan>\n' | sudo tee /etc/sentinelflow/healthcheck.env >/dev/null
sudo chmod 600 /etc/sentinelflow/healthcheck.env   # webhook adresi eklenecekse
sudo cp deploy/systemd/sentinelflow-*.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sentinelflow-backup.timer sentinelflow-healthcheck.timer
systemctl list-timers 'sentinelflow-*'
```

## 3. Bellek bütçesi

Hedef: 12 GB'lık makinede tüm servisler (P0 + SF-511) sınırlar içinde kalsın. Sınırlar
`deploy/compose.prod.yml`'dadır. "Canlı" sütunu kurulumdan sonra
`docker stats --no-stream --format '{{.Name}}\t{{.MemUsage}}'` ile boşta ölçülüp doldurulur.

| Servis | Sınır | Yerel boşta (SF-500, x86_64, sınırsız) | Canlı boşta (aarch64) |
|---|---:|---:|---:|
| postgres | 512 MiB | 59 MiB | |
| redis | 384 MiB | 8 MiB | |
| api | 1 GiB | 234 MiB | |
| frontend | 384 MiB | 43 MiB | |
| caddy | 256 MiB | — | |
| **P0 toplam** | **2.5 GiB** | **~344 MiB** | |
| zookeeper (heap 256 MiB) | 512 MiB | 137 MiB | |
| kafka (heap 512 MiB) | 1 GiB | 386 MiB | |
| neo4j (heap 512 MiB, page cache 256 MiB) | 1.5 GiB | 1.23 GiB (heap 1 GiB ile) | |
| **Tümü** | **5.5 GiB** | | |

Oracle, A1 makinede bellek kullanımı 7 gün boyunca %20'nin (12 GB'ta ~2.4 GB) altında kalırsa
(CPU ve ağ da düşükse) makineyi boşta sayabilir (plan §10). Yalnız P0 ile bu eşiğin altında
kalınır; ilk hafta Oracle Monitoring'deki üç ölçüm izlenip buraya yazılır.

## 4. Yeni sürüme geçiş

1. Sürüm notlarını (`CHANGELOG.md`) okuyun; şema değişikliği var mı bakın.
2. **Önce yedek:** `sudo systemctl start sentinelflow-backup.service` ve
   `journalctl -u sentinelflow-backup -n 5` ile yeni dosyayı görün.
3. Geçiş:

   ```bash
   git fetch --tags
   git rev-parse HEAD > /var/backups/sentinelflow/previous-release   # dönüş için
   git checkout vX.Y.Z
   dc config --format json | python3 deploy/check_ports.py
   dc up -d --build
   dc ps
   ```

4. §2.6'daki doğrulamaları tekrarlayın. Model sürümü değiştiyse §2.3'ü yeni Release adıyla
   yapın.

**Şema:** API açılışta `Base.metadata.create_all` ile eksik tabloları oluşturur ama var olan
tabloyu **değiştirmez**. Var olan bir tabloya sütun eklenen sürümde Alembic migration'ı
gerekir; bu yol henüz netleşmedi (§9). O zamana kadar böyle bir sürüm canlıya alınmadan
önce Buğra'yla konuşulur.

## 5. Önceki sürüme dönüş

```bash
git checkout "$(cat /var/backups/sentinelflow/previous-release)"
dc up -d --build
```

Yeni sürüm şemayı değiştirdiyse kod dönüşü yetmez; geçişten hemen önce alınan yedeğe §6.2 ile
dönülür. Caddy sertifikaları `sentinelflow-caddy-data` volume'unda kalır, yeniden alınmaz.

## 6. Yedekleme ve yedekten dönme

### 6.1 Yedekleme (SF-508)

- `sentinelflow-backup.timer` her gün 03:15 UTC'de `deploy/backup/pg_backup.sh`'ı çalıştırır.
- Yedekler `/var/backups/sentinelflow/sentinelflow-<UTC zaman>.dump` (pg_dump custom format,
  `umask 077`). En yeni 7 dosya kalır (`KEEP_DAILY`).
- Pazar günleri en yeni yedek, `/etc/sentinelflow/backup.env` içinde `OCI_BUCKET` tanımlıysa
  Oracle Object Storage'a kopyalanır (`oci` CLI ve instance principal / API anahtarı ile;
  kurulum SF-508 kaydına yazılır). `OCI_BUCKET` boşsa günlükte uyarı çıkar.
- Elle: `sudo deploy/backup/pg_backup.sh`.

### 6.2 Yedekten dönme

**Geri yükleme testi** (üretim veritabanına dokunmaz; ayda bir ve her büyük değişiklikten
önce):

```bash
sudo deploy/backup/pg_restore.sh /var/backups/sentinelflow/<dosya>.dump
```

Boş `sentinelflow_restore_test` veritabanına yükler, tablo satır sayılarını ve süreyi yazar,
sonra siler. Yerel deneme (28 KB dump): 3 sn. Canlıdaki ilk deneme sonucu:

| Tarih | Dosya boyutu | Süre | users / alerts / cases | Yapan |
|---|---:|---:|---|---|
| | | | | |

**Gerçek dönüş:**

```bash
dc stop api frontend
sudo deploy/backup/pg_backup.sh          # o anki durumu da sakla
sudo deploy/backup/pg_restore.sh /var/backups/sentinelflow/<dosya>.dump --replace
dc up -d
```

`--replace` API çalışırken reddeder ve veritabanı adının yazılmasını ister.

## 7. İzleme

- `sentinelflow-healthcheck.timer` 5 dakikada bir `deploy/monitor/healthcheck.sh`'ı çalıştırır:
  `https://<alan>/api/v1/system/health` 200 ve `healthy`, token'sız `ml/models` 401, kök disk
  %85'in altında, kullanılabilir bellek %10'un üstünde.
- Sonuçlar: `journalctl -u sentinelflow-healthcheck -n 20`.
- Hata olursa ve `ALERT_WEBHOOK_URL` tanımlıysa kısa bir JSON mesajı (`text`/`content`) o
  adrese gönderilir; mesajda sır yoktur.
- Makinenin tamamen kapanmasını bu betik göremez. Bunun için dışarıdan bir uptime izleyicisi
  aynı sağlık adresine bakar (seçilen hizmet ve sahibi SF-509 kaydına yazılır).
- Konteyner logları: `dc logs --tail 200 <servis>` (json-file, servis başına 3 × 10 MB).

## 8. Sorun giderme

| Belirti | Bakılacak yer |
|---|---|
| Sertifika alınamıyor | `dc logs caddy`; DNS kaydı sunucu IP'sini gösteriyor mu; 80 VCN'de ve iptables'ta açık mı |
| Web açılıyor, giriş başarısız / CORS hatası | `.env`'deki `CORS_ORIGINS` ve `NEXT_PUBLIC_*`; adres değiştiyse `dc up -d --build frontend` |
| Canlı alarm akışı bağlanmıyor | Tarayıcı konsolunda `wss://<alan>/ws/alerts`; `NEXT_PUBLIC_WS_URL` `wss://` ile mi |
| `ml_model` degraded | `models/fraud/current` dört dosya ve `sha256sum -c`; `dc logs api` |
| API başlamıyor: `Set NEO4J_PASSWORD` | `.env`'de `NEO4J_PASSWORD` tanımlı olmalı, Neo4j çalışmasa da |
| Konteyner `OOMKilled` | `docker inspect <ad> --format '{{.State.OOMKilled}}'`; §3 tablosu ve sınırlar |

## 9. Açık konular

- Şema değiştiren sürümler için Alembic migration yolu (Buğra ile).
- Off-site yedeğin `oci` CLI kimlik doğrulama yöntemi (instance principal önerilir).
- Dış uptime izleyicisi ve uyarı kanalının seçimi (ekip kararı).
