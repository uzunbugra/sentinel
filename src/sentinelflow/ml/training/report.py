# =============================================================================
# SentinelFlow - ML-04 markdown report
# =============================================================================
"""Renders ``selection.json`` + ``test-report.json`` as the human-readable ML-04 report."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _f(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "evet" if value else "hayır"
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _metrics_rows(name: str, m: Mapping[str, Any]) -> str:
    thr = m.get("at_threshold")
    cells = [name, _f(m["pr_auc"]), _f(m["roc_auc"])]
    if thr:
        cells += [_f(thr["threshold"], 6), _f(thr["precision"]), _f(thr["recall"]), _f(thr["f1"])]
        cells += [_f(thr["alerts"])]
    else:
        cells += ["—"] * 5
    cells += [_f(m["support_positive"]), _f(m["support_total"])]
    return "| " + " | ".join(cells) + " |"


_METRIC_HEADER = (
    "| Model | PR-AUC | ROC-AUC | Eşik | Precision | Recall | F1 | Alarm | Pozitif | Toplam |\n"
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
)


def _confusion(m: Mapping[str, Any]) -> str:
    cm = m["at_threshold"]["confusion_matrix"]
    return (
        "| | Tahmin: aklama | Tahmin: normal |\n|---|---:|---:|\n"
        f"| Gerçek: aklama | TP {_f(cm['tp'])} | FN {_f(cm['fn'])} |\n"
        f"| Gerçek: normal | FP {_f(cm['fp'])} | TN {_f(cm['tn'])} |"
    )


def _typology(rows: list[Mapping[str, Any]], min_support: int = 30) -> str:
    lines = [
        "| Tipoloji | Destek | Yakalanan | Recall | Hedefe dahil |",
        "|---|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['typology']} | {_f(r['support'])} | {_f(r['detected'])} | "
            f"{_f(r['recall'])} | {'evet' if r['support'] >= min_support else 'hayır (destek < 30)'} |"
        )
    return "\n".join(lines)


def _targets(rows: list[Mapping[str, Any]]) -> str:
    lines = ["| Hedef | Değer | Ölçüt | Sonuç | Not |", "|---|---:|---|---|---|"]
    for t in rows:
        lines.append(
            f"| {t['target']} | {_f(t['value'])} | {t['goal']} | "
            f"{'✅ geçti' if t['passed'] else '❌ kaldı'} | {t['note']} |"
        )
    return "\n".join(lines)


def render_markdown(selection: Mapping[str, Any], report: Mapping[str, Any]) -> str:
    sel = selection["selected"]
    sampling = selection["sampling"]
    env = report
    hw = env["hardware"]
    libs = ", ".join(f"{k} {v}" for k, v in env["library_versions"].items())
    verdict = (
        "**Tüm hedefler geçti — model yayınlanabilir (ML-05).**"
        if report["publishable"]
        else "**En az bir hedef kaldı — model YAYINLANMAZ** (ADR 0003 §7: rapor saklanır, "
        "hedef düşürülmez)."
    )
    params = {k: sel["params"][k] for k in ("num_leaves", "learning_rate", "scale_pos_weight")}
    lat = report["latency"]
    parts = [
        "# ML-04 — Model değerlendirme raporu (SAML-D, fs-1)",
        "",
        f"- `dataset_id`: `{selection['dataset_id']}` · `feature_set_version`: "
        f"`{selection['feature_set_version']}`",
        f"- Seçim (validation) commit'i: `{selection['git_sha']}` · seçim zamanı "
        f"{selection['created_at']}",
        f"- Test açılışı: {report['evaluated_at']} (tek sefer; `test-opened.json`)",
        f"- Model `model.txt` SHA-256: `{report['model_sha256']}`",
        "",
        verdict,
        "",
        "## Hedefler (kilitli test, ADR 0003 §7–§8)",
        "",
        _targets(report["targets"]),
        "",
        "## Test metrikleri",
        "",
        _METRIC_HEADER,
        _metrics_rows("LightGBM", report["test"]["lightgbm"]),
        _metrics_rows("LR tabanı", report["test"]["baseline"]),
        "",
        "Eşikler validation'da seçildi; LR tabanı kendi validation eşiğiyle (yalnız bilgi).",
        "",
        "### Karışıklık matrisi (LightGBM, validation eşiği)",
        "",
        _confusion(report["test"]["lightgbm"]),
        "",
        "### Tipoloji başına recall (test)",
        "",
        _typology(report["test"]["lightgbm"]["typology_recall"]),
        "",
        "## Validation metrikleri (seçim aşaması)",
        "",
        _METRIC_HEADER,
        _metrics_rows("LightGBM", selection["validation"]["lightgbm"]),
        _metrics_rows("LR tabanı", selection["validation"]["baseline"]),
        "",
        "## Seçilen model",
        "",
        f"- LightGBM `binary`, {sel['num_trees']} ağaç (≤ 200), `max_depth` "
        f"{sel['params']['max_depth']} (gerçek en derin yaprak {sel['structure']['max_depth']}), "
        f"seed {sel['params']['seed']}, `deterministic=true`, {sel['params']['num_threads']} iş "
        "parçacığı.",
        f"- Izgara noktası: `{params}`; {len(selection['candidates'])} aday içinden validation "
        "PR-AUC'u en yüksek olan. Ağaç sayısı: validation average precision'ın en iyi olduğu "
        "iterasyon.",
        f"- Eşik politikası: {selection['threshold_policy']} → `{sel['threshold']}`.",
        "- Kalibrasyon: yok (`calibration: null`); skor ham LightGBM olasılığıdır.",
        "",
        "## Örnekleme ve özellik geçmişi",
        "",
        f"- Özellik geçmişi: {selection['feature_history']} (train/val/test birlikte).",
        f"- Train: {sampling['train']}, oran {sampling['negative_rate']}, seed "
        f"{sampling['seed']}; {_f(sampling['train_rows_before'])} → "
        f"{_f(sampling['train_rows_after'])} satır ({_f(sampling['train_positives'])} pozitif). "
        f"Uygulama: {sampling['applied']}.",
        f"- Validation ve test: {sampling['val']}.",
        "",
        "## Gecikme ve donanım",
        "",
        f"- Tek satır `predict` + `pred_contrib` ({_f(lat['n'])} ölçüm): p50 "
        f"{_f(lat['p50_ms'], 3)} ms, p95 {_f(lat['p95_ms'], 3)} ms, p99 {_f(lat['p99_ms'], 3)} ms.",
        f"- Donanım: {hw['processor']}, {hw['logical_cpus']} mantıksal çekirdek, {hw['platform']}. "
        "ADR §8 bütçesi CI runner'ı (ubuntu-latest, 2 vCPU) içindir; bu ölçüm eğitim makinesidir.",
        f"- Kütüphaneler: {libs}.",
        "",
    ]
    return "\n".join(parts)
