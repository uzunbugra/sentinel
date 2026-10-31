# =============================================================================
# SentinelFlow API - Transaction Ingestion
# =============================================================================
"""``POST /api/v1/transactions``: JWT or legacy X-API-Key, fraud model scoring."""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from sentinelflow.api.schemas import (
    Evidence,
    FraudType,
    Severity,
    TransactionCreate,
    TransactionResponse,
)
from sentinelflow.api.state import state
from sentinelflow.auth.dependencies import get_current_user
from sentinelflow.contracts import User
from sentinelflow.contracts.enums import DetectorType
from sentinelflow.ml.features import FeatureInputError
from sentinelflow.ml.serving import ScoredTransaction

router = APIRouter()

# Contract §4.4: model alerts at or above this score are critical, others high.
CRITICAL_SCORE = 0.85

# Optional legacy API key for service-to-service transaction ingestion.
# Set SENTINELFLOW_API_KEY in the environment to enable this fallback.
_INGEST_API_KEY = os.getenv("SENTINELFLOW_API_KEY", "")


async def require_ingest_auth(
    request: Request,
    user: User | None = Depends(get_current_user),
) -> None:
    """
    Guard the transaction ingestion endpoint.

    Accepts either:
    - A valid JWT bearer token for an active user, or
    - A legacy ``X-API-Key`` header matching SENTINELFLOW_API_KEY (when set).
    """
    if user is not None:
        return

    api_key = request.headers.get("x-api-key")
    if _INGEST_API_KEY and api_key and api_key == _INGEST_API_KEY:
        return

    raise HTTPException(
        status_code=401,
        detail="Authentication required (JWT bearer token or valid X-API-Key)",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post(
    "/api/v1/transactions",
    response_model=TransactionResponse,
    tags=["Transactions"],
    summary="Submit a transaction for fraud analysis",
)
async def submit_transaction(
    tx: TransactionCreate,
    _auth: None = Depends(require_ingest_auth),
) -> TransactionResponse:
    """Analyze a transaction for fraud."""
    start_time = time.perf_counter()
    tx_data = tx.with_defaults().model_dump()
    tx_id = tx_data["transaction_id"]

    try:
        # Ingestion is the only path that records the account history.
        scored = state.scorer.score(tx_data, record=True)
    except FeatureInputError as exc:
        state.errors += 1
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        state.transactions_processed += 1
        alerts_list: list[Any] = []
        result = scored.result if scored else None
        is_fraud = bool(result and result.is_fraud)

        if scored is not None and is_fraud:
            state.fraud_detected += 1
            alert = _persist_model_alert(scored, tx_data)
            if alert is not None:
                alerts_list.append(alert)
                await state.broadcast_alert(alert.model_dump(mode="json"))

        elapsed = (time.perf_counter() - start_time) * 1000

        return TransactionResponse(
            transaction_id=tx_id,
            status="analyzed",
            message="Fraud detected!" if is_fraud else "Transaction is clean",
            is_fraud=is_fraud,
            fraud_score=round(result.score, 4) if result else None,
            model_version=result.model_version if result else None,
            alerts=alerts_list if alerts_list else None,
            processing_time_ms=round(elapsed, 2),
        )

    except Exception as e:
        state.errors += 1
        logger.error(f"Transaction analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def model_evidence(scored: ScoredTransaction) -> Evidence:
    """ML alert evidence (contract §4.5), frozen with the model of this moment."""
    result = scored.result
    return Evidence(
        detector_type=DetectorType.ML_MODEL,
        detector_version=result.model_version,
        confidence=result.score,
        contribution=1.0,
        summary=f"Model skoru {result.score:.2f} ≥ eşik {result.threshold:.2f}",
        details={
            "model_version": result.model_version,
            "feature_set_version": result.feature_set_version,
            "score": result.score,
            "threshold": result.threshold,
            "contribution_unit": result.contribution_unit,
            "base_value": result.base_value,
            "top_features": [
                {"feature": f.feature, "value": f.value, "contribution": f.contribution}
                for f in result.top_features
            ],
            "history_cold_start": scored.history_cold_start,
        },
        related_transactions=[scored.transaction_id],
    )


def _persist_model_alert(scored: ScoredTransaction, tx_data: dict[str, Any]) -> Any:
    """Create and store the ``ml_model`` alert; returns None if it cannot be saved."""
    from sentinelflow.api.deps import get_db_session
    from sentinelflow.processor.alert_writer import create_alert_from_detection
    from sentinelflow.repository import AlertRepository

    score = scored.result.score
    alert_create = create_alert_from_detection(
        fraud_type=FraudType.ML_MODEL,
        severity=Severity.CRITICAL if score >= CRITICAL_SCORE else Severity.HIGH,
        confidence=score,
        tx_data=tx_data,
        description=f"Fraud model flagged the transaction (score: {score:.2f})",
        evidence=[model_evidence(scored)],
        related_transactions=[scored.transaction_id],
    )
    try:
        session = next(get_db_session())
        try:
            alert = AlertRepository(session).create(alert_create)
            session.commit()
            return alert
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Failed to persist alert: {e}")
        return None
