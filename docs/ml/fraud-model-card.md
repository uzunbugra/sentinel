# Model kartı — `fraud-lgbm-20261030-0e0c647`

## Özet

- **Görev:** işlem başına ikili sınıflandırma, kara para aklama şüphesi (SAML-D `is_laundering`). Skor ≥ eşik → ML alarmı (`fraud_type = ml_model`).
- **Model:** LightGBM `binary`, 190 ağaç, `max_depth` 6, `num_leaves` 31, öğrenme oranı 0.1; kalibrasyon yok.
- **Özellikler:** `fs-1`, 15 özellik (sözleşme §2); kategorik: `payment_type_code`, `sender_country_code`, `receiver_country_code`.
- **Eşik:** `0.11301326300215633` — validation'da precision ≥ 0.20 koşulunda en yüksek recall (ADR 0003 §6). Testte yeniden ayarlanmadı.
- **Veri:** `samld-e8dfe86cce3f` (SAML-D, sentetik; CC BY-NC-SA 4.0, Oztas vd. 2023). Veri kartı: `docs/ml/samld-data-card.md`.
- **Eğitim:** 2026-10-30T15:27:54+00:00, commit `0e0c647b66785fff9bd76a0999c800f75f08c103`.

## Kilitli test sonuçları

| PR-AUC | ROC-AUC | Precision | Recall | F1 | Pozitif | Toplam | LR tabanı PR-AUC |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.6152 | 0.9835 | 0.2457 | 0.6671 | 0.3591 | 1.697 | 1.425.728 | 0.0628 |

Tüm ADR 0003 §7–§8 hedefleri ve tipoloji recall'u: `reports/ml04/report.md`.

## Eğitim verisi ve örnekleme

- Zaman bölmesi %70 / %15 / %15 (train / validation / test), test kilitli ve bir kez açıldı.
- Train negatifleri özellikler hesaplandıktan sonra 0.25 oranında örneklendi (seed 20261030); validation ve test doğal dağılımda.
- Hesap geçmişi özellikleri tüm olay akışı üzerinden, yalnız önceki olaylarla hesaplandı.

## Kullanım ve sınırlar

- Skor ham LightGBM olasılığıdır; eğitimde negatifler alt örneklendiği için gerçek olasılık olarak **yorumlanmamalıdır** — yalnız eşikle karşılaştırılır.
- Veri sentetiktir; tipolojiler simülatörün kurallarını yansıtır, gerçek trafiğe genelleme doğrulanmamıştır. Para birimi/ülke dönüşümleri etiketlidir (veri kartı §2).
- Servis yeniden başlayınca hesap geçmişi boştur (cold-start); ilk işlemlerde geçmiş özellikleri 0 olur ve skor eğitimdeki dağılımdan sapabilir.
- Model insan incelemesine alarm üretir; tek başına işlem engelleme kararı için kullanılmaz. Kural motorlarının yerine geçmez.
- Recall'u 0.5'in altında kalan tipolojiler (destek ≥ 30): Behavioural_Change_1 (0.42), Cycle (0.22), Fan_Out (0.33), Gather-Scatter (0.46), Layered_Fan_Out (0.27), Single_large (0.41).

## Dosyalar

- `model.txt` SHA-256 `75a5b44ee5febde432002994ea3fb903689a7da7e966518a6380d2c5b1f2fcd5` (LightGBM metin formatı, pickle yok); `metadata.json` sözleşme §3; `SHA256SUMS`.
- Kütüphaneler: python 3.13.7, lightgbm 4.7.0, numpy 2.5.4, pandas 3.1.0, scikit-learn 1.9.1, pyarrow 26.0.0.
