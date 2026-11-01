# =============================================================================
# SentinelFlow - Kafka detector on the served fraud model (ML-06)
# =============================================================================
"""
The detector scores with the same artifact, feature set and history rules as the
API (ADR 0003 §8-9) and raises ``ml_model`` alerts with contract §4.5 evidence.
No Kafka, Neo4j or database: the detection and publishing methods are called
directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ml_artifacts import MODEL_VERSION, metadata_for, train_booster, write_artifact

from sentinelflow.ml.serving import build_scorer

pytest.importorskip("lightgbm")
pytest.importorskip("confluent_kafka")

from sentinelflow.processor.detector import FraudDetectorService, FraudType  # noqa: E402

# Shape of a generator Kafka message (naive ISO timestamp, no country/payment type).
KAFKA_TX = {
    "transaction_id": "8f0c2b9e-1d2a-4c55-9a43-0d6c3a7b9e11",
    "sender_account_id": "a1",
    "sender_iban": "TR330006100519786457841326",
    "sender_name": "Gönderen",
    "sender_city": "İstanbul",
    "receiver_account_id": "b1",
    "receiver_iban": "TR110006400000468521793064",
    "receiver_name": "Alıcı",
    "receiver_city": "Ankara",
    "amount": 5000.0,
    "currency": "TRY",
    "description": "kira",
    "timestamp": "2026-11-05T10:00:00.123456",
    "status": "pending",
    "fraud_type": "none",
    "fraud_score": 0.0,
    "is_flagged": False,
}


def _model_dir(tmp_path: Path, threshold: float | None = None) -> Path:
    model_text = train_booster().model_to_string()
    overrides = {} if threshold is None else {"threshold": threshold}
    return write_artifact(
        tmp_path / "model", model_text=model_text, metadata=metadata_for(model_text, **overrides)
    )


def _detector(model_dir: Path) -> FraudDetectorService:
    detector = FraudDetectorService(scorer=build_scorer(model_dir))
    detector._init_fraud_model()
    return detector


def test_detector_and_api_serve_the_same_model(tmp_path, monkeypatch):
    """Acceptance: API, risk/score and detector report one model_version and one score."""
    from fastapi.testclient import TestClient

    from sentinelflow.api.app import app
    from sentinelflow.api.state import state
    from sentinelflow.auth.dependencies import require_analyst

    model_dir = _model_dir(tmp_path)
    api_scorer = build_scorer(model_dir)
    api_scorer.service.load()
    monkeypatch.setattr(state, "scorer", api_scorer)
    detector = _detector(model_dir)

    app.dependency_overrides[require_analyst] = lambda: None
    try:
        body = TestClient(app).post("/api/v1/risk/score", json=KAFKA_TX).json()
    finally:
        app.dependency_overrides.clear()
    scored = detector._scorer.score(KAFKA_TX, record=False)

    assert scored is not None
    assert body["model_version"] == scored.result.model_version == MODEL_VERSION
    assert body["score"] == pytest.approx(scored.result.score)


def test_model_alert_carries_contract_evidence(tmp_path):
    detector = _detector(_model_dir(tmp_path, threshold=1e-6))
    alert = detector._check_ml_model(KAFKA_TX)

    assert alert is not None
    assert alert.fraud_type is FraudType.ML_MODEL
    assert alert.detector_version == MODEL_VERSION
    assert alert.severity in {"high", "critical"}
    details = alert.evidence["details"]
    assert alert.evidence["detector_type"] == "ml_model"
    assert details["model_version"] == MODEL_VERSION
    assert details["contribution_unit"] == "log_odds"
    assert len(details["top_features"]) == 5
    assert details["history_cold_start"] is True
    assert [e.detector_version for e in alert.evidence_records] == [MODEL_VERSION]
    assert detector.stats.ml_model_hits == 1
    assert detector._scorer.history.recorded == 1


def test_duplicate_message_raises_no_second_alert(tmp_path):
    detector = _detector(_model_dir(tmp_path, threshold=1e-6))
    assert detector._check_ml_model(KAFKA_TX) is not None
    assert detector._check_ml_model(KAFKA_TX) is None
    assert detector.stats.ml_model_hits == 1
    assert detector._scorer.history.duplicates == 1


def test_below_threshold_makes_no_alert(tmp_path):
    detector = _detector(_model_dir(tmp_path, threshold=0.999999))
    assert detector._check_ml_model(KAFKA_TX) is None
    assert detector._scorer.history.recorded == 1


def test_without_model_no_score_but_history_is_recorded(tmp_path):
    detector = _detector(tmp_path / "missing")
    assert not detector._scorer.service.is_loaded
    assert detector._check_ml_model(KAFKA_TX) is None
    assert detector._scorer.history.recorded == 1
    assert detector.stats.errors == 0


def test_contract_violation_is_counted_not_raised(tmp_path):
    detector = _detector(_model_dir(tmp_path))
    assert detector._check_ml_model({**KAFKA_TX, "currency": ""}) is None
    assert detector.stats.errors == 1
    assert detector._scorer.history.recorded == 0


def test_published_alert_persists_the_evidence(tmp_path):
    detector = _detector(_model_dir(tmp_path, threshold=1e-6))
    alert = detector._check_ml_model(KAFKA_TX)
    written = []

    class _Writer:
        def write(self, alert_create):
            written.append(alert_create)
            return None

    detector._alert_writer = _Writer()
    detector._publish_alert(alert)

    assert len(written) == 1
    stored = written[0]
    assert stored.fraud_type == "ml_model"
    assert stored.related_transactions == [KAFKA_TX["transaction_id"]]
    assert stored.evidence[0].details["model_version"] == MODEL_VERSION


def test_model_failure_is_counted_not_raised(tmp_path, monkeypatch):
    """A model error must not escape and drop the other engines' pending alerts."""
    detector = _detector(_model_dir(tmp_path))

    def _boom(*args, **kwargs):
        raise RuntimeError("booster crashed")

    monkeypatch.setattr(detector._scorer, "score", _boom)
    assert detector._check_ml_model(KAFKA_TX) is None
    assert detector.stats.errors == 1
