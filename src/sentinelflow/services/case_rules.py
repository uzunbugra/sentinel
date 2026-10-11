# =============================================================================
# SentinelFlow - Case Workflow Rules
# =============================================================================
"""
Pure business rules for the case workflow: status transitions and SLA.

See docs/contracts/sprint3-case-api.md §2.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sentinelflow.contracts.enums import CasePriority, CaseStatus

OPEN_STATUSES: frozenset[CaseStatus] = frozenset(s for s in CaseStatus if s.is_open)
RESOLVED_STATUSES: frozenset[CaseStatus] = frozenset(
    {CaseStatus.RESOLVED_TRUE_POSITIVE, CaseStatus.RESOLVED_FALSE_POSITIVE}
)

SLA_DURATIONS: dict[CasePriority, timedelta] = {
    CasePriority.P1_CRITICAL: timedelta(hours=4),
    CasePriority.P2_HIGH: timedelta(hours=24),
    CasePriority.P3_MEDIUM: timedelta(hours=72),
    CasePriority.P4_LOW: timedelta(hours=168),
}


def allowed_transitions(current: CaseStatus) -> frozenset[CaseStatus]:
    """Statuses a case in ``current`` may move to (excluding ``current`` itself)."""
    if current in OPEN_STATUSES:
        targets = OPEN_STATUSES | RESOLVED_STATUSES | {CaseStatus.CLOSED}
    elif current in RESOLVED_STATUSES:
        targets = frozenset({CaseStatus.CLOSED, CaseStatus.INVESTIGATING})
    else:  # CLOSED is terminal
        targets = frozenset()
    return frozenset(targets - {current})


def is_valid_transition(current: CaseStatus, new: CaseStatus) -> bool:
    """Whether ``current -> new`` is allowed. Same status is not a transition."""
    return new in allowed_transitions(current)


def sla_due_at(priority: CasePriority, created_at: datetime) -> datetime:
    """SLA deadline for a case of ``priority`` opened at ``created_at``."""
    return created_at + SLA_DURATIONS[priority]
