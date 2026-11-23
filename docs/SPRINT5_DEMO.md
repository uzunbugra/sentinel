# Sprint 5 canlı demo ve kabul testi (SF-510)

Bu senaryo `docs/SPRINT5_PLAN.md` §8'deki bitiş kapılarını canlı adrese karşı sırayla
doğrular. Sunucunun kurulumu bu belgenin konusu değildir; kurulum, güncelleme ve yedekten
dönme için [`deploy/README.md`](../deploy/README.md) runbook'unu izleyin.

Aşağıda `<alan>` canlı alan adıdır (plan §4 kararı). Parolalar ekibin parola kasasındadır;
bu belgeye, issue'lara ve ekran görüntülerine yazılmaz. Ekran görüntüsü alırken adres
çubuğunda token, tarayıcıda parola yöneticisi açılır penceresi görünmemelidir.

Komutlar PowerShell içindir (Windows PowerShell 5.1 veya `pwsh`). Yerelde provası yapmak için
`$base = 'http://localhost:3000'` ve `$api = 'http://localhost:8000/api/v1'` kullanın.

```powershell
$base = 'https://<alan>'
$api  = "$base/api/v1"
```

## 1. Altyapı kapıları

```powershell
# HTTP -> HTTPS yönlendirmesi (beklenen: 308 ve Location: https://...)
(Invoke-WebRequest "http://<alan>/" -MaximumRedirection 0 -ErrorAction SilentlyContinue -UseBasicParsing).StatusCode

# Sağlık (beklenen: healthy)
(Invoke-RestMethod "$api/system/health").status

# Dışarıya kapalı uç noktalar (beklenen: 404 ve 403)
try { Invoke-WebRequest "$base/metrics" -UseBasicParsing } catch { $_.Exception.Response.StatusCode.value__ }
try { Invoke-WebRequest "$api/auth/register" -Method Post -ContentType 'application/json' -Body '{}' -UseBasicParsing } catch { $_.Exception.Response.StatusCode.value__ }
```

Port taraması ekip bilgisayarından (sunucunun içinden değil) yapılır; yalnız 22, 80 ve 443
açık görünmelidir:

```powershell
nmap -Pn -p 1-65535 <sunucu-ip>
```

Sertifikanın geçerli olduğunu tarayıcının adres çubuğundan doğrulayın (staging sertifikası
"güvenli değil" uyarısı verir; kabul testi gerçek sertifikayla yapılır).

## 2. Model

```powershell
$cred = Get-Credential -UserName analyst -Message 'Analist demo hesabı'
$login = @{ username = $cred.UserName; password = $cred.GetNetworkCredential().Password } | ConvertTo-Json
$token = Invoke-RestMethod "$api/auth/login" -Method Post -ContentType 'application/json' -Body $login
$headers = @{ Authorization = "Bearer $($token.access_token)" }
$models = Invoke-RestMethod "$api/ml/models" -Headers $headers
$models | ConvertTo-Json -Depth 4
```

Beklenen: `status: loaded` ve model sürümü `fraud-lgbm-20261030-0e0c647`.

## 3. Analist senaryosu (tarayıcıda)

1. `https://<alan>/login` → analist hesabıyla giriş.
2. Dashboard: üst menüde **Ağ grafiği**, **Skorlama**, **Müşteri taraması** bağlantıları ve
   parola değiştirme düğmesi görünür; "Aktif model" kartında model sürümü yazar.
3. **Demo işlem gönder** (SF-523): örneklerden şüpheli olanı seçip **Gönder**. Sonuçta
   "Şüpheli: model alarm üretti." yazar ve alarm, sayfa yenilenmeden canlı akışta görünür
   (WebSocket `wss://<alan>/ws/alerts`).
4. Alarma tıklayın: alarm detayında model sürümü, skor, eşik ve ilk 5 katkı görünür.
5. Alarmdan vaka oluşturun. Vaka sayfasındaki zaman çizelgesinde `case_created` ve
   `alert_linked_to_case` olayları görünür.
6. **Skorlama** (`/score`, SF-521): bir işlem skorlanır; skor, eşik, karar ve ilk 5 katkı
   görünür. Ekranda skorlamanın hesap geçmişini değiştirmediği yazar.
7. **Müşteri taraması** (`/kyc`, SF-522): örnek listedeki bir ad taranır; eşleşme türü, liste
   ve skor görünür. Ekranda listelerin örnek veri olduğu yazar.
8. **Parola değiştir** (SF-524): mevcut ve yeni parola girilir; başarı mesajı görünür. Çıkış
   yapıp yeni parolayla tekrar giriş yapılır. Yeni parola aynı gün kasaya yazılır.
9. **Ağ grafiği** (`/graph`, SF-520): Neo4j canlıda çalışmıyorsa (SF-511 kararı) sayfa
   "Graf veritabanı (Neo4j) bu ortamda çalışmıyor." der; bu beklenen durumdur. Neo4j açıksa
   halka listesi görünür ve bir IBAN'a tıklayınca hesap komşuluğu açılır.
10. Yardım asistanı paneli (SF-525) dashboard'da bir öneriye cevap verir; panelde kural tabanlı
    olduğu ve LLM kullanmadığı yazar.

Yanıt sürelerini tarayıcının geliştirici araçlarındaki Network sekmesinden (`/alerts`,
`/risk/score`, `/transactions` istekleri) okuyup §6 tablosuna yazın.

## 4. Viewer senaryosu

Viewer hesabıyla giriş yapın:

- Dashboard, alarm listesi, alarm detayı ve vakalar görünür.
- **Skorlama**, **Müşteri taraması** bağlantıları ve demo işlem formu görünmez; alarm
  detayında vaka oluşturma ve kapatma düğmeleri yoktur.
- `/score` adresine elle gidildiğinde yetki mesajı gösterilir.

## 5. Ağ grafiği yerel kabulü

Canlıda Neo4j yoksa plan §8 yerel kabulü yeterli sayar. Yerelde:

```powershell
docker compose --profile frontend up -d --build
```

Sprint 4 demosu §4'teki gibi Kafka detector ile birkaç işlem gönderildikten sonra
`http://localhost:3000/graph` halka listesini ve hesap komşuluğunu gösterir.

## 6. Kabul kaydı

Testi yapan kişi bu tabloyu doldurur ve sonucu Sprint 5 milestone'undaki SF-510 issue'suna
(sır içermeyen ekran görüntüleriyle) yazar.

| Kapı | Sonuç | Not |
|---|---|---|
| HTTPS geçerli sertifika, HTTP → HTTPS | | |
| `system/health` healthy | | |
| `ml/models` loaded, `fraud-lgbm-20261030-0e0c647` | | |
| Port taraması: yalnız 22/80/443 | | |
| `/metrics` 404, `register` 403 | | |
| Demo işlem → ML alarmı canlı akışta | | |
| Alarm detayı: sürüm, skor, eşik, ilk 5 katkı | | |
| Alarmdan vaka, zaman çizelgesi olayları | | |
| Skorlama, KYC, parola değiştirme | | |
| Viewer eylem düğmelerini görmüyor | | |
| Ağ grafiği (yerel / canlı) | | |
| Yedekten geri yükleme süresi (runbook §6.2) | | |

| İstek | Ölçülen süre | Tarih |
|---|---:|---|
| `GET /alerts` | | |
| `POST /risk/score` | | |
| `POST /transactions` | | |
