# ML-04 — Model değerlendirme raporu (SAML-D, fs-1)

- `dataset_id`: `samld-e8dfe86cce3f` · `feature_set_version`: `fs-1`
- Seçim (validation) commit'i: `0e0c647b66785fff9bd76a0999c800f75f08c103` · seçim zamanı 2026-10-30T15:27:54+00:00
- Test açılışı: 2026-10-30T15:28:47+00:00 (tek sefer; `test-opened.json`)
- Model `model.txt` SHA-256: `75a5b44ee5febde432002994ea3fb903689a7da7e966518a6380d2c5b1f2fcd5`

**Tüm hedefler geçti — model yayınlanabilir (ML-05).**

## Hedefler (kilitli test, ADR 0003 §7–§8)

| Hedef | Değer | Ölçüt | Sonuç | Not |
|---|---:|---|---|---|
| PR-AUC (test) | 0.6152 | >= 0.4 | ✅ geçti |  |
| PR-AUC gain vs LR baseline (test) | 8.7988 | >= 25% relative | ✅ geçti | baseline PR-AUC 0.0628 |
| Precision at validation threshold (test) | 0.2457 | >= 0.15 | ✅ geçti |  |
| Recall at validation threshold (test) | 0.6671 | >= 0.5 | ✅ geçti |  |
| Typology recall (support >= 30, test) | 0.2245 | >= 0.2 for each of 15 typologies | ✅ geçti |  |
| Artifact size | 636.601 | <= 5242880 bytes | ✅ geçti |  |
| Predict + contributions p95 (single row) | 1.1258 | <= 5.0 ms | ✅ geçti | measured on the training machine, not the CI runner |
| Trees | 190 | <= 200 | ✅ geçti |  |
| Max depth | 6 | <= 6 | ✅ geçti |  |

## Test metrikleri

| Model | PR-AUC | ROC-AUC | Eşik | Precision | Recall | F1 | Alarm | Pozitif | Toplam |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LightGBM | 0.6152 | 0.9835 | 0.113013 | 0.2457 | 0.6671 | 0.3591 | 4.608 | 1.697 | 1.425.728 |
| LR tabanı | 0.0628 | 0.9164 | 0.999462 | 0.3230 | 0.0489 | 0.0850 | 257 | 1.697 | 1.425.728 |

Eşikler validation'da seçildi; LR tabanı kendi validation eşiğiyle (yalnız bilgi).

### Karışıklık matrisi (LightGBM, validation eşiği)

| | Tahmin: aklama | Tahmin: normal |
|---|---:|---:|
| Gerçek: aklama | TP 1.132 | FN 565 |
| Gerçek: normal | FP 3.476 | TN 1.420.555 |

### Tipoloji başına recall (test)

| Tipoloji | Destek | Yakalanan | Recall | Hedefe dahil |
|---|---:|---:|---:|---|
| Behavioural_Change_1 | 62 | 26 | 0.4194 | evet |
| Behavioural_Change_2 | 62 | 49 | 0.7903 | evet |
| Bipartite | 26 | 13 | 0.5000 | hayır (destek < 30) |
| Cash_Withdrawal | 241 | 198 | 0.8216 | evet |
| Cycle | 49 | 11 | 0.2245 | evet |
| Deposit-Send | 163 | 107 | 0.6564 | evet |
| Fan_In | 36 | 24 | 0.6667 | evet |
| Fan_Out | 58 | 19 | 0.3276 | evet |
| Gather-Scatter | 82 | 38 | 0.4634 | evet |
| Layered_Fan_In | 88 | 56 | 0.6364 | evet |
| Layered_Fan_Out | 100 | 27 | 0.2700 | evet |
| Over-Invoicing | 7 | 1 | 0.1429 | hayır (destek < 30) |
| Scatter-Gather | 46 | 25 | 0.5435 | evet |
| Single_large | 34 | 14 | 0.4118 | evet |
| Smurfing | 152 | 128 | 0.8421 | evet |
| Stacked Bipartite | 128 | 77 | 0.6016 | evet |
| Structuring | 363 | 319 | 0.8788 | evet |

## Validation metrikleri (seçim aşaması)

| Model | PR-AUC | ROC-AUC | Eşik | Precision | Recall | F1 | Alarm | Pozitif | Toplam |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LightGBM | 0.5379 | 0.9825 | 0.113013 | 0.2019 | 0.6119 | 0.3036 | 4.280 | 1.412 | 1.425.727 |
| LR tabanı | 0.0470 | 0.9143 | 0.999462 | 0.3216 | 0.0390 | 0.0695 | 171 | 1.412 | 1.425.727 |

## Seçilen model

- LightGBM `binary`, 190 ağaç (≤ 200), `max_depth` 6 (gerçek en derin yaprak 6), seed 20261030, `deterministic=true`, 4 iş parçacığı.
- Izgara noktası: `{'num_leaves': 31, 'learning_rate': 0.1, 'scale_pos_weight': 1.0}`; 8 aday içinden validation PR-AUC'u en yüksek olan. Ağaç sayısı: validation average precision'ın en iyi olduğu iterasyon.
- Eşik politikası: validation: highest recall with precision >= 0.2 → `0.11301326300215633`.
- Kalibrasyon: yok (`calibration: null`); skor ham LightGBM olasılığıdır.

## Örnekleme ve özellik geçmişi

- Özellik geçmişi: all splits in (timestamp, transaction_id) order (train/val/test birlikte).
- Train: all positives + Bernoulli sample of negatives, oran 0.25, seed 20261030; 6.653.397 → 1.667.505 satır (6.764 pozitif). Uygulama: after fs-1 features were computed over the full event stream.
- Validation ve test: natural distribution (no sampling).

## Gecikme ve donanım

- Tek satır `predict` + `pred_contrib` (2.000 ölçüm): p50 1.079 ms, p95 1.126 ms, p99 1.150 ms.
- Donanım: Intel64 Family 6 Model 141 Stepping 1, GenuineIntel, 12 mantıksal çekirdek, Windows-11-10.0.26300-SP0. ADR §8 bütçesi CI runner'ı (ubuntu-latest, 2 vCPU) içindir; bu ölçüm eğitim makinesidir.
- Kütüphaneler: python 3.13.7, lightgbm 4.7.0, numpy 2.5.4, pandas 3.1.0, scikit-learn 1.9.1, pyarrow 26.0.0.
