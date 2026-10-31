# =============================================================================
# SentinelFlow - Test helpers for fraud model artifacts (ML-06)
# =============================================================================
"""
Builds small, real LightGBM artifacts in the contract §3 layout so the serving
tests exercise the actual loader. Not a packaging tool: ML-05 owns packaging.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

# fs-1 order from docs/contracts/sprint4-ml-api.md §2.
FS1_FEATURE_NAMES: tuple[str, ...] = (
    "log_amount",
    "hour",
    "day_of_week",
    "payment_type_code",
    "currency_mismatch",
    "cross_border",
    "sender_country_code",
    "receiver_country_code",
    "sender_tx_count_24h",
    "sender_amount_sum_24h",
    "sender_unique_receivers_7d",
    "receiver_tx_count_24h",
    "receiver_unique_senders_7d",
    "pair_tx_count_7d",
    "sender_seconds_since_prev",
)
FS1_VERSION = "fs-1"
MODEL_VERSION = "fraud-lgbm-20261105-a1b2c3d"


def training_data(n: int = 600, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """Synthetic matrix where fan-out and cross-border drive the label."""
    rng = np.random.default_rng(seed)
    x = rng.random((n, len(FS1_FEATURE_NAMES)))
    x[:, 5] = rng.integers(0, 2, n)  # cross_border
    x[:, 10] = rng.integers(0, 20, n)  # sender_unique_receivers_7d
    y = ((x[:, 10] > 12) & (x[:, 5] == 1)).astype(int)
    return x, y


def train_booster(feature_names: Sequence[str] = FS1_FEATURE_NAMES, objective: str = "binary"):
    import lightgbm as lgb

    x, y = training_data()
    params = {
        "objective": objective,
        "num_leaves": 7,
        "learning_rate": 0.2,
        "min_data_in_leaf": 5,
        "verbose": -1,
        "seed": 1,
        "deterministic": True,
        "num_threads": 1,
    }
    data = lgb.Dataset(x, label=y, feature_name=list(feature_names))
    return lgb.train(params, data, num_boost_round=15)


def metadata_for(model_text: str, **overrides: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "model_version": MODEL_VERSION,
        "model_family": "lightgbm",
        "objective": "binary",
        "feature_set_version": FS1_VERSION,
        "feature_names": list(FS1_FEATURE_NAMES),
        "categorical_features": [
            "payment_type_code",
            "sender_country_code",
            "receiver_country_code",
        ],
        "threshold": 0.5,
        "calibration": None,
        "dataset_id": "samld-test",
        "metrics": {"split": "test", "pr_auc": None},
        "trained_at": "2026-11-05T12:00:00+00:00",
        "git_sha": "a1b2c3d",
        "library_versions": {"lightgbm": "test"},
        "model_sha256": hashlib.sha256(model_text.encode()).hexdigest(),
    }
    metadata.update(overrides)
    return metadata


def write_artifact(
    directory: Path,
    *,
    booster: Any = None,
    model_text: str | None = None,
    metadata: dict[str, Any] | None = None,
    checksums: dict[str, str] | None = None,
) -> Path:
    """Write ``model.txt``, ``metadata.json``, ``model_card.md`` and ``SHA256SUMS``."""
    directory.mkdir(parents=True, exist_ok=True)
    if model_text is None:
        model_text = (booster or train_booster()).model_to_string()
    if metadata is None:
        metadata = metadata_for(model_text)
    metadata_text = json.dumps(metadata, indent=2)
    (directory / "model.txt").write_text(model_text, encoding="utf-8")
    (directory / "metadata.json").write_text(metadata_text, encoding="utf-8")
    (directory / "model_card.md").write_text("# test model\n", encoding="utf-8")
    sums = checksums or {
        "model.txt": hashlib.sha256(model_text.encode()).hexdigest(),
        "metadata.json": hashlib.sha256(metadata_text.encode()).hexdigest(),
    }
    (directory / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sums.items()), encoding="utf-8"
    )
    return directory
