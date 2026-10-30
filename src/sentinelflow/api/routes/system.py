# =============================================================================
# SentinelFlow API - System, Root & Metrics Endpoints
# =============================================================================
"""Health, statistics, service info and Prometheus-style metrics."""

from __future__ import annotations

import time

from fastapi import APIRouter
from loguru import logger

from sentinelflow.api.schemas import (
    SCHEMA_VERSION,
    ComponentStatus,
    HealthResponse,
    StatsResponse,
)
from sentinelflow.api.state import state

router = APIRouter()


def _ml_model_status() -> ComponentStatus:
    """``ml_model`` component (contract §4.3): message is the model version or the error."""
    service = state.scorer.service
    meta = service.metadata
    if meta is not None:
        return ComponentStatus(name="ml_model", status="healthy", message=meta.model_version)
    return ComponentStatus(name="ml_model", status="degraded", message=service.error)


@router.get(
    "/api/v1/system/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health check",
)
async def health_check() -> HealthResponse:
    """Check system health."""
    uptime = time.time() - state.start_time

    components = {
        "api": ComponentStatus(name="api", status="healthy"),
        "database": ComponentStatus(
            name="database",
            status="healthy" if state.db_initialized else "degraded",
        ),
        "ml_model": _ml_model_status(),
    }

    healthy = all(c.status == "healthy" for c in components.values())
    overall = "healthy" if healthy else "degraded"

    return HealthResponse(
        status=overall,
        version="2.2.0",
        schema_version=SCHEMA_VERSION,
        uptime_seconds=round(uptime, 2),
        components=components,
    )


@router.get(
    "/api/v1/system/stats",
    response_model=StatsResponse,
    tags=["System"],
    summary="System statistics",
)
async def system_stats() -> StatsResponse:
    """Get system-wide statistics."""
    from sentinelflow.api.deps import get_db_session
    from sentinelflow.repository import AlertRepository, CaseRepository

    uptime = time.time() - state.start_time

    # Get database stats
    alerts_created = 0
    cases_open = 0
    cases_resolved = 0
    by_fraud_type = {}
    by_severity = {}

    try:
        session = next(get_db_session())
        alert_repo = AlertRepository(session)
        case_repo = CaseRepository(session)

        alert_stats = alert_repo.get_stats()
        case_stats = case_repo.get_stats()

        alerts_created = alert_stats.get("total", 0)
        by_fraud_type = alert_stats.get("by_fraud_type", {})
        by_severity = alert_stats.get("by_severity", {})
        cases_open = case_stats.get("open", 0)
        cases_resolved = case_stats.get("closed", 0)

        session.close()
    except Exception as e:
        logger.warning(f"Could not fetch DB stats: {e}")

    fraud_rate = (
        (state.fraud_detected / state.transactions_processed * 100)
        if state.transactions_processed > 0
        else 0.0
    )

    return StatsResponse(
        transactions_processed=state.transactions_processed,
        fraud_detected=state.fraud_detected,
        alerts_created=alerts_created,
        cases_open=cases_open,
        cases_resolved=cases_resolved,
        by_fraud_type=by_fraud_type,
        by_severity=by_severity,
        uptime_seconds=round(uptime, 2),
        fraud_rate=round(fraud_rate, 2),
    )


@router.get("/", tags=["Root"])
async def root():
    """API root - service info."""
    return {
        "service": "SentinelFlow Fraud Detection API",
        "version": "2.2.0",
        "schema_version": SCHEMA_VERSION,
        "docs": "/docs",
        "health": "/api/v1/system/health",
    }


@router.get("/metrics", tags=["Monitoring"])
async def metrics():
    """Prometheus-compatible metrics endpoint."""
    uptime = time.time() - state.start_time

    lines = [
        "# HELP sentinelflow_transactions_processed_total Total transactions processed",
        "# TYPE sentinelflow_transactions_processed_total counter",
        f"sentinelflow_transactions_processed_total {state.transactions_processed}",
        "",
        "# HELP sentinelflow_fraud_detected_total Total fraud cases detected",
        "# TYPE sentinelflow_fraud_detected_total counter",
        f"sentinelflow_fraud_detected_total {state.fraud_detected}",
        "",
        "# HELP sentinelflow_errors_total Total errors",
        "# TYPE sentinelflow_errors_total counter",
        f"sentinelflow_errors_total {state.errors}",
        "",
        "# HELP sentinelflow_uptime_seconds API uptime in seconds",
        "# TYPE sentinelflow_uptime_seconds gauge",
        f"sentinelflow_uptime_seconds {uptime:.2f}",
        "",
        "# HELP sentinelflow_websocket_clients Active WebSocket connections",
        "# TYPE sentinelflow_websocket_clients gauge",
        f"sentinelflow_websocket_clients {len(state.ws_clients)}",
        "",
    ]

    return "\n".join(lines)
