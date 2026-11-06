# Sprint 4 gerçek ML demosu (SF-403)

Bu senaryo, ML-05 model paketini Docker'daki API'ye yükler ve bir demo
işleminden üretilen ML alarmını bir vakaya bağlar.

## 1. Modeli yükle ve servisleri başlat

Docker Desktop çalışırken, temiz bir demo ortamında [Sprint 3 kurulum
adımlarını](SPRINT3_DEMO.md#başlangıç) izleyin. Sprint 3 fixture alarmı ekleme
adımını atlayın.

Gerçek `fraud-lgbm-20261030-0e0c647` ML-05 paketinin dört dosyasını
(`model.txt`, `metadata.json`, `model_card.md`, `SHA256SUMS`)
`models/fraud/current/` dizinine yerleştirin. Bu paket ekipten alınabilir
veya dondurulmuş ML-04 çıktılarından `python -m sentinelflow.ml.training package`
ile oluşturulabilir. Model dosyalarını Git'e eklemeyin.

API'nin model klasörünü salt okunur bağlaması gerekir. Compose dosyanızda
bağlama henüz yoksa repo kökünde yerel bir `compose.sf403.yml` oluşturun:

```yaml
services:
  api:
    environment:
      SENTINELFLOW_MODEL_DIR: /app/models/fraud/current
    volumes:
      - ./models:/app/models:ro
```

```powershell
docker compose -f docker-compose.yml -f compose.sf403.yml --profile frontend up -d --build
docker compose -f docker-compose.yml -f compose.sf403.yml ps -a
```

Bağlama ana Compose dosyasında varsa ek dosya ve `-f` seçenekleri gerekmez.
Yönetici hesabını Sprint 3 belgesindeki seed adımıyla oluşturun.

## 2. İşlemden ML alarmı üret

```powershell
$api = 'http://localhost:8000/api/v1'
$cred = Get-Credential -UserName admin -Message 'Demo hesabı'
$login = @{
    username = $cred.UserName
    password = $cred.GetNetworkCredential().Password
} | ConvertTo-Json
$token = Invoke-RestMethod "$api/auth/login" -Method Post -ContentType 'application/json' -Body $login
$headers = @{ Authorization = "Bearer $($token.access_token)" }

$active = Invoke-RestMethod "$api/ml/models" -Headers $headers
if ($active.status -ne 'loaded' -or $active.model.model_version -ne 'fraud-lgbm-20261030-0e0c647') {
    throw 'Beklenen ML-05 modeli yüklenmedi.'
}
$active.model | Select-Object model_version, threshold

$transaction = @{
    transaction_id = "SF403-$([guid]::NewGuid().ToString('N'))"
    sender_iban = 'TR330006100519786457841326'
    sender_name = 'Demo Sender'
    receiver_iban = 'TR110006400000468521793064'
    receiver_name = 'Demo Receiver'
    amount = 25000
    currency = 'TRY'
    received_currency = 'USD'
    sender_country = 'TR'
    receiver_country = 'TR'
    payment_type = 'cash_withdrawal'
} | ConvertTo-Json
$result = Invoke-RestMethod "$api/transactions" -Method Post -Headers $headers -ContentType 'application/json' -Body $transaction
if (!$result.is_fraud -or !$result.alerts -or $result.model_version -ne $active.model.model_version) {
    throw 'Beklenen model alarmı üretilmedi.'
}

$alertId = $result.alerts[0].alert_id
$alert = Invoke-RestMethod "$api/alerts/$alertId" -Headers $headers
$evidence = $alert.evidence | Where-Object detector_type -eq 'ml_model'
if (!$evidence -or $evidence.details.model_version -ne $active.model.model_version -or
    $evidence.details.score -lt $evidence.details.threshold -or !$evidence.details.top_features) {
    throw 'Alarmın model kanıtı eksik veya tutarsız.'
}
$evidence.details | ConvertTo-Json -Depth 5
```

Beklenen eşik yaklaşık `0.113`. Alarm detayında model sürümü, skor, eşik ve
ilk özellik katkıları görünür. Her çalıştırmada farklı işlem kimliği kullanılır.

## 3. Vakayı ve olay geçmişini doğrula

```powershell
$caseBody = @{ title = "SF-403 ML demo $alertId"; alert_ids = @($alertId) } | ConvertTo-Json
$case = Invoke-RestMethod "$api/cases" -Method Post -Headers $headers -ContentType 'application/json' -Body $caseBody
$timeline = Invoke-RestMethod "$api/cases/$($case.case_id)/events" -Headers $headers
if ('case_created' -notin $timeline.events.event_type -or
    'alert_linked_to_case' -notin $timeline.events.event_type) {
    throw 'Vaka oluşturma veya alarm bağlama olayı eksik.'
}
$timeline.events | Select-Object event_type, created_at
```

Web'de aynı hesapla giriş yapın. Panoda aktif model sürümünü, alarm detayında
model değerlendirmesini ve vaka detayında oluşturma ile alarm bağlama olaylarını
kontrol edin.

## 4. Aynı modeli Kafka detector ile doğrula

Repo kökünde şu PowerShell komutlarını çalıştırın. Model bağlantısı için ek
Compose dosyası kullandıysanız `$composeFiles` tanımındaki iki dosyayı da verin.

```powershell
$composeFiles = @('-f', 'docker-compose.yml')
if (Test-Path compose.sf403.yml) { $composeFiles += @('-f', 'compose.sf403.yml') }
docker compose @composeFiles ps -a kafka neo4j neo4j-init
docker compose @composeFiles exec -T kafka kafka-topics --bootstrap-server kafka:29092 --create --if-not-exists --topic transactions --partitions 1 --replication-factor 1
docker compose @composeFiles run -d --no-deps --name sf403-detector api python -m sentinelflow.processor.detector --no-dashboard
docker logs sf403-detector
```

Kafka ve Neo4j `healthy`, `neo4j-init` ise `Exited (0)` olmalı. Detector
günlüğünde `Fraud model loaded: fraud-lgbm-20261030-0e0c647` satırını görün.
Sonraki bloğun ilk komutuyla Kafka tüketici grubunun `transactions` bölümüne
atandığını doğrulayın, ardından işlemi gönderin.

```powershell
docker compose @composeFiles exec -T kafka kafka-consumer-groups --bootstrap-server kafka:29092 --describe --group sentinelflow-detectors --members --verbose
$kafkaTx = $transaction | ConvertFrom-Json
$kafkaTx.transaction_id = "SF403-KAFKA-$([guid]::NewGuid().ToString('N'))"
$kafkaTx | Add-Member -NotePropertyName timestamp -NotePropertyValue ([datetime]::UtcNow.ToString('o'))
$kafkaTx | ConvertTo-Json -Compress | docker compose @composeFiles exec -T kafka kafka-console-producer --bootstrap-server kafka:29092 --topic transactions
```

Birkaç saniye sonra alarm listesinde yeni işlem kimliğini arayın. Detector
tarafından kaydedilen alarmda API ile aynı model sürümü ve beş katkı görünmeli.

```powershell
$alerts = Invoke-RestMethod "$api/alerts?fraud_type=ml_model" -Headers $headers
$kafkaAlert = $alerts.alerts | Where-Object transaction_id -eq $kafkaTx.transaction_id
if (!$kafkaAlert) { throw 'Kafka işleminin alarmı henüz görünmüyor.' }
$kafkaEvidence = $kafkaAlert.evidence | Where-Object detector_type -eq 'ml_model'
if ($kafkaEvidence.details.model_version -ne $active.model.model_version -or
    $kafkaEvidence.details.top_features.Count -ne 5) {
    throw 'Detector alarmındaki model kanıtı uyuşmuyor.'
}
$kafkaEvidence.details | ConvertTo-Json -Depth 5
```

## 5. Docker smoke sonucu (6 Kasım 2026)

Ayrı Docker Compose projesinde PostgreSQL, Redis, Kafka, Neo4j, API ve web
sağlık kontrollerinden geçti. `neo4j-init` çıkış kodu `0` döndü. Yerel koşuda
Neo4j için [Sprint 3 belgesindeki](SPRINT3_DEMO.md#başlangıç) UBI8 imajı
kullanıldı.
API imajına LightGBM'in OpenMP çalışma zamanı (`libgomp1`) eklendikten sonra
model yüklendi. Demo işlemi yaklaşık `0.99864` skorla `0.11301` eşiğini
geçti. API, beş özellik katkısı içeren `ml_model` alarmı üretti.
Alarmdan vaka oluşturuldu ve API olay geçmişinde `case_created` ile
`alert_linked_to_case` görüldü. Chromium'da giriş yapıldı, aktif model kartı
ve alarm açıklaması görüldü, alarmdan vaka oluşturuldu ve her iki olay
geçmişte görüntülendi.

Kafka'ya gönderilen ayrı işlemden detector aynı model sürümü, skor, eşik ve
beş katkıyla bir alarm üretti. Alarm PostgreSQL'e kaydedildi ve API üzerinden
okundu. Neo4j Community, detector'un istediği Enterprise'a özgü property
existence constraint için bir uyarı verdi. Neo4j şema kurulumu ve demo
akışı başarıyla tamamlandı.
