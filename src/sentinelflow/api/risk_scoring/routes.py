# =============================================================================
# SentinelFlow - Risk Scoring Routes
# =============================================================================
"""FastAPI router for real-time risk scoring with the served fraud model."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from sentinelflow.api.schemas import TopFeature, TransactionCreate
from sentinelflow.api.state import state
from sentinelflow.auth.dependencies import require_analyst, require_viewer
from sentinelflow.contracts import User
from sentinelflow.ml.features import FeatureInputError

from .schemas import HistoryStats, RiskScoreResponse, RiskStatsResponse

router = APIRouter(prefix="/api/v1/risk", tags=["Risk Scoring"])

# End-to-end budget from ADR 0003 §8.
TARGET_LATENCY_MS = 30.0


class _Counters:
    total_predictions = 0
    total_latency_ms = 0.0

    @classmethod
    def add(cls, latency_ms: float) -> None:
        cls.total_predictions += 1
        cls.total_latency_ms += latency_ms

    @classmethod
    def avg_latency_ms(cls) -> float:
        return cls.total_latency_ms / cls.total_predictions if cls.total_predictions else 0.0


def model_not_loaded() -> HTTPException:
    service = state.scorer.service
    return HTTPException(
        status_code=503,
        detail={
            "code": "model_not_loaded",
            "message": "No valid fraud model is loaded",
            "status": service.status.value,
        },
    )


@router.post(
    "/score",
    response_model=RiskScoreResponse,
    summary="Score one transaction",
    description=(
        "Scores the transaction against the current account history without recording it. "
        "503 `model_not_loaded` when no valid model is loaded."
    ),
    responses={503: {"description": "No valid fraud model is loaded"}},
)
async def score_transaction(
    tx: TransactionCreate, _user: User = Depends(require_analyst)
) -> RiskScoreResponse:
    tx_data = tx.with_defaults().model_dump()
    try:
        scored = state.scorer.score(tx_data, record=False)
    except FeatureInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if scored is None:
        raise model_not_loaded()

    result = scored.result
    _Counters.add(scored.latency_ms)
    return RiskScoreResponse(
        transaction_id=scored.transaction_id,
        model_version=result.model_version,
        feature_set_version=result.feature_set_version,
        score=result.score,
        threshold=result.threshold,
        is_fraud=result.is_fraud,
        contribution_unit=result.contribution_unit,
        base_value=result.base_value,
        top_features=[
            TopFeature(feature=f.feature, value=f.value, contribution=f.contribution)
            for f in result.top_features
        ],
        history_cold_start=scored.history_cold_start,
        latency_ms=round(scored.latency_ms, 3),
    )


@router.get(
    "/stats",
    response_model=RiskStatsResponse,
    summary="Risk scoring statistics",
    description=(
        "Scoring latency and the account history counters. The history lives in the "
        "process: after a restart `history.recorded` is 0 and history features start cold."
    ),
)
async def get_stats(_user: User = Depends(require_viewer)) -> RiskStatsResponse:
    avg = _Counters.avg_latency_ms()
    history = state.scorer.history
    return RiskStatsResponse(
        total_predictions=_Counters.total_predictions,
        avg_latency_ms=round(avg, 3),
        target_latency_ms=TARGET_LATENCY_MS,
        performance_status="optimal" if avg < TARGET_LATENCY_MS else "degraded",
        history=HistoryStats(
            recorded=history.recorded,
            duplicates=history.duplicates,
            out_of_order=history.out_of_order,
        ),
    )
