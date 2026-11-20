# =============================================================================
# SentinelFlow - Fraud Model Artifact Loader (ML-06)
# =============================================================================
"""
Loads and validates a fraud model artifact (``docs/contracts/sprint4-ml-api.md`` §3).

An artifact is a directory::

    model.txt        LightGBM text model (no pickle)
    metadata.json    contract §3 metadata
    model_card.md    human-readable card (not read here)
    SHA256SUMS       "<sha256>  <file>" lines for model.txt and metadata.json

Every check that fails raises :class:`ArtifactError`; the loader never falls back to
another model. Packaging the artifact is ML-05's job; this module only reads it.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MODEL_FILE = "model.txt"
METADATA_FILE = "metadata.json"
CHECKSUM_FILE = "SHA256SUMS"
CHECKSUMMED_FILES: tuple[str, ...] = (MODEL_FILE, METADATA_FILE)

SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})
SUPPORTED_MODEL_FAMILIES: frozenset[str] = frozenset({"lightgbm"})
SUPPORTED_OBJECTIVE = "binary"

REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "schema_version",
    "model_version",
    "model_family",
    "objective",
    "feature_set_version",
    "feature_names",
    "threshold",
    "dataset_id",
    "metrics",
    "trained_at",
    "git_sha",
    "library_versions",
    "model_sha256",
)


class ArtifactNotFoundError(FileNotFoundError):
    """The artifact directory does not exist (no model deployed)."""


class ArtifactError(ValueError):
    """The artifact exists but is corrupt, incomplete or incompatible."""


@dataclass(frozen=True)
class ModelMetadata:
    """The validated subset of ``metadata.json`` the service relies on."""

    model_version: str
    model_family: str
    feature_set_version: str
    feature_names: tuple[str, ...]
    categorical_features: tuple[str, ...]
    threshold: float
    dataset_id: str
    trained_at: str
    git_sha: str
    model_sha256: str
    metrics: Mapping[str, Any]
    library_versions: Mapping[str, str]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class ModelArtifact:
    """A loaded, validated artifact: metadata plus the LightGBM booster."""

    path: Path
    metadata: ModelMetadata
    booster: Any  # lightgbm.Booster


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_checksums(path: Path) -> dict[str, str]:
    sums: dict[str, str] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ArtifactError(f"{CHECKSUM_FILE} line {line_no} is not '<sha256>  <file>'")
        digest, name = parts
        sums[name.lstrip("*")] = digest.lower()
    return sums


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ArtifactError(message)


def _parse_metadata(raw: Mapping[str, Any]) -> ModelMetadata:
    missing = [name for name in REQUIRED_METADATA_FIELDS if name not in raw]
    _require(not missing, f"metadata.json is missing required fields: {missing}")
    _require(
        raw["schema_version"] in SUPPORTED_SCHEMA_VERSIONS,
        f"unsupported metadata schema_version {raw['schema_version']!r}",
    )
    _require(
        raw["model_family"] in SUPPORTED_MODEL_FAMILIES,
        f"unsupported model_family {raw['model_family']!r}",
    )
    _require(
        raw["objective"] == SUPPORTED_OBJECTIVE,
        f"unsupported objective {raw['objective']!r} (expected {SUPPORTED_OBJECTIVE!r})",
    )
    _require(
        raw.get("calibration") is None,
        "calibrated artifacts are not supported by this service version",
    )

    names = raw["feature_names"]
    _require(
        isinstance(names, list) and len(names) > 0 and all(isinstance(n, str) for n in names),
        "feature_names must be a non-empty list of strings",
    )
    _require(len(set(names)) == len(names), "feature_names contains duplicates")
    categorical = raw.get("categorical_features") or []
    _require(
        isinstance(categorical, list) and set(categorical) <= set(names),
        "categorical_features must be a subset of feature_names",
    )

    threshold = raw["threshold"]
    _require(
        isinstance(threshold, (int, float))
        and not isinstance(threshold, bool)
        and math.isfinite(threshold)
        and 0.0 < threshold < 1.0,
        f"threshold must be a number in (0, 1), got {threshold!r}",
    )
    for field in ("model_version", "feature_set_version", "dataset_id", "model_sha256"):
        _require(
            isinstance(raw[field], str) and raw[field].strip() != "",
            f"{field} must be a non-empty string",
        )
    _require(isinstance(raw["metrics"], dict), "metrics must be an object")
    _require(isinstance(raw["library_versions"], dict), "library_versions must be an object")

    return ModelMetadata(
        model_version=raw["model_version"],
        model_family=raw["model_family"],
        feature_set_version=raw["feature_set_version"],
        feature_names=tuple(names),
        categorical_features=tuple(categorical),
        threshold=float(threshold),
        dataset_id=raw["dataset_id"],
        trained_at=str(raw["trained_at"]),
        git_sha=str(raw["git_sha"]),
        model_sha256=raw["model_sha256"].lower(),
        metrics=dict(raw["metrics"]),
        library_versions={str(k): str(v) for k, v in raw["library_versions"].items()},
        raw=dict(raw),
    )


def _load_booster(model_text: str) -> Any:
    import lightgbm as lgb

    try:
        return lgb.Booster(model_str=model_text)
    except Exception as exc:  # LightGBM raises its own error types
        raise ArtifactError(f"{MODEL_FILE} is not a loadable LightGBM model: {exc}") from exc


def _booster_objective(booster: Any) -> str:
    objective = str(booster.dump_model(num_iteration=0).get("objective", ""))
    return objective.split()[0] if objective else ""


def load_artifact(
    path: str | Path,
    *,
    feature_set_version: str,
    feature_names: Sequence[str],
) -> ModelArtifact:
    """Load the artifact at ``path`` and check it against the service's feature set.

    Raises:
        ArtifactNotFoundError: ``path`` does not exist.
        ArtifactError: anything else is wrong (files, checksums, metadata, model,
            feature set or feature order mismatch).
    """
    root = Path(path)
    if not root.exists():
        raise ArtifactNotFoundError(f"model directory not found: {root}")
    _require(root.is_dir(), f"model path is not a directory: {root}")

    for name in (*CHECKSUMMED_FILES, CHECKSUM_FILE):
        _require((root / name).is_file(), f"{name} is missing in {root}")

    # Hash the exact bytes that get parsed, so nothing can change in between.
    model_bytes = (root / MODEL_FILE).read_bytes()
    metadata_bytes = (root / METADATA_FILE).read_bytes()
    actual = {MODEL_FILE: _sha256(model_bytes), METADATA_FILE: _sha256(metadata_bytes)}

    sums = _read_checksums(root / CHECKSUM_FILE)
    for name in CHECKSUMMED_FILES:
        _require(name in sums, f"{CHECKSUM_FILE} has no entry for {name}")
        _require(sums[name] == actual[name], f"checksum mismatch for {name}")

    try:
        raw = json.loads(metadata_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"{METADATA_FILE} is not valid JSON: {exc}") from exc
    _require(isinstance(raw, dict), f"{METADATA_FILE} must be a JSON object")
    metadata = _parse_metadata(raw)

    _require(
        metadata.model_sha256 == actual[MODEL_FILE],
        "metadata model_sha256 does not match model.txt",
    )
    _require(
        metadata.feature_set_version == feature_set_version,
        f"feature_set_version {metadata.feature_set_version!r} does not match the "
        f"service's {feature_set_version!r}",
    )
    _require(
        metadata.feature_names == tuple(feature_names),
        "feature_names differ from the service's feature set (content or order)",
    )

    booster = _load_booster(model_bytes.decode("utf-8"))
    _require(
        tuple(booster.feature_name()) == metadata.feature_names,
        "model feature names differ from metadata feature_names",
    )
    _require(
        _booster_objective(booster) == SUPPORTED_OBJECTIVE,
        f"model objective {_booster_objective(booster)!r} is not {SUPPORTED_OBJECTIVE!r}",
    )
    return ModelArtifact(path=root, metadata=metadata, booster=booster)
