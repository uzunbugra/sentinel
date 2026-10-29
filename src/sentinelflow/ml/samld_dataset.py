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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

TRANSFORM_VERSION = "samld-v1"
MANIFEST_SCHEMA_VERSION = 1
SOURCE_ENV_VAR = "SENTINELFLOW_SAMLD_PATH"
SOURCE_MEMBER = "SAML-D.csv"
KAGGLE_DATASET = "berkanoztas/synthetic-transaction-monitoring-dataset-aml"
TRANSACTION_ID_PREFIX = "SAMLD-"
AMOUNT_SCALE = 50
UNKNOWN = "unknown"

# Default chronological split (ADR 0003 §3).
DEFAULT_TRAIN_FRACTION = 0.70
DEFAULT_VAL_FRACTION = 0.15
SPLITS: tuple[str, ...] = ("train", "val", "test")

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
SPLIT_COLUMN = "split"
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

# --- Display identities --------------------------------------------------------
# Fictional 5-digit bank codes (not assigned to real Turkish banks). Name lists are
# common Turkish names; FIRST_NAMES is 40 male then 40 female names.
DISPLAY_BANK_CODES: tuple[str, ...] = tuple(f"9{n:04d}" for n in range(1, 12))
# fmt: off
FIRST_NAMES: tuple[str, ...] = (
    "Ahmet", "Mehmet", "Mustafa", "Ali", "Hüseyin", "Hasan", "İbrahim", "Murat", "Ömer",
    "Yusuf", "Emre", "Burak", "Can", "Cem", "Deniz", "Eren", "Fatih", "Gökhan", "Halil",
    "Kemal", "Kerem", "Levent", "Onur", "Orhan", "Serkan", "Sinan", "Tolga", "Uğur", "Volkan",
    "Yasin", "Bora", "Tuncay", "Barış", "Enes", "Furkan", "Hakan", "Selim", "Tarık", "Umut",
    "Berk", "Ayşe", "Fatma", "Emine", "Hatice", "Zeynep", "Elif", "Meryem", "Şerife", "Zehra",
    "Sultan", "Hanife", "Merve", "Büşra", "Esra", "Gizem", "Selin", "Ece", "Derya", "Ebru",
    "Özlem", "Pınar", "Seda", "Tuğba", "Yasemin", "Nur", "Aslı", "Burcu", "Cansu", "Dilek",
    "Gamze", "İrem", "Kübra", "Melike", "Neslihan", "Sevgi", "Sibel", "Şule", "Tuba", "Yağmur",
    "Zerrin",
)
LAST_NAMES: tuple[str, ...] = (
    "Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Yıldırım", "Öztürk", "Aydın",
    "Özdemir", "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara", "Koç", "Kurt", "Özkan",
    "Şimşek", "Polat", "Özcan", "Korkmaz", "Çakır", "Erdoğan", "Yavuz", "Can", "Acar", "Şen",
    "Aktaş", "Güler", "Yalçın", "Güneş", "Kartal", "Bulut", "Keskin", "Ünal", "Turan", "Gül",
    "Özer", "Işık", "Kaplan", "Avcı", "Sarı", "Aydemir", "Taş", "Köse", "Yüksel", "Ateş",
    "Aksoy", "Sezer", "Karataş", "Erdem", "Tunç", "Altın", "Toprak", "Karaca", "Özgür", "Duman",
    "Akın",
)
# fmt: on
DOUBLE_FIRST_NAME_PERCENT = 45


class SamldDatasetError(ValueError):
    """Raised when the source or the prepared dataset breaks an ML-02 invariant."""


@dataclass(frozen=True)
class SplitBoundary:
    """Rows with ``timestamp >= start`` belong to ``split`` (until the next boundary)."""

    split: str
    start: pd.Timestamp


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


def _iban(account: str, bank_code: str) -> str:
    """TR IBAN: TR + mod-97 check digits + bank code + reserve 0 + 16-digit account."""
    bban = f"{bank_code}0{int(account):016d}"
    # Move "TR00" to the end and replace letters (T=29, R=27) before mod 97.
    check = 98 - int(f"{bban}292700") % 97
    return f"TR{check:02d}{bban}"


def _display_identity(account: str) -> tuple[str, str]:
    digest = hashlib.sha256(f"{TRANSFORM_VERSION}:{account}".encode()).digest()
    pick = int.from_bytes(digest[:8], "big")
    bank = DISPLAY_BANK_CODES[pick % len(DISPLAY_BANK_CODES)]
    first = FIRST_NAMES[(pick >> 8) % len(FIRST_NAMES)]
    last = LAST_NAMES[(pick >> 16) % len(LAST_NAMES)]
    name = f"{first} {last}"
    if (pick >> 24) % 100 < DOUBLE_FIRST_NAME_PERCENT:
        # Second first name of the same gender half as the first one.
        half = len(FIRST_NAMES) // 2
        offset = 0 if FIRST_NAMES.index(first) < half else half
        second = FIRST_NAMES[offset + (pick >> 32) % half]
        if second != first:
            name = f"{first} {second} {last}"
    return _iban(account, bank), name


def display_identities(accounts: pd.Series) -> pd.DataFrame:
    """IBAN and name per unique account, deterministic in the account id."""
    unique = pd.unique(accounts.astype(str))
    pairs = [_display_identity(account) for account in unique]
    return pd.DataFrame(pairs, index=pd.Index(unique, name="account"), columns=["iban", "name"])


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

    identities = display_identities(pd.concat([out["sender_account"], out["receiver_account"]]))
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
# Chronological split
# =============================================================================


def compute_split_boundaries(
    timestamps: pd.Series,
    train_fraction: float = DEFAULT_TRAIN_FRACTION,
    val_fraction: float = DEFAULT_VAL_FRACTION,
) -> list[SplitBoundary]:
    """Cut a sorted timestamp series into train/val/test by row fraction.

    Each cut moves forward to the first row whose timestamp differs from the previous
    row, so equal timestamps never straddle a boundary.
    """
    if not 0 < train_fraction < 1 or not 0 < val_fraction < 1:
        raise SamldDatasetError("Split fractions must be in (0, 1).")
    if train_fraction + val_fraction >= 1:
        raise SamldDatasetError("train_fraction + val_fraction must be < 1 (test needs rows).")
    values = timestamps.to_numpy()
    if len(values) and not (values[1:] >= values[:-1]).all():
        raise SamldDatasetError("Timestamps must be sorted before splitting.")

    n = len(values)
    starts = [0]
    for fraction in (train_fraction, train_fraction + val_fraction):
        cut = min(int(n * fraction), n - 1)
        if cut > 0 and values[cut] == values[cut - 1]:
            # Inside a timestamp group: move the whole group to the later split.
            cut = int(np.searchsorted(values, values[cut], side="right"))
        starts.append(cut)
    if not (0 < starts[1] < starts[2] < n):
        raise SamldDatasetError(
            "Cannot split without breaking a timestamp group: each split needs at least "
            f"one distinct timestamp (row starts {starts}, {n} rows)."
        )
    return [
        SplitBoundary(split, pd.Timestamp(values[start]))
        for split, start in zip(SPLITS, starts, strict=True)
    ]


def assign_splits(timestamps: pd.Series, boundaries: Sequence[SplitBoundary]) -> pd.Series:
    """Label each row with its split from the boundaries' start timestamps."""
    codes = np.zeros(len(timestamps), dtype="int8")
    for boundary in boundaries[1:]:
        codes += (timestamps >= boundary.start).to_numpy(dtype="int8")
    return pd.Series(pd.Categorical.from_codes(codes, categories=list(SPLITS)), name=SPLIT_COLUMN)


def check_split_invariants(df: pd.DataFrame) -> None:
    """Raise unless splits are time-disjoint and in train < val < test order."""
    bounds = df.groupby(SPLIT_COLUMN, observed=False)["timestamp"].agg(["min", "max", "size"])
    for split in SPLITS:
        if bounds.loc[split, "size"] == 0:
            raise SamldDatasetError(f"Split '{split}' is empty.")
    for earlier, later in zip(SPLITS, SPLITS[1:], strict=False):
        if not bounds.loc[earlier, "max"] < bounds.loc[later, "min"]:
            raise SamldDatasetError(
                f"max({earlier})={bounds.loc[earlier, 'max']} must be < "
                f"min({later})={bounds.loc[later, 'min']}."
            )


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
