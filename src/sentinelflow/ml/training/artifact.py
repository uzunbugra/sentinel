# =============================================================================
# SentinelFlow - ML-05 model artifact packaging
# =============================================================================
"""
Packages the frozen ML-04 model as the contract §3 artifact::

    models/fraud/<model_version>/
        model.txt        LightGBM text model (byte-identical to the frozen one)
        metadata.json    contract §3 fields; metrics are the locked-test results
        model_card.md    human-readable card
        SHA256SUMS       "<sha256>  <file>" for model.txt and metadata.json

``model_version`` is ``fraud-lgbm-<YYYYMMDD>-<git_sha7>``: the training date and
the commit the model was trained from. Only a publishable ML-04 result is packaged
(ADR 0003 §7); artifacts are not committed (ADR §9: ``models/`` is ignored, releases
carry the directory).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from sentinelflow.ml.features import CATEGORICAL_FEATURES
from sentinelflow.ml.training import pipeline
from sentinelflow.ml.training.metrics import TARGETS
from sentinelflow.ml.training.report import _f

METADATA_FILE = "metadata.json"
MODEL_CARD_FILE = "model_card.md"
CHECKSUM_FILE = "SHA256SUMS"
SCHEMA_VERSION = 1
MAX_ARTIFACT_BYTES = int(TARGETS["artifact_max_bytes"])


class ArtifactBuildError(RuntimeError):
    """The ML-04 result cannot be packaged."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def model_version_for(selection: Mapping[str, Any]) -> str:
    sha = selection.get("git_sha")
    if not sha:
        raise ArtifactBuildError("selection has no git_sha (train from a git checkout)")
    day = datetime.fromisoformat(selection["created_at"]).strftime("%Y%m%d")
    return f"fraud-lgbm-{day}-{sha[:7]}"


def build_metadata(
    selection: Mapping[str, Any], report: Mapping[str, Any], model_bytes: bytes
) -> dict[str, Any]:
    test = report["test"]["lightgbm"]
    thr = test["at_threshold"]
    return {
        "schema_version": SCHEMA_VERSION,
        "model_version": model_version_for(selection),
        "model_family": "lightgbm",
        "objective": "binary",
        "feature_set_version": selection["feature_set_version"],
        "feature_names": list(selection["feature_names"]),
        "categorical_features": list(CATEGORICAL_FEATURES),
        "threshold": selection["selected"]["threshold"],
        "calibration": None,
        "dataset_id": selection["dataset_id"],
        "metrics": {
            "split": "test",
            "pr_auc": test["pr_auc"],
            "roc_auc": test["roc_auc"],
            "precision": thr["precision"],
            "recall": thr["recall"],
            "f1": thr["f1"],
            "support_positive": test["support_positive"],
            "support_total": test["support_total"],
            "baseline_pr_auc": report["test"]["baseline"]["pr_auc"],
        },
        "trained_at": selection["created_at"],
        "git_sha": selection["git_sha"],
        "library_versions": dict(selection["library_versions"]),
        "model_sha256": _sha256(model_bytes),
    }


def render_model_card(
    metadata: Mapping[str, Any], selection: Mapping[str, Any], report: Mapping[str, Any]
) -> str:
    m = metadata["metrics"]
    sel = selection["selected"]
    sampling = selection["sampling"]
    typologies = report["test"]["lightgbm"]["typology_recall"]
    weak = [r for r in typologies if r["support"] >= 30 and r["recall"] < 0.5]
    lines = [
        f"# Model kartı — `{metadata['model_version']}`",
        "",
        "## Özet",
        "",
        "- **Görev:** işlem başına ikili sınıflandırma, kara para aklama şüphesi (SAML-D "
        "`is_laundering`). Skor ≥ eşik → ML alarmı (`fraud_type = ml_model`).",
        f"- **Model:** LightGBM `binary`, {sel['num_trees']} ağaç, `max_depth` "
        f"{sel['params']['max_depth']}, `num_leaves` {sel['params']['num_leaves']}, "
        f"öğrenme oranı {sel['params']['learning_rate']}; kalibrasyon yok.",
        f"- **Özellikler:** `{metadata['feature_set_version']}`, "
        f"{len(metadata['feature_names'])} özellik (sözleşme §2); kategorik: "
        + ", ".join(f"`{c}`" for c in metadata["categorical_features"])
        + ".",
        f"- **Eşik:** `{metadata['threshold']}` — validation'da precision ≥ 0.20 koşulunda "
        "en yüksek recall (ADR 0003 §6). Testte yeniden ayarlanmadı.",
        f"- **Veri:** `{metadata['dataset_id']}` (SAML-D, sentetik; CC BY-NC-SA 4.0, Oztas vd. "
        "2023). Veri kartı: `docs/ml/samld-data-card.md`.",
        f"- **Eğitim:** {metadata['trained_at']}, commit `{metadata['git_sha']}`.",
        "",
        "## Kilitli test sonuçları",
        "",
        "| PR-AUC | ROC-AUC | Precision | Recall | F1 | Pozitif | Toplam | LR tabanı PR-AUC |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| {_f(m['pr_auc'])} | {_f(m['roc_auc'])} | {_f(m['precision'])} | "
        f"{_f(m['recall'])} | {_f(m['f1'])} | {_f(m['support_positive'])} | "
        f"{_f(m['support_total'])} | {_f(m['baseline_pr_auc'])} |",
        "",
        "Tüm ADR 0003 §7–§8 hedefleri ve tipoloji recall'u: `reports/ml04/report.md`.",
        "",
        "## Eğitim verisi ve örnekleme",
        "",
        "- Zaman bölmesi %70 / %15 / %15 (train / validation / test), test kilitli ve bir kez "
        "açıldı.",
        f"- Train negatifleri özellikler hesaplandıktan sonra {sampling['negative_rate']} "
        f"oranında örneklendi (seed {sampling['seed']}); validation ve test doğal dağılımda.",
        "- Hesap geçmişi özellikleri tüm olay akışı üzerinden, yalnız önceki olaylarla hesaplandı.",
        "",
        "## Kullanım ve sınırlar",
        "",
        "- Skor ham LightGBM olasılığıdır; eğitimde negatifler alt örneklendiği için gerçek "
        "olasılık olarak **yorumlanmamalıdır** — yalnız eşikle karşılaştırılır.",
        "- Veri sentetiktir; tipolojiler simülatörün kurallarını yansıtır, gerçek trafiğe "
        "genelleme doğrulanmamıştır. Para birimi/ülke dönüşümleri etiketlidir (veri kartı §2).",
        "- Servis yeniden başlayınca hesap geçmişi boştur (cold-start); ilk işlemlerde geçmiş "
        "özellikleri 0 olur ve skor eğitimdeki dağılımdan sapabilir.",
        "- Model insan incelemesine alarm üretir; tek başına işlem engelleme kararı için "
        "kullanılmaz. Kural motorlarının yerine geçmez.",
    ]
    if weak:
        lines.append(
            "- Recall'u 0.5'in altında kalan tipolojiler (destek ≥ 30): "
            + ", ".join(f"{r['typology']} ({_f(r['recall'], 2)})" for r in weak)
            + "."
        )
    lines += [
        "",
        "## Dosyalar",
        "",
        f"- `model.txt` SHA-256 `{metadata['model_sha256']}` (LightGBM metin formatı, pickle "
        "yok); `metadata.json` sözleşme §3; `SHA256SUMS`.",
        "- Kütüphaneler: "
        + ", ".join(f"{k} {v}" for k, v in metadata["library_versions"].items())
        + ".",
        "",
    ]
    return "\n".join(lines)


def build_artifact(
    report_dir: Path,
    work_dir: Path,
    out_root: Path,
    *,
    require_publishable: bool = True,
) -> Path:
    """Write ``out_root/<model_version>/`` from the frozen ML-04 result; return the path."""
    selection = json.loads((report_dir / pipeline.SELECTION_FILE).read_text(encoding="utf-8"))
    report_path = report_dir / pipeline.TEST_REPORT_FILE
    if not report_path.is_file():
        raise ArtifactBuildError("no locked-test report; run evaluate-test first")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if require_publishable and not report["publishable"]:
        failed = [t["target"] for t in report["targets"] if not t["passed"]]
        raise ArtifactBuildError(f"ML-04 targets failed, model is not published: {failed}")

    model_bytes = (work_dir / pipeline.MODEL_FILE).read_bytes()
    if _sha256(model_bytes) != selection["files"][pipeline.MODEL_FILE]["sha256"]:
        raise ArtifactBuildError("model.txt does not match the frozen selection")
    if _sha256(model_bytes) != report["model_sha256"]:
        raise ArtifactBuildError("model.txt is not the model evaluated on the test set")

    metadata = build_metadata(selection, report, model_bytes)
    metadata_bytes = (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    card_bytes = render_model_card(metadata, selection, report).encode("utf-8")
    sums = (
        f"{_sha256(model_bytes)}  {pipeline.MODEL_FILE}\n"
        f"{_sha256(metadata_bytes)}  {METADATA_FILE}\n"
    ).encode()
    total = len(model_bytes) + len(metadata_bytes) + len(card_bytes) + len(sums)
    if total > MAX_ARTIFACT_BYTES:
        raise ArtifactBuildError(f"artifact is {total} bytes, budget {MAX_ARTIFACT_BYTES}")

    target = out_root / metadata["model_version"]
    if target.exists():
        raise ArtifactBuildError(f"artifact already exists: {target}")
    staging = out_root / f".{metadata['model_version']}.tmp"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for name, blob in (
        (pipeline.MODEL_FILE, model_bytes),
        (METADATA_FILE, metadata_bytes),
        (MODEL_CARD_FILE, card_bytes),
        (CHECKSUM_FILE, sums),
    ):
        (staging / name).write_bytes(blob)
    staging.rename(target)
    return target


def artifact_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.iterdir() if p.is_file())
