# =============================================================================
# SentinelFlow - fs-1 feature engine tests (ML-03)
# =============================================================================
"""
Contract: ``docs/contracts/sprint4-ml-api.md`` §2 and §5, ADR 0003 §4.

Besides batch <-> streaming parity, every vector is compared with a naive
reference written straight from the contract text (datetime arithmetic, full
scan of earlier events), so the two engine paths cannot agree on a shared bug.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from sentinelflow.ml.features import (
    CATEGORICAL_FEATURES,
    COUNTRIES,
    CURRENCIES,
    FEATURE_DTYPES,
    FEATURE_NAMES,
    FEATURE_SET_VERSION,
    PAYMENT_TYPES,
    UNKNOWN,
    UNKNOWN_CODE,
    AccountHistory,
    FeatureInputError,
    build_features_batch,
)
from sentinelflow.ml.features import __main__ as fixture_cli
from sentinelflow.ml.features.spec import CURRENCY_CODES

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ml"
T0 = datetime(2022, 10, 1, 9, 0, 0, tzinfo=timezone.utc)

CONTRACT_FEATURES = (
    ("log_amount", "float32"),
    ("hour", "int8"),
    ("day_of_week", "int8"),
    ("payment_type_code", "int8"),
    ("currency_mismatch", "int8"),
    ("cross_border", "int8"),
    ("sender_country_code", "int8"),
    ("receiver_country_code", "int8"),
    ("sender_tx_count_24h", "int32"),
    ("sender_amount_sum_24h", "float32"),
    ("sender_unique_receivers_7d", "int32"),
    ("receiver_tx_count_24h", "int32"),
    ("receiver_unique_senders_7d", "int32"),
    ("pair_tx_count_7d", "int32"),
    ("sender_seconds_since_prev", "float32"),
)


# --- helpers ------------------------------------------------------------------
def make_tx(tid: str, ts: datetime | str, sender: str, receiver: str, amount: float, **kw) -> dict:
    tx = {
        "transaction_id": tid,
        "timestamp": ts if isinstance(ts, str) else ts.isoformat(),
        "sender_account": sender,
        "receiver_account": receiver,
        "amount": amount,
        "payment_currency": "TRY",
    }
    tx.update(kw)
    return tx


def to_frame(transactions: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(transactions)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    return df


def stream(transactions: list[dict], history: AccountHistory | None = None) -> np.ndarray:
    history = AccountHistory() if history is None else history
    rows = []
    for tx in transactions:
        rows.append(history.features_for(tx))
        history.record(tx)
    return np.vstack(rows) if rows else np.empty((0, len(FEATURE_NAMES)))


def batch(transactions: list[dict]) -> np.ndarray:
    return build_features_batch(to_frame(transactions)).to_numpy(dtype=np.float64)


def sort_key(tx: dict) -> tuple:
    return (pd.Timestamp(tx["timestamp"]).tz_convert("UTC"), tx["transaction_id"])


def reference_vectors(transactions: list[dict]) -> np.ndarray:
    """Contract §2 read literally; ``transactions`` must already be in stream order."""
    seen: set[str] = set()
    recorded: list[dict] = []
    out = []
    for tx in transactions:
        t = datetime.fromisoformat(tx["timestamp"]).astimezone(timezone.utc)
        key = (t, tx["transaction_id"])
        prev = [e for e in recorded if (e["t"], e["id"]) < key]
        sender, receiver = tx["sender_account"], tx["receiver_account"]
        s_prev = [e for e in prev if e["s"] == sender]
        r_prev = [e for e in prev if e["r"] == receiver]
        s24 = [e for e in s_prev if e["t"] >= t - timedelta(hours=24)]
        s7 = [e for e in s_prev if e["t"] >= t - timedelta(days=7)]
        r24 = [e for e in r_prev if e["t"] >= t - timedelta(hours=24)]
        r7 = [e for e in r_prev if e["t"] >= t - timedelta(days=7)]
        pay = tx["payment_currency"].strip().upper()
        rec = (tx.get("received_currency") or pay).strip().upper()
        s_cty = (tx.get("sender_country") or "TR").strip().upper()
        r_cty = (tx.get("receiver_country") or "TR").strip().upper()
        ptype = (
            (tx.get("payment_type") or UNKNOWN).strip().lower().replace(" ", "_").replace("-", "_")
        )
        last = max((e["t"] for e in s_prev), default=None)
        out.append(
            [
                np.float32(np.log1p(tx["amount"])),
                t.hour,
                t.weekday(),
                PAYMENT_TYPES.index(ptype) if ptype in PAYMENT_TYPES else 0,
                int(pay != rec),
                int(s_cty != r_cty),
                COUNTRIES.index(s_cty) if s_cty in COUNTRIES else 0,
                COUNTRIES.index(r_cty) if r_cty in COUNTRIES else 0,
                len(s24),
                np.float32(sum(e["amount"] for e in s24)),
                len({e["r"] for e in s7}),
                len(r24),
                len({e["s"] for e in r7}),
                sum(1 for e in s7 if e["r"] == receiver),
                np.float32(-1.0 if last is None else (t - last).total_seconds()),
            ]
        )
        if tx["transaction_id"] not in seen:
            seen.add(tx["transaction_id"])
            recorded.append(
                {
                    "t": t,
                    "id": tx["transaction_id"],
                    "s": sender,
                    "r": receiver,
                    "amount": tx["amount"],
                }
            )
    return np.array(out, dtype=np.float64)


def random_sequence(seed: int, n: int = 300) -> list[dict]:
    """Few accounts, coarse time grid (many ties and exact 24h/7d edges), duplicates."""
    rng = random.Random(seed)
    accounts = [f"ACC-{i}" for i in range(7)]
    txs: list[dict] = []
    for i in range(n):
        if txs and rng.random() < 0.05:
            txs.append(dict(rng.choice(txs)))
            continue
        offset = timedelta(hours=rng.randrange(0, 24 * 20, 6), seconds=rng.choice([0, 0, 0, 1, -1]))
        txs.append(
            make_tx(
                f"R{rng.randrange(10_000):05d}-{i}",
                T0 + offset,
                rng.choice(accounts),
                rng.choice(accounts),
                round(rng.uniform(1, 50_000), 2),
                received_currency=rng.choice(["TRY", "TRY", "EUR", None]),
                sender_country=rng.choice(["TR", "TR", "DE", "ZZ", None]),
                receiver_country=rng.choice(["TR", "AE", None]),
                payment_type=rng.choice(["ach", "Cash Deposit", "cross_border", "wire", None]),
            )
        )
    txs.sort(key=sort_key)
    return txs


def assert_vectors_equal(actual: np.ndarray, expected: np.ndarray) -> None:
    assert actual.shape == expected.shape
    np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-6)


@pytest.fixture(scope="module")
def fixture_transactions() -> list[dict]:
    return fixture_cli.read_jsonl(FIXTURE_DIR / fixture_cli.TRANSACTIONS_FILE)


# --- spec ---------------------------------------------------------------------
def test_feature_names_dtypes_and_order_match_contract():
    assert FEATURE_SET_VERSION == "fs-1"
    assert tuple((n, str(FEATURE_DTYPES[n])) for n in FEATURE_NAMES) == CONTRACT_FEATURES
    assert CATEGORICAL_FEATURES == (
        "payment_type_code",
        "sender_country_code",
        "receiver_country_code",
    )


def test_vocabularies_start_with_unknown_and_are_unique():
    for vocab in (PAYMENT_TYPES, COUNTRIES, CURRENCIES):
        assert vocab[UNKNOWN_CODE] == UNKNOWN
        assert len(set(vocab)) == len(vocab)
        assert len(vocab) <= np.iinfo(np.int8).max


def test_vocabularies_match_contract_and_keep_codes():
    # Contract §1 value sets (what ML-02 produces).
    assert set(PAYMENT_TYPES[1:]) == {
        "ach",
        "cash_deposit",
        "cash_withdrawal",
        "cheque",
        "credit_card",
        "cross_border",
        "debit_card",
    }
    contract_currencies = "AED ALL CHF EUR GBP INR JPY MAD MXN NGN PKR TRY USD"
    contract_countries = "AE AL AT CH DE ES FR GB IN IT JP MA MX NG NL PK TR US"
    assert sorted(CURRENCIES[1:]) == contract_currencies.split(" ")
    assert sorted(COUNTRIES[1:]) == contract_countries.split(" ")
    # Codes are append-only: GB/GBP were added at the end, earlier codes unchanged.
    assert COUNTRIES.index("TR") == 1 and COUNTRIES.index("US") == 17
    assert COUNTRIES[-1] == "GB" and COUNTRIES.index("GB") == 18
    assert CURRENCIES.index("TRY") == 1 and CURRENCIES[-1] == "GBP"


def test_swapped_turkey_and_lira_values_are_not_unknown():
    # SAML-D Turkey -> GB, Turkish lira -> GBP (contract §1); UK -> TR, UK pounds -> TRY.
    tx = make_tx(
        "GB-1",
        T0,
        "S",
        "R",
        1.0,
        payment_currency="GBP",
        received_currency="TRY",
        sender_country="GB",
        receiver_country="TR",
    )
    vec = dict(zip(FEATURE_NAMES, AccountHistory().features_for(tx)))
    assert vec["sender_country_code"] == COUNTRIES.index("GB") != UNKNOWN_CODE
    assert vec["receiver_country_code"] == COUNTRIES.index("TR")
    assert vec["cross_border"] == 1
    assert vec["currency_mismatch"] == 1
    assert CURRENCY_CODES["GBP"] != UNKNOWN_CODE


def test_batch_output_has_contract_columns_dtypes_and_index(fixture_transactions):
    df = to_frame(fixture_transactions)
    df.index = pd.RangeIndex(100, 100 + len(df))
    features = build_features_batch(df)
    assert tuple(features.columns) == FEATURE_NAMES
    assert {c: str(features[c].dtype) for c in features.columns} == dict(CONTRACT_FEATURES)
    assert features.index.equals(df.index)


def test_stream_vector_shape_and_dtype(fixture_transactions):
    vec = AccountHistory().features_for(fixture_transactions[0])
    assert vec.shape == (len(FEATURE_NAMES),)
    assert vec.dtype == np.float64


# --- parity and reference -----------------------------------------------------
def test_fixture_batch_stream_and_reference_agree(fixture_transactions):
    streamed = stream(fixture_transactions)
    assert np.array_equal(batch(fixture_transactions), streamed)
    assert_vectors_equal(streamed, reference_vectors(fixture_transactions))


@pytest.mark.parametrize("seed", range(6))
def test_random_sequence_batch_stream_and_reference_agree(seed):
    txs = random_sequence(seed)
    streamed = stream(txs)
    assert np.array_equal(batch(txs), streamed)
    assert_vectors_equal(streamed, reference_vectors(txs))


def test_batch_sorts_unsorted_input_and_keeps_input_order():
    # Duplicates are dropped here: with them, which copy comes "first" depends on input order.
    shuffled = list({tx["transaction_id"]: tx for tx in random_sequence(11)}.values())
    random.Random(4).shuffle(shuffled)
    ordered = sorted(shuffled, key=sort_key)

    got = build_features_batch(to_frame(shuffled))
    got.index = [tx["transaction_id"] for tx in shuffled]
    expected = pd.DataFrame(stream(ordered), index=[tx["transaction_id"] for tx in ordered])
    assert np.array_equal(got.loc[expected.index].to_numpy(np.float64), expected.to_numpy())


def test_batch_continues_from_given_history(fixture_transactions):
    head, tail = fixture_transactions[:10], fixture_transactions[10:]
    history = AccountHistory()
    stream(head, history)
    continued = build_features_batch(to_frame(tail), history=history)
    assert np.array_equal(continued.to_numpy(np.float64), stream(fixture_transactions)[10:])
    assert history.recorded == len({tx["transaction_id"] for tx in fixture_transactions})


# --- leakage ------------------------------------------------------------------
def test_future_events_do_not_change_earlier_rows():
    txs = random_sequence(21)
    full = batch(txs)
    for cut in (1, 50, 150, 299):
        assert np.array_equal(batch(txs[:cut]), full[:cut])


def test_same_timestamp_events_see_each_other_in_id_order():
    count = FEATURE_NAMES.index("sender_tx_count_24h")
    since = FEATURE_NAMES.index("sender_seconds_since_prev")
    rows = [
        make_tx("T-200", T0, "S", "R", 10.0),
        make_tx("T-300", T0, "S", "R", 20.0),
        make_tx("T-100", T0, "S", "R", 30.0),
    ]
    got = batch(rows)  # input order is kept; processing order is T-100, T-200, T-300
    assert got[:, count].tolist() == [1, 2, 0]
    assert got[:, since].tolist() == [0.0, 0.0, -1.0]


def test_labels_never_reach_features(fixture_transactions):
    df = to_frame(fixture_transactions)
    plain = build_features_batch(df)
    rng = np.random.default_rng(0)
    df["is_laundering"] = rng.integers(0, 2, len(df))
    df["laundering_type"] = rng.choice(["Fan_In", "Normal_Fan_Out"], len(df))
    assert build_features_batch(df).equals(plain)

    history = AccountHistory()
    for tx in fixture_transactions:
        history.record({**tx, "is_laundering": 1, "laundering_type": "Smurfing"})
    other = AccountHistory()
    for tx in fixture_transactions:
        other.record(tx)
    probe = make_tx("Z-1", T0 + timedelta(days=21, hours=4), "ACC-K", "ACC-K", 1.0)
    assert np.array_equal(history.features_for(probe), other.features_for(probe))


def test_features_for_does_not_mutate_state(fixture_transactions):
    history = AccountHistory()
    stream(fixture_transactions[:12], history)
    probe = make_tx("Z-1", T0 + timedelta(days=60), "ACC-A", "ACC-B", 5.0)
    before = history.features_for(fixture_transactions[12])
    history.features_for(probe)
    assert np.array_equal(history.features_for(fixture_transactions[12]), before)
    assert "Z-1" not in history


# --- defaults, categories, windows --------------------------------------------
def test_cold_start_defaults():
    history = AccountHistory()
    tx = make_tx("C-1", T0, "NEW-S", "NEW-R", 100.0)
    vec = dict(zip(FEATURE_NAMES, history.features_for(tx)))
    assert history.is_cold_start(tx)
    for name in FEATURE_NAMES[8:14]:
        assert vec[name] == 0
    assert vec["sender_seconds_since_prev"] == -1.0
    assert vec["currency_mismatch"] == 0 and vec["cross_border"] == 0
    assert vec["payment_type_code"] == UNKNOWN_CODE
    assert vec["sender_country_code"] == vec["receiver_country_code"] == COUNTRIES.index("TR")

    history.record(tx)
    # The receiver now has history, so a transfer out of it is not cold any more.
    assert not history.is_cold_start(make_tx("C-2", T0, "NEW-R", "OTHER", 1.0))


def test_unknown_categories_and_normalisation():
    vec = dict(
        zip(
            FEATURE_NAMES,
            AccountHistory().features_for(
                make_tx(
                    "U-1",
                    T0,
                    "S",
                    "R",
                    1.0,
                    payment_currency=" usd ",
                    received_currency="USD",
                    sender_country="xx",
                    receiver_country=" de",
                    payment_type="Cash Withdrawal",
                )
            ),
        )
    )
    assert vec["payment_type_code"] == PAYMENT_TYPES.index("cash_withdrawal")
    assert vec["currency_mismatch"] == 0
    assert vec["sender_country_code"] == UNKNOWN_CODE
    assert vec["receiver_country_code"] == COUNTRIES.index("DE")
    assert vec["cross_border"] == 1

    unknown_type = AccountHistory().features_for(
        make_tx("U-2", T0, "S", "R", 1.0, payment_type="wire")
    )
    assert unknown_type[FEATURE_NAMES.index("payment_type_code")] == UNKNOWN_CODE


@pytest.mark.parametrize(
    ("window", "count_feature"),
    [(timedelta(hours=24), "sender_tx_count_24h"), (timedelta(days=7), "pair_tx_count_7d")],
)
def test_window_lower_edge_is_inclusive(window, count_feature):
    idx = FEATURE_NAMES.index(count_feature)
    t = T0 + timedelta(days=10)
    for delta, expected in ((window, 1), (window + timedelta(seconds=1), 0)):
        history = AccountHistory()
        history.record(make_tx("W-1", t - delta, "S", "R", 1.0))
        assert history.features_for(make_tx("W-2", t, "S", "R", 1.0))[idx] == expected


def test_seconds_since_prev_survives_window_pruning():
    history = AccountHistory()
    history.record(make_tx("P-1", T0, "S", "R", 1.0))
    history.record(make_tx("P-2", T0 + timedelta(days=30), "S", "R2", 1.0))
    vec = history.features_for(make_tx("P-3", T0 + timedelta(days=40), "S", "R", 1.0))
    assert vec[FEATURE_NAMES.index("sender_seconds_since_prev")] == 10 * 86400
    assert vec[FEATURE_NAMES.index("pair_tx_count_7d")] == 0


def test_hour_and_weekday_use_utc():
    # 2022-10-03 01:30 in Istanbul is Sunday 22:30 UTC.
    vec = AccountHistory().features_for(make_tx("H-1", "2022-10-03T01:30:00+03:00", "S", "R", 1.0))
    assert vec[FEATURE_NAMES.index("hour")] == 22
    assert vec[FEATURE_NAMES.index("day_of_week")] == 6


# --- duplicates, out of order, validation -------------------------------------
def test_duplicate_is_scored_but_recorded_once():
    history = AccountHistory()
    tx = make_tx("D-1", T0, "S", "R", 10.0)
    first = history.features_for(tx)
    assert history.record(tx) is True
    assert np.array_equal(history.features_for(tx), first)
    assert history.record(tx) is False
    assert history.recorded == 1 and history.duplicates == 1
    nxt = history.features_for(make_tx("D-2", T0 + timedelta(minutes=1), "S", "R", 1.0))
    assert nxt[FEATURE_NAMES.index("sender_tx_count_24h")] == 1


def test_out_of_order_record_is_counted_and_used():
    history = AccountHistory()
    history.record(make_tx("O-2", T0 + timedelta(hours=2), "S", "R", 1.0))
    history.record(make_tx("O-1", T0 + timedelta(hours=1), "S", "R", 1.0))
    assert history.out_of_order == 1
    vec = history.features_for(make_tx("O-3", T0 + timedelta(hours=3), "S", "R", 1.0))
    assert vec[FEATURE_NAMES.index("sender_tx_count_24h")] == 2
    # A late what-if only sees what precedes it.
    late = history.features_for(make_tx("O-0", T0 + timedelta(hours=1, minutes=30), "S", "R", 1.0))
    assert late[FEATURE_NAMES.index("sender_tx_count_24h")] == 1
    assert late[FEATURE_NAMES.index("sender_seconds_since_prev")] == 1800


@pytest.mark.parametrize(
    "change",
    [
        {"timestamp": "2022-10-01T09:00:00"},
        {"timestamp": None},
        {"amount": 0},
        {"amount": float("nan")},
        {"amount": "abc"},
        {"sender_account": ""},
        {"payment_currency": None},
        {"transaction_id": None},
    ],
)
def test_invalid_transactions_are_rejected(change):
    tx = {**make_tx("V-1", T0, "S", "R", 1.0), **change}
    with pytest.raises(FeatureInputError):
        AccountHistory().features_for(tx)


def test_batch_rejects_naive_timestamps_and_missing_columns():
    df = pd.DataFrame([make_tx("V-1", T0, "S", "R", 1.0)])
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
    with pytest.raises(FeatureInputError, match="timezone-aware"):
        build_features_batch(df)
    with pytest.raises(FeatureInputError, match="missing required columns"):
        build_features_batch(df.drop(columns=["amount"]))


def test_empty_batch():
    df = to_frame([make_tx("E-1", T0, "S", "R", 1.0)]).iloc[:0]
    features = build_features_batch(df)
    assert features.shape == (0, len(FEATURE_NAMES))
    assert tuple(features.columns) == FEATURE_NAMES


# --- shared fixture (contract §5) ---------------------------------------------
def test_expected_features_fixture_is_up_to_date(fixture_transactions):
    path = FIXTURE_DIR / fixture_cli.EXPECTED_FILE
    expected = fixture_cli.read_jsonl(path)
    assert expected == fixture_cli.expected_rows(fixture_transactions)
    assert [row["transaction_id"] for row in expected] == [
        tx["transaction_id"] for tx in fixture_transactions
    ]
    assert fixture_cli.main(["expected", str(FIXTURE_DIR), "--check"]) == 0


def test_fixture_covers_contract_cases(fixture_transactions):
    ids = [tx["transaction_id"] for tx in fixture_transactions]
    keys = [sort_key(tx) for tx in fixture_transactions]
    timestamps = [k[0] for k in keys]
    assert keys == sorted(keys), "fixture must be in stream order"
    assert len(ids) != len(set(ids)), "needs a duplicate transaction_id"
    assert len(timestamps) != len(set(timestamps)), "needs same-timestamp events"
    vectors = stream(fixture_transactions)
    since_prev = vectors[:, FEATURE_NAMES.index("sender_seconds_since_prev")]
    assert (since_prev == -1.0).any() and (since_prev == 0.0).any()
    assert (vectors[:, FEATURE_NAMES.index("payment_type_code")] == UNKNOWN_CODE).any()
    assert (vectors[:, FEATURE_NAMES.index("sender_country_code")] == UNKNOWN_CODE).any()


def test_metadata_example_matches_feature_set():
    meta = json.loads((FIXTURE_DIR / "metadata.example.json").read_text(encoding="utf-8"))
    assert meta["feature_set_version"] == FEATURE_SET_VERSION
    assert tuple(meta["feature_names"]) == FEATURE_NAMES
    assert tuple(meta["categorical_features"]) == CATEGORICAL_FEATURES
    assert 0 < meta["threshold"] < 1
