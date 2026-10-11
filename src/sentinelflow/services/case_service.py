# =============================================================================
# SentinelFlow - Case Workflow Service
# =============================================================================
"""
Atomic alert-to-case workflow (SF-304).

Every public write method is one unit of work: validation, case/alert updates
and audit events are flushed together and committed once; any error rolls the
whole request back. Contract: docs/contracts/sprint3-case-api.md.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sentinelflow.contracts.case import (
    Case,
    CaseCreate,
    CaseEventListResponse,
    CaseEventOut,
    CaseUpdate,
)
from sentinelflow.contracts.enums import CasePriority, CaseStatus, EventType
from sentinelflow.database.models import AlertModel, CaseModel
from sentinelflow.repository.case_repository import CaseRepository, generate_case_id
from sentinelflow.repository.event_repository import EventRepository
from sentinelflow.services.case_rules import (
    OPEN_STATUSES,
    RESOLVED_STATUSES,
    is_valid_transition,
    sla_due_at,
)

# =============================================================================
# Errors
# =============================================================================


class CaseServiceError(Exception):
    """Base error; ``status_code`` and ``detail()`` map 1:1 to the HTTP response."""

    status_code = 400

    def __init__(self, message: str, *, code: str | None = None, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.context = {k: v for k, v in context.items() if v is not None}

    def detail(self) -> str | dict[str, Any]:
        if self.code is None:
            return self.message
        return {"code": self.code, "message": self.message, **self.context}


class CaseNotFoundError(CaseServiceError):
    status_code = 404


class CaseConflictError(CaseServiceError):
    status_code = 409


class CaseRuleError(CaseServiceError):
    status_code = 422


# =============================================================================
# Helpers
# =============================================================================


class _EventClock:
    """Strictly increasing UTC timestamps so events of one request keep their order."""

    def __init__(self) -> None:
        self._last: datetime | None = None

    def now(self) -> datetime:
        current = datetime.now(timezone.utc)
        if self._last is not None and current <= self._last:
            current = self._last + timedelta(microseconds=1)
        self._last = current
        return current


def _is_open(status: str) -> bool:
    return CaseStatus(status) in OPEN_STATUSES


# =============================================================================
# Service
# =============================================================================


class CaseService:
    """Use cases for the analyst case workflow (sync SQLAlchemy session)."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._cases = CaseRepository(session)
        self._events = EventRepository(session)
        self._clock = _EventClock()
        self._detached_from: set[str] = set()

    # ------------------------------------------------------------------ writes

    def create_from_alerts(self, data: CaseCreate, actor: str) -> Case:
        """Create a case and link its alerts in one transaction."""
        alert_ids = list(dict.fromkeys(data.alert_ids))
        with self._unit_of_work():
            alerts = self._lock_alerts(alert_ids)
            for alert in alerts:
                self._ensure_linkable(alert, target_case_id=None)

            now = self._clock.now()
            priority = CasePriority(data.priority)
            case = CaseModel(
                case_id=generate_case_id(),
                title=data.title,
                description=data.description or "",
                status=CaseStatus.NEW.value,
                priority=priority.value,
                primary_fraud_type=data.primary_fraud_type,
                tags=list(data.tags or []),
                assigned_to=data.assigned_to,
                assigned_team=data.assigned_team,
                alert_count=0,
                created_at=now,
                updated_at=now,
                sla_due_at=sla_due_at(priority, now),
            )
            self._session.add(case)
            self._session.flush()
            self._log(case.case_id, EventType.CASE_CREATED, "Case created", actor)

            for alert in alerts:
                self._attach(case, alert, actor)
            self._session.flush()
            self._refresh_aggregates(case.case_id)
            case_id = case.case_id
        return self._read(case_id)

    def link_alert(self, case_id: str, alert_id: str, actor: str) -> Case:
        """Link an existing alert to an existing open case (idempotent)."""
        with self._unit_of_work():
            case = self._lock_case(case_id)
            (alert,) = self._lock_alerts([alert_id])
            if alert.case_id == case.case_id:
                return self._read(case_id)
            if not _is_open(case.status):
                raise CaseConflictError(
                    f"Case {case_id} is {case.status}; alerts can only be added to open cases",
                    code="case_not_open",
                    case_id=case_id,
                )
            self._ensure_linkable(alert, target_case_id=case_id)
            self._attach(case, alert, actor)
            case.updated_at = self._clock.now()
            self._session.flush()
            self._refresh_aggregates(case_id)
        return self._read(case_id)

    def update_case(self, case_id: str, update: CaseUpdate, actor: str) -> Case:
        """Apply status / priority / assignment / note changes with audit events."""
        if update.tags is not None:
            raise CaseRuleError(
                "Tags cannot be changed with this endpoint",
                code="unsupported_field",
                field="tags",
            )
        with self._unit_of_work():
            case = self._lock_case(case_id)
            changed = False
            if update.status is not None and CaseStatus(update.status).value != case.status:
                changed |= self._apply_status(case, CaseStatus(update.status), update, actor)
            elif update.resolution is not None:
                changed |= self._apply_resolution(case, update.resolution, actor)
            if update.priority is not None:
                changed |= self._apply_priority(case, CasePriority(update.priority), actor)
            if update.assigned_to is not None or update.assigned_team is not None:
                changed |= self._apply_assignment(
                    case, update.assigned_to, update.assigned_team, actor
                )
            note = (update.note or "").strip()
            if note:
                case.notes_count = (case.notes_count or 0) + 1
                case.last_note = note
                self._log(case_id, EventType.NOTE_ADDED, note, actor)
                changed = True
            if changed:
                case.updated_at = self._clock.now()
            self._session.flush()
        return self._read(case_id)

    def assign(self, case_id: str, assigned_to: str, assigned_team: str | None, actor: str) -> Case:
        """Assign a case (kept for the legacy ``/assign`` endpoint)."""
        return self.update_case(
            case_id, CaseUpdate(assigned_to=assigned_to, assigned_team=assigned_team), actor
        )

    # ------------------------------------------------------------------- reads

    def list_events(
        self,
        case_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
        event_type: EventType | None = None,
    ) -> CaseEventListResponse:
        """Audit timeline of a case, newest first."""
        if self._session.get(CaseModel, case_id) is None:
            raise CaseNotFoundError(f"Case {case_id} not found")
        events, total = self._events.list_by_case(
            case_id,
            page=page,
            page_size=page_size,
            event_type=EventType(event_type).value if event_type else None,
        )
        return CaseEventListResponse(
            total=total,
            page=page,
            page_size=page_size,
            events=[CaseEventOut.model_validate(e.model_dump()) for e in events],
        )

    # ---------------------------------------------------------------- internals

    @contextmanager
    def _unit_of_work(self) -> Iterator[None]:
        try:
            yield
            self._session.commit()
        except Exception:
            self._session.rollback()
            self._detached_from.clear()
            raise

    def _read(self, case_id: str) -> Case:
        case = self._cases.get_by_id(case_id)
        if case is None:  # pragma: no cover - guarded by callers
            raise CaseNotFoundError(f"Case {case_id} not found")
        return case

    def _lock_case(self, case_id: str) -> CaseModel:
        stmt = select(CaseModel).where(CaseModel.case_id == case_id).with_for_update()
        case = self._session.execute(stmt).scalar_one_or_none()
        if case is None:
            raise CaseNotFoundError(f"Case {case_id} not found")
        return case

    def _lock_alerts(self, alert_ids: Sequence[str]) -> list[AlertModel]:
        """Load alerts in request order, row-locked (sorted to avoid deadlocks)."""
        stmt = (
            select(AlertModel)
            .where(AlertModel.alert_id.in_(alert_ids))
            .order_by(AlertModel.alert_id)
            .with_for_update()
        )
        found = {a.alert_id: a for a in self._session.execute(stmt).scalars()}
        missing = [alert_id for alert_id in alert_ids if alert_id not in found]
        if missing:
            raise CaseNotFoundError(f"Alert(s) not found: {', '.join(missing)}")
        return [found[alert_id] for alert_id in alert_ids]

    def _ensure_linkable(self, alert: AlertModel, target_case_id: str | None) -> None:
        if alert.is_dismissed:
            raise CaseConflictError(
                f"Alert {alert.alert_id} was dismissed and cannot be linked to a case",
                code="alert_dismissed",
                alert_id=alert.alert_id,
            )
        if alert.case_id and alert.case_id != target_case_id:
            current = self._session.get(CaseModel, alert.case_id)
            if current is not None and _is_open(current.status):
                raise CaseConflictError(
                    f"Alert {alert.alert_id} is already linked to open case {current.case_id}",
                    code="alert_already_linked",
                    alert_id=alert.alert_id,
                    case_id=current.case_id,
                )

    def _attach(self, case: CaseModel, alert: AlertModel, actor: str) -> None:
        previous_case_id = alert.case_id
        alert.case = case
        alert.updated_at = self._clock.now()
        if previous_case_id and previous_case_id != case.case_id:
            self._detached_from.add(previous_case_id)
            self._log(
                previous_case_id,
                EventType.ALERT_UNLINKED_FROM_CASE,
                f"Alert {alert.alert_id} moved to case {case.case_id}",
                actor,
                alert_id=alert.alert_id,
                new_value=case.case_id,
            )
        self._log(
            case.case_id,
            EventType.ALERT_LINKED_TO_CASE,
            f"Alert {alert.alert_id} linked to case",
            actor,
            alert_id=alert.alert_id,
            transaction_id=alert.transaction_id,
        )

    def _apply_status(
        self, case: CaseModel, new: CaseStatus, update: CaseUpdate, actor: str
    ) -> bool:
        current = CaseStatus(case.status)
        if not is_valid_transition(current, new):
            raise CaseConflictError(
                f"Cannot change case status from {current.value} to {new.value}",
                code="invalid_status_transition",
                case_id=case.case_id,
                from_status=current.value,
                to_status=new.value,
            )
        if new in RESOLVED_STATUSES and not (update.resolution or "").strip():
            raise CaseRuleError(
                f"A resolution is required to set status {new.value}",
                code="resolution_required",
                field="resolution",
            )
        now = self._clock.now()
        case.status = new.value
        if update.resolution is not None:
            case.resolution = update.resolution
        if new in OPEN_STATUSES:
            case.resolved_at = None
            case.resolved_by = None
        else:
            case.resolved_at = now
            case.resolved_by = actor
        self._log(
            case.case_id,
            EventType.CASE_STATUS_CHANGED,
            f"Status changed from {current.value} to {new.value}",
            actor,
            previous_value=current.value,
            new_value=new.value,
            created_at=now,
        )
        return True

    def _apply_resolution(self, case: CaseModel, resolution: str, actor: str) -> bool:
        if CaseStatus(case.status) not in RESOLVED_STATUSES:
            raise CaseRuleError(
                "A resolution can only be set while resolving a case or on a resolved case",
                code="resolution_not_allowed",
                field="resolution",
                case_id=case.case_id,
            )
        if not resolution.strip():
            raise CaseRuleError(
                "A resolved case must keep a non-empty resolution",
                code="resolution_required",
                field="resolution",
            )
        previous = case.resolution
        if resolution == previous:
            return False
        case.resolution = resolution
        self._log(
            case.case_id,
            EventType.CASE_RESOLUTION_UPDATED,
            "Resolution updated",
            actor,
            previous_value=previous,
            new_value=resolution,
        )
        return True

    def _refresh_aggregates(self, case_id: str) -> None:
        """Refresh the target case and any case that just lost alerts to it."""
        for affected in sorted(self._detached_from | {case_id}):
            self._cases.refresh_aggregates(affected)
        self._detached_from.clear()

    def _apply_priority(self, case: CaseModel, new: CasePriority, actor: str) -> bool:
        current = case.priority
        if new.value == current:
            return False
        case.priority = new.value
        case.sla_due_at = sla_due_at(new, case.created_at)
        self._log(
            case.case_id,
            EventType.CASE_PRIORITY_CHANGED,
            f"Priority changed from {current} to {new.value}",
            actor,
            previous_value=current,
            new_value=new.value,
        )
        return True

    def _apply_assignment(
        self, case: CaseModel, assigned_to: str | None, assigned_team: str | None, actor: str
    ) -> bool:
        new_to = assigned_to if assigned_to is not None else case.assigned_to
        new_team = assigned_team if assigned_team is not None else case.assigned_team
        if (new_to, new_team) == (case.assigned_to, case.assigned_team):
            return False
        previous = case.assigned_to
        case.assigned_to, case.assigned_team = new_to, new_team
        target = new_to or "unassigned"
        self._log(
            case.case_id,
            EventType.CASE_ASSIGNED,
            f"Case assigned to {target}" + (f" ({new_team})" if new_team else ""),
            actor,
            previous_value=previous,
            new_value=new_to,
        )
        return True

    def _log(
        self,
        case_id: str,
        event_type: EventType,
        description: str,
        actor: str,
        *,
        created_at: datetime | None = None,
        **fields: Any,
    ) -> None:
        self._events.create(
            case_id=case_id,
            event_type=event_type,
            description=description,
            actor=actor,
            actor_type="user",
            created_at=created_at or self._clock.now(),
            **fields,
        )
