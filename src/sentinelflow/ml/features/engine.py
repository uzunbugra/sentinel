# =============================================================================
# SentinelFlow - Feature Engine fs-1 (batch + streaming, one code path)
# =============================================================================
"""
Computes feature set ``fs-1`` for canonical transactions.

Two entry points share one implementation:

* :func:`build_features_batch` — training. Sorts a canonical DataFrame by
  ``(timestamp, transaction_id)`` and feeds every row through an
  :class:`AccountHistory`, exactly as the service would.
* :class:`AccountHistory` — service. ``features_for(tx)`` reads the state,
  ``record(tx)`` writes it (ingestion path only).

History rules (contract §2, ADR 0003 §4):

* Events are ordered by ``(timestamp, transaction_id)``. An event is *earlier*
  than the current one when its key sorts strictly before the current key, so
  events with the same timestamp see each other in ``transaction_id`` order and
  the current event never sees itself.
* A window of width ``W`` covers earlier events with ``timestamp >= t - W``:
  the lower edge is inclusive, the upper edge is "strictly earlier in order".
* A ``transaction_id`` that was already recorded is scored but not recorded
  again. Ids are kept only for the longest window (see :class:`AccountHistory`),
  so memory does not grow with the length of the stream.
* Only canonical fields are read. Labels never enter the state; account ids are
  only used as keys.
"""

from __future__ import annotations

import heapq
import math
from array import array
from bisect import bisect_left, insort
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from sentinelflow.ml.features import spec
from sentinelflow.ml.features.spec import (
    DEFAULT_COUNTRY,
    FEATURE_DTYPES,
    FEATURE_NAMES,
    MAX_WINDOW_NS,
    NO_PREVIOUS_SECONDS,
    NS_PER_SECOND,
    NUM_FEATURES,
    UNKNOWN,
    WINDOW_7D_NS,
    WINDOW_24H_NS,
    FeatureInputError,
)

_NS_PER_HOUR = 3600 * NS_PER_SECOND
_NS_PER_DAY = 24 * _NS_PER_HOUR
# 1970-01-01 was a Thursday; Monday is 0.
_EPOCH_WEEKDAY = 3

_Key = tuple[int, str]
_Canonical = tuple[str, int, str, str, float, str, str, str, str, str]

_FLOAT32_POSITIONS = tuple(
    i for i, name in enumerate(FEATURE_NAMES) if FEATURE_DTYPES[name] == np.float32
)
# ``array`` type codes matching the contract dtypes (int8, int32, float32).
_ARRAY_TYPECODES: dict[np.dtype, str] = {
    np.dtype(np.int8): "b",
    np.dtype(np.int32): "i",
    np.dtype(np.float32): "f",
}
assert all(array(code).itemsize == dtype.itemsize for dtype, code in _ARRAY_TYPECODES.items())


def timestamp_to_ns(value: Any) -> int:
    """Convert a tz-aware timestamp (datetime, ``pd.Timestamp`` or ISO string) to UTC ns."""
    if spec.is_missing(value):
        raise FeatureInputError("missing required field 'timestamp'")
    try:
        ts = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise FeatureInputError(f"timestamp is not parseable: {value!r}") from exc
    if ts.tzinfo is None:
        raise FeatureInputError(f"timestamp must be timezone-aware (UTC), got {value!r}")
    return int(ts.tz_convert("UTC").as_unit("ns").value)


def _timestamps_to_ns(column: pd.Series) -> np.ndarray:
    if not isinstance(column.dtype, pd.DatetimeTZDtype):
        raise FeatureInputError(
            f"column 'timestamp' must be timezone-aware datetime64, got {column.dtype}"
        )
    if column.isna().any():
        raise FeatureInputError("missing required field 'timestamp'")
    return column.dt.tz_convert("UTC").dt.as_unit("ns").to_numpy(dtype="int64")


def _canonical(
    transaction_id: Any,
    ts_ns: int,
    sender: Any,
    receiver: Any,
    amount: Any,
    payment_currency: Any,
    received_currency: Any,
    sender_country: Any,
    receiver_country: Any,
    payment_type: Any,
) -> _Canonical:
    """Apply contract §1 validation, defaults and normalisation to raw values."""
    tid = spec.required_value(transaction_id, spec.TRANSACTION_ID)
    pay_cur = spec.normalize_code(spec.required_value(payment_currency, spec.PAYMENT_CURRENCY))
    rec_cur = spec.optional_value(received_currency)
    s_cty = spec.optional_value(sender_country)
    r_cty = spec.optional_value(receiver_country)
    ptype = spec.optional_value(payment_type)
    return (
        tid,
        ts_ns,
        spec.required_value(sender, spec.SENDER_ACCOUNT),
        spec.required_value(receiver, spec.RECEIVER_ACCOUNT),
        spec.validate_amount(amount),
        pay_cur,
        pay_cur if rec_cur is None else spec.normalize_code(rec_cur),
        DEFAULT_COUNTRY if s_cty is None else spec.normalize_code(s_cty),
        DEFAULT_COUNTRY if r_cty is None else spec.normalize_code(r_cty),
        UNKNOWN if ptype is None else spec.normalize_payment_type(ptype),
    )


def canonicalize(tx: Mapping[str, Any]) -> _Canonical:
    """Validate and normalise one canonical transaction mapping."""
    return _canonical(
        tx.get(spec.TRANSACTION_ID),
        timestamp_to_ns(tx.get(spec.TIMESTAMP)),
        tx.get(spec.SENDER_ACCOUNT),
        tx.get(spec.RECEIVER_ACCOUNT),
        tx.get(spec.AMOUNT),
        tx.get(spec.PAYMENT_CURRENCY),
        tx.get(spec.RECEIVED_CURRENCY),
        tx.get(spec.SENDER_COUNTRY),
        tx.get(spec.RECEIVER_COUNTRY),
        tx.get(spec.PAYMENT_TYPE),
    )


class _Side:
    """One account's events in one direction, kept for the longest window."""

    __slots__ = ("keys", "counterparties", "amounts", "last_key")

    def __init__(self) -> None:
        self.keys: list[_Key] = []
        self.counterparties: list[str] = []
        self.amounts: list[float] = []
        # Latest recorded key; survives window pruning (``seconds_since_prev``).
        self.last_key: _Key | None = None

    def add(self, key: _Key, counterparty: str, amount: float) -> bool:
        """Insert an event; return False when it is older than the latest one."""
        in_order = self.last_key is None or key >= self.last_key
        if in_order:
            self.keys.append(key)
            self.counterparties.append(counterparty)
            self.amounts.append(amount)
            self.last_key = key
        else:
            pos = bisect_left(self.keys, key)
            self.keys.insert(pos, key)
            self.counterparties.insert(pos, counterparty)
            self.amounts.insert(pos, amount)
        # Drop events that no window of a later event can reach.
        horizon = bisect_left(self.keys, (self.last_key[0] - MAX_WINDOW_NS,))
        if horizon:
            del self.keys[:horizon]
            del self.counterparties[:horizon]
            del self.amounts[:horizon]
        return in_order


class AccountHistory:
    """In-memory account history for fs-1 (ADR 0003 §4).

    ``features_for`` never mutates the state, so ``risk/score`` can call it
    freely; only the ingestion path calls ``record``.

    ``track_ids=False`` skips the duplicate-id set; only for callers that remove
    duplicates themselves (the batch builder does).

    The id set is bounded: an id is kept while its timestamp is within
    ``MAX_WINDOW_NS`` of the latest recorded timestamp. An older transaction is
    checked against the stored events of its sender and receiver instead. Its
    original is either still there, or it was pruned and can no longer reach any
    window, so recording it again leaves the features unchanged.
    """

    def __init__(self, *, track_ids: bool = True) -> None:
        self._out: dict[str, _Side] = {}
        self._in: dict[str, _Side] = {}
        self._seen: set[str] | None = set() if track_ids else None
        # Min-heap of (timestamp, id) for ``_seen``, oldest first.
        self._seen_by_time: list[_Key] = []
        self._latest_ns: int | None = None
        self.recorded = 0
        self.duplicates = 0
        self.out_of_order = 0

    # --- public API -----------------------------------------------------------
    def features_for(self, tx: Mapping[str, Any]) -> np.ndarray:
        """Feature vector of ``tx`` against the current state (float64, fs-1 order)."""
        return _as_vector(self._compute(canonicalize(tx)))

    def record(self, tx: Mapping[str, Any]) -> bool:
        """Add ``tx`` to the state. Returns False (and changes nothing) for a duplicate id."""
        return self._record_checked(canonicalize(tx))

    def is_cold_start(self, tx: Mapping[str, Any]) -> bool:
        """True when neither the sender nor the receiver account has any recorded event."""
        sender = spec.required_value(tx.get(spec.SENDER_ACCOUNT), spec.SENDER_ACCOUNT)
        receiver = spec.required_value(tx.get(spec.RECEIVER_ACCOUNT), spec.RECEIVER_ACCOUNT)
        return not any(acc in self._out or acc in self._in for acc in (sender, receiver))

    def __contains__(self, transaction_id: object) -> bool:
        return self._seen is not None and transaction_id in self._seen

    # --- shared core ----------------------------------------------------------
    def _compute(self, c: _Canonical) -> tuple:
        tid, t, sender, receiver, amount, pay_cur, rec_cur, s_cty, r_cty, ptype = c
        key = (t, tid)
        lo24 = (t - WINDOW_24H_NS,)
        lo7 = (t - WINDOW_7D_NS,)

        s_count24 = 0
        s_sum24 = 0.0
        s_unique7 = 0
        pair7 = 0
        since_prev = NO_PREVIOUS_SECONDS
        out = self._out.get(sender)
        if out is not None:
            keys = out.keys
            end = bisect_left(keys, key)
            start24 = bisect_left(keys, lo24, 0, end)
            start7 = bisect_left(keys, lo7, 0, start24)
            s_count24 = end - start24
            if s_count24:
                s_sum24 = math.fsum(out.amounts[start24:end])
            if end > start7:
                recent = out.counterparties[start7:end]
                s_unique7 = len(set(recent))
                pair7 = recent.count(receiver)
            last = out.last_key
            if last < key:
                since_prev = (t - last[0]) / NS_PER_SECOND
            elif end:
                since_prev = (t - keys[end - 1][0]) / NS_PER_SECOND

        r_count24 = 0
        r_unique7 = 0
        inc = self._in.get(receiver)
        if inc is not None:
            keys = inc.keys
            end = bisect_left(keys, key)
            start24 = bisect_left(keys, lo24, 0, end)
            start7 = bisect_left(keys, lo7, 0, start24)
            r_count24 = end - start24
            if end > start7:
                r_unique7 = len(set(inc.counterparties[start7:end]))

        return (
            math.log1p(amount),
            (t // _NS_PER_HOUR) % 24,
            (t // _NS_PER_DAY + _EPOCH_WEEKDAY) % 7,
            spec.payment_type_code(ptype),
            int(pay_cur != rec_cur),
            int(s_cty != r_cty),
            spec.country_code(s_cty),
            spec.country_code(r_cty),
            s_count24,
            s_sum24,
            s_unique7,
            r_count24,
            r_unique7,
            pair7,
            since_prev,
        )

    def _record_checked(self, c: _Canonical) -> bool:
        if self._seen is not None:
            tid, t = c[0], c[1]
            if tid in self._seen or (self._before_id_horizon(t) and self._has_event(c)):
                self.duplicates += 1
                return False
            self._remember_id(tid, t)
        self._record(c)
        return True

    def _before_id_horizon(self, t: int) -> bool:
        """True when an id with timestamp ``t`` may already have left ``_seen``."""
        return self._latest_ns is not None and t < self._latest_ns - MAX_WINDOW_NS

    def _has_event(self, c: _Canonical) -> bool:
        """True when the sender's or receiver's stored events contain this key."""
        key = (c[1], c[0])
        for side in (self._out.get(c[2]), self._in.get(c[3])):
            if side is not None:
                pos = bisect_left(side.keys, key)
                if pos < len(side.keys) and side.keys[pos] == key:
                    return True
        return False

    def _remember_id(self, tid: str, t: int) -> None:
        assert self._seen is not None
        if self._latest_ns is None or t > self._latest_ns:
            self._latest_ns = t
        horizon = self._latest_ns - MAX_WINDOW_NS
        if t >= horizon:
            self._seen.add(tid)
            heapq.heappush(self._seen_by_time, (t, tid))
        heap = self._seen_by_time
        while heap and heap[0][0] < horizon:
            self._seen.discard(heapq.heappop(heap)[1])

    def _record(self, c: _Canonical) -> None:
        tid, t, sender, receiver, amount = c[:5]
        key = (t, tid)
        out = self._out.get(sender)
        if out is None:
            out = self._out[sender] = _Side()
        inc = self._in.get(receiver)
        if inc is None:
            inc = self._in[receiver] = _Side()
        in_order = out.add(key, receiver, amount)
        in_order = inc.add(key, sender, amount) and in_order
        if not in_order:
            self.out_of_order += 1
        self.recorded += 1


def _as_vector(values: tuple) -> np.ndarray:
    vec = np.array(values, dtype=np.float64)
    for i in _FLOAT32_POSITIONS:
        vec[i] = np.float32(vec[i])
    return vec


def _optional_column(df: pd.DataFrame, name: str, n: int) -> list:
    return df[name].tolist() if name in df.columns else [None] * n


def build_features_batch(df: pd.DataFrame, history: AccountHistory | None = None) -> pd.DataFrame:
    """fs-1 feature matrix for a canonical transaction DataFrame.

    Rows are processed in ``(timestamp, transaction_id)`` order (input order breaks
    ties between identical keys) through the same code as :class:`AccountHistory`;
    the result keeps the input index and row order. With ``history`` the batch
    continues from that state and records into it; by default it starts empty.
    Only canonical columns are read — label columns are ignored.
    """
    missing = [c for c in spec.REQUIRED_FIELDS if c not in df.columns]
    if missing:
        raise FeatureInputError(f"missing required columns: {missing}")
    n = len(df)
    ts_ns = _timestamps_to_ns(df[spec.TIMESTAMP])
    tids = df[spec.TRANSACTION_ID].tolist()
    # Ids compare as strings, like the streaming path (``5`` and ``"5"`` are one id).
    tid_keys = [str(x) for x in tids]
    order = (
        pd.DataFrame({"t": ts_ns, "id": tid_keys, "pos": np.arange(n)})
        .sort_values(["t", "id", "pos"], kind="mergesort")["pos"]
        .to_numpy()
    )

    if history is None:
        history = AccountHistory(track_ids=False)
    ids_sorted = pd.Series([tid_keys[i] for i in order], dtype=object)
    duplicate = ids_sorted.duplicated(keep="first").to_numpy()
    tracks_ids = history._seen is not None

    columns = (
        df[spec.SENDER_ACCOUNT].tolist(),
        df[spec.RECEIVER_ACCOUNT].tolist(),
        df[spec.AMOUNT].tolist(),
        df[spec.PAYMENT_CURRENCY].tolist(),
        _optional_column(df, spec.RECEIVED_CURRENCY, n),
        _optional_column(df, spec.SENDER_COUNTRY, n),
        _optional_column(df, spec.RECEIVER_COUNTRY, n),
        _optional_column(df, spec.PAYMENT_TYPE, n),
    )
    sender, receiver, amount, pay_cur, rec_cur, s_cty, r_cty, ptype = columns
    ts_list = ts_ns.tolist()

    outputs = [
        array(_ARRAY_TYPECODES[FEATURE_DTYPES[name]], bytes(n * FEATURE_DTYPES[name].itemsize))
        for name in FEATURE_NAMES
    ]
    compute = history._compute
    record_checked = history._record_checked
    record = history._record
    feature_range = range(NUM_FEATURES)
    for rank, i in enumerate(order.tolist()):
        c = _canonical(
            tids[i],
            ts_list[i],
            sender[i],
            receiver[i],
            amount[i],
            pay_cur[i],
            rec_cur[i],
            s_cty[i],
            r_cty[i],
            ptype[i],
        )
        values = compute(c)
        for j in feature_range:
            outputs[j][i] = values[j]
        if tracks_ids:
            # Also catches ids recorded before this batch.
            record_checked(c)
        elif not duplicate[rank]:
            record(c)

    return pd.DataFrame(
        {
            name: np.frombuffer(outputs[j], dtype=FEATURE_DTYPES[name])
            for j, name in enumerate(FEATURE_NAMES)
        },
        index=df.index,
    )
