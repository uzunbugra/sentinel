# =============================================================================
# SentinelFlow - Transaction scorer (ML-06)
# =============================================================================
"""
Joins the fs-1 account history with the loaded fraud model for the API.

``score(tx, record=False)`` is the ``risk/score`` path: it reads the history and
never changes it. ``score(tx, record=True)`` is the ingestion path: features are
computed against the history *before* the transaction, then it is recorded
(ADR 0003 §4). The history is recorded even when no model is loaded, so that a
model loaded later sees the same history it would have seen from the start.

A duplicate ``transaction_id`` on the ingestion path gets the vector of the
original (contract §2); those vectors are kept in a bounded cache.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np

from sentinelflow.ml.features import AccountHistory

from .service import FraudModelService, ModelNotLoadedError, ScoreResult

DEFAULT_DUPLICATE_CACHE_SIZE = 10_000


def canonical_transaction(tx: Mapping[str, Any]) -> dict[str, Any]:
    """Map a ``TransactionCreate`` dump to the canonical record (contract §1).

    Missing optional fields stay ``None``; the feature module applies defaults.
    """
    timestamp = tx.get("timestamp")
    if isinstance(timestamp, datetime) and timestamp.tzinfo is None:
        # The API treats naive timestamps as UTC (contract §4: dates are UTC).
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return {
        "transaction_id": tx.get("transaction_id"),
        "timestamp": timestamp,
        "sender_account": tx.get("sender_iban"),
        "receiver_account": tx.get("receiver_iban"),
        "amount": tx.get("amount"),
        "payment_currency": tx.get("currency"),
        "received_currency": tx.get("received_currency"),
        "sender_country": tx.get("sender_country"),
        "receiver_country": tx.get("receiver_country"),
        "payment_type": tx.get("payment_type"),
    }


@dataclass(frozen=True)
class ScoredTransaction:
    """Model output for one transaction plus history context."""

    transaction_id: str
    result: ScoreResult
    history_cold_start: bool
    latency_ms: float


class TransactionScorer:
    """Thread-safe history + model pair shared by the API routes."""

    def __init__(
        self,
        service: FraudModelService,
        history: AccountHistory | None = None,
        *,
        duplicate_cache_size: int = DEFAULT_DUPLICATE_CACHE_SIZE,
    ) -> None:
        self.service = service
        self.history = history if history is not None else AccountHistory()
        self._lock = threading.Lock()
        self._vectors: OrderedDict[str, tuple[np.ndarray, bool]] = OrderedDict()
        self._cache_size = duplicate_cache_size

    def score(self, tx: Mapping[str, Any], *, record: bool) -> ScoredTransaction | None:
        """Score ``tx`` (a ``TransactionCreate`` dump with defaults applied).

        Returns ``None`` when no model is loaded; with ``record=True`` the
        transaction is still added to the history.

        Raises:
            FeatureInputError: the transaction violates contract §1.
        """
        start = time.perf_counter()
        canonical = canonical_transaction(tx)
        tid = str(canonical["transaction_id"])

        with self._lock:
            cached = self._vectors.get(tid) if record else None
            if cached is not None:
                vector, cold_start = cached
            else:
                vector = self.history.features_for(canonical)
                cold_start = self.history.is_cold_start(canonical)
            if record and self.history.record(canonical):
                self._remember(tid, vector, cold_start)

        try:
            result = self.service.score(vector)
        except ModelNotLoadedError:
            return None
        latency_ms = (time.perf_counter() - start) * 1000
        return ScoredTransaction(
            transaction_id=tid,
            result=result,
            history_cold_start=cold_start,
            latency_ms=latency_ms,
        )

    def _remember(self, tid: str, vector: np.ndarray, cold_start: bool) -> None:
        self._vectors[tid] = (vector, cold_start)
        if len(self._vectors) > self._cache_size:
            self._vectors.popitem(last=False)
