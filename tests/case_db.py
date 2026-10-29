# =============================================================================
# SentinelFlow - In-memory database helpers for case workflow tests
# =============================================================================
"""
Shared builders for case/alert tests: an in-memory SQLite engine with the full
schema (ARRAY/JSONB fall back to JSON on SQLite), seeded users and alerts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from sentinelflow.database.models import AlertModel, Base

BASE_TIME = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)


def make_engine() -> Engine:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def make_session(engine: Engine) -> Session:
    # Mirror production: no autoflush, objects stay usable after commit.
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def add_alert(
    session: Session,
    alert_id: str,
    *,
    amount: float = 1000.0,
    severity: str = "high",
    fraud_type: str = "circular_ring",
    confidence: float = 0.9,
    minutes: int = 0,
    dismissed: bool = False,
) -> AlertModel:
    alert = AlertModel(
        alert_id=alert_id,
        fraud_type=fraud_type,
        severity=severity,
        confidence=confidence,
        transaction_id=f"TX-{alert_id}",
        sender_iban=f"TR00SENDER{alert_id}",
        sender_name="Gönderen",
        receiver_iban=f"TR00RECEIVER{alert_id}",
        receiver_name="Alıcı",
        amount=amount,
        detected_at=BASE_TIME + timedelta(minutes=minutes),
        is_dismissed=dismissed,
    )
    session.add(alert)
    session.commit()
    return alert
