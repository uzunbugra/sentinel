# =============================================================================
# SentinelFlow - Risk Scoring Schemas
# =============================================================================
"""Response models for ``POST /api/v1/risk/score`` (contract §4.2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from sentinelflow.api.schemas import TopFeature


class RiskScoreResponse(BaseModel):
    """Fraud model score for one transaction, with its log-odds explanation."""

    model_config = ConfigDict(protected_namespaces=())

    transaction_id: str
    model_version: str
    feature_set_version: str
    score: float = Field(..., ge=0, le=1, description="Model probability")
    threshold: float = Field(..., description="Decision threshold of the model")
    is_fraud: bool = Field(..., description="score >= threshold")
    contribution_unit: str = Field(
        "log_odds", description="Unit of `contribution` and `base_value`"
    )
    base_value: float = Field(..., description="Model bias term in log-odds")
    top_features: list[TopFeature] = Field(
        ..., description="Top 5 features by |contribution| for this transaction"
    )
    history_cold_start: bool = Field(
        ..., description="Neither account has any recorded transaction in either direction"
    )
    latency_ms: float


class RiskStatsResponse(BaseModel):
    """Scoring counters since startup (outside the contract)."""

    total_predictions: int
    avg_latency_ms: float
    target_latency_ms: float
    performance_status: str
