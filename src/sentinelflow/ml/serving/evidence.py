# =============================================================================
# SentinelFlow - Fraud model alert evidence (ML-06)
# =============================================================================
"""
The ``ml_model`` alert built the same way by the API ingestion route and the
Kafka detector (contract §4.4, §4.5).
"""

from __future__ import annotations

from sentinelflow.contracts import Evidence, Severity
from sentinelflow.contracts.enums import DetectorType

from .scorer import ScoredTransaction

# Contract §4.4: model alerts at or above this score are critical, others high.
CRITICAL_SCORE = 0.85


def model_severity(score: float, critical_score: float = CRITICAL_SCORE) -> Severity:
    return Severity.CRITICAL if score >= critical_score else Severity.HIGH


def model_evidence(scored: ScoredTransaction) -> Evidence:
    """ML alert evidence (contract §4.5), frozen with the model of this moment."""
    result = scored.result
    return Evidence(
        detector_type=DetectorType.ML_MODEL,
        detector_version=result.model_version,
        confidence=result.score,
        contribution=1.0,
        summary=f"Model skoru {result.score:.2f} ≥ eşik {result.threshold:.2f}",
        details={
            "model_version": result.model_version,
            "feature_set_version": result.feature_set_version,
            "score": result.score,
            "threshold": result.threshold,
            "contribution_unit": result.contribution_unit,
            "base_value": result.base_value,
            "top_features": [
                {"feature": f.feature, "value": f.value, "contribution": f.contribution}
                for f in result.top_features
            ],
            "history_cold_start": scored.history_cold_start,
        },
        related_transactions=[scored.transaction_id],
    )
