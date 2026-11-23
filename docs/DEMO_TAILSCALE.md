# Kendi bilgisayarından demo: Docker Compose + Tailscale Funnel

SentinelFlow her zamanki Docker Compose kurulumuyla geliştiricinin bilgisayarında çalışır.
Hocaların veya danışmanın kendi cihazlarından açması gerektiğinde,
[Tailscale Funnel](https://tailscale.com/kb/1223/funnel) bilgisayardaki tek bir portu
geçici bir genel HTTPS adresine (`https://<makine>.<tailnet>.ts.net`) bağlar. Sunucu,
alan adı veya sertifika gerekmez. Adres yalnız bilgisayar açıkken ve Funnel açıkken
çalışır.

```
Hocanın tarayıcısı ──HTTPS──▶ Tailscale Funnel ──▶ 127.0.0.1:8088 (Caddy)
                                                   ├─ /api/*, /ws/*  ──▶ api:8000
                                                   └─ diğer her şey  ──▶ frontend:3000
```

Bu kurulumun parçaları:

| Dosya | Ne yapar |
|---|---|
| `deploy/funnel/compose.funnel.yml` | Compose override'ı: tüm portları yalnız `127.0.0.1`'e bağlar (Wi-Fi/LAN'dan erişilemez), web'i aynı-köken (`same-origin`) modunda derler, kayıt uç noktasını kapatır, 8088'de Caddy başlatır. |
| `deploy/funnel/Caddyfile` | Tek port üzerinden yönlendirme; `/metrics`, `/docs` ve kayıt dışarıya kapalı. |
| `scripts/funnel.ps1` | Yığını başlatır, sağlığı bekler, Funnel'ı açar ve paylaşılacak adresi yazar; `-Stop` ile kapatır. |

Komutlar PowerShell içindir ve repo kökünde çalıştırılır.

## 1. Bir kerelik hazırlık

1. **Docker Desktop** kurulu ve çalışıyor olmalı.
2. **Tailscale**'i kurun (<https://tailscale.com/download>) ve giriş yapın:

   ```powershell
   tailscale up
   ```

3. Funnel'ı tailnet'te bir kez açın. İlk `tailscale funnel` komutu, gerekiyorsa
   yönetici konsolunda HTTPS sertifikalarını ve Funnel'ı etkinleştirmek için bir bağlantı
   yazar; bağlantıyı açıp onaylayın. Ücretsiz kişisel plan yeterlidir.
4. Model paketini indirin ([Sprint 4 demosu §1](SPRINT4_DEMO.md#1-modeli-yükle-ve-servisleri-başlat)).
   Model yoksa uygulama çalışır ama ML alarmı üretilmez.

## 2. `.env`

`.env.example` dosyasını `.env` olarak kopyalayın ve en az `POSTGRES_PASSWORD`,
`NEO4J_PASSWORD`, `JWT_SECRET_KEY` değerlerini doldurun. Adres internete açılacağı için
güçlü, rastgele değerler kullanın:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

> **Demo dönemi kararı:** Şu anki her şey demo olduğu için ekip, demo bilgisayarının `.env`
> dosyasını ve demo hesap parolalarını (`demo-accounts.txt`) repoya ekledi. Repo herkese açık
> olduğundan bu değerler **herkes tarafından okunabilir**: Funnel açıkken adresi bilen herkes
> bu hesaplarla giriş yapabilir ve `JWT_SECRET_KEY` ile token üretebilir. Bu yüzden Funnel
> yalnız demo süresince açılır. Gerçek bir ortama geçilmeden önce bütün değerler yenilenir ve
> `.env` repodan çıkarılır.
`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL` ve `CORS_ORIGINS` bu kurulumda **gerekmez**:
web, açıldığı adresin `/api` ve `/ws` yollarını kullanır.

## 3. Başlatma

```powershell
.\scripts\funnel.ps1
```

Betik sırasıyla:

1. `docker compose -f docker-compose.yml -f deploy/funnel/compose.funnel.yml up -d --build`
   çalıştırır,
2. `http://127.0.0.1:8088/api/v1/system/health` yanıt verene kadar bekler,
3. `tailscale funnel --bg 8088` ile Funnel'ı açar,
4. paylaşılacak adresi yazar: `Paylaşılacak adres: https://<makine>.<tailnet>.ts.net`.

Funnel olmadan prova için `.\scripts\funnel.ps1 -LocalOnly` kullanın ve
<http://localhost:8088> adresini açın; hocaların göreceği ekranın aynısıdır. Görüntüler
değişmediyse `-NoBuild` ile yeniden derlemeden başlatabilirsiniz.

İlk açılışta Tailscale sertifikayı alırken ve DNS kaydı yayılırken adresin açılması birkaç
dakika sürebilir.

## 4. Demo hesapları

Kayıt uç noktası bu kurulumda kapalıdır; hesaplar seed betiğiyle açılır. Parola komut
satırına değil ortam değişkenine verilir:

```powershell
$cred = Get-Credential -UserName analyst -Message 'Analist demo parolası'
$env:SEED_ADMIN_PASSWORD = $cred.GetNetworkCredential().Password
docker compose -f docker-compose.yml -f deploy/funnel/compose.funnel.yml exec -T -e SEED_ADMIN_PASSWORD api python scripts/seed_admin.py --role analyst --no-generate
Remove-Item Env:SEED_ADMIN_PASSWORD
```

Aynısını `--role viewer` (ve gerekirse `--role admin`) için tekrarlayın. Demo bilgisayarındaki
`admin`, `analyst` ve `viewer` hesaplarının şu anki parolaları repodaki `demo-accounts.txt`
dosyasındadır. Betik var olan
kullanıcıyı değiştirmez. Hocalara adres ve hesap bilgisini özel bir kanaldan iletin;
demodan sonra parolaları uygulamadaki **Parola değiştir** menüsünden değiştirin.

## 5. Demo akışı

[Sprint 5 demosu §3–4](SPRINT5_DEMO.md#3-analist-senaryosu-tarayıcıda) aynen geçerlidir;
`<alan>` yerine Funnel adresini kullanın. Kafka ve Neo4j bu kurulumda varsayılan olarak
çalıştığı için ağ grafiği sayfası da veri gösterir.

## 6. Kapatma

```powershell
.\scripts\funnel.ps1 -Stop     # genel adres kapanır, konteynerler yerelde çalışmaya devam eder
.\scripts\funnel.ps1 -Down     # Funnel kapanır ve konteynerler durur (veriler korunur)
```

`tailscale funnel status` ile Funnel'ın kapalı olduğunu doğrulayın.

## 7. Güvenlik notları

- Funnel açıkken adres **internetteki herkese açıktır**; yalnız demo süresince açın.
- Dışarıya yalnız 8088'deki ters vekil açılır. Veritabanı, Redis, Kafka, Neo4j ve yönetim
  arayüzleri yalnız `127.0.0.1`'de dinler; aynı Wi-Fi'deki cihazlar da erişemez.
- `/metrics`, `/docs`, `/redoc`, `/openapi.json` ve kayıt (`POST /auth/register`) dışarıya
  kapalıdır. Bu bilgisayarda API belgeleri <http://localhost:8000/docs> adresinde açık kalır.
- Yalnız sentetik demo verisi kullanılır; gerçek kişisel veri girilmez (KVKK).
- Bilgisayar uykuya geçerse veya ağ değişirse adres geçici olarak açılmaz. Demo sırasında
  uyku modunu kapatın.

## 8. Sorun giderme

| Belirti | Bakılacak yer |
|---|---|
| `Tailscale bulunamadı` | Tailscale kurulu mu; `tailscale version` |
| `Tailscale bağlı değil` | `tailscale up` |
| Funnel komutu bir bağlantı yazıp duruyor | Bağlantıyı açıp tailnet'te HTTPS ve Funnel'ı etkinleştirin, komutu tekrar çalıştırın |
| API 3 dakikada hazır olmadı | `docker compose -f docker-compose.yml -f deploy/funnel/compose.funnel.yml logs api caddy` |
| Sayfa açılıyor, giriş başarısız | Hesap seed edildi mi (§4); `logs api` |
| Canlı alarm akışı bağlanmıyor | Tarayıcı konsolunda `wss://<adres>/ws/alerts`; `logs caddy` |
| `port is already allocated` | 3000, 8000, 8088 vb. portu kullanan başka bir uygulama veya eski konteyner |
