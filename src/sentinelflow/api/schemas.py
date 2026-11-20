# =============================================================================
# SentinelFlow API - Pydantic Schemas
# =============================================================================
"""
Request/response schemas for the SentinelFlow REST API.

This module re-exports contract schemas and adds API-specific extensions.
All core schemas come from sentinelflow.contracts (single source of truth).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Re-export from contracts (single source of truth)
# =============================================================================
from sentinelflow.contracts import (
    # Version
    SCHEMA_VERSION,
    # Alert
    Alert,
    AlertCreate,
    # Case
    Case,
    CaseCreate,
    CaseEvent,
    CasePriority,
    CaseStatus,
    EventType,
    Evidence,
    # Enums
    FraudType,
    Severity,
    # Transaction
    TransactionCreate,
    TransactionSummary,
)
from sentinelflow.contracts.alert import AlertListResponse
from sentinelflow.contracts.case import CaseListResponse, CaseSummary, CaseUpdate

# Backwards compatibility aliases
FraudTypeEnum = FraudType
SeverityEnum = Severity
TransactionSubmit = TransactionCreate
AlertResponse = Alert


# =============================================================================
# API-specific Response Schemas
# =============================================================================


class TransactionResponse(BaseModel):
    """Response after submitting a transaction."""

    transaction_id: str
    status: str = Field(default="analyzed", description="Processing status")
    message: str = Field(default="Transaction analyzed successfully")
    is_fraud: bool = Field(default=False, description="Fraud detection result")
    fraud_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Fraud model score; null when no model is loaded",
    )
    model_version: str | None = Field(
        default=None, description="Model that produced `fraud_score`; null without a model"
    )
    alerts: list[Alert] | None = Field(default=None, description="Generated alerts, if any")
    processing_time_ms: float = Field(default=0.0)


class BatchTransactionResponse(BaseModel):
    """Response for batch transaction submission."""

    total_processed: int
    fraud_detected: int
    results: list[TransactionResponse]
    processing_time_ms: float


# =============================================================================
# ML Pipeline Schemas
# =============================================================================


class ModelMetrics(BaseModel):
    """Evaluation metrics recorded in the artifact; a missing value is null, not 0."""

    split: str | None = None
    pr_auc: float | None = None
    roc_auc: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    support_positive: int | None = None
    support_total: int | None = None
    baseline_pr_auc: float | None = None


class ActiveModel(BaseModel):
    """The fraud model the API is serving (contract §4.1)."""

    model_config = ConfigDict(protected_namespaces=())

    model_version: str
    model_family: str
    feature_set_version: str
    feature_names: list[str]
    threshold: float
    dataset_id: str
    trained_at: str
    loaded_at: datetime
    metrics: ModelMetrics
    model_sha256: str


class ModelStatusResponse(BaseModel):
    """`GET /ml/models`: always 200; `model` is null unless `status` is `loaded`."""

    status: Literal["loaded", "not_loaded", "invalid"]
    model: ActiveModel | None = None
    error: str | None = None


class TopFeature(BaseModel):
    """One feature's contribution to a single score, in log-odds."""

    feature: str
    value: float
    contribution: float


class FeatureDefinition(BaseModel):
    """One feature of the served feature set."""

    name: str
    dtype: str
    categorical: bool


class FeatureSetResponse(BaseModel):
    """`GET /ml/features`: the feature set the service computes."""

    feature_set_version: str
    total_features: int
    features: list[FeatureDefinition]


# =============================================================================
# System Schemas
# =============================================================================


class ComponentStatus(BaseModel):
    """Status of a system component."""

    name: str
    status: str = "unknown"  # healthy, degraded, down, unknown
    latency_ms: float | None = None
    message: str | None = None


class HealthResponse(BaseModel):
    """System health check response."""

    status: str = Field(default="healthy", description="Overall system status")
    version: str = Field(default="2.0.0")
    schema_version: str = Field(default=SCHEMA_VERSION)
    uptime_seconds: float = Field(default=0.0)
    components: dict[str, ComponentStatus] = Field(default_factory=dict)


class StatsResponse(BaseModel):
    """System statistics response."""

    transactions_processed: int = 0
    fraud_detected: int = 0
    alerts_created: int = 0
    cases_open: int = 0
    cases_resolved: int = 0

    # By fraud type
    by_fraud_type: dict[str, int] = Field(default_factory=dict)

    # By severity
    by_severity: dict[str, int] = Field(default_factory=dict)

    # Performance
    avg_detection_latency_ms: float = 0.0
    p95_detection_latency_ms: float = 0.0

    # Time range
    period_start: datetime | None = None
    period_end: datetime | None = None
    uptime_seconds: float = 0.0

    # Rates
    fraud_rate: float = Field(default=0.0, description="Fraud detection rate (percentage)")
    alerts_per_minute: float = 0.0


# =============================================================================
# KYC / Screening Schemas
# =============================================================================


class KYCScreenRequest(BaseModel):
    """Request to screen a customer against PEP & sanctions lists."""

    name: str = Field(..., min_length=2, max_length=200, description="Customer full name")
    country: str | None = Field(default=None, description="Country (ISO or name)")
    additional_info: dict[str, Any] | None = Field(
        default=None, description="Optional context (dob, id number, etc.)"
    )


class KYCScreenResponse(BaseModel):
    """Screening result combining PEP + sanctions checks."""

    screening_id: str
    query_name: str
    screening_types: list[str]
    has_matches: bool
    matches_count: int
    matches: list[dict[str, Any]] = Field(default_factory=list)
    risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendation: str = ""
    screened_at: str = ""


# =============================================================================
# WebSocket Message Schemas
# =============================================================================


class WSMessage(BaseModel):
    """WebSocket message format."""

    type: str = Field(..., description="Message type: alert, stats, heartbeat, error")
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class WSAlertMessage(BaseModel):
    """WebSocket alert notification."""

    type: str = "alert"
    alert: Alert


class WSStatsMessage(BaseModel):
    """WebSocket stats update."""

    type: str = "stats"
    stats: StatsResponse


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Version
    "SCHEMA_VERSION",
    # Enums
    "FraudType",
    "FraudTypeEnum",  # backwards compat
    "Severity",
    "SeverityEnum",  # backwards compat
    "CaseStatus",
    "CasePriority",
    "EventType",
    # Transaction
    "TransactionCreate",
    "TransactionSubmit",  # backwards compat
    "TransactionSummary",
    "TransactionResponse",
    "BatchTransactionResponse",
    # Alert
    "Alert",
    "AlertCreate",
    "AlertResponse",  # backwards compat
    "AlertListResponse",
    "Evidence",
    # Case
    "Case",
    "CaseCreate",
    "CaseUpdate",
    "CaseEvent",
    "CaseListResponse",
    "CaseSummary",
    # ML
    "ActiveModel",
    "FeatureDefinition",
    "FeatureSetResponse",
    "ModelMetrics",
    "ModelStatusResponse",
    "TopFeature",
    # System
    "ComponentStatus",
    "HealthResponse",
    "StatsResponse",
    # KYC
    "KYCScreenRequest",
    "KYCScreenResponse",
    # WebSocket
    "WSMessage",
    "WSAlertMessage",
    "WSStatsMessage",
]
