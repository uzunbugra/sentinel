# =============================================================================
# SentinelFlow - ML-04 pipeline: validation stage, then the locked test once
# =============================================================================
"""
Two stages with a hard boundary between them (ADR 0003 §3, §6–§7):

1. :func:`run_selection` reads **train and val only**. It fits the baseline and
   the LightGBM grid on train, picks the configuration, tree count and threshold
   on validation, writes the frozen models to ``work_dir`` and the evidence
   (``selection.json``: choices, hashes, validation metrics) to ``report_dir``.
   ``selection.json`` is committed before the test set is opened.
2. :func:`run_test_evaluation` scores the locked test split with the frozen
   models exactly once. It writes ``test-opened.json`` before reading the test
   rows and refuses to run again; nothing is re-fitted or re-tuned.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sentinelflow.ml.features import FEATURE_NAMES, FEATURE_SET_VERSION
from sentinelflow.ml.training import data as tdata
from sentinelflow.ml.training import metrics as tmetrics
from sentinelflow.ml.training import models as tmodels
from sentinelflow.ml.training.report import render_markdown

MODEL_FILE = "model.txt"
BASELINE_FILE = "baseline_lr.json"
SELECTION_FILE = "selection.json"
TEST_MARKER_FILE = "test-opened.json"
TEST_REPORT_FILE = "test-report.json"
REPORT_MD_FILE = "report.md"
LIBRARIES = ("lightgbm", "numpy", "pandas", "scikit-learn", "pyarrow")


class LockedTestError(RuntimeError):
    """The test set was already opened, or the frozen selection is not intact."""


@dataclass(frozen=True)
class TrainingConfig:
    negative_rate: float = 0.25
    seed: int = tmodels.SEED
    min_val_precision: float = tmetrics.MIN_VAL_PRECISION
    max_trees: int = tmodels.MAX_TREES
    num_threads: int = 4
    grid: tuple[dict[str, Any], ...] = field(default=tmodels.DEFAULT_GRID)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(repo_dir: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=repo_dir, capture_output=True, text=True, check=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def environment(repo_dir: Path | None) -> dict[str, Any]:
    versions = {"python": platform.python_version()}
    for lib in LIBRARIES:
        try:
            versions[lib] = importlib_metadata.version(lib)
        except importlib_metadata.PackageNotFoundError:
            versions[lib] = "missing"
    sha = _git(repo_dir, "rev-parse", "HEAD") if repo_dir else None
    status = _git(repo_dir, "status", "--porcelain", "--untracked-files=no") if repo_dir else None
    return {
        "git_sha": sha,
        "git_dirty": None if status is None else bool(status),
        "library_versions": versions,
        "hardware": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor() or "unknown",
            "logical_cpus": os.cpu_count(),
        },
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --- stage 1: validation ------------------------------------------------------
def run_selection(
    dataset_dir: Path,
    work_dir: Path,
    report_dir: Path,
    config: TrainingConfig | None = None,
    repo_dir: Path | None = None,
) -> dict[str, Any]:
    """Fit on train, choose everything on validation, freeze models and evidence."""
    config = config or TrainingConfig()
    if (report_dir / TEST_MARKER_FILE).exists():
        raise LockedTestError("the test set was already opened; selection is frozen")
    cache_info = tdata.build_feature_cache(dataset_dir)
    started = time.perf_counter()

    train_full = tdata.load_split(dataset_dir, ["train"])
    train, sampling = tdata.sample_train(train_full, config.negative_rate, config.seed)
    del train_full
    val = tdata.load_split(dataset_dir, ["val"])

    baseline = tmodels.train_baseline(train.features, train.label)
    baseline_val = tmodels.baseline_predict(baseline, val.features)

    candidates = tmodels.train_lightgbm_grid(
        train.features,
        train.label,
        val.features,
        val.label,
        config.grid,
        max_trees=config.max_trees,
        num_threads=config.num_threads,
    )
    scored = []
    for cand in candidates:
        val_score = tmodels.booster_predict(tmodels.load_booster(cand.model_text), val.features)
        scored.append((tmetrics.ranking_metrics(val.label, val_score)["pr_auc"], cand, val_score))
    best_index = max(range(len(scored)), key=lambda i: (scored[i][0], -i))
    _, best, best_val = scored[best_index]

    threshold = tmetrics.select_threshold(val.label, best_val, config.min_val_precision)
    baseline_threshold = tmetrics.select_threshold(
        val.label, baseline_val, config.min_val_precision
    )

    work_dir.mkdir(parents=True, exist_ok=True)
    model_bytes = best.model_text.encode("utf-8")
    (work_dir / MODEL_FILE).write_bytes(model_bytes)
    baseline_bytes = (json.dumps(baseline, indent=2) + "\n").encode("utf-8")
    (work_dir / BASELINE_FILE).write_bytes(baseline_bytes)
    structure = tmodels.tree_structure(tmodels.load_booster(best.model_text))

    env = environment(repo_dir)
    selection = {
        "stage": "validation",
        "created_at": _now(),
        "dataset_id": cache_info["dataset_id"],
        "dataset_content_sha256": cache_info.get("dataset_content_sha256"),
        "feature_set_version": FEATURE_SET_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "feature_history": cache_info["history_scope"],
        "sampling": sampling,
        "config": {**asdict(config), "grid": list(config.grid)},
        "threshold_policy": (
            f"validation: highest recall with precision >= {config.min_val_precision}"
        ),
        "calibration": None,
        "selected": {
            "model_family": "lightgbm",
            "params": best.params,
            "num_trees": best.num_trees,
            "structure": structure,
            "threshold": threshold,
            "selection_rule": "highest validation PR-AUC over the grid (first on ties)",
        },
        "candidates": [
            {"params": c.params, "num_trees": c.num_trees, "val_pr_auc": ap} for ap, c, _ in scored
        ],
        "baseline": {
            "model": "logistic_regression",
            "class_weight": "balanced",
            "encoding": "numeric standardised, categorical one-hot",
            "threshold": baseline_threshold,
        },
        "files": {
            MODEL_FILE: {"sha256": sha256_bytes(model_bytes), "bytes": len(model_bytes)},
            BASELINE_FILE: {"sha256": sha256_bytes(baseline_bytes), "bytes": len(baseline_bytes)},
        },
        "validation": {
            "lightgbm": tmetrics.evaluate(val.label, best_val, threshold, val.typology),
            "baseline": tmetrics.evaluate(val.label, baseline_val, baseline_threshold),
        },
        "train_seconds": round(time.perf_counter() - started, 1),
        **env,
    }
    _write_json(report_dir / SELECTION_FILE, selection)
    return selection


# --- stage 2: the locked test, once ---------------------------------------------
def _verify_frozen(selection: dict[str, Any], work_dir: Path) -> tuple[bytes, dict[str, Any]]:
    model_bytes = (work_dir / MODEL_FILE).read_bytes()
    baseline_bytes = (work_dir / BASELINE_FILE).read_bytes()
    for name, blob in ((MODEL_FILE, model_bytes), (BASELINE_FILE, baseline_bytes)):
        if sha256_bytes(blob) != selection["files"][name]["sha256"]:
            raise LockedTestError(f"{name} does not match the frozen selection")
    return model_bytes, json.loads(baseline_bytes)


def measure_latency(booster: Any, features: pd.DataFrame, n: int = 2000, warmup: int = 100):
    """Single-row ``predict`` + ``pred_contrib`` timings on ready vectors (ADR §8)."""
    rows = features[list(FEATURE_NAMES)].to_numpy(dtype=np.float64)[: n + warmup]
    samples = []
    for i, row in enumerate(rows):
        vec = row.reshape(1, -1)
        t0 = time.perf_counter_ns()
        booster.predict(vec)
        booster.predict(vec, pred_contrib=True)
        if i >= warmup:
            samples.append(time.perf_counter_ns() - t0)
    return tmetrics.latency_summary(samples)


def run_test_evaluation(
    dataset_dir: Path, work_dir: Path, report_dir: Path, repo_dir: Path | None = None
) -> dict[str, Any]:
    """Score the locked test split with the frozen models; refuses a second run."""
    marker = report_dir / TEST_MARKER_FILE
    if marker.exists():
        raise LockedTestError(f"the test set was already opened ({marker})")
    selection = _read_json(report_dir / SELECTION_FILE)
    threshold = selection["selected"]["threshold"]
    if threshold is None:
        raise LockedTestError("no validation threshold met the precision floor; not publishable")
    model_bytes, baseline = _verify_frozen(selection, work_dir)
    cache_info = tdata.build_feature_cache(dataset_dir)
    if cache_info["dataset_id"] != selection["dataset_id"]:
        raise LockedTestError("feature cache belongs to another dataset than the selection")

    _write_json(
        marker,
        {
            "opened_at": _now(),
            "selection_sha256": sha256_bytes((report_dir / SELECTION_FILE).read_bytes()),
            "model_sha256": selection["files"][MODEL_FILE]["sha256"],
            "threshold": threshold,
        },
    )
    test = tdata.load_split(dataset_dir, ["test"])
    booster = tmodels.load_booster(model_bytes.decode("utf-8"))
    score = tmodels.booster_predict(booster, test.features)
    baseline_score = tmodels.baseline_predict(baseline, test.features)

    lgbm = tmetrics.evaluate(test.label, score, threshold, test.typology)
    base = tmetrics.evaluate(test.label, baseline_score, selection["baseline"]["threshold"])
    latency = measure_latency(booster, test.features)
    structure = tmodels.tree_structure(booster)
    targets = tmetrics.check_targets(lgbm, base, structure, len(model_bytes), latency)

    report = {
        "stage": "test",
        "evaluated_at": _now(),
        "dataset_id": selection["dataset_id"],
        "model_sha256": selection["files"][MODEL_FILE]["sha256"],
        "threshold": threshold,
        "test": {"lightgbm": lgbm, "baseline": base},
        "latency": {**latency, "scope": "predict + pred_contrib, one row, ready vector"},
        "structure": structure,
        "artifact_bytes_model_txt": len(model_bytes),
        "targets": targets,
        "publishable": all(t["passed"] for t in targets),
        **environment(repo_dir),
    }
    _write_json(report_dir / TEST_REPORT_FILE, report)
    (report_dir / REPORT_MD_FILE).write_text(render_markdown(selection, report), encoding="utf-8")
    return report
