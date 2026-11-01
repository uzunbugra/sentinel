# =============================================================================
# SentinelFlow - SAML-D Training Dataset Preparation (ML-02)
# =============================================================================
"""
Turn the raw SAML-D CSV into the canonical transaction record of
``docs/contracts/sprint4-ml-api.md`` §1, split it chronologically and write a
manifest that identifies the result.

The transformation is a *labelled* one, not real FX or geography:

- every ``Amount`` is multiplied by a fixed ``AMOUNT_SCALE`` (x50) and labelled TRY;
  SAML-D amounts share one (pound) scale whatever the payment currency is;
- the UK and Turkey bank locations swap places (UK -> ``TR``, Turkey -> ``GB``), and
  so do UK pounds and Turkish lira (-> ``TRY`` / ``GBP``), so the mapping stays 1:1;
- account identifiers are kept unchanged as strings: they are the history key.
  ``*_iban`` / ``*_name`` are display-only columns derived deterministically from
  the account identifier (no RNG); they are never model input.

The raw data never enters the repository; its path is a CLI argument or the
``SENTINELFLOW_SAMLD_PATH`` environment variable. A ``.zip`` holding ``SAML-D.csv``
(the Kaggle download) is read directly.

CLI::

    python -m sentinelflow.ml.samld_dataset --source path/to/archive.zip --out data/samld
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sentinelflow.ml.samld_identity import display_identities
from sentinelflow.ml.samld_split import (
    DEFAULT_TRAIN_FRACTION,
    DEFAULT_VAL_FRACTION,
    SPLIT_COLUMN,
    SPLITS,
    SamldDatasetError,
    SplitBoundary,
    assign_splits,
    check_split_invariants,
    compute_split_boundaries,
)

TRANSFORM_VERSION = "samld-v1"
MANIFEST_SCHEMA_VERSION = 1
SOURCE_ENV_VAR = "SENTINELFLOW_SAMLD_PATH"
SOURCE_MEMBER = "SAML-D.csv"
KAGGLE_DATASET = "berkanoztas/synthetic-transaction-monitoring-dataset-aml"
TRANSACTION_ID_PREFIX = "SAMLD-"
AMOUNT_SCALE = 50
UNKNOWN = "unknown"

# Default chronological split (ADR 0003 §3).

# --- Raw SAML-D columns -------------------------------------------------------
RAW_COLUMNS: tuple[str, ...] = (
    "Time",
    "Date",
    "Sender_account",
    "Receiver_account",
    "Amount",
    "Payment_currency",
    "Received_currency",
    "Sender_bank_location",
    "Receiver_bank_location",
    "Payment_type",
    "Is_laundering",
    "Laundering_type",
)

# --- Canonical record (contract §1), in output order ---------------------------
CANONICAL_COLUMNS: tuple[str, ...] = (
    "transaction_id",
    "timestamp",
    "sender_account",
    "receiver_account",
    "amount",
    "payment_currency",
    "received_currency",
    "sender_country",
    "receiver_country",
    "payment_type",
    "is_laundering",
    "laundering_type",
)
# Display-only columns (demo/UI); derived from the account id, never features.
DISPLAY_COLUMNS: tuple[str, ...] = ("sender_iban", "sender_name", "receiver_iban", "receiver_name")
OUTPUT_COLUMNS: tuple[str, ...] = CANONICAL_COLUMNS + DISPLAY_COLUMNS + (SPLIT_COLUMN,)

# --- Category vocabularies (raw value -> canonical code) -----------------------
COUNTRY_CODES: Mapping[str, str] = {
    "UK": "TR",
    "Turkey": "GB",
    "Albania": "AL",
    "Austria": "AT",
    "France": "FR",
    "Germany": "DE",
    "India": "IN",
    "Italy": "IT",
    "Japan": "JP",
    "Mexico": "MX",
    "Morocco": "MA",
    "Netherlands": "NL",
    "Nigeria": "NG",
    "Pakistan": "PK",
    "Spain": "ES",
    "Switzerland": "CH",
    "UAE": "AE",
    "USA": "US",
}
CURRENCY_CODES: Mapping[str, str] = {
    "UK pounds": "TRY",
    "Turkish lira": "GBP",
    "Albanian lek": "ALL",
    "Dirham": "AED",
    "Euro": "EUR",
    "Indian rupee": "INR",
    "Mexican Peso": "MXN",
    "Moroccan dirham": "MAD",
    "Naira": "NGN",
    "Pakistani rupee": "PKR",
    "Swiss franc": "CHF",
    "US dollar": "USD",
    "Yen": "JPY",
}
PAYMENT_TYPES: Mapping[str, str] = {
    "ACH": "ach",
    "Cash Deposit": "cash_deposit",
    "Cash Withdrawal": "cash_withdrawal",
    "Cheque": "cheque",
    "Credit card": "credit_card",
    "Cross-border": "cross_border",
    "Debit card": "debit_card",
}

# =============================================================================
# Source handling
# =============================================================================


def _open_source(path: Path):
    if path.suffix.lower() == ".zip":
        archive = zipfile.ZipFile(path)
        names = archive.namelist()
        if SOURCE_MEMBER not in names:
            raise SamldDatasetError(f"{path} does not contain {SOURCE_MEMBER}; members: {names}")
        return archive.open(SOURCE_MEMBER)
    return path.open("rb")


def _sha256_stream(stream, chunk_size: int = 1 << 22) -> str:
    digest = hashlib.sha256()
    while chunk := stream.read(chunk_size):
        digest.update(chunk)
    return digest.hexdigest()


def source_fingerprint(path: Path) -> dict[str, Any]:
    """SHA-256 of the CSV bytes (stable across re-zips) and of the file given."""
    with _open_source(path) as stream:
        csv_sha = _sha256_stream(stream)
    info: dict[str, Any] = {
        "file_name": path.name,
        "file_size_bytes": path.stat().st_size,
        "csv_member": SOURCE_MEMBER if path.suffix.lower() == ".zip" else path.name,
        "csv_sha256": csv_sha,
        "kaggle_dataset": KAGGLE_DATASET,
    }
    if path.suffix.lower() == ".zip":
        with path.open("rb") as stream:
            info["file_sha256"] = _sha256_stream(stream)
    else:
        info["file_sha256"] = csv_sha
    return info


def read_source(path: Path) -> pd.DataFrame:
    """Read the raw SAML-D CSV (or the Kaggle zip) with identifiers as strings."""
    categorical = (
        "Payment_currency",
        "Received_currency",
        "Sender_bank_location",
        "Receiver_bank_location",
        "Payment_type",
        "Laundering_type",
    )
    dtypes: dict[str, Any] = dict.fromkeys(categorical, "category")
    dtypes.update(
        {
            "Time": "string[pyarrow]",
            "Date": "string[pyarrow]",
            "Sender_account": "string[pyarrow]",
            "Receiver_account": "string[pyarrow]",
            "Amount": "float64",
            "Is_laundering": "int8",
        }
    )
    with _open_source(path) as stream:
        raw = pd.read_csv(stream, dtype=dtypes, engine="pyarrow")
    missing = [name for name in RAW_COLUMNS if name not in raw.columns]
    if missing:
        raise SamldDatasetError(f"Source is missing SAML-D columns: {missing}")
    return raw[list(RAW_COLUMNS)]


# =============================================================================
# Transformation
# =============================================================================


def _map_category(series: pd.Series, vocabulary: Mapping[str, str]) -> pd.Series:
    """Map raw categories through ``vocabulary``; anything unseen becomes ``unknown``."""
    return series.astype("string").map(vocabulary).fillna(UNKNOWN).astype("category")


def transform(raw: pd.DataFrame) -> pd.DataFrame:
    """Return the canonical record (contract §1) plus display columns, in source order.

    ``transaction_id`` is ``SAMLD-<0-based source row, 9 digits>``; with the source in
    time order, sorting by ``(timestamp, transaction_id)`` keeps the source order.
    """
    if raw.empty:
        raise SamldDatasetError("Source is empty: at least one transaction row is required.")
    if not raw["Sender_account"].str.fullmatch(r"\d+").all() or not (
        raw["Receiver_account"].str.fullmatch(r"\d+").all()
    ):
        raise SamldDatasetError("Account identifiers must be non-empty digit strings.")

    timestamp = pd.to_datetime(
        raw["Date"].astype(str) + " " + raw["Time"].astype(str),
        format="%Y-%m-%d %H:%M:%S",
        utc=True,
    )
    row_number = np.arange(len(raw))
    out = pd.DataFrame(
        {
            "transaction_id": pd.Series(
                [f"{TRANSACTION_ID_PREFIX}{n:09d}" for n in row_number], dtype="string[pyarrow]"
            ),
            "timestamp": timestamp.to_numpy(),
            "sender_account": raw["Sender_account"].astype("string[pyarrow]").to_numpy(),
            "receiver_account": raw["Receiver_account"].astype("string[pyarrow]").to_numpy(),
            "amount": (raw["Amount"].to_numpy(dtype="float64") * AMOUNT_SCALE).round(2),
            "payment_currency": _map_category(raw["Payment_currency"], CURRENCY_CODES).to_numpy(),
            "received_currency": _map_category(raw["Received_currency"], CURRENCY_CODES).to_numpy(),
            "sender_country": _map_category(raw["Sender_bank_location"], COUNTRY_CODES).to_numpy(),
            "receiver_country": _map_category(
                raw["Receiver_bank_location"], COUNTRY_CODES
            ).to_numpy(),
            "payment_type": _map_category(raw["Payment_type"], PAYMENT_TYPES).to_numpy(),
            "is_laundering": raw["Is_laundering"].to_numpy(dtype="int8"),
            "laundering_type": raw["Laundering_type"].astype("category").to_numpy(),
        }
    )
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)

    if not (out["amount"] > 0).all():
        raise SamldDatasetError("Every amount must be > 0.")
    if not out["is_laundering"].isin([0, 1]).all():
        raise SamldDatasetError("is_laundering must be 0 or 1.")

    identities = display_identities(
        pd.concat([out["sender_account"], out["receiver_account"]]), TRANSFORM_VERSION
    )
    for side in ("sender", "receiver"):
        matched = identities.reindex(out[f"{side}_account"].astype(str).to_numpy())
        out[f"{side}_iban"] = pd.Series(matched["iban"].to_numpy(), dtype="string[pyarrow]")
        out[f"{side}_name"] = pd.Series(matched["name"].to_numpy(), dtype="string[pyarrow]")

    # Deterministic event order (ADR 0003 §4); ids grow with source rows.
    order = np.argsort(out["timestamp"].to_numpy(), kind="stable")
    if not np.array_equal(order, row_number):
        out = out.iloc[order].reset_index(drop=True)
    return out


# =============================================================================
# Manifest
# =============================================================================


def _git_state(repo_dir: Path) -> dict[str, Any]:
    def run(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args], cwd=repo_dir, capture_output=True, text=True, check=True
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return result.stdout.strip()

    status = run("status", "--porcelain", "--untracked-files=no")
    return {
        "git_sha": run("rev-parse", "HEAD"),
        "git_dirty": None if status is None else bool(status),
    }


def make_dataset_id(source_sha256: str, parameters: Mapping[str, Any]) -> str:
    payload = json.dumps(
        {"source_sha256": source_sha256, "transform_version": TRANSFORM_VERSION, **parameters},
        sort_keys=True,
    )
    return "samld-" + hashlib.sha256(payload.encode()).hexdigest()[:12]


def _iso(value: pd.Timestamp) -> str:
    return pd.Timestamp(value).tz_convert("UTC").isoformat()


def _counts(series: pd.Series) -> dict[str, int]:
    return {str(k): int(v) for k, v in sorted(series.value_counts().items()) if v}


def content_sha256(df: pd.DataFrame) -> str:
    """Hash of the row values (independent of the Parquet encoding)."""
    hashed = pd.util.hash_pandas_object(df[list(OUTPUT_COLUMNS)], index=False)
    return hashlib.sha256(hashed.to_numpy().tobytes()).hexdigest()


def build_manifest(
    df: pd.DataFrame,
    source: Mapping[str, Any],
    boundaries: Sequence[SplitBoundary],
    parameters: Mapping[str, Any],
    git: Mapping[str, Any],
    output_file: str,
) -> dict[str, Any]:
    dataset_id = make_dataset_id(source["csv_sha256"], parameters)
    splits: dict[str, Any] = {}
    for boundary in boundaries:
        part = df[df[SPLIT_COLUMN] == boundary.split]
        positives = int(part["is_laundering"].sum())
        splits[boundary.split] = {
            "rows": len(part),
            "positives": positives,
            "positive_rate": positives / len(part),
            "timestamp_min": _iso(part["timestamp"].min()),
            "timestamp_max": _iso(part["timestamp"].max()),
            "start_inclusive": _iso(boundary.start),
            "laundering_type_counts": _counts(
                part.loc[part["is_laundering"] == 1, "laundering_type"].astype(str)
            ),
        }
    positives = int(df["is_laundering"].sum())
    unknown = {
        column: int((df[column] == UNKNOWN).sum())
        for column in (
            "payment_currency",
            "received_currency",
            "sender_country",
            "receiver_country",
            "payment_type",
        )
    }
    accounts = pd.concat([df["sender_account"], df["receiver_account"]]).nunique()
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "transform_version": TRANSFORM_VERSION,
        "source": dict(source),
        "parameters": dict(parameters),
        "git_sha": git.get("git_sha"),
        "git_dirty": git.get("git_dirty"),
        "output": {
            "file": output_file,
            "columns": list(OUTPUT_COLUMNS),
            "content_sha256": content_sha256(df),
        },
        "rows": len(df),
        "positives": positives,
        "negatives": len(df) - positives,
        "positive_rate": positives / len(df),
        "unique_accounts": int(accounts),
        "timestamp_min": _iso(df["timestamp"].min()),
        "timestamp_max": _iso(df["timestamp"].max()),
        "unknown_category_counts": unknown,
        "splits": splits,
        "sampling": None,
    }


# =============================================================================
# Pipeline
# =============================================================================


def prepare(
    source_path: Path,
    out_dir: Path,
    train_fraction: float = DEFAULT_TRAIN_FRACTION,
    val_fraction: float = DEFAULT_VAL_FRACTION,
    repo_dir: Path | None = None,
) -> dict[str, Any]:
    """Run ML-02 end to end; write ``<out_dir>/<dataset_id>/`` and return the manifest."""
    source = source_fingerprint(source_path)
    df = transform(read_source(source_path))
    boundaries = compute_split_boundaries(df["timestamp"], train_fraction, val_fraction)
    df[SPLIT_COLUMN] = assign_splits(df["timestamp"], boundaries).to_numpy()
    check_split_invariants(df)
    if df["transaction_id"].duplicated().any():
        raise SamldDatasetError("transaction_id must be unique.")

    parameters = {
        "train_fraction": train_fraction,
        "val_fraction": val_fraction,
        "test_fraction": round(1 - train_fraction - val_fraction, 10),
        "split_method": "chronological_row_fraction_timestamp_groups_intact",
        "amount_scale": AMOUNT_SCALE,
        "sampling": None,
        "seed": None,
    }
    git = _git_state(repo_dir or Path(__file__).resolve().parent)
    output_file = "transactions.parquet"
    manifest = build_manifest(df, source, boundaries, parameters, git, output_file)

    target = out_dir / manifest["dataset_id"]
    target.mkdir(parents=True, exist_ok=True)
    df[list(OUTPUT_COLUMNS)].to_parquet(target / output_file, index=False)
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare the SAML-D training dataset (ML-02)")
    parser.add_argument(
        "--source",
        type=Path,
        default=os.environ.get(SOURCE_ENV_VAR),
        help=f"SAML-D.csv or the Kaggle zip (default: ${SOURCE_ENV_VAR})",
    )
    parser.add_argument("--out", type=Path, default=Path("data/samld"))
    parser.add_argument("--train-fraction", type=float, default=DEFAULT_TRAIN_FRACTION)
    parser.add_argument("--val-fraction", type=float, default=DEFAULT_VAL_FRACTION)
    args = parser.parse_args(argv)

    if args.source is None:
        parser.error(f"--source is required (or set {SOURCE_ENV_VAR})")
    if not Path(args.source).is_file():
        parser.error(f"source not found: {args.source}")

    try:
        manifest = prepare(Path(args.source), args.out, args.train_fraction, args.val_fraction)
    except SamldDatasetError as exc:
        print(f"SAML-D preparation failed: {exc}")
        return 1

    print(f"dataset_id: {manifest['dataset_id']}")
    print(f"rows: {manifest['rows']}, positives: {manifest['positives']}")
    for split, info in manifest["splits"].items():
        print(
            f"{split}: {info['rows']} rows, {info['positives']} positives, "
            f"{info['timestamp_min']} -> {info['timestamp_max']}"
        )
    print(f"written: {args.out / manifest['dataset_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
