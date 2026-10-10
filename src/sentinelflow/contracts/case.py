# =============================================================================
# SentinelFlow - Case Contracts
# =============================================================================
"""
Case management schema definitions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field, model_validator

from sentinelflow.contracts.base import (
    ContractBase,
    generate_id,
    utc_now,
)
from sentinelflow.contracts.enums import (
    CasePriority,
    CaseStatus,
    EventType,
    FraudType,
    Severity,
)


def _as_utc(value: datetime | None) -> datetime | None:
    """Return ``value`` as an aware UTC datetime (naive values are treated as UTC)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class CaseCreate(ContractBase):
    """
    Schema for creating a new case.
    Cases are created from correlated alerts.
    """

    title: str = Field(..., min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)

    # Initial alerts
    alert_ids: list[str] = Field(default_factory=list, min_length=1)

    # Priority (can be auto-calculated from alerts)
    priority: CasePriority = Field(default=CasePriority.P3_MEDIUM)

    # Primary fraud type (from highest severity alert)
    primary_fraud_type: FraudType | None = None

    # Tags for categorization
    tags: list[str] = Field(default_factory=list)

    # Assignment
    assigned_to: str | None = Field(default=None, description="Username of assigned analyst")
    assigned_team: str | None = Field(default=None, description="Team name")


class Case(ContractBase):
    """
    Full case record with database fields.
    """

    # Identity
    case_id: str = Field(default_factory=lambda: generate_id("CASE"))

    # Core fields
    title: str
    description: str = ""
    status: CaseStatus = Field(default=CaseStatus.NEW)
    priority: CasePriority = Field(default=CasePriority.P3_MEDIUM)

    # Fraud classification
    primary_fraud_type: FraudType | None = None
    fraud_types: list[FraudType] = Field(
        default_factory=list,
        description="All fraud types from linked alerts",
    )

    # Linked alerts
    alert_ids: list[str] = Field(default_factory=list)
    alert_count: int = 0

    # Aggregated metrics from alerts
    total_amount: float = Field(default=0.0, description="Sum of transaction amounts")
    max_severity: Severity = Field(default=Severity.MEDIUM)
    avg_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Related entities (deduplicated from alerts)
    involved_accounts: list[str] = Field(default_factory=list)
    involved_transactions: list[str] = Field(default_factory=list)

    # Assignment
    assigned_to: str | None = None
    assigned_team: str | None = None

    # Tags
    tags: list[str] = Field(default_factory=list)

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    first_alert_at: datetime | None = None
    last_alert_at: datetime | None = None

    # SLA tracking
    sla_due_at: datetime | None = None
    sla_breached: bool = False

    # Resolution
    resolution: str | None = Field(default=None, description="Resolution summary")
    resolved_at: datetime | None = None
    resolved_by: str | None = None

    # Compliance
    str_required: bool = Field(default=False, description="STR filing required")
    str_filed: bool = False
    str_filed_at: datetime | None = None
    str_reference: str | None = None

    # Notes (latest; full history in case_events)
    notes_count: int = 0
    last_note: str | None = None

    @classmethod
    def from_create(cls, create: CaseCreate, **kwargs: Any) -> Case:
        """Create Case from CaseCreate with additional fields."""
        data = create.model_dump()
        data["alert_count"] = len(data.get("alert_ids", []))
        data.update(kwargs)
        return cls(**data)

    @model_validator(mode="after")
    def _normalise_times_and_sla(self) -> Case:
        """Serve all timestamps as UTC and derive ``sla_breached`` at read time."""
        for name in (
            "created_at",
            "updated_at",
            "first_alert_at",
            "last_alert_at",
            "sla_due_at",
            "resolved_at",
            "str_filed_at",
        ):
            setattr(self, name, _as_utc(getattr(self, name)))
        if self.is_open and self.sla_due_at and self.sla_due_at < datetime.now(timezone.utc):
            self.sla_breached = True
        return self

    @property
    def is_open(self) -> bool:
        """Whether case is still open."""
        return CaseStatus(self.status).is_open


class CaseEvent(ContractBase):
    """
    Audit log entry for case events.
    Provides full history/audit trail.
    """

    # Identity
    event_id: str = Field(default_factory=lambda: generate_id("EVT"))
    case_id: str

    # Event type
    event_type: EventType

    # Who/what triggered
    actor: str = Field(
        default="system",
        description="Username or 'system' for automated events",
    )
    actor_type: str = Field(
        default="system",
        description="user, system, api",
    )

    # What changed (notes are stored in full, up to CaseUpdate.note's limit)
    description: str = Field(default="", max_length=5000)

    # State change (for status/priority changes)
    previous_value: str | None = None
    new_value: str | None = None

    # Additional data
    extra_data: dict[str, Any] = Field(default_factory=dict)

    # Related entities
    alert_id: str | None = None
    transaction_id: str | None = None

    # Timestamp
    created_at: datetime = Field(default_factory=utc_now)

    # IP/request tracking for audit
    ip_address: str | None = None
    user_agent: str | None = None


class CaseUpdate(ContractBase):
    """
    Schema for updating a case.
    """

    status: CaseStatus | None = None
    priority: CasePriority | None = None
    assigned_to: str | None = None
    assigned_team: str | None = None
    tags: list[str] | None = None
    resolution: str | None = None

    # For adding notes
    note: str | None = Field(default=None, max_length=5000)


class CaseListResponse(ContractBase):
    """Paginated list of cases."""

    total: int
    page: int = 1
    page_size: int = 20
    cases: list[Case] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)


class CaseSummary(ContractBase):
    """
    Lightweight case summary for lists and dashboards.
    """

    case_id: str
    title: str
    status: CaseStatus
    priority: CasePriority
    primary_fraud_type: FraudType | None
    alert_count: int
    total_amount: float
    max_severity: Severity
    assigned_to: str | None
    created_at: datetime
    updated_at: datetime
    sla_breached: bool = False


# =============================================================================
# API models for the case workflow (docs/contracts/sprint3-case-api.md)
# =============================================================================


class CaseAlertLink(ContractBase):
    """Request body for linking an existing alert to a case."""

    alert_id: str = Field(..., min_length=1, max_length=50)


class CaseEventOut(ContractBase):
    """Audit timeline entry as served by the API (no IP / user-agent)."""

    event_id: str
    case_id: str
    event_type: EventType
    actor: str
    actor_type: str
    description: str = ""
    previous_value: str | None = None
    new_value: str | None = None
    alert_id: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def _utc_created_at(self) -> CaseEventOut:
        self.created_at = _as_utc(self.created_at)
        return self


class CaseEventListResponse(ContractBase):
    """Paginated audit timeline, newest first."""

    total: int
    page: int
    page_size: int
    events: list[CaseEventOut] = Field(default_factory=list)


class ApiErrorDetail(ContractBase):
    """Machine-readable error for 409 and business-rule 422 responses."""

    code: str = Field(..., description="Stable error code, e.g. alert_already_linked")
    message: str
    alert_id: str | None = None
    case_id: str | None = None
    field: str | None = None
    from_status: str | None = None
    to_status: str | None = None


class ApiErrorResponse(ContractBase):
    """Error envelope used by the case workflow endpoints."""

    detail: ApiErrorDetail
