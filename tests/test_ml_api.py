# =============================================================================
# SentinelFlow - Fraud model API tests (ML-06)
# =============================================================================
"""
Contract: docs/contracts/sprint4-ml-api.md §4 (ml/models, risk/score, health,
ingestion) on top of a real LightGBM artifact built by ``ml_artifacts``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from ml_artifacts import (
    FS1_FEATURE_NAMES,
    FS1_VERSION,
    MODEL_VERSION,
    metadata_for,
    train_booster,
    write_artifact,
)

from sentinelflow.ml.serving import (
    FraudModelService,
    ModelNotLoadedError,
    ModelStatus,
    TransactionScorer,
    canonical_transaction,
)

pytest.importorskip("lightgbm")

FIXTURES = Path(__file__).parent / "fixtures" / "ml"

TX = {
    "transaction_id": "TXN-API-1",
    "sender_iban": "TR330006100519786457841326",
    "sender_name": "Gönderen",
    "receiver_iban": "TR110006400000468521793064",
    "receiver_name": "Alıcı",
    "amount": 5000.0,
    "currency": "TRY",
    "timestamp": "2026-11-05T10:00:00+00:00",
    "sender_country": "TR",
    "receiver_country": "DE",
    "payment_type": "cross_border",
}


def _service(model_dir: Path) -> FraudModelService:
    service = FraudModelService(
        model_dir, feature_set_version=FS1_VERSION, feature_names=FS1_FEATURE_NAMES
    )
    service.load()
    return service


@pytest.fixture()
def artifact_dir(tmp_path):
    model_text = train_booster().model_to_string()
    metadata = metadata_for(
        model_text,
        metrics={"split": "test", "pr_auc": 0.52, "recall": "n/a", "extra": 1},
    )
    return write_artifact(tmp_path / "model", model_text=model_text, metadata=metadata)


@pytest.fixture()
def client():
    """No database: auth is covered by test_api_auth, so every guard is overridden."""
    from fastapi.testclient import TestClient

    from sentinelflow.api.app import app
    from sentinelflow.api.routes.transactions import require_ingest_auth
    from sentinelflow.auth.dependencies import require_analyst, require_viewer

    app.dependency_overrides[require_viewer] = lambda: None
    app.dependency_overrides[require_analyst] = lambda: None
    app.dependency_overrides[require_ingest_auth] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def use_scorer(monkeypatch):
    from sentinelflow.api.state import state

    def _use(service: FraudModelService) -> TransactionScorer:
        scorer = TransactionScorer(service)
        monkeypatch.setattr(state, "scorer", scorer)
        return scorer

    return _use


# --- scorer ---------------------------------------------------------------------


class _RecordingService:
    """Stands in for the model; keeps the vectors it is asked to score."""

    def __init__(self) -> None:
        self.vectors: list[np.ndarray] = []

    def score(self, vector):
        self.vectors.append(np.asarray(vector))
        raise ModelNotLoadedError(ModelStatus.NOT_LOADED, "recording only")


def _as_api_tx(canonical: dict) -> dict:
    """Contract §1 service-side column names for a canonical fixture row."""
    return {
        "transaction_id": canonical["transaction_id"],
        "timestamp": canonical["timestamp"],
        "sender_iban": canonical["sender_account"],
        "receiver_iban": canonical["receiver_account"],
        "amount": canonical["amount"],
        "currency": canonical["payment_currency"],
        "received_currency": canonical.get("received_currency"),
        "sender_country": canonical.get("sender_country"),
        "receiver_country": canonical.get("receiver_country"),
        "payment_type": canonical.get("payment_type"),
    }


def test_ingestion_path_reproduces_the_shared_fixture():
    """API field mapping + record-after-score gives the ML-03 expected vectors."""
    rows = [json.loads(line) for line in (FIXTURES / "transactions.jsonl").open()]
    expected = {
        r["transaction_id"]: r["features"]
        for r in map(json.loads, (FIXTURES / "expected_features.jsonl").open())
    }
    service = _RecordingService()
    scorer = TransactionScorer(service)  # type: ignore[arg-type]
    for row in rows:
        assert scorer.score(_as_api_tx(row), record=True) is None
    assert len(service.vectors) == len(rows)
    for row, vector in zip(rows, service.vectors):
        np.testing.assert_allclose(vector, expected[row["transaction_id"]], rtol=1e-6)


def test_score_without_record_leaves_history_unchanged():
    service = _RecordingService()
    scorer = TransactionScorer(service)  # type: ignore[arg-type]
    scorer.score(TX, record=False)
    scorer.score(TX, record=False)
    assert scorer.history.recorded == 0
    np.testing.assert_array_equal(service.vectors[0], service.vectors[1])


def test_duplicate_id_gets_the_original_vector():
    service = _RecordingService()
    scorer = TransactionScorer(service)  # type: ignore[arg-type]
    scorer.score(TX, record=True)
    later = {**TX, "transaction_id": "TXN-API-2", "timestamp": "2026-11-05T10:05:00+00:00"}
    scorer.score(later, record=True)
    scorer.score(TX, record=True)
    np.testing.assert_array_equal(service.vectors[2], service.vectors[0])
    assert scorer.history.recorded == 2


def test_history_not_the_cache_decides_what_is_a_duplicate():
    """An id the history accepts as new is scored fresh even if the cache still holds it."""
    service = _RecordingService()
    scorer = TransactionScorer(service)  # type: ignore[arg-type]
    stale = np.full(len(FS1_FEATURE_NAMES), -1.0)
    scorer._vectors[TX["transaction_id"]] = (stale, False)
    scorer.score(TX, record=True)
    assert not np.array_equal(service.vectors[0], stale)
    assert scorer.history.recorded == 1


def test_duplicate_flag(artifact_dir):
    scorer = TransactionScorer(_service(artifact_dir))
    assert scorer.score(TX, record=True).duplicate is False
    assert scorer.score(TX, record=True).duplicate is True
    assert scorer.score(TX, record=False).duplicate is False


def test_duplicate_cache_is_bounded():
    scorer = TransactionScorer(_RecordingService(), duplicate_cache_size=2)  # type: ignore[arg-type]
    for i in range(5):
        scorer.score({**TX, "transaction_id": f"TXN-{i}"}, record=True)
    assert list(scorer._vectors) == ["TXN-3", "TXN-4"]


def test_canonical_transaction_treats_naive_timestamps_as_utc():
    from datetime import datetime

    canonical = canonical_transaction({**TX, "timestamp": datetime(2026, 11, 5, 10, 0)})
    assert canonical["timestamp"].utcoffset().total_seconds() == 0
    assert canonical["sender_account"] == TX["sender_iban"]
    assert canonical["payment_currency"] == "TRY"
    assert canonical["received_currency"] is None  # default applied by the feature module


# --- GET /ml/models ---------------------------------------------------------------


def test_models_loaded(client, use_scorer, artifact_dir):
    use_scorer(_service(artifact_dir))
    res = client.get("/api/v1/ml/models")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "loaded" and body["error"] is None
    model = body["model"]
    assert model["model_version"] == MODEL_VERSION
    assert model["feature_names"] == list(FS1_FEATURE_NAMES)
    assert model["loaded_at"]
    # Unknown keys dropped, malformed values and missing keys become null (not 0).
    assert model["metrics"]["pr_auc"] == 0.52
    assert model["metrics"]["recall"] is None
    assert model["metrics"]["f1"] is None
    assert "extra" not in model["metrics"]


@pytest.mark.parametrize("broken", ["missing", "invalid"])
def test_models_not_loaded_is_still_200(client, use_scorer, artifact_dir, tmp_path, broken):
    if broken == "missing":
        model_dir = tmp_path / "nope"
    else:
        (artifact_dir / "model.txt").write_text("tampered", encoding="utf-8")
        model_dir = artifact_dir
    use_scorer(_service(model_dir))
    res = client.get("/api/v1/ml/models")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == ("not_loaded" if broken == "missing" else "invalid")
    assert body["model"] is None
    assert body["error"]


def test_features_lists_fs1(client):
    body = client.get("/api/v1/ml/features").json()
    assert body["feature_set_version"] == FS1_VERSION
    assert [f["name"] for f in body["features"]] == list(FS1_FEATURE_NAMES)
    assert {f["name"] for f in body["features"] if f["categorical"]} == {
        "payment_type_code",
        "sender_country_code",
        "receiver_country_code",
    }


def test_training_endpoints_are_gone(client):
    assert client.post("/api/v1/ml/train", json={}).status_code == 404
    assert client.get("/api/v1/ml/train/status").status_code == 404


# --- POST /risk/score ---------------------------------------------------------------


def test_risk_score_contract_fields(client, use_scorer, artifact_dir):
    scorer = use_scorer(_service(artifact_dir))
    res = client.post("/api/v1/risk/score", json=TX)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["transaction_id"] == "TXN-API-1"
    assert body["model_version"] == MODEL_VERSION
    assert body["feature_set_version"] == FS1_VERSION
    assert 0.0 <= body["score"] <= 1.0
    assert body["is_fraud"] == (body["score"] >= body["threshold"])
    assert body["contribution_unit"] == "log_odds"
    assert len(body["top_features"]) == 5
    magnitudes = [abs(f["contribution"]) for f in body["top_features"]]
    assert magnitudes == sorted(magnitudes, reverse=True)
    assert body["history_cold_start"] is True
    assert body["latency_ms"] >= 0
    # Read only: nothing was recorded.
    assert scorer.history.recorded == 0


def test_risk_score_sees_ingested_history(client, use_scorer, artifact_dir):
    use_scorer(_service(artifact_dir))
    first = {**TX, "transaction_id": "TXN-HIST-1", "timestamp": "2026-11-05T09:00:00+00:00"}
    assert client.post("/api/v1/transactions", json=first).status_code == 200
    body = client.post("/api/v1/risk/score", json=TX).json()
    assert body["history_cold_start"] is False


def test_risk_score_503_without_model(client, use_scorer, tmp_path):
    use_scorer(_service(tmp_path / "missing"))
    res = client.post("/api/v1/risk/score", json=TX)
    assert res.status_code == 503
    assert res.json()["detail"] == {
        "code": "model_not_loaded",
        "message": "No valid fraud model is loaded",
        "status": "not_loaded",
    }


def test_risk_stats_reports_history_counters(client, use_scorer, artifact_dir):
    use_scorer(_service(artifact_dir))
    assert client.get("/api/v1/risk/stats").json()["history"] == {
        "recorded": 0,
        "duplicates": 0,
        "out_of_order": 0,
    }
    earlier = {**TX, "transaction_id": "TXN-OLD", "timestamp": "2026-11-05T09:00:00+00:00"}
    for tx in (TX, TX, earlier):
        assert client.post("/api/v1/transactions", json=tx).status_code == 200
    assert client.get("/api/v1/risk/stats").json()["history"] == {
        "recorded": 2,
        "duplicates": 1,
        "out_of_order": 1,
    }


def test_risk_batch_is_removed(client):
    assert client.post("/api/v1/risk/batch", json={"transactions": []}).status_code == 404


# --- health -----------------------------------------------------------------------


def test_health_reports_ml_model(client, use_scorer, artifact_dir, tmp_path, monkeypatch):
    from sentinelflow.api.state import state

    monkeypatch.setattr(state, "db_initialized", True)
    use_scorer(_service(artifact_dir))
    body = client.get("/api/v1/system/health").json()
    assert "ml_ensemble" not in body["components"]
    assert body["components"]["ml_model"] == {
        "name": "ml_model",
        "status": "healthy",
        "latency_ms": None,
        "message": MODEL_VERSION,
    }
    assert body["status"] == "healthy"

    use_scorer(_service(tmp_path / "missing"))
    body = client.get("/api/v1/system/health").json()
    assert body["components"]["ml_model"]["status"] == "degraded"
    assert "not found" in body["components"]["ml_model"]["message"]
    assert body["status"] == "degraded"


# --- ingestion ----------------------------------------------------------------------


def test_ingestion_without_model_returns_null_score_and_records(client, use_scorer, tmp_path):
    scorer = use_scorer(_service(tmp_path / "missing"))
    res = client.post("/api/v1/transactions", json=TX)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["fraud_score"] is None
    assert body["model_version"] is None
    assert body["is_fraud"] is False
    assert scorer.history.recorded == 1


def test_ingestion_below_threshold_makes_no_alert(client, use_scorer, tmp_path):
    model_text = train_booster().model_to_string()
    write_artifact(
        tmp_path / "model",
        model_text=model_text,
        metadata=metadata_for(model_text, threshold=0.999999),
    )
    use_scorer(_service(tmp_path / "model"))
    body = client.post("/api/v1/transactions", json=TX).json()
    assert body["is_fraud"] is False
    assert body["alerts"] is None
    assert body["model_version"] == MODEL_VERSION
    assert 0.0 <= body["fraud_score"] < 0.999999


def test_ingestion_rejects_contract_violations(client, use_scorer, artifact_dir):
    use_scorer(_service(artifact_dir))
    bad = {**TX, "currency": ""}
    res = client.post("/api/v1/transactions", json=bad)
    assert res.status_code == 422


def test_duplicate_ingestion_returns_the_alert_without_rebroadcast(
    client, use_scorer, tmp_path, monkeypatch
):
    from sentinelflow.api.routes import transactions as tx_routes
    from sentinelflow.api.state import state
    from sentinelflow.contracts import Alert, FraudType, Severity

    model_text = train_booster().model_to_string()
    write_artifact(
        tmp_path / "model", model_text=model_text, metadata=metadata_for(model_text, threshold=1e-6)
    )
    use_scorer(_service(tmp_path / "model"))
    alert = Alert(
        alert_id="ALR-1",
        fraud_type=FraudType.ML_MODEL,
        severity=Severity.HIGH,
        confidence=0.5,
        transaction_id=TX["transaction_id"],
        sender_iban=TX["sender_iban"],
        sender_name=TX["sender_name"],
        receiver_iban=TX["receiver_iban"],
        receiver_name=TX["receiver_name"],
        amount=TX["amount"],
    )
    # The repository returns the existing alert for a duplicate (no DB here).
    monkeypatch.setattr(tx_routes, "_persist_model_alert", lambda scored, tx_data: alert)
    broadcasts: list[dict] = []

    async def _broadcast(payload):
        broadcasts.append(payload)

    monkeypatch.setattr(state, "broadcast_alert", _broadcast)
    monkeypatch.setattr(state, "fraud_detected", 0)

    first = client.post("/api/v1/transactions", json=TX).json()
    again = client.post("/api/v1/transactions", json=TX).json()
    assert first["is_fraud"] and again["is_fraud"]
    assert first["fraud_score"] == again["fraud_score"]
    assert [a["alert_id"] for a in again["alerts"]] == ["ALR-1"]
    assert [b["alert_id"] for b in broadcasts] == ["ALR-1"]
    assert state.fraud_detected == 1
