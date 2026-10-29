"""Fraud model serving (ML-06): artifact loader and the shared model service."""

from sentinelflow.ml.serving.artifact import (
    ArtifactError,
    ArtifactNotFoundError,
    ModelArtifact,
    ModelMetadata,
    load_artifact,
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
    "load_artifact",
]
