# =============================================================================
# SentinelFlow API - Transaction Ingestion
# =============================================================================
"""``POST /api/v1/transactions``: JWT or legacy X-API-Key, ML ensemble scoring."""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from sentinelflow.api.schemas import (
    FraudType,
    Severity,
    TransactionCreate,
    TransactionResponse,
)
from sentinelflow.api.state import state
from sentinelflow.auth.dependencies import get_current_user
from sentinelflow.contracts import User

router = APIRouter()

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
    from sentinelflow.api.deps import get_db_session
    from sentinelflow.processor.alert_writer import create_alert_from_detection
    from sentinelflow.repository import AlertRepository

    start_time = time.perf_counter()

    try:
        tx_with_defaults = tx.with_defaults()
        tx_id = tx_with_defaults.transaction_id
        state.transactions_processed += 1

        is_fraud = False
        fraud_score = 0.0
        alerts_list: list[Any] = []

        # Run ML detection if available
        if state._ml_loaded and state._ensemble:
            import numpy as np

            from sentinelflow.ml.feature_engine import FEATURE_NAMES

            tx_data = tx_with_defaults.model_dump()
            features_dict = state._feature_engine.extract(tx_data)
            features_vector = np.array([features_dict[name] for name in FEATURE_NAMES])

            prediction = state._ensemble.predict(features_vector)
            fraud_score = prediction.final_score
            is_fraud = prediction.is_fraud

            if is_fraud:
                state.fraud_detected += 1

                # Create alert and persist
                alert_create = create_alert_from_detection(
                    fraud_type=FraudType.ML_ENSEMBLE,
                    severity=Severity.CRITICAL if fraud_score > 0.85 else Severity.HIGH,
                    confidence=fraud_score,
                    tx_data=tx_data,
                    description=f"ML Ensemble detected fraud (score: {fraud_score:.2f})",
                )

                # Persist to database
                try:
                    session = next(get_db_session())
                    repo = AlertRepository(session)
                    alert = repo.create(alert_create)
                    session.commit()
                    alerts_list.append(alert)

                    # Broadcast to WebSocket
                    await state.broadcast_alert(alert.model_dump(mode="json"))
                except Exception as e:
                    logger.error(f"Failed to persist alert: {e}")

        elapsed = (time.perf_counter() - start_time) * 1000

        return TransactionResponse(
            transaction_id=tx_id,
            status="analyzed",
            message="Fraud detected!" if is_fraud else "Transaction is clean",
            is_fraud=is_fraud,
            fraud_score=round(fraud_score, 4),
            alerts=alerts_list if alerts_list else None,
            processing_time_ms=round(elapsed, 2),
        )

    except Exception as e:
        state.errors += 1
        logger.error(f"Transaction analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
