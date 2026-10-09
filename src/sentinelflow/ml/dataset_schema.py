# =============================================================================
# SentinelFlow - Transaction Dataset Contract
# =============================================================================
"""
Single source of truth for the labelled transaction dataset used by the ML
pipeline (data validation, training and CI).

The contract mirrors what ``CompetitionDatasetGenerator`` produces. Any code
that needs column names, dtypes or model features must import them from here
instead of hard-coding strings, so a schema change fails in one place with a
clear message.

CLI (used by ``.github/workflows/ml-pipeline.yml``)::

    python -m sentinelflow.ml.dataset_schema --sample-size 1000
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from pandas.api import types as ptypes

ColumnKind = Literal["string", "numeric", "datetime", "label"]

# --- Column names -------------------------------------------------------------
TRANSACTION_ID = "transaction_id"
TIMESTAMP = "timestamp"
SENDER_IBAN = "sender_iban"
RECEIVER_IBAN = "receiver_iban"
AMOUNT = "amount"
LABEL = "is_fraud"

SENDER_CITY = "sender_city"
RECEIVER_CITY = "receiver_city"
DESCRIPTION = "description"
CHANNEL = "channel"
DEVICE_ID = "device_id"

# Columns derived from the label; never usable as model input.
LEAKAGE_COLUMNS: tuple[str, ...] = ("fraud_type",)

# Known channel vocabulary (fixed order -> stable integer codes).
CHANNELS: tuple[str, ...] = ("mobile", "web", "atm", "branch", "eft", "pos")


@dataclass(frozen=True)
class ColumnSpec:
    """A required column and the kind of values it must hold."""

    name: str
    kind: ColumnKind


REQUIRED_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec(TRANSACTION_ID, "string"),
    ColumnSpec(TIMESTAMP, "datetime"),
    ColumnSpec(SENDER_IBAN, "string"),
    ColumnSpec(RECEIVER_IBAN, "string"),
    ColumnSpec(AMOUNT, "numeric"),
    ColumnSpec(LABEL, "label"),
)

# Extra columns needed to build model features.
FEATURE_SOURCE_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec(SENDER_CITY, "string"),
    ColumnSpec(RECEIVER_CITY, "string"),
    ColumnSpec(DESCRIPTION, "string"),
    ColumnSpec(CHANNEL, "string"),
    ColumnSpec(DEVICE_ID, "string"),
)

FEATURE_COLUMNS: tuple[str, ...] = (
    "amount",
    "log_amount",
    "hour",
    "day_of_week",
    "is_night",
    "cross_city",
    "description_length",
    "channel_code",
    "sender_tx_count",
    "receiver_tx_count",
    "sender_device_count",
)


class DatasetSchemaError(ValueError):
    """Raised when a dataset does not satisfy the transaction contract."""


def _kind_matches(series: pd.Series, kind: ColumnKind) -> bool:
    if kind == "string":
        return ptypes.is_string_dtype(series) or ptypes.is_object_dtype(series)
    if kind == "numeric":
        return ptypes.is_numeric_dtype(series) and not ptypes.is_bool_dtype(series)
    if kind == "datetime":
        return ptypes.is_datetime64_any_dtype(series)
    # label: bool, or integers restricted to {0, 1}
    if ptypes.is_bool_dtype(series):
        return True
    return ptypes.is_integer_dtype(series) and set(series.dropna().unique()) <= {0, 1}


def validate_transaction_dataset(
    df: pd.DataFrame,
    columns: Sequence[ColumnSpec] = REQUIRED_COLUMNS,
) -> None:
    """Validate ``df`` against the contract; raise ``DatasetSchemaError`` on failure.

    All problems are collected and reported together so one CI run shows
    everything that is wrong.
    """
    if df.empty:
        raise DatasetSchemaError("Dataset is empty: at least one transaction row is required.")

    missing = [spec.name for spec in columns if spec.name not in df.columns]
    if missing:
        raise DatasetSchemaError(
            f"Missing required columns: {missing}. "
            f"Expected contract columns: {[spec.name for spec in columns]}; "
            f"got: {list(df.columns)}."
        )

    problems: list[str] = []
    for spec in columns:
        series = df[spec.name]
        if not _kind_matches(series, spec.kind):
            problems.append(f"column '{spec.name}' must be {spec.kind}, got dtype {series.dtype}")
        null_count = int(series.isna().sum())
        if null_count:
            problems.append(f"column '{spec.name}' has {null_count} null value(s)")
    if problems:
        raise DatasetSchemaError("Dataset schema violations: " + "; ".join(problems) + ".")


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return numeric model features (``FEATURE_COLUMNS``) derived from the contract.

    Identifiers, raw strings, the label and leakage columns are never included.
    """
    validate_transaction_dataset(df, REQUIRED_COLUMNS + FEATURE_SOURCE_COLUMNS)

    timestamps = df[TIMESTAMP]
    amount = df[AMOUNT].astype(float)
    channel_index = {name: code for code, name in enumerate(CHANNELS)}

    features = pd.DataFrame(
        {
            "amount": amount,
            "log_amount": np.log1p(amount.clip(lower=0)),
            "hour": timestamps.dt.hour,
            "day_of_week": timestamps.dt.dayofweek,
            "is_night": timestamps.dt.hour.lt(6).astype(int),
            "cross_city": df[SENDER_CITY].ne(df[RECEIVER_CITY]).astype(int),
            "description_length": df[DESCRIPTION].fillna("").str.len(),
            "channel_code": df[CHANNEL].map(channel_index).fillna(-1).astype(int),
            "sender_tx_count": df.groupby(SENDER_IBAN)[TRANSACTION_ID].transform("count"),
            "receiver_tx_count": df.groupby(RECEIVER_IBAN)[TRANSACTION_ID].transform("count"),
            "sender_device_count": df.groupby(SENDER_IBAN)[DEVICE_ID].transform("nunique"),
        },
        index=df.index,
    )
    return features[list(FEATURE_COLUMNS)]


def label_series(df: pd.DataFrame) -> pd.Series:
    """Return the fraud label as integers (0/1)."""
    return df[LABEL].astype(int)


def main(argv: Sequence[str] | None = None) -> int:
    """Generate a sample dataset and validate it against the contract."""
    parser = argparse.ArgumentParser(description="Validate the transaction dataset contract")
    parser.add_argument("--sample-size", type=int, default=1000)
    parser.add_argument("--fraud-ratio", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    from sentinelflow.ml.competition_dataset import CompetitionDatasetGenerator

    generator = CompetitionDatasetGenerator(seed=args.seed, n_users=100)
    df = generator.generate(n_transactions=args.sample_size, fraud_ratio=args.fraud_ratio)

    try:
        validate_transaction_dataset(df)
        features = build_feature_frame(df)
    except DatasetSchemaError as exc:
        print(f"Data validation failed: {exc}")
        return 1

    print("Data validation passed!")
    print(f"Rows: {len(df)}, Columns: {len(df.columns)}, Features: {features.shape[1]}")
    print(f"Fraud ratio: {label_series(df).mean():.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
