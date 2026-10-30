"""Fraud model serving (ML-06): artifact loader, model service and API scorer."""

from sentinelflow.ml.serving.artifact import (
    ArtifactError,
    ArtifactNotFoundError,
    ModelArtifact,
    ModelMetadata,
    load_artifact,
)
from sentinelflow.ml.serving.scorer import (
    ScoredTransaction,
    TransactionScorer,
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
    "canonical_transaction",
    "load_artifact",
]
