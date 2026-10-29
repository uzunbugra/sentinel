"""
Feature set ``fs-1`` — the single feature definition shared by training and the
service (``docs/contracts/sprint4-ml-api.md`` §2, ADR 0003 §4).

Training::

    from sentinelflow.ml.features import build_features_batch
    X = build_features_batch(canonical_df)          # columns == FEATURE_NAMES

Service::

    from sentinelflow.ml.features import AccountHistory
    history = AccountHistory()
    vec = history.features_for(tx)                  # read only
    history.record(tx)                              # ingestion path only
"""

from sentinelflow.ml.features.engine import (
    AccountHistory,
    build_features_batch,
    canonicalize,
    timestamp_to_ns,
)
from sentinelflow.ml.features.spec import (
    CATEGORICAL_FEATURES,
    COUNTRIES,
    CURRENCIES,
    FEATURE_DTYPES,
    FEATURE_NAMES,
    FEATURE_SET_VERSION,
    NO_PREVIOUS_SECONDS,
    NUM_FEATURES,
    PAYMENT_TYPES,
    UNKNOWN,
    UNKNOWN_CODE,
    FeatureInputError,
)

__all__ = [
    "CATEGORICAL_FEATURES",
    "COUNTRIES",
    "CURRENCIES",
    "FEATURE_DTYPES",
    "FEATURE_NAMES",
    "FEATURE_SET_VERSION",
    "NO_PREVIOUS_SECONDS",
    "NUM_FEATURES",
    "PAYMENT_TYPES",
    "UNKNOWN",
    "UNKNOWN_CODE",
    "AccountHistory",
    "FeatureInputError",
    "build_features_batch",
    "canonicalize",
    "timestamp_to_ns",
]
