# =============================================================================
# SentinelFlow - ML-04 training data (fs-1 features over the ML-02 dataset)
# =============================================================================
"""
Turns the ML-02 dataset into model matrices.

* :func:`build_feature_cache` runs the ML-03 batch path over the **whole** event
  stream (train, val and test together, in time order) so every row's history
  is complete, then stores the feature matrix next to the dataset. Labels are
  copied alongside but never reach the feature engine.
* :func:`load_split` reads only the requested splits from that cache; the
  validation stage never asks for ``test``.
* :func:`sample_train` subsamples train negatives *after* the features exist
  (ADR 0003 §3). Validation and test keep their natural distribution.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from sentinelflow.ml.features import FEATURE_NAMES, FEATURE_SET_VERSION, build_features_batch
from sentinelflow.ml.features import spec as feature_spec

LABEL = "is_laundering"
TYPOLOGY = "laundering_type"
SPLIT = "split"
SPLITS = ("train", "val", "test")
DATASET_FILE = "transactions.parquet"
MANIFEST_FILE = "manifest.json"
# Columns the feature engine may read: contract §1 canonical fields only.
CANONICAL_COLUMNS: tuple[str, ...] = (
    *feature_spec.REQUIRED_FIELDS,
    *feature_spec.OPTIONAL_FIELDS,
)


class TrainingDataError(ValueError):
    """The dataset or feature cache is missing, stale or inconsistent."""


@dataclass(frozen=True)
class SplitData:
    """Feature matrix plus labels for one or more splits (input row order)."""

    features: pd.DataFrame
    label: np.ndarray
    typology: np.ndarray

    def __len__(self) -> int:
        return len(self.label)

    @property
    def positives(self) -> int:
        return int(self.label.sum())


def feature_cache_paths(dataset_dir: Path) -> tuple[Path, Path]:
    stem = f"features-{FEATURE_SET_VERSION}"
    return dataset_dir / f"{stem}.parquet", dataset_dir / f"{stem}.json"


def read_manifest(dataset_dir: Path) -> dict[str, Any]:
    path = dataset_dir / MANIFEST_FILE
    if not path.is_file():
        raise TrainingDataError(f"ML-02 manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_feature_cache(dataset_dir: Path, *, force: bool = False) -> dict[str, Any]:
    """Compute fs-1 for every row of the dataset and write the cache; return its info."""
    manifest = read_manifest(dataset_dir)
    cache_path, info_path = feature_cache_paths(dataset_dir)
    if not force and cache_path.is_file() and info_path.is_file():
        info = json.loads(info_path.read_text(encoding="utf-8"))
        if info.get("dataset_id") == manifest["dataset_id"]:
            return info

    columns = [*CANONICAL_COLUMNS, LABEL, TYPOLOGY, SPLIT]
    started = time.perf_counter()
    frame = pq.read_table(dataset_dir / DATASET_FILE, columns=columns).to_pandas()
    labels = frame[[LABEL, TYPOLOGY, SPLIT]].copy()
    features = build_features_batch(frame[list(CANONICAL_COLUMNS)])
    del frame
    seconds = time.perf_counter() - started

    out = pd.concat([features, labels], axis=1)
    out[LABEL] = out[LABEL].astype(np.int8)
    out.to_parquet(cache_path, index=False)
    info = {
        "dataset_id": manifest["dataset_id"],
        "dataset_content_sha256": manifest.get("output", {}).get("content_sha256"),
        "feature_set_version": FEATURE_SET_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "rows": len(out),
        "history_scope": "all splits in (timestamp, transaction_id) order",
        "build_seconds": round(seconds, 1),
        "cache_sha256": _sha256_file(cache_path),
    }
    info_path.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    return info


def load_split(dataset_dir: Path, splits: Sequence[str]) -> SplitData:
    """Read the cached features of ``splits`` only (row order of the dataset)."""
    unknown = set(splits) - set(SPLITS)
    if unknown:
        raise TrainingDataError(f"unknown splits: {sorted(unknown)}")
    cache_path, _ = feature_cache_paths(dataset_dir)
    if not cache_path.is_file():
        raise TrainingDataError(f"feature cache not found: {cache_path} (run 'features' first)")
    table = pq.read_table(cache_path, filters=[(SPLIT, "in", list(splits))])
    frame = table.to_pandas()
    if list(frame.columns[: len(FEATURE_NAMES)]) != list(FEATURE_NAMES):
        raise TrainingDataError("feature cache columns differ from FEATURE_NAMES")
    return SplitData(
        features=frame[list(FEATURE_NAMES)].reset_index(drop=True),
        label=frame[LABEL].to_numpy(dtype=np.int8),
        typology=frame[TYPOLOGY].astype(str).to_numpy(),
    )


def sample_train(data: SplitData, negative_rate: float, seed: int) -> tuple[SplitData, dict]:
    """Keep every positive and a seeded Bernoulli sample of negatives."""
    if not 0.0 < negative_rate <= 1.0:
        raise TrainingDataError(f"negative_rate must be in (0, 1], got {negative_rate}")
    rng = np.random.default_rng(seed)
    keep = (data.label == 1) | (rng.random(len(data)) < negative_rate)
    sampled = SplitData(
        features=data.features[keep].reset_index(drop=True),
        label=data.label[keep],
        typology=data.typology[keep],
    )
    strategy = {
        "train": "all positives + Bernoulli sample of negatives",
        "negative_rate": negative_rate,
        "seed": seed,
        "applied": "after fs-1 features were computed over the full event stream",
        "train_rows_before": len(data),
        "train_rows_after": len(sampled),
        "train_positives": sampled.positives,
        "val": "natural distribution (no sampling)",
        "test": "natural distribution (no sampling)",
    }
    return sampled, strategy
