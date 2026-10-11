# =============================================================================
# SentinelFlow API - Case Routes
# =============================================================================
"""
Case management endpoints.

Write endpoints delegate to ``CaseService`` (one transaction per request).
Contract: docs/contracts/sprint3-case-api.md.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from sentinelflow.api.deps import get_db_session
from sentinelflow.api.schemas import (
    Case,
    CaseCreate,
    CaseListResponse,
    CaseUpdate,
)
from sentinelflow.auth.dependencies import require_analyst, require_viewer
from sentinelflow.contracts import EventType, User
from sentinelflow.contracts.case import (
    ApiErrorResponse,
    CaseAlertLink,
    CaseEventListResponse,
)
from sentinelflow.services import CaseService, CaseServiceError

router = APIRouter(prefix="/cases", tags=["Cases"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "Case or alert not found"}}
_CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ApiErrorResponse, "description": "Conflicts with the current case state"}
}
_RULE: dict[int | str, dict[str, Any]] = {
    422: {"description": "Validation error or business rule violation"}
}


def _http_error(exc: CaseServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail())


@router.get(
    "",
    response_model=CaseListResponse,
    summary="List cases",
    description="Returns a paginated list of investigation cases.",
)
async def list_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Filter by status"),
    priority: str | None = Query(None, description="Filter by priority"),
    assigned_to: str | None = Query(None, description="Filter by assignee"),
    is_open: bool | None = Query(None, description="Filter open/closed cases"),
    session=Depends(get_db_session),
    _user: User = Depends(require_viewer),
):
    """List cases with pagination and filtering."""
    from sentinelflow.repository import CaseRepository

    repo = CaseRepository(session)

    cases, total = repo.list(
        page=page,
        page_size=page_size,
        status=status,
        priority=priority,
        assigned_to=assigned_to,
        is_open=is_open,
    )

    return CaseListResponse(
        total=total,
        page=page,
        page_size=page_size,
        cases=cases,
        filters={"status": status, "priority": priority, "assigned_to": assigned_to},
    )


@router.get(
    "/stats",
    summary="Get case statistics",
)
async def get_case_stats(
    session=Depends(get_db_session),
    _user: User = Depends(require_viewer),
):
    """Get case statistics."""
    from sentinelflow.repository import CaseRepository

    repo = CaseRepository(session)
    return repo.get_stats()


@router.post(
    "",
    response_model=Case,
    status_code=status.HTTP_201_CREATED,
    summary="Create a case from alerts",
    description=(
        "Atomically creates a case and links the given alerts. Writes `case_created` "
        "followed by one `alert_linked_to_case` event per alert."
    ),
    responses={**_NOT_FOUND, **_CONFLICT, **_RULE},
)
async def create_case(
    case_data: CaseCreate,
    session=Depends(get_db_session),
    user: User = Depends(require_analyst),
):
    """Create a new case from one or more alerts."""
    try:
        return CaseService(session).create_from_alerts(case_data, actor=user.username)
    except CaseServiceError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/{case_id}",
    response_model=Case,
    summary="Get case details",
)
async def get_case(
    case_id: str,
    session=Depends(get_db_session),
    _user: User = Depends(require_viewer),
):
    """Get a specific case by ID."""
    from sentinelflow.repository import CaseRepository

    repo = CaseRepository(session)
    case = repo.get_by_id(case_id)

    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    return case


@router.patch(
    "/{case_id}",
    response_model=Case,
    summary="Update case",
    description="Change status, priority, assignment and/or add a note; one event per change.",
    responses={**_NOT_FOUND, **_CONFLICT, **_RULE},
)
async def update_case(
    case_id: str,
    update_data: CaseUpdate,
    session=Depends(get_db_session),
    user: User = Depends(require_analyst),
):
    """Update case fields."""
    try:
        return CaseService(session).update_case(case_id, update_data, actor=user.username)
    except CaseServiceError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{case_id}/assign",
    response_model=Case,
    summary="Assign case",
    responses={**_NOT_FOUND},
)
async def assign_case(
    case_id: str,
    assigned_to: str = Query(..., min_length=1, description="Username to assign to"),
    assigned_team: str | None = Query(None, description="Team name"),
    session=Depends(get_db_session),
    user: User = Depends(require_analyst),
):
    """Assign case to analyst/team."""
    try:
        return CaseService(session).assign(case_id, assigned_to, assigned_team, actor=user.username)
    except CaseServiceError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{case_id}/alerts",
    response_model=Case,
    summary="Link an alert to a case",
    description="Idempotent: linking an alert that is already in this case returns 200.",
    responses={**_NOT_FOUND, **_CONFLICT},
)
async def link_alert(
    case_id: str,
    link: CaseAlertLink = Body(...),
    session=Depends(get_db_session),
    user: User = Depends(require_analyst),
):
    """Link an existing alert to an existing open case."""
    try:
        return CaseService(session).link_alert(case_id, link.alert_id, actor=user.username)
    except CaseServiceError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{case_id}/add-alert/{alert_id}",
    response_model=Case,
    summary="Add alert to case (deprecated)",
    description="Deprecated alias of `POST /cases/{case_id}/alerts`.",
    deprecated=True,
    responses={**_NOT_FOUND, **_CONFLICT},
)
async def add_alert_to_case(
    case_id: str,
    alert_id: str,
    session=Depends(get_db_session),
    user: User = Depends(require_analyst),
):
    """Add an alert to an existing case."""
    try:
        return CaseService(session).link_alert(case_id, alert_id, actor=user.username)
    except CaseServiceError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/{case_id}/events",
    response_model=CaseEventListResponse,
    summary="Get case events (audit log)",
    description="Audit timeline, newest first. Timestamps are UTC.",
    responses={**_NOT_FOUND},
)
async def get_case_events(
    case_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    event_type: EventType | None = Query(None),
    session=Depends(get_db_session),
    _user: User = Depends(require_viewer),
):
    """Get audit log events for a case."""
    try:
        return CaseService(session).list_events(
            case_id, page=page, page_size=page_size, event_type=event_type
        )
    except CaseServiceError as exc:
        raise _http_error(exc) from exc
