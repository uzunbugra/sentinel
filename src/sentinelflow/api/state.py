# =============================================================================
# SentinelFlow API - Application State
# =============================================================================
"""
Process-wide API state: counters, WebSocket clients and the fraud model
scorer. ``state`` is the single shared instance.
"""

from __future__ import annotations

import json
import time

from fastapi import WebSocket
from loguru import logger

from sentinelflow.ml.serving import TransactionScorer


class AppState:
    """Holds application-wide state."""

    def __init__(self) -> None:
        self.start_time = time.time()
        self.transactions_processed = 0
        self.fraud_detected = 0
        self.errors = 0

        # WebSocket connections for real-time alerts
        self.ws_clients: list[WebSocket] = []

        # Database initialized flag
        self.db_initialized = False

        # Fraud model + fs-1 account history (ADR 0003 §8-9)
        self.scorer: TransactionScorer = self._build_scorer()

    def init_database(self) -> bool:
        """Initialize database connection and tables."""
        try:
            from sentinelflow.database.postgres import init_db

            init_db(drop_all=False)
            self.db_initialized = True
            logger.info("Database initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False

    @staticmethod
    def _build_scorer() -> TransactionScorer:
        from sentinelflow.config import get_settings
        from sentinelflow.ml.features import FEATURE_NAMES, FEATURE_SET_VERSION
        from sentinelflow.ml.serving import FraudModelService

        service = FraudModelService(
            get_settings().serving.dir,
            feature_set_version=FEATURE_SET_VERSION,
            feature_names=FEATURE_NAMES,
        )
        return TransactionScorer(service)

    def load_fraud_model(self) -> bool:
        """Load the fraud model artifact; the API keeps running without it."""
        self.scorer.service.load()
        return self.scorer.service.is_loaded

    async def broadcast_alert(self, alert_data: dict) -> None:
        """Broadcast alert to all WebSocket clients."""
        disconnected: list[WebSocket] = []
        message = json.dumps(alert_data, ensure_ascii=False, default=str)

        for ws in self.ws_clients:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            if ws in self.ws_clients:
                self.ws_clients.remove(ws)


# Module-level state
state = AppState()
