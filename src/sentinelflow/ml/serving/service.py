# =============================================================================
# SentinelFlow - Fraud Model Service (ML-06)
# =============================================================================
"""
One fraud model, shared by the API, the detector and the risk engine
(ADR 0003, ``docs/contracts/sprint4-ml-api.md`` §4).

``FraudModelService`` loads the configured artifact once. When the artifact is
missing or invalid the service stays up in ``not_loaded`` / ``invalid`` state and
:meth:`FraudModelService.score` raises :class:`ModelNotLoadedError` — it never
scores with an untrained or fallback model.

Scores are the model's probability; contributions are LightGBM ``pred_contrib``
values in log-odds, so ``base_value + sum(all contributions) == logit(score)``.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import numpy as np
from loguru import logger

from sentinelflow.ml.serving.artifact import (
    ArtifactError,
    ArtifactNotFoundError,
    ModelArtifact,
    ModelMetadata,
    load_artifact,
)

CONTRIBUTION_UNIT = "log_odds"
DEFAULT_TOP_N = 5


class ModelStatus(str, Enum):
    LOADED = "loaded"
    NOT_LOADED = "not_loaded"
    INVALID = "invalid"


class ModelNotLoadedError(RuntimeError):
    """Raised by ``score`` when no valid model is loaded (API maps it to 503)."""

    def __init__(self, status: ModelStatus, error: str | None) -> None:
        super().__init__(error or "No valid fraud model is loaded")
        self.status = status
        self.error = error


@dataclass(frozen=True)
class FeatureContribution:
    feature: str
    value: float
    contribution: float


@dataclass(frozen=True)
class ScoreResult:
    model_version: str
    feature_set_version: str
    score: float
    threshold: float
    is_fraud: bool
    base_value: float
    top_features: tuple[FeatureContribution, ...]
    contribution_unit: str = CONTRIBUTION_UNIT


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


class FraudModelService:
    """Loads one artifact and scores fs-N feature vectors with it."""

    def __init__(
        self,
        model_dir: str | Path,
        *,
        feature_set_version: str,
        feature_names: Sequence[str],
        top_n: int = DEFAULT_TOP_N,
    ) -> None:
        if top_n < 1:
            raise ValueError("top_n must be >= 1")
        self.model_dir = Path(model_dir)
        self.feature_set_version = feature_set_version
        self.feature_names: tuple[str, ...] = tuple(feature_names)
        self.top_n = top_n
        self._lock = threading.Lock()
        self._artifact: ModelArtifact | None = None
        self._status = ModelStatus.NOT_LOADED
        self._error: str | None = "model not loaded yet"
        self._loaded_at: datetime | None = None

    # ------------------------------------------------------------------ loading

    def load(self) -> ModelStatus:
        """(Re)load the artifact. A failed load clears any previously loaded model."""
        with self._lock:
            try:
                artifact = load_artifact(
                    self.model_dir,
                    feature_set_version=self.feature_set_version,
                    feature_names=self.feature_names,
                )
            except ArtifactNotFoundError as exc:
                self._set_failed(ModelStatus.NOT_LOADED, str(exc))
            except ArtifactError as exc:
                self._set_failed(ModelStatus.INVALID, str(exc))
            else:
                self._artifact = artifact
                self._status = ModelStatus.LOADED
                self._error = None
                self._loaded_at = datetime.now(timezone.utc)
                logger.info(
                    "Fraud model {} loaded from {} (feature set {})",
                    artifact.metadata.model_version,
                    self.model_dir,
                    artifact.metadata.feature_set_version,
                )
            return self._status

    def _set_failed(self, status: ModelStatus, error: str) -> None:
        self._artifact = None
        self._status = status
        self._error = error
        self._loaded_at = None
        logger.error("Fraud model not loaded ({}): {}", status.value, error)

    # ------------------------------------------------------------------ status

    @property
    def status(self) -> ModelStatus:
        return self._status

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def is_loaded(self) -> bool:
        return self._status is ModelStatus.LOADED

    @property
    def metadata(self) -> ModelMetadata | None:
        artifact = self._artifact
        return artifact.metadata if artifact else None

    @property
    def loaded_at(self) -> datetime | None:
        return self._loaded_at

    # ------------------------------------------------------------------ scoring

    def score(self, features: Sequence[float] | np.ndarray) -> ScoreResult:
        """Score one feature vector in ``feature_names`` order.

        Raises:
            ModelNotLoadedError: no valid model is loaded.
            ValueError: the vector has the wrong length.
        """
        artifact = self._artifact
        if artifact is None:
            raise ModelNotLoadedError(self._status, self._error)

        vector = np.asarray(features, dtype=np.float64).reshape(-1)
        if vector.shape[0] != len(self.feature_names):
            raise ValueError(f"expected {len(self.feature_names)} features, got {vector.shape[0]}")

        # One pass: per-feature contributions plus the bias term (last column).
        contribs = np.asarray(
            artifact.booster.predict(vector.reshape(1, -1), pred_contrib=True)
        ).reshape(-1)
        feature_contribs = contribs[:-1]
        base_value = float(contribs[-1])
        score = _sigmoid(float(contribs.sum()))
        threshold = artifact.metadata.threshold

        ranked = sorted(
            range(len(self.feature_names)),
            key=lambda i: (-abs(float(feature_contribs[i])), self.feature_names[i]),
        )[: self.top_n]
        top = tuple(
            FeatureContribution(
                feature=self.feature_names[i],
                value=float(vector[i]),
                contribution=float(feature_contribs[i]),
            )
            for i in ranked
        )
        return ScoreResult(
            model_version=artifact.metadata.model_version,
            feature_set_version=artifact.metadata.feature_set_version,
            score=score,
            threshold=threshold,
            is_fraud=score >= threshold,
            base_value=base_value,
            top_features=top,
        )
