# =============================================================================
# SentinelFlow - ML-04 metrics, threshold policy and target checks
# =============================================================================
"""
Metrics and the locked targets of ADR 0003 §6–§8.

* Threshold (§6): on validation, among thresholds with precision >= 0.20 take the
  one with the highest recall (ties: higher precision, then higher threshold).
  ``is_fraud = score >= threshold``.
* Targets (§7) are checked once, on the locked test set, by :func:`check_targets`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score

MIN_VAL_PRECISION = 0.20
TARGETS: dict[str, float] = {
    "pr_auc": 0.40,
    "relative_pr_auc_gain_vs_baseline": 0.25,
    "test_precision_at_threshold": 0.15,
    "test_recall_at_threshold": 0.50,
    "typology_min_support": 30,
    "typology_min_recall": 0.20,
    "artifact_max_bytes": 5 * 1024 * 1024,
    "predict_p95_ms": 5.0,
    "max_trees": 200,
    "max_depth": 6,
}


def ranking_metrics(label: np.ndarray, score: np.ndarray) -> dict[str, float]:
    return {
        "pr_auc": float(average_precision_score(label, score)),
        "roc_auc": float(roc_auc_score(label, score)),
    }


def select_threshold(
    label: np.ndarray, score: np.ndarray, min_precision: float = MIN_VAL_PRECISION
) -> float | None:
    """Highest-recall threshold whose precision is >= ``min_precision``; None if none."""
    precision, recall, thresholds = precision_recall_curve(label, score)
    # The last precision/recall pair has no threshold (recall 0 end point).
    precision, recall = precision[:-1], recall[:-1]
    ok = (precision >= min_precision) & (thresholds > 0.0) & (thresholds < 1.0)
    if not ok.any():
        return None
    candidates = np.flatnonzero(ok)
    best = max(candidates, key=lambda i: (recall[i], precision[i], thresholds[i]))
    return float(thresholds[best])


def at_threshold(label: np.ndarray, score: np.ndarray, threshold: float) -> dict[str, Any]:
    predicted = score >= threshold
    positive = label == 1
    tp = int(np.sum(predicted & positive))
    fp = int(np.sum(predicted & ~positive))
    fn = int(np.sum(~predicted & positive))
    tn = int(np.sum(~predicted & ~positive))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "threshold": threshold,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "alerts": tp + fp,
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
    }


def typology_recall(
    label: np.ndarray, score: np.ndarray, typology: np.ndarray, threshold: float
) -> list[dict[str, Any]]:
    """Recall per laundering typology over the positives, with support counts."""
    positive = label == 1
    rows = []
    for name in sorted(set(typology[positive].tolist())):
        mask = positive & (typology == name)
        support = int(mask.sum())
        detected = int(np.sum(score[mask] >= threshold))
        rows.append(
            {
                "typology": name,
                "support": support,
                "detected": detected,
                "recall": detected / support,
            }
        )
    return rows


def evaluate(
    label: np.ndarray,
    score: np.ndarray,
    threshold: float | None,
    typology: np.ndarray | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        **ranking_metrics(label, score),
        "support_positive": int(label.sum()),
        "support_total": len(label),
    }
    if threshold is not None:
        result["at_threshold"] = at_threshold(label, score, threshold)
        if typology is not None:
            result["typology_recall"] = typology_recall(label, score, typology, threshold)
    return result


def latency_summary(samples_ns: Sequence[int]) -> dict[str, float]:
    ms = np.asarray(samples_ns, dtype=np.float64) / 1e6
    return {
        "n": len(ms),
        "p50_ms": float(np.percentile(ms, 50)),
        "p95_ms": float(np.percentile(ms, 95)),
        "p99_ms": float(np.percentile(ms, 99)),
        "max_ms": float(np.max(ms)),
    }


def _check(name: str, value: Any, target: str, passed: bool, note: str = "") -> dict:
    return {"target": name, "value": value, "goal": target, "passed": bool(passed), "note": note}


def check_targets(
    test: Mapping[str, Any],
    baseline_test: Mapping[str, Any],
    structure: Mapping[str, int],
    artifact_bytes: int,
    latency: Mapping[str, float],
) -> list[dict[str, Any]]:
    """Pass/fail for every ADR 0003 §7–§8 target, evaluated on the test split."""
    t = TARGETS
    pr_auc = test["pr_auc"]
    base = baseline_test["pr_auc"]
    gain = (pr_auc - base) / base if base > 0 else float("inf")
    thr = test["at_threshold"]
    typologies = [r for r in test["typology_recall"] if r["support"] >= t["typology_min_support"]]
    failing = [r["typology"] for r in typologies if r["recall"] < t["typology_min_recall"]]
    return [
        _check("PR-AUC (test)", pr_auc, f">= {t['pr_auc']}", pr_auc >= t["pr_auc"]),
        _check(
            "PR-AUC gain vs LR baseline (test)",
            gain,
            f">= {t['relative_pr_auc_gain_vs_baseline']:.0%} relative",
            gain >= t["relative_pr_auc_gain_vs_baseline"],
            f"baseline PR-AUC {base:.4f}",
        ),
        _check(
            "Precision at validation threshold (test)",
            thr["precision"],
            f">= {t['test_precision_at_threshold']}",
            thr["precision"] >= t["test_precision_at_threshold"],
        ),
        _check(
            "Recall at validation threshold (test)",
            thr["recall"],
            f">= {t['test_recall_at_threshold']}",
            thr["recall"] >= t["test_recall_at_threshold"],
        ),
        _check(
            "Typology recall (support >= 30, test)",
            min((r["recall"] for r in typologies), default=None),
            f">= {t['typology_min_recall']} for each of {len(typologies)} typologies",
            not failing,
            "failing: " + ", ".join(failing) if failing else "",
        ),
        _check(
            "Artifact size",
            artifact_bytes,
            f"<= {t['artifact_max_bytes']} bytes",
            artifact_bytes <= t["artifact_max_bytes"],
        ),
        _check(
            "Predict + contributions p95 (single row)",
            latency["p95_ms"],
            f"<= {t['predict_p95_ms']} ms",
            latency["p95_ms"] <= t["predict_p95_ms"],
            "measured on the training machine, not the CI runner",
        ),
        _check(
            "Trees",
            structure["num_trees"],
            f"<= {t['max_trees']}",
            structure["num_trees"] <= t["max_trees"],
        ),
        _check(
            "Max depth",
            structure["max_depth"],
            f"<= {t['max_depth']}",
            structure["max_depth"] <= t["max_depth"],
        ),
    ]
