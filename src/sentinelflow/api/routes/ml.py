# =============================================================================
# SentinelFlow API - ML Routes
# =============================================================================
"""
Active fraud model and feature set (docs/contracts/sprint4-ml-api.md §4.1).

Training is offline (CLI + CI, ADR 0003 §10); the API only serves.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from sentinelflow.api.schemas import (
    ActiveModel,
    FeatureDefinition,
    FeatureSetResponse,
    ModelMetrics,
    ModelStatusResponse,
)
from sentinelflow.api.state import state
from sentinelflow.auth.dependencies import require_viewer
from sentinelflow.contracts import User
from sentinelflow.ml.features import (
    CATEGORICAL_FEATURES,
    FEATURE_DTYPES,
    FEATURE_NAMES,
    FEATURE_SET_VERSION,
)

router = APIRouter(prefix="/ml", tags=["Machine Learning"])


def _metrics(raw: dict[str, Any]) -> ModelMetrics:
    """Keep only the contract keys; anything absent or malformed becomes null."""
    values: dict[str, Any] = {}
    for name in ModelMetrics.model_fields:
        try:
            ModelMetrics(**{name: raw.get(name)})
        except ValidationError:
            continue
        values[name] = raw.get(name)
    return ModelMetrics(**values)


@router.get(
    "/models",
    response_model=ModelStatusResponse,
    summary="Active fraud model",
    description="Always 200. `model` is null when no valid model is loaded; `error` says why.",
)
async def get_model_status(_user: User = Depends(require_viewer)) -> ModelStatusResponse:
    service = state.scorer.service
    meta = service.metadata
    loaded_at = service.loaded_at
    if meta is None or loaded_at is None:
        return ModelStatusResponse(status=service.status.value, model=None, error=service.error)
    return ModelStatusResponse(
        status=service.status.value,
        model=ActiveModel(
            model_version=meta.model_version,
            model_family=meta.model_family,
            feature_set_version=meta.feature_set_version,
            feature_names=list(meta.feature_names),
            threshold=meta.threshold,
            dataset_id=meta.dataset_id,
            trained_at=meta.trained_at,
            loaded_at=loaded_at,
            metrics=_metrics(dict(meta.metrics)),
            model_sha256=meta.model_sha256,
        ),
        error=None,
    )


@router.get(
    "/features",
    response_model=FeatureSetResponse,
    summary="Served feature set",
    description="Feature names in model input order, with dtype and categorical flag.",
)
async def get_features(_user: User = Depends(require_viewer)) -> FeatureSetResponse:
    return FeatureSetResponse(
        feature_set_version=FEATURE_SET_VERSION,
        total_features=len(FEATURE_NAMES),
        features=[
            FeatureDefinition(
                name=name,
                dtype=str(FEATURE_DTYPES[name]),
                categorical=name in CATEGORICAL_FEATURES,
            )
            for name in FEATURE_NAMES
        ],
    )
