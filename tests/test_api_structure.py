# =============================================================================
# SentinelFlow - API Package Structure Tests (SF-309)
# =============================================================================
"""
Guards for the api/app.py split: public import paths stay stable, the app
factory wires every router, the WebSocket stream still works, and hand-written
API modules stay under the 500-line limit from docs/SPRINT3_PLAN.md.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

API_DIR = Path(__file__).resolve().parents[1] / "src" / "sentinelflow" / "api"
MAX_MODULE_LINES = 500


def test_public_import_paths():
    from sentinelflow.api import app as app_module
    from sentinelflow.api.lifecycle import lifespan
    from sentinelflow.api.routes.transactions import require_ingest_auth
    from sentinelflow.api.state import AppState, state

    assert app_module.state is state
    assert app_module.AppState is AppState
    assert app_module.lifespan is lifespan
    assert app_module.require_ingest_auth is require_ingest_auth
    assert callable(app_module.main)
    assert app_module.app.title == "SentinelFlow - Fraud Detection API"


def test_create_app_builds_equivalent_independent_apps():
    from sentinelflow.api.app import app, create_app

    fresh = create_app()
    assert fresh is not app
    assert fresh.openapi() == app.openapi()


@pytest.mark.parametrize(
    "path",
    ["/", "/metrics", "/api/v1/system/health", "/api/v1/transactions", "/ws/alerts"],
)
def test_core_routes_are_registered(path):
    from sentinelflow.api.app import app

    assert path in app.openapi()["paths"] or path == "/ws/alerts"
    client = TestClient(app)
    if path == "/ws/alerts":
        with client.websocket_connect(path) as ws:
            assert ws.receive_json()["type"] == "connection"
            ws.send_text("ping")
            assert ws.receive_json() == {"type": "pong"}


def test_websocket_clients_are_tracked_and_released():
    from sentinelflow.api.app import app
    from sentinelflow.api.state import state

    before = len(state.ws_clients)
    with TestClient(app).websocket_connect("/ws/alerts") as ws:
        ws.receive_json()
        assert len(state.ws_clients) == before + 1
    assert len(state.ws_clients) == before


@pytest.mark.parametrize(
    "module",
    sorted(p for p in API_DIR.rglob("*.py") if "__pycache__" not in p.parts),
    ids=lambda p: str(p.relative_to(API_DIR)),
)
def test_api_modules_stay_small(module):
    lines = len(module.read_text(encoding="utf-8").splitlines())
    assert lines < MAX_MODULE_LINES, f"{module.name} has {lines} lines"
