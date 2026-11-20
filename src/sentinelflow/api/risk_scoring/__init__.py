# =============================================================================
# SentinelFlow - Real-Time Risk Scoring API
# =============================================================================
"""
``POST /api/v1/risk/score``: scores one transaction with the served fraud model
(ADR 0003, docs/contracts/sprint4-ml-api.md §4.2) without changing the account
history. Ingestion (``POST /api/v1/transactions``) is the only path that records.
"""

from .routes import router
from .schemas import RiskScoreResponse, RiskStatsResponse

__all__ = [
    "RiskScoreResponse",
    "RiskStatsResponse",
    "router",
]
