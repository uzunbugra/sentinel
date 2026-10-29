# =============================================================================
# SentinelFlow - Case Repository
# =============================================================================
"""
Repository for case database operations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, desc, func, select, update
from sqlalchemy.orm import Session, selectinload

from sentinelflow.contracts import Case
from sentinelflow.database.models import AlertModel, CaseModel


def generate_case_id() -> str:
    """Generate unique case ID."""
    return f"CASE-{uuid4().hex[:12].upper()}"


class CaseRepository:
    """Read-side case queries and aggregate maintenance.

    Writes (create, link, status/assignment changes) go through
    ``sentinelflow.services.CaseService`` so the workflow rules and audit
    events cannot be bypassed.
    """

    def __init__(self, session: Session):
        self._session = session

    # =========================================================================
    # Read Operations
    # =========================================================================

    def get_by_id(self, case_id: str) -> Case | None:
        """Get case by ID (sync)."""
        stmt = (
            select(CaseModel)
            .options(selectinload(CaseModel.alerts))
            .where(CaseModel.case_id == case_id)
        )
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return Case.model_validate(model.to_dict()) if model else None

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        priority: str | None = None,
        assigned_to: str | None = None,
        is_open: bool | None = None,
    ) -> tuple[list[Case], int]:
        """List cases with pagination and filtering (sync)."""
        stmt = select(CaseModel).options(selectinload(CaseModel.alerts))
        count_stmt = select(func.count(CaseModel.case_id))

        conditions = []
        if status:
            conditions.append(CaseModel.status == status)
        if priority:
            conditions.append(CaseModel.priority == priority)
        if assigned_to:
            conditions.append(CaseModel.assigned_to == assigned_to)
        if is_open is not None:
            open_statuses = ["new", "triage", "investigating", "escalated", "pending_info"]
            if is_open:
                conditions.append(CaseModel.status.in_(open_statuses))
            else:
                conditions.append(~CaseModel.status.in_(open_statuses))

        if conditions:
            stmt = stmt.where(and_(*conditions))
            count_stmt = count_stmt.where(and_(*conditions))

        total = self._session.execute(count_stmt).scalar() or 0

        stmt = stmt.order_by(desc(CaseModel.created_at))
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = self._session.execute(stmt)
        models = result.scalars().all()

        cases = [Case.model_validate(m.to_dict()) for m in models]
        return cases, total

    # =========================================================================
    # Stats Operations
    # =========================================================================

    def get_stats(self) -> dict[str, Any]:
        """Get case statistics (sync)."""
        total = self._session.execute(select(func.count(CaseModel.case_id))).scalar() or 0

        # By status
        by_status = dict(
            self._session.execute(
                select(CaseModel.status, func.count(CaseModel.case_id)).group_by(CaseModel.status)
            ).all()
        )

        # By priority
        by_priority = dict(
            self._session.execute(
                select(CaseModel.priority, func.count(CaseModel.case_id)).group_by(
                    CaseModel.priority
                )
            ).all()
        )

        # Open vs closed
        open_statuses = ["new", "triage", "investigating", "escalated", "pending_info"]
        open_count = (
            self._session.execute(
                select(func.count(CaseModel.case_id)).where(CaseModel.status.in_(open_statuses))
            ).scalar()
            or 0
        )

        return {
            "total": total,
            "open": open_count,
            "closed": total - open_count,
            "by_status": by_status,
            "by_priority": by_priority,
        }

    # =========================================================================
    # Aggregates
    # =========================================================================

    def refresh_aggregates(self, case_id: str) -> None:
        """Recompute alert-derived case fields (count, amount, severity, ...)."""
        self._update_case_aggregates_sync(case_id)

    def _update_case_aggregates_sync(self, case_id: str) -> None:
        """Update case aggregated values from alerts (sync)."""
        # Get linked alerts
        alerts_stmt = select(AlertModel).where(AlertModel.case_id == case_id)
        result = self._session.execute(alerts_stmt)
        alerts = result.scalars().all()

        if not alerts:
            self._session.execute(
                update(CaseModel)
                .where(CaseModel.case_id == case_id)
                .values(
                    alert_count=0,
                    total_amount=0.0,
                    avg_confidence=0.0,
                    fraud_types=[],
                    involved_accounts=[],
                    involved_transactions=[],
                    first_alert_at=None,
                    last_alert_at=None,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            return

        # Calculate aggregates
        total_amount = sum(a.amount for a in alerts)
        fraud_types = list({a.fraud_type for a in alerts})
        involved_accounts = list(
            set([a.sender_iban for a in alerts] + [a.receiver_iban for a in alerts])
        )
        involved_txns = list({a.transaction_id for a in alerts})

        # Determine max severity
        severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        max_sev = max(alerts, key=lambda a: severity_order.get(a.severity, 0)).severity

        avg_conf = sum(a.confidence for a in alerts) / len(alerts)

        first_alert = min(alerts, key=lambda a: a.detected_at).detected_at
        last_alert = max(alerts, key=lambda a: a.detected_at).detected_at

        # Update case
        stmt = (
            update(CaseModel)
            .where(CaseModel.case_id == case_id)
            .values(
                alert_count=len(alerts),
                total_amount=total_amount,
                max_severity=max_sev,
                avg_confidence=avg_conf,
                fraud_types=fraud_types,
                involved_accounts=involved_accounts,
                involved_transactions=involved_txns,
                first_alert_at=first_alert,
                last_alert_at=last_alert,
                primary_fraud_type=fraud_types[0] if fraud_types else None,
                updated_at=datetime.now(timezone.utc),
            )
        )
        self._session.execute(stmt)
