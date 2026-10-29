# Veri kartı — SAML-D eğitim veri seti (ML-02)

**Sahip:** Alper (@alper-tekin) · **İş:** issue #17 · **Kod:** `src/sentinelflow/ml/samld_dataset.py`
**Sözleşme:** `docs/contracts/sprint4-ml-api.md` §1 · **Karar kaydı:** ADR 0003 §2–§3
**`transform_version`:** `samld-v1` · **`dataset_id`:** `samld-e8dfe86cce3f`
**Manifest:** [`samld-manifest.json`](samld-manifest.json) (tam veriyle üretilmiş kopya)

## 1. Kaynak

| | |
|---|---|
| Ad | Anti Money Laundering Transaction Data (SAML-D) — Oztas vd., 2023 |
| Dağıtım | Kaggle `berkanoztas/synthetic-transaction-monitoring-dataset-aml`, **sürüm 2** (son güncelleme 2024-01-12) |
| Dosya | `archive.zip` → `SAML-D.csv` (996.168.850 bayt) |
| `SAML-D.csv` SHA-256 | `5b71ce2ea7b47fe6f19da1aa151776b04ec74560a852c2c077df91d20b8b4ef9` |
| `archive.zip` SHA-256 | `87476ada943fc698ab30bc9ee132c68324ae762e4f9addb61d5347af3a738a00` (Kaggle yeniden paketlerse değişebilir; asıl kimlik CSV hash'idir) |
| Lisans | **CC BY-NC-SA 4.0** (Kaggle API `datasets/view`, 2026-10-29'da okundu) |

SAML-D **sentetik** bir AML işlem veri setidir; gerçek müşteri verisi içermez.

**Lisans notu:** CC BY-NC-SA 4.0 ticari olmayan kullanıma, atıf ve aynı lisansla
paylaşma koşuluyla izin verir. Bitirme projesi (ticari olmayan, akademik) kullanımı bu
koşullara uygundur; atıf bu kartta ve model kartında verilir. Ham veri ve dönüştürülmüş
parquet repoya girmez (`data/` ve `*.parquet` ignore). Paylaşılırsa aynı lisansla ve
atıfla paylaşılmalıdır; ürünün ticari dağıtımında bu veriyle eğitilmiş model ayrıca
değerlendirilmelidir.

### Tekrar üretme

```bash
# Kaggle'dan sürüm 2'yi indir (hesap gerekir), sonra:
python -m sentinelflow.ml.samld_dataset --source path/to/archive.zip --out data/samld
# ya da: SENTINELFLOW_SAMLD_PATH=path/to/SAML-D.csv python -m sentinelflow.ml.samld_dataset
```

Komut `data/samld/<dataset_id>/transactions.parquet` ve `manifest.json` yazar. CSV
hash'i yukarıdakiyle aynıysa `dataset_id`, satır/sınıf sayıları, bölme sınırları ve
`output.content_sha256` aynı çıkar (testte iki çalıştırmanın aynı manifesti ürettiği
doğrulanır; tam veride de iki koşu bayt bayt aynı `manifest.json` üretti, 2026-10-29). Örnekleme ve rastgelelik yoktur (`seed: null`).

## 2. Dönüşüm (etiketli, gerçek kur/coğrafya değil)

> **Uyarı:** Aşağıdaki para birimi, ülke ve tutar dönüşümleri ürünü Türkiye bağlamında
> göstermek için seçilmiş **etiketli dönüşümlerdir**. **Gerçek döviz kuru değildir,
> gerçek coğrafi veri değildir.** TRY tutarları gerçek TL büyüklükleri olarak
> yorumlanmamalı; `TR` ülkesi gerçek Türk bankacılık trafiğini temsil etmez.

| Kanonik alan | Kaynak | Kural |
|---|---|---|
| `transaction_id` | satır sırası | `SAMLD-<0 tabanlı kaynak satırı, 9 hane>`; kaynak zaman sıralı olduğundan `(timestamp, transaction_id)` sırası kaynak sırasıdır |
| `timestamp` | `Date` + `Time` | Kaynakta saat dilimi yok; **UTC kabul edilir**, tz-aware |
| `sender_account` / `receiver_account` | `Sender_account` / `Receiver_account` | **Değiştirilmeden** string (yalnız rakam olduğu doğrulanır); geçmiş anahtarı, doğrudan özellik değil |
| `amount` | `Amount` | **Her satırda** `× 50`, 2 ondalık, TRY etiketi. SAML-D tutarları para biriminden bağımsız aynı (sterlin) ölçekte: ödeme para birimine göre medyan 6.046 (GBP) – 7.652 (Naira), Yen 7.176. Bu yüzden ölçek tüm satırlara uygulanır |
| `payment_currency` / `received_currency` | `Payment_currency` / `Received_currency` | ISO 4217; **UK pounds → `TRY`, Turkish lira → `GBP`** (yer değiştirme), diğerleri kendi kodu |
| `sender_country` / `receiver_country` | `Sender_bank_location` / `Receiver_bank_location` | ISO 3166 alpha-2 **ülke** kodu (şehir değil); **UK → `TR`, Turkey → `GB`** (yer değiştirme), diğerleri kendi kodu |
| `payment_type` | `Payment_type` | snake_case: `ach`, `cash_deposit`, `cash_withdrawal`, `cheque`, `credit_card`, `cross_border`, `debit_card` |
| `is_laundering` | `Is_laundering` | int8 {0,1}; **hedef** |
| `laundering_type` | `Laundering_type` | Olduğu gibi; **yalnız raporlama** (tipoloji başına recall), özellik girdisi değil |

Bilinmeyen kategori `unknown` olur ve manifestte `unknown_category_counts` altında
sayılır (tam veride hepsi 0).

**Neden yer değiştirme:** Kaynakta UK'nin yanında gerçek `Turkey` (gönderen 20.902,
alıcı 35.586 satır) ve `Turkish lira` de var. Hepsini `TR`/`TRY` yapmak (önceki v5
dönüşümü) UK→Turkey işlemlerini TR→TR gösterir ve sınır ötesi bilgisini siler. UK↔Turkey
ve GBP↔TRY yer değiştirmesi eşlemeyi bire bir tutar (Alper kararı, 2026-10-29).

### Görüntüleme sütunları (yalnız demo/UI)

`sender_iban`, `sender_name`, `receiver_iban`, `receiver_name` hesap kimliğinden
**deterministik** türetilir (RNG yok; aynı hesap her çalıştırmada aynı değeri alır):

- IBAN: `TR` + mod-97 kontrol hanesi + 5 haneli **kurgusal** banka kodu (`90001`–`90011`,
  gerçek bir bankaya ait değil) + `0` + hesap kimliğinin 16 haneye sıfırla doldurulmuş
  hâli. Hesap → IBAN bire birdir; IBAN'lar çakışmaz.
- İsim: sabit Türkçe ad/soyad listelerinden, `sha256("samld-v1:<hesap>")` ile seçilir;
  hesapların ~%45'i iki adlıdır. Gerçek kişilere ait değildir.

Bu sütunlar **model girdisi değildir** ve geçmiş anahtarı olarak kullanılmaz; anahtar
`*_account` alanlarıdır. Sözleşme §1'de yer almadıkları için ek bir CONTRACT-REQUEST
ile önerilir.

## 3. Zaman bölmesi

- Sıralama `(timestamp, transaction_id)`; oranlar ADR 0003 §3: kronolojik **%70 / %15 / %15**
  (satır sayısına göre).
- Kesim noktası bir zaman damgası grubunun içine düşerse kesim grubun sonuna kayar;
  aynı zaman damgalı satırlar sınırda ayrılmaz. Kod `max(train) < min(val)` ve
  `max(val) < min(test)` koşullarını doğrular, tutmazsa yazmaz.
- Örnekleme **yok**: val ve test doğal sınıf dağılımında. Train'de negatif alt
  örnekleme ML-04'te yalnız etiketli satır seçiminde yapılabilir; geçmiş özellikleri
  (ML-03) bütün olay akışından hesaplanmalıdır. Bu yüzden çıktı tek dosyadır ve `split`
  sütunu taşır.

| Bölme | Satır | Pozitif | Pozitif oranı | İlk zaman damgası (UTC) | Son zaman damgası (UTC) |
|---|---:|---:|---:|---|---|
| train | 6.653.397 | 6.764 | %0,102 | 2022-10-07T10:35:19+00:00 | 2023-05-18T19:28:03+00:00 |
| val | 1.425.727 | 1.412 | %0,099 | 2023-05-18T19:28:08+00:00 | 2023-07-05T15:24:39+00:00 |
| test | 1.425.728 | 1.697 | %0,119 | 2023-07-05T15:24:42+00:00 | 2023-08-23T10:57:12+00:00 |

Boşluklar: train→val 5 sn, val→test 3 sn (sınırdaki zaman damgaları farklı).

## 4. Sayılar (tam veri)

- Satır: **9.504.852** · pozitif (`is_laundering=1`): **9.873** (%0,104) · negatif: 9.494.979
- Farklı hesap: 855.460 · zaman aralığı: 2022-10-07T10:35:19+00:00 → 2023-08-23T10:57:12+00:00
- Bilinmeyen kategori: 0 (tüm alanlar)
- Çıktı: `transactions.parquet` (570.100.929 bayt), `content_sha256` `0874f6d8ccae3906b030e6a6ce06a83f272dd446e2050a333b3567f17ff9fca8`
- Üreten kod: git `2f7938a8fb0b43db4522deb5447bb0371eeb0000` (temiz ağaç), `transform_version` `samld-v1`

Şüpheli tipoloji destekleri (yalnız pozitifler):

| Tipoloji | train | val | test |
|---|---:|---:|---:|
| Behavioural_Change_1 | 261 | 71 | 62 |
| Behavioural_Change_2 | 197 | 86 | 62 |
| Bipartite | 320 | 37 | 26 |
| Cash_Withdrawal | 920 | 173 | 241 |
| Cycle | 267 | 66 | 49 |
| Deposit-Send | 648 | 134 | 163 |
| Fan_In | 260 | 68 | 36 |
| Fan_Out | 92 | 87 | 58 |
| Gather-Scatter | 229 | 43 | 82 |
| Layered_Fan_In | 476 | 92 | 88 |
| Layered_Fan_Out | 376 | 53 | 100 |
| Over-Invoicing | 33 | 14 | 7 |
| Scatter-Gather | 249 | 43 | 46 |
| Single_large | 185 | 31 | 34 |
| Smurfing | 653 | 127 | 152 |
| Stacked Bipartite | 285 | 93 | 128 |
| Structuring | 1.313 | 194 | 363 |

Testte destek < 30 olan tipolojiler: `Over-Invoicing` (7) ve `Bipartite` (26). ADR 0003 §7'deki tipoloji başına recall hedefi bunlara uygulanmaz; destek sayısıyla raporlanır.

## 5. Bilinen sınırlamalar

- Sentetik veri: tipolojiler üreticinin kurallarını yansıtır; gerçek dünyaya genelleme
  sınırlıdır.
- Zaman dilimi kaynakta yok; UTC kabulü saat/gün özelliklerini yalnız göreli anlamlı kılar.
- `payment_type = cross_border` olan her satırda ülkeler farklı; ama ülkeleri farklı
  417 satırın ödeme tipi `cross_border` değil (kaynağın kendi özelliği; dönüşüm bunu
  değiştirmez). Yer değiştirme sayesinde aynı-ülke `cross_border` satırı yok (v5'te 53.391 vardı).
- Hesap kimlikleri sayısal; IBAN/isim yalnız görüntüleme içindir, gerçek doğrulama
  (KYC, IBAN banka kodu) anlamı taşımaz.
