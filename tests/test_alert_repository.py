# =============================================================================
# SentinelFlow - Alert Repository Tests (issue #13)
# =============================================================================
"""
Alert persistence round trips: AlertRepository.create used to store evidence
as {"items": [...]} while Alert expects a list, so every create raised a
ValidationError and ML alerts were never saved.
"""

import importlib.util
from pathlib import Path

import pytest
from case_db import make_engine, make_session

from sentinelflow.contracts import AlertCreate, UserCreate
from sentinelflow.contracts.alert import Evidence
from sentinelflow.database.models import AlertModel
from sentinelflow.repository import AlertRepository

BASE = {
    "fraud_type": "ml_ensemble",
    "severity": "high",
    "confidence": 0.9,
    "transaction_id": "TX-1",
    "sender_iban": "TR00SENDER",
    "sender_name": "Gönderen",
    "receiver_iban": "TR00RECEIVER",
    "receiver_name": "Alıcı",
    "amount": 1250.0,
}


@pytest.fixture()
def session():
    engine = make_engine()
    s = make_session(engine)
    yield s
    s.close()
    engine.dispose()


def _evidence():
    return Evidence(
        detector_type="ml_ensemble",
        confidence=0.9,
        summary="Ensemble score 0.90",
        details={"score": 0.9},
    )


class TestCreateRoundTrip:
    @pytest.mark.parametrize("evidence", [None, [], "one"])
    def test_create_then_read_back(self, session, evidence):
        data = dict(BASE)
        if evidence == "one":
            data["evidence"] = [_evidence()]
        elif evidence is not None:
            data["evidence"] = evidence
        repo = AlertRepository(session)

        created = repo.create(AlertCreate(**data))
        session.commit()
        fetched = repo.get_by_id(created.alert_id)

        assert fetched is not None
        assert fetched.evidence == created.evidence
        assert len(fetched.evidence) == (1 if evidence == "one" else 0)
        alerts, total = repo.list()
        assert total == 1 and alerts[0].alert_id == created.alert_id

    def test_evidence_is_stored_as_a_list(self, session):
        created = AlertRepository(session).create(AlertCreate(**BASE, evidence=[_evidence()]))
        stored = session.get(AlertModel, created.alert_id).evidence
        assert isinstance(stored, list)
        assert stored[0]["summary"] == "Ensemble score 0.90"

    def test_duplicate_returns_existing_alert(self, session):
        repo = AlertRepository(session)
        first = repo.create(AlertCreate(**BASE))
        again = repo.create(AlertCreate(**BASE))
        assert again.alert_id == first.alert_id


class TestLegacyRows:
    @pytest.mark.parametrize(
        ("stored", "expected"),
        [
            ({"items": []}, 0),
            ({"items": [{"detector_type": "ml_ensemble"}]}, 1),
            (None, 0),
            ({}, 0),
        ],
    )
    def test_old_or_missing_evidence_is_readable(self, session, stored, expected):
        created = AlertRepository(session).create(AlertCreate(**BASE))
        session.get(AlertModel, created.alert_id).evidence = stored
        session.commit()
        session.expire_all()
        fetched = AlertRepository(session).get_by_id(created.alert_id)
        assert len(fetched.evidence) == expected


class TestTransactionEndpointPersistsMlAlerts:
    """End-to-end impact from the issue: an ML-flagged transaction must be saved."""

    def test_flagged_transaction_creates_and_broadcasts_alert(self, session, monkeypatch, tmp_path):
        pytest.importorskip("lightgbm")
        from fastapi.testclient import TestClient
        from ml_artifacts import (
            FS1_FEATURE_NAMES,
            FS1_VERSION,
            metadata_for,
            train_booster,
            write_artifact,
        )

        import sentinelflow.api.deps as deps
        import sentinelflow.api.routes.transactions as tx_routes
        from sentinelflow.api.app import app
        from sentinelflow.api.state import state
        from sentinelflow.ml.serving import FraudModelService, TransactionScorer

        # Near-zero threshold and critical cut-off: every score is a critical alert.
        model_text = train_booster().model_to_string()
        write_artifact(
            tmp_path / "model",
            model_text=model_text,
            metadata=metadata_for(model_text, threshold=1e-6),
        )
        service = FraudModelService(
            tmp_path / "model", feature_set_version=FS1_VERSION, feature_names=FS1_FEATURE_NAMES
        )
        service.load()
        assert service.is_loaded
        monkeypatch.setattr(tx_routes, "CRITICAL_SCORE", 0.0)

        broadcasts = []

        async def fake_broadcast(payload):
            broadcasts.append(payload)

        monkeypatch.setattr(state, "scorer", TransactionScorer(service))
        monkeypatch.setattr(state, "broadcast_alert", fake_broadcast)

        def _session():
            yield session

        # Auth resolves the session via Depends(); the route body calls it directly.
        app.dependency_overrides[deps.get_db_session] = _session
        monkeypatch.setattr(deps, "get_db_session", _session)
        monkeypatch.setattr(tx_routes, "_INGEST_API_KEY", "test-key")

        try:
            res = TestClient(app).post(
                "/api/v1/transactions",
                json={
                    "transaction_id": "TX-E2E",
                    "sender_iban": "TR330006100519786457841326",
                    "sender_name": "Gönderen",
                    "receiver_iban": "TR330006100519786457841327",
                    "receiver_name": "Alıcı",
                    "amount": 5000.0,
                },
                headers={"X-API-Key": "test-key"},
            )
        finally:
            app.dependency_overrides.clear()

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["is_fraud"] is True
        assert body["alerts"] and body["alerts"][0]["transaction_id"] == "TX-E2E"
        assert body["model_version"] == service.metadata.model_version
        saved = session.query(AlertModel).filter_by(transaction_id="TX-E2E").one()
        assert saved.severity == "critical"
        assert saved.fraud_type == "ml_model"
        evidence = body["alerts"][0]["evidence"][0]
        assert evidence["detector_type"] == "ml_model"
        assert evidence["details"]["contribution_unit"] == "log_odds"
        assert evidence["details"]["history_cold_start"] is True
        assert broadcasts and broadcasts[0]["alert_id"] == saved.alert_id


def test_seed_admin_default_email_is_valid():
    path = Path(__file__).resolve().parents[1] / "scripts" / "seed_admin.py"
    spec = importlib.util.spec_from_file_location("seed_admin", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    user = UserCreate(
        username="admin",
        email=module.DEFAULT_ADMIN_EMAIL,
        password="Admin12345!",
        full_name="SentinelFlow Admin",
    )
    assert user.email == "admin@example.com"
