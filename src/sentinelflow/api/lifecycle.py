# =============================================================================
# SentinelFlow API - Lifecycle
# =============================================================================
"""Startup/shutdown: fail-fast secret check, database and optional ML init."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from sentinelflow.api.state import state


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App startup/shutdown lifecycle."""
    logger.info("SentinelFlow API starting...")

    # Fail fast on missing secrets (no silent defaults): the app refuses to
    # start without a JWT signing key. See .env.example for required values.
    from sentinelflow.auth.config import auth_config

    auth_config.ensure_ready()

    # Initialize database
    state.init_database()

    # Try to load ML components (optional)
    state.load_ml_components()

    yield

    logger.info("SentinelFlow API shutting down...")
