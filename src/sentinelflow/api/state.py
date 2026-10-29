# =============================================================================
# SentinelFlow API - Application State
# =============================================================================
"""
Process-wide API state: counters, WebSocket clients and lazily loaded ML
components. ``state`` is the single shared instance.
"""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import WebSocket
from loguru import logger


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

        # ML components (lazy loaded)
        self._ml_loaded = False
        self._feature_engine: Any = None
        self._ensemble: Any = None
        self._explainer: Any = None

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

    def load_ml_components(self) -> bool:
        """Lazy load ML components (optional, may fail on some systems)."""
        if self._ml_loaded:
            return True

        try:
            from sentinelflow.ml.ensemble import EnsembleVoter
            from sentinelflow.ml.explainer import FraudExplainer
            from sentinelflow.ml.feature_engine import NUM_FEATURES, TransactionFeatureEngine
            from sentinelflow.ml.models import (
                AutoEncoderModel,
                IsolationForestModel,
                XGBoostFraudModel,
            )

            self._feature_engine = TransactionFeatureEngine(history_window_size=1000)

            if_model = IsolationForestModel(
                contamination=0.05, n_estimators=200, min_samples_to_train=50
            )
            xgb_model = XGBoostFraudModel(n_estimators=300, max_depth=6, learning_rate=0.05)
            ae_model = AutoEncoderModel(input_dim=NUM_FEATURES, encoding_dim=8)

            self._ensemble = EnsembleVoter(threshold=0.7)
            self._ensemble.add_model(if_model, weight=0.4)
            self._ensemble.add_model(xgb_model, weight=0.4)
            self._ensemble.add_model(ae_model, weight=0.2)

            self._explainer = FraudExplainer(enable_shap=False)  # Disable SHAP for faster startup

            self._ml_loaded = True
            logger.info("ML components loaded")
            return True

        except Exception as e:
            logger.warning(f"ML components not loaded (optional): {e}")
            return False

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
