# =============================================================================
# SentinelFlow - ML-04 models: logistic regression baseline + LightGBM
# =============================================================================
"""
Both models are stored without pickle:

* The baseline (ADR 0003 §5) is a class-weighted logistic regression on the same
  fs-1 features: numeric features standardised, the three categorical codes
  one-hot encoded over their fixed vocabularies. It is saved as JSON parameters
  and always scored through :func:`baseline_predict`, so validation and test use
  the same code path. It is reported, never served.
* LightGBM (``binary``, <= 200 trees, ``max_depth`` <= 6, fixed seed,
  ``deterministic=True``) is saved in its text format. Each grid point is
  trained on train only; the number of trees is the iteration with the best
  validation average precision.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from sentinelflow.ml.features import CATEGORICAL_FEATURES, COUNTRIES, FEATURE_NAMES, PAYMENT_TYPES
from sentinelflow.ml.training.metrics import TARGETS

SEED = 20261030
MAX_TREES = int(TARGETS["max_trees"])
MAX_DEPTH = int(TARGETS["max_depth"])

CATEGORY_SIZES: dict[str, int] = {
    "payment_type_code": len(PAYMENT_TYPES),
    "sender_country_code": len(COUNTRIES),
    "receiver_country_code": len(COUNTRIES),
}
NUMERIC_FEATURES: tuple[str, ...] = tuple(n for n in FEATURE_NAMES if n not in CATEGORY_SIZES)
assert set(CATEGORY_SIZES) == set(CATEGORICAL_FEATURES)

LGBM_BASE_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "metric": "average_precision",
    "max_depth": MAX_DEPTH,
    "min_data_in_leaf": 100,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "max_cat_to_onehot": 8,
    "seed": SEED,
    "deterministic": True,
    "force_col_wise": True,
    "feature_pre_filter": False,
    "verbose": -1,
}
DEFAULT_GRID: tuple[dict[str, Any], ...] = tuple(
    {"num_leaves": leaves, "learning_rate": lr, "scale_pos_weight": weight}
    for leaves, lr, weight in itertools.product((15, 31), (0.05, 0.1), (1.0, 4.0))
)


# --- logistic regression baseline -------------------------------------------
def _design(features: pd.DataFrame, params: Mapping[str, Any]) -> np.ndarray:
    numeric = features[list(NUMERIC_FEATURES)].to_numpy(dtype=np.float64)
    numeric = (numeric - np.asarray(params["mean"])) / np.asarray(params["scale"])
    blocks = [numeric]
    for name, size in CATEGORY_SIZES.items():
        codes = features[name].to_numpy(dtype=np.int64)
        codes = np.where((codes >= 0) & (codes < size), codes, 0)
        blocks.append(np.eye(size, dtype=np.float64)[codes])
    return np.hstack(blocks)


def train_baseline(features: pd.DataFrame, label: np.ndarray) -> dict[str, Any]:
    """Fit the LR baseline and return its JSON-serialisable parameters."""
    numeric = features[list(NUMERIC_FEATURES)].to_numpy(dtype=np.float64)
    mean = numeric.mean(axis=0)
    scale = numeric.std(axis=0)
    scale[scale == 0] = 1.0
    params: dict[str, Any] = {
        "model": "logistic_regression",
        "class_weight": "balanced",
        "C": 1.0,
        "numeric_features": list(NUMERIC_FEATURES),
        "categorical_features": dict(CATEGORY_SIZES),
        "mean": mean.tolist(),
        "scale": scale.tolist(),
    }
    model = LogisticRegression(
        C=params["C"], class_weight="balanced", max_iter=2000, solver="lbfgs", random_state=SEED
    )
    model.fit(_design(features, params), label)
    params["coef"] = model.coef_.ravel().tolist()
    params["intercept"] = float(model.intercept_[0])
    params["n_iter"] = int(model.n_iter_[0])
    return params


def baseline_predict(params: Mapping[str, Any], features: pd.DataFrame) -> np.ndarray:
    z = _design(features, params) @ np.asarray(params["coef"]) + params["intercept"]
    return 1.0 / (1.0 + np.exp(-z))


# --- LightGBM ---------------------------------------------------------------
@dataclass(frozen=True)
class Candidate:
    """One trained grid point: params, chosen tree count and the saved model text."""

    params: dict[str, Any]
    num_trees: int
    val_average_precision_curve: list[float]
    model_text: str


def _dataset(features: pd.DataFrame, label: np.ndarray, reference: Any = None) -> Any:
    import lightgbm as lgb

    return lgb.Dataset(
        features,
        label=label,
        feature_name=list(FEATURE_NAMES),
        categorical_feature=list(CATEGORICAL_FEATURES),
        reference=reference,
        free_raw_data=False,
    )


def train_lightgbm_grid(
    train_x: pd.DataFrame,
    train_y: np.ndarray,
    val_x: pd.DataFrame,
    val_y: np.ndarray,
    grid: Sequence[Mapping[str, Any]] = DEFAULT_GRID,
    *,
    max_trees: int = MAX_TREES,
    num_threads: int = 4,
) -> list[Candidate]:
    """Train every grid point on train; pick each one's tree count on validation."""
    import lightgbm as lgb

    if max_trees > MAX_TREES:
        raise ValueError(f"max_trees must be <= {MAX_TREES}")
    train_set = _dataset(train_x, train_y)
    val_set = _dataset(val_x, val_y, reference=train_set)
    candidates = []
    for point in grid:
        params = {**LGBM_BASE_PARAMS, **point, "num_threads": num_threads}
        if params["max_depth"] > MAX_DEPTH or params["max_depth"] <= 0:
            raise ValueError(f"max_depth must be in 1..{MAX_DEPTH}")
        history: dict[str, Any] = {}
        booster = lgb.train(
            params,
            train_set,
            num_boost_round=max_trees,
            valid_sets=[val_set],
            valid_names=["val"],
            callbacks=[lgb.record_evaluation(history)],
        )
        curve = [float(v) for v in history["val"]["average_precision"]]
        best = int(np.argmax(curve)) + 1  # first iteration with the best value
        candidates.append(
            Candidate(
                params=params,
                num_trees=best,
                val_average_precision_curve=curve,
                model_text=booster.model_to_string(num_iteration=best),
            )
        )
    return candidates


def load_booster(model_text: str) -> Any:
    import lightgbm as lgb

    return lgb.Booster(model_str=model_text)


def booster_predict(booster: Any, features: pd.DataFrame) -> np.ndarray:
    return np.asarray(booster.predict(features[list(FEATURE_NAMES)]), dtype=np.float64)


def tree_structure(booster: Any) -> dict[str, int]:
    """Number of trees and the deepest leaf depth actually present in the model."""

    def depth(node: Mapping[str, Any]) -> int:
        if "split_index" not in node:  # leaf
            return 0
        return 1 + max(depth(node["left_child"]), depth(node["right_child"]))

    trees = booster.dump_model()["tree_info"]
    return {
        "num_trees": len(trees),
        "max_depth": max((depth(t["tree_structure"]) for t in trees), default=0),
    }
