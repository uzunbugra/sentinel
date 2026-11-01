# =============================================================================
# SentinelFlow - FastAPI Application
# =============================================================================
"""
Main FastAPI application for SentinelFlow REST API.

Run:
    uvicorn sentinelflow.api.app:app --host 0.0.0.0 --port 8000 --reload

Or:
    python -m sentinelflow.api.app
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from sentinelflow.api.lifecycle import lifespan
from sentinelflow.api.risk_scoring import router as risk_router
from sentinelflow.api.routes.alerts import router as alerts_router
from sentinelflow.api.routes.auth import router as auth_router
from sentinelflow.api.routes.cases import router as cases_router
from sentinelflow.api.routes.chat import router as chat_router
from sentinelflow.api.routes.graph import router as graph_router
from sentinelflow.api.routes.kyc import router as kyc_router
from sentinelflow.api.routes.ml import router as ml_router
from sentinelflow.api.routes.system import router as system_router
from sentinelflow.api.routes.transactions import require_ingest_auth
from sentinelflow.api.routes.transactions import router as transactions_router
from sentinelflow.api.state import AppState, state
from sentinelflow.api.websocket import router as websocket_router

__all__ = ["AppState", "app", "create_app", "lifespan", "main", "require_ingest_auth", "state"]


API_DESCRIPTION = """
## SentinelFlow Real-Time Fraud Detection Platform

Bitirme projesi olarak geliştirilmiş, yapay zeka destekli
gerçek zamanlı dolandırıcılık tespit platformu.

### Özellikler
- **Dolandırıcılık modeli**: SAML-D ile offline eğitilmiş tek LightGBM modeli (`/api/v1/ml`, `/api/v1/risk`)
- **PostgreSQL**: Kalıcı alert ve case yönetimi
- **Case Management**: Alert korelasyonu, triage, audit log
- **WebSocket**: Canlı alert akışı
- **Explainability**: ML alarmında model sürümü ve ilk 5 özellik katkısı

### API Grupları
- `/api/v1/alerts` - Alarm listesi ve detayları
- `/api/v1/cases` - Vaka yönetimi
- `/api/v1/transactions` - İşlem analizi
- `/api/v1/system` - Sistem sağlık ve istatistikler
- `/ws/alerts` - WebSocket canlı alert akışı
    """


# CORS
#
# CORS_ORIGINS (comma-separated): browsable frontend origins, e.g.
#   CORS_ORIGINS="http://localhost:3000,https://app.example.com"
# If unset, defaults to the local dev frontend. "*" keeps the legacy open
# mode but then credentials MUST be disabled (cookies/Auth headers).
def _cors_settings() -> tuple[list[str], bool]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000").strip()
    if raw == "*":
        return ["*"], False
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["http://localhost:3000"], True


def create_app() -> FastAPI:
    """Build the FastAPI application (routers are registered in a fixed order)."""
    application = FastAPI(
        title="SentinelFlow - Fraud Detection API",
        description=API_DESCRIPTION,
        version="2.2.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    cors_origins, cors_allow_credentials = _cors_settings()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
        expose_headers=["X-Request-Id"],
    )

    for router in (
        auth_router,
        alerts_router,
        cases_router,
        ml_router,
        graph_router,
        chat_router,
        kyc_router,
    ):
        application.include_router(router, prefix="/api/v1")
    application.include_router(risk_router)
    application.include_router(transactions_router)
    application.include_router(system_router)
    application.include_router(websocket_router)
    return application


app = create_app()


# =============================================================================
# CLI Entry Point
# =============================================================================


def main():
    """Run the API server."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    import uvicorn

    # All-interfaces bind is intentional for containerized deploys.
    host = os.getenv("SENTINELFLOW_API_HOST", "0.0.0.0")  # nosec
    port = int(os.getenv("SENTINELFLOW_API_PORT", "8000"))

    logger.info(f"Starting SentinelFlow API on {host}:{port}")
    uvicorn.run(
        "sentinelflow.api.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
