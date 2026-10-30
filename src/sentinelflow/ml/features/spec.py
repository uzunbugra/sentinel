# =============================================================================
# SentinelFlow - Feature Set fs-1 Specification
# =============================================================================
"""
Feature set ``fs-1`` as fixed in ``docs/contracts/sprint4-ml-api.md`` §1–§2.

This module holds everything a consumer needs to agree on *without* computing
anything: the version string, the ordered feature names, their dtypes, the
fixed category vocabularies and the normalisation of canonical transaction
fields. Training (ML-04), the artifact (ML-05) and the service (ML-06) import
these names; nobody keeps a second copy.

Any change to names, order, dtypes, vocabularies or definitions is a new
feature set version.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

FEATURE_SET_VERSION = "fs-1"

# --- Canonical transaction fields (contract §1) -------------------------------
TRANSACTION_ID = "transaction_id"
TIMESTAMP = "timestamp"
SENDER_ACCOUNT = "sender_account"
RECEIVER_ACCOUNT = "receiver_account"
AMOUNT = "amount"
PAYMENT_CURRENCY = "payment_currency"
RECEIVED_CURRENCY = "received_currency"
SENDER_COUNTRY = "sender_country"
RECEIVER_COUNTRY = "receiver_country"
PAYMENT_TYPE = "payment_type"

REQUIRED_FIELDS: tuple[str, ...] = (
    TRANSACTION_ID,
    TIMESTAMP,
    SENDER_ACCOUNT,
    RECEIVER_ACCOUNT,
    AMOUNT,
    PAYMENT_CURRENCY,
)
OPTIONAL_FIELDS: tuple[str, ...] = (
    RECEIVED_CURRENCY,
    SENDER_COUNTRY,
    RECEIVER_COUNTRY,
    PAYMENT_TYPE,
)
# Label columns of the training set. They are never read by the feature code.
LABEL_FIELDS: tuple[str, ...] = ("is_laundering", "laundering_type")

DEFAULT_COUNTRY = "TR"
UNKNOWN = "unknown"

# --- Ordered feature list (contract §2) ---------------------------------------
FEATURE_DTYPES: dict[str, np.dtype] = {
    "log_amount": np.dtype(np.float32),
    "hour": np.dtype(np.int8),
    "day_of_week": np.dtype(np.int8),
    "payment_type_code": np.dtype(np.int8),
    "currency_mismatch": np.dtype(np.int8),
    "cross_border": np.dtype(np.int8),
    "sender_country_code": np.dtype(np.int8),
    "receiver_country_code": np.dtype(np.int8),
    "sender_tx_count_24h": np.dtype(np.int32),
    "sender_amount_sum_24h": np.dtype(np.float32),
    "sender_unique_receivers_7d": np.dtype(np.int32),
    "receiver_tx_count_24h": np.dtype(np.int32),
    "receiver_unique_senders_7d": np.dtype(np.int32),
    "pair_tx_count_7d": np.dtype(np.int32),
    "sender_seconds_since_prev": np.dtype(np.float32),
}
FEATURE_NAMES: tuple[str, ...] = tuple(FEATURE_DTYPES)
NUM_FEATURES = len(FEATURE_NAMES)
CATEGORICAL_FEATURES: tuple[str, ...] = (
    "payment_type_code",
    "sender_country_code",
    "receiver_country_code",
)

# Value of ``sender_seconds_since_prev`` when the sender has no earlier event.
NO_PREVIOUS_SECONDS = -1.0

# --- History windows ----------------------------------------------------------
NS_PER_SECOND = 1_000_000_000
WINDOW_24H_NS = 24 * 3600 * NS_PER_SECOND
WINDOW_7D_NS = 7 * 24 * 3600 * NS_PER_SECOND
MAX_WINDOW_NS = WINDOW_7D_NS

# --- Category vocabularies ----------------------------------------------------
# Fixed order -> stable integer codes. Code 0 is always ``unknown``; known values
# start at 1. Append-only in a new feature set version, never reorder.
#
# Payment types are SAML-D ``Payment_type`` values, lower-cased with spaces and
# hyphens turned into ``_`` ("Cash Deposit" -> "cash_deposit").
PAYMENT_TYPES: tuple[str, ...] = (
    UNKNOWN,
    "ach",
    "cash_deposit",
    "cash_withdrawal",
    "cheque",
    "credit_card",
    "cross_border",
    "debit_card",
)
# ISO-3166 alpha-2 codes of the SAML-D bank locations. UK and Turkey swap places
# (UK -> TR, Turkey -> GB), so the mapping stays one to one (contract §1).
COUNTRIES: tuple[str, ...] = (
    UNKNOWN,
    "TR",
    "AE",
    "AL",
    "AT",
    "CH",
    "DE",
    "ES",
    "FR",
    "IN",
    "IT",
    "JP",
    "MA",
    "MX",
    "NG",
    "NL",
    "PK",
    "US",
    "GB",
)
# ISO-4217 codes of the SAML-D currencies. UK pounds and Turkish lira swap places
# (UK pounds -> TRY, Turkish lira -> GBP). Not a model input in fs-1 (only
# ``currency_mismatch`` is); kept here so data prep and the service validate
# against one list.
CURRENCIES: tuple[str, ...] = (
    UNKNOWN,
    "TRY",
    "AED",
    "ALL",
    "CHF",
    "EUR",
    "INR",
    "JPY",
    "MAD",
    "MXN",
    "NGN",
    "PKR",
    "USD",
    "GBP",
)

PAYMENT_TYPE_CODES: dict[str, int] = {name: code for code, name in enumerate(PAYMENT_TYPES)}
COUNTRY_CODES: dict[str, int] = {name: code for code, name in enumerate(COUNTRIES)}
CURRENCY_CODES: dict[str, int] = {name: code for code, name in enumerate(CURRENCIES)}
UNKNOWN_CODE = 0

assert max(len(PAYMENT_TYPES), len(COUNTRIES)) <= np.iinfo(np.int8).max


class FeatureInputError(ValueError):
    """A canonical transaction is missing a required field or has a bad value."""


def is_missing(value: Any) -> bool:
    """None, NaN, ``pd.NA``/``NaT`` or a blank string."""
    # Called several times per row on the batch path; strings first.
    if type(value) is str:
        return not value or value.isspace()
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    return isinstance(value, str) and (not value or value.isspace())


@lru_cache(maxsize=1024)
def normalize_payment_type(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


@lru_cache(maxsize=1024)
def normalize_code(value: str) -> str:
    """Country and currency codes compare upper-cased without surrounding space."""
    return value.strip().upper()


def payment_type_code(payment_type: str) -> int:
    return PAYMENT_TYPE_CODES.get(payment_type, UNKNOWN_CODE)


def country_code(country: str) -> int:
    return COUNTRY_CODES.get(country, UNKNOWN_CODE)


def optional_value(value: Any) -> str | None:
    """An optional string field; None when missing (the caller applies the default)."""
    return None if is_missing(value) else str(value)


def required_value(value: Any, field: str) -> str:
    """A required string field (ids are opaque keys, kept as given).

    Numeric ids become their decimal string; a float id column (e.g. one with
    NaNs) would turn into ``"123.0"``, so data prep must deliver ids as strings.
    """
    if is_missing(value):
        raise FeatureInputError(f"missing required field {field!r}")
    return str(value)


def validate_amount(value: Any) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise FeatureInputError(f"amount must be a number, got {value!r}")
    if not math.isfinite(amount) or amount <= 0:
        raise FeatureInputError(f"amount must be finite and > 0, got {value!r}")
    return amount
