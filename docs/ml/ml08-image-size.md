# ML-08 Docker imaj boyutu: önce / sonra

ML-08 ile çekirdek bağımlılıklardan `torch`, `torch-geometric`, `xgboost`, `catboost`, `shap` ve `imbalanced-learn` çıkarıldı, `pyarrow` eklendi. Bu ölçüm, değişikliğin production imajına etkisini gösterir (#61).

## Koşullar

| | Önce | Sonra |
|---|---|---|
| Kaynak | `archive/ml-legacy-s4` etiketi (09d6757) | `develop` (a26bb01) |
| Dockerfile farkı | — | runtime'a `libgomp1` eklendi |
| Taban imaj | `python:3.11-slim` (çok aşamalı) | aynı |

Aynı makinede, aynı ayarlarla, önbellek kullanılmadan derlendi:

```bash
docker build --pull --no-cache --platform linux/arm64 -t sentinelflow-ml08:<önce|sonra> .
```

Docker Desktop 29.8.0, Apple Silicon (linux/arm64). Ölçüm tarihi 2026-11-10/11.

## Sonuç

| | Önce | Sonra | Fark |
|---|---:|---:|---:|
| İmaj boyutu (açılmış, `docker image inspect`) | 12.07 GB | 1.63 GB | **−86 %** |
| İçerik boyutu (sıkıştırılmış katmanlar) | 4.05 GB | 351 MB | −91 % |
| `site-packages` | 7.3 GB | 1.0 GB | −86 % |
| Derleme süresi (önbelleksiz) | 6215 s (~104 dk) | 518 s (~9 dk) | −92 % |

Derleme süresi ağ hızına bağlıdır (bu ölçümde ~720 kB/s). Asıl farkı indirilen veri miktarı belirler.

## Boyutun kaynağı

"Önce" imajındaki en büyük `site-packages` dizinleri:

| Paket | MB | Sonra |
|---|---:|---|
| `nvidia` (torch'un CUDA kütüphaneleri) | 3522 | yok |
| `torch` | 1110 | yok |
| `triton` | 919 | yok |
| `catboost` | 269 | yok |
| `xgboost` | 227 | yok |
| `llvmlite` (shap → numba) | 169 | yok |
| `pyarrow` | 156 | 156 |
| `scipy` | 122 | 122 |
| `pandas` | 88 | 88 |

Linux'ta PyPI'deki `torch` tekerleği CUDA kütüphanelerini de bağımlılık olarak çeker. Servis edilen model GPU kullanmadığı hâlde eski imaj bu ~5.5 GB'ı (`nvidia` + `torch` + `triton`) taşıyordu. "Sonra" imajında kalan en büyük paketler `pyarrow`, `scipy` ve `pandas`.

## Not

Ölçüm linux/arm64 üzerinde yapıldı. linux/amd64'te CUDA tekerlekleri farklı boyutta olabilir, ama oran aynı yöndedir: farkın neredeyse tamamı ML-08'de kaldırılan paketlerden gelir.
