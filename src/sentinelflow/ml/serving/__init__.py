"""Fraud model serving (ML-06): artifact loader, model service, scorer and alert evidence."""

from sentinelflow.ml.serving.artifact import (
    ArtifactError,
    ArtifactNotFoundError,
    ModelArtifact,
    ModelMetadata,
    load_artifact,
)
from sentinelflow.ml.serving.evidence import CRITICAL_SCORE, model_evidence, model_severity
from sentinelflow.ml.serving.scorer import (
    ScoredTransaction,
    TransactionScorer,
    build_scorer,
    canonical_transaction,
)
from sentinelflow.ml.serving.service import (
    CONTRIBUTION_UNIT,
    FeatureContribution,
    FraudModelService,
    ModelNotLoadedError,
    ModelStatus,
    ScoreResult,
)

__all__ = [
    "CONTRIBUTION_UNIT",
    "CRITICAL_SCORE",
    "ArtifactError",
    "ArtifactNotFoundError",
    "FeatureContribution",
    "FraudModelService",
    "ModelArtifact",
    "ModelMetadata",
    "ModelNotLoadedError",
    "ModelStatus",
    "ScoreResult",
    "ScoredTransaction",
    "TransactionScorer",
    "build_scorer",
    "canonical_transaction",
    "load_artifact",
    "model_evidence",
    "model_severity",
]
