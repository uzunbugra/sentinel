# =============================================================================
# SentinelFlow - Fraud model loader and service tests (ML-06)
# =============================================================================
"""
Contract: docs/contracts/sprint4-ml-api.md §3 (artifact) and §4.2 (score fields).
Uses real LightGBM artifacts built by ``ml_artifacts``.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest
from ml_artifacts import (
    FS1_FEATURE_NAMES,
    FS1_VERSION,
    MODEL_VERSION,
    metadata_for,
    train_booster,
    training_data,
    write_artifact,
)

from sentinelflow.config.settings import ModelServingSettings
from sentinelflow.ml.serving import (
    CONTRIBUTION_UNIT,
    ArtifactError,
    ArtifactNotFoundError,
    FraudModelService,
    ModelNotLoadedError,
    ModelStatus,
    load_artifact,
)

pytest.importorskip("lightgbm")


@pytest.fixture(scope="module")
def booster():
    return train_booster()


@pytest.fixture()
def artifact_dir(tmp_path: Path, booster) -> Path:
    return write_artifact(tmp_path / "model", booster=booster)


def make_service(path: Path, **kwargs) -> FraudModelService:
    return FraudModelService(
        path, feature_set_version=FS1_VERSION, feature_names=FS1_FEATURE_NAMES, **kwargs
    )


def logit(p: float) -> float:
    return math.log(p / (1 - p))


# =============================================================================
# Loader
# =============================================================================


def test_load_valid_artifact(artifact_dir: Path) -> None:
    artifact = load_artifact(
        artifact_dir, feature_set_version=FS1_VERSION, feature_names=FS1_FEATURE_NAMES
    )
    assert artifact.metadata.model_version == MODEL_VERSION
    assert artifact.metadata.feature_names == FS1_FEATURE_NAMES
    assert artifact.metadata.threshold == 0.5


def test_missing_directory_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(ArtifactNotFoundError):
        load_artifact(tmp_path / "nope", feature_set_version=FS1_VERSION, feature_names=())


@pytest.mark.parametrize("name", ["model.txt", "metadata.json", "SHA256SUMS"])
def test_missing_file_is_invalid(artifact_dir: Path, name: str) -> None:
    (artifact_dir / name).unlink()
    with pytest.raises(ArtifactError, match=name):
        load_artifact(
            artifact_dir, feature_set_version=FS1_VERSION, feature_names=FS1_FEATURE_NAMES
        )


def test_tampered_model_fails_checksum(artifact_dir: Path) -> None:
    with (artifact_dir / "model.txt").open("a", encoding="utf-8") as fh:
        fh.write("\n")
    with pytest.raises(ArtifactError, match="checksum mismatch for model.txt"):
        load_artifact(
            artifact_dir, feature_set_version=FS1_VERSION, feature_names=FS1_FEATURE_NAMES
        )


def test_checksum_file_must_list_both_files(tmp_path: Path, booster) -> None:
    text = booster.model_to_string()
    path = write_artifact(
        tmp_path / "m", model_text=text, checksums={"model.txt": metadata_for(text)["model_sha256"]}
    )
    with pytest.raises(ArtifactError, match="no entry for metadata.json"):
        load_artifact(path, feature_set_version=FS1_VERSION, feature_names=FS1_FEATURE_NAMES)


def test_metadata_hash_must_match_model(tmp_path: Path, booster) -> None:
    text = booster.model_to_string()
    path = write_artifact(
        tmp_path / "m", model_text=text, metadata=metadata_for(text, model_sha256="0" * 64)
    )
    with pytest.raises(ArtifactError, match="model_sha256"):
        load_artifact(path, feature_set_version=FS1_VERSION, feature_names=FS1_FEATURE_NAMES)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"schema_version": 2}, "schema_version"),
        ({"model_family": "xgboost"}, "model_family"),
        ({"objective": "regression"}, "objective"),
        ({"calibration": {"method": "isotonic"}}, "calibrated"),
        ({"threshold": 0}, "threshold"),
        ({"threshold": 1.5}, "threshold"),
        ({"threshold": True}, "threshold"),
        ({"model_version": ""}, "model_version"),
        ({"categorical_features": ["not_a_feature"]}, "categorical_features"),
    ],
)
def test_bad_metadata_is_invalid(tmp_path: Path, booster, overrides, message) -> None:
    text = booster.model_to_string()
    path = write_artifact(tmp_path / "m", model_text=text, metadata=metadata_for(text, **overrides))
    with pytest.raises(ArtifactError, match=message):
        load_artifact(path, feature_set_version=FS1_VERSION, feature_names=FS1_FEATURE_NAMES)


def test_missing_required_metadata_field(tmp_path: Path, booster) -> None:
    text = booster.model_to_string()
    metadata = metadata_for(text)
    del metadata["dataset_id"]
    path = write_artifact(tmp_path / "m", model_text=text, metadata=metadata)
    with pytest.raises(ArtifactError, match="dataset_id"):
        load_artifact(path, feature_set_version=FS1_VERSION, feature_names=FS1_FEATURE_NAMES)


def test_feature_set_version_mismatch(artifact_dir: Path) -> None:
    with pytest.raises(ArtifactError, match="feature_set_version"):
        load_artifact(artifact_dir, feature_set_version="fs-2", feature_names=FS1_FEATURE_NAMES)


def test_feature_order_mismatch(artifact_dir: Path) -> None:
    swapped = (FS1_FEATURE_NAMES[1], FS1_FEATURE_NAMES[0], *FS1_FEATURE_NAMES[2:])
    with pytest.raises(ArtifactError, match="order"):
        load_artifact(artifact_dir, feature_set_version=FS1_VERSION, feature_names=swapped)


def test_model_feature_names_must_match_metadata(tmp_path: Path) -> None:
    renamed = tuple(f"f{i}" for i in range(len(FS1_FEATURE_NAMES)))
    path = write_artifact(tmp_path / "m", booster=train_booster(renamed))
    with pytest.raises(ArtifactError, match="model feature names"):
        load_artifact(path, feature_set_version=FS1_VERSION, feature_names=FS1_FEATURE_NAMES)


def test_model_objective_must_be_binary(tmp_path: Path) -> None:
    path = write_artifact(tmp_path / "m", booster=train_booster(objective="regression"))
    with pytest.raises(ArtifactError, match="model objective"):
        load_artifact(path, feature_set_version=FS1_VERSION, feature_names=FS1_FEATURE_NAMES)


def test_garbage_model_text_is_invalid(tmp_path: Path) -> None:
    path = write_artifact(tmp_path / "m", model_text="not a model")
    with pytest.raises(ArtifactError, match="LightGBM"):
        load_artifact(path, feature_set_version=FS1_VERSION, feature_names=FS1_FEATURE_NAMES)


def test_invalid_json_metadata(artifact_dir: Path) -> None:
    (artifact_dir / "metadata.json").write_text("{", encoding="utf-8")
    model_sha = hashlib.sha256((artifact_dir / "model.txt").read_bytes()).hexdigest()
    (artifact_dir / "SHA256SUMS").write_text(
        f"{model_sha}  model.txt\n{hashlib.sha256(b'{').hexdigest()}  metadata.json\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(ArtifactError, match="not valid JSON"):
        load_artifact(
            artifact_dir, feature_set_version=FS1_VERSION, feature_names=FS1_FEATURE_NAMES
        )


# =============================================================================
# Service state
# =============================================================================


def test_service_starts_not_loaded(artifact_dir: Path) -> None:
    service = make_service(artifact_dir)
    assert service.status is ModelStatus.NOT_LOADED
    with pytest.raises(ModelNotLoadedError):
        service.score(np.zeros(len(FS1_FEATURE_NAMES)))


def test_missing_model_keeps_service_up(tmp_path: Path) -> None:
    service = make_service(tmp_path / "absent")
    assert service.load() is ModelStatus.NOT_LOADED
    assert "not found" in (service.error or "")
    assert service.metadata is None
    with pytest.raises(ModelNotLoadedError) as exc:
        service.score(np.zeros(len(FS1_FEATURE_NAMES)))
    assert exc.value.status is ModelStatus.NOT_LOADED


def test_invalid_model_reports_reason(artifact_dir: Path) -> None:
    (artifact_dir / "model.txt").write_text("tampered", encoding="utf-8")
    service = make_service(artifact_dir)
    assert service.load() is ModelStatus.INVALID
    assert "checksum mismatch" in (service.error or "")


def test_failed_reload_drops_previous_model(artifact_dir: Path) -> None:
    service = make_service(artifact_dir)
    assert service.load() is ModelStatus.LOADED
    (artifact_dir / "model.txt").write_text("tampered", encoding="utf-8")
    assert service.load() is ModelStatus.INVALID
    assert not service.is_loaded
    with pytest.raises(ModelNotLoadedError):
        service.score(np.zeros(len(FS1_FEATURE_NAMES)))


def test_loaded_service_exposes_metadata(artifact_dir: Path) -> None:
    service = make_service(artifact_dir)
    assert service.load() is ModelStatus.LOADED
    assert service.error is None
    assert service.metadata is not None
    assert service.metadata.model_version == MODEL_VERSION
    assert service.loaded_at is not None


# =============================================================================
# Scoring
# =============================================================================


@pytest.fixture()
def service(artifact_dir: Path) -> FraudModelService:
    svc = make_service(artifact_dir)
    assert svc.load() is ModelStatus.LOADED
    return svc


def test_score_matches_lightgbm_probability(service: FraudModelService, booster) -> None:
    x, _ = training_data()
    for row in x[:25]:
        result = service.score(row)
        expected = float(booster.predict(row.reshape(1, -1))[0])
        assert result.score == pytest.approx(expected, abs=1e-12)
        assert 0.0 <= result.score <= 1.0


def test_contributions_sum_to_logit(service: FraudModelService) -> None:
    # The default top 5 is only part of the sum; a top_n of all features returns every term.
    full = make_service(service.model_dir, top_n=len(FS1_FEATURE_NAMES))
    full.load()
    x, _ = training_data()
    for row in x[:25]:
        result = full.score(row)
        total = result.base_value + sum(f.contribution for f in result.top_features)
        assert total == pytest.approx(logit(result.score), abs=1e-9)
        assert result.contribution_unit == CONTRIBUTION_UNIT == "log_odds"


def test_top_features_are_ranked_by_absolute_contribution(service: FraudModelService) -> None:
    x, y = training_data()
    row = x[int(np.argmax(y))]
    result = service.score(row)
    assert len(result.top_features) == 5
    magnitudes = [abs(f.contribution) for f in result.top_features]
    assert magnitudes == sorted(magnitudes, reverse=True)
    for f in result.top_features:
        assert f.value == pytest.approx(row[FS1_FEATURE_NAMES.index(f.feature)])


def test_ties_break_by_feature_name(service: FraudModelService) -> None:
    # Features the model never splits on contribute exactly 0; they must come out
    # in alphabetical order after the non-zero ones.
    full = make_service(service.model_dir, top_n=len(FS1_FEATURE_NAMES))
    full.load()
    result = full.score(np.zeros(len(FS1_FEATURE_NAMES)))
    zeros = [f.feature for f in result.top_features if f.contribution == 0.0]
    assert zeros == sorted(zeros)


def test_is_fraud_compares_with_threshold(tmp_path: Path, booster) -> None:
    text = booster.model_to_string()
    x, _ = training_data()
    probe = make_service(write_artifact(tmp_path / "probe", booster=booster))
    probe.load()
    score = probe.score(x[0]).score

    at = make_service(
        write_artifact(
            tmp_path / "at", model_text=text, metadata=metadata_for(text, threshold=score)
        )
    )
    at.load()
    assert at.score(x[0]).is_fraud is True  # score >= threshold

    above = min(score + 1e-6, 0.999999)
    over = make_service(
        write_artifact(
            tmp_path / "over", model_text=text, metadata=metadata_for(text, threshold=above)
        )
    )
    over.load()
    assert over.score(x[0]).is_fraud is False


def test_same_vector_same_score_across_instances(artifact_dir: Path) -> None:
    # API, detector and risk engine each build their own service from the same artifact.
    services = [make_service(artifact_dir) for _ in range(3)]
    for svc in services:
        svc.load()
    x, _ = training_data()
    results = [svc.score(x[3]) for svc in services]
    assert {r.model_version for r in results} == {MODEL_VERSION}
    assert {r.score for r in results} == {results[0].score}
    assert {r.top_features for r in results} == {results[0].top_features}


def test_wrong_vector_length_is_rejected(service: FraudModelService) -> None:
    with pytest.raises(ValueError, match="expected 15 features"):
        service.score(np.zeros(14))


def test_top_n_must_be_positive(artifact_dir: Path) -> None:
    with pytest.raises(ValueError):
        make_service(artifact_dir, top_n=0)


# =============================================================================
# Settings
# =============================================================================


def test_model_dir_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTINELFLOW_MODEL_DIR", raising=False)
    assert ModelServingSettings().dir == "models/fraud/current"
    monkeypatch.setenv("SENTINELFLOW_MODEL_DIR", "/srv/models/fraud-lgbm-1")
    assert ModelServingSettings().dir == "/srv/models/fraud-lgbm-1"


def test_metadata_example_matches_contract_shape(tmp_path: Path, booster) -> None:
    # The written metadata round-trips through JSON with every required field.
    path = write_artifact(tmp_path / "m", booster=booster)
    raw = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    from sentinelflow.ml.serving.artifact import REQUIRED_METADATA_FIELDS

    assert set(REQUIRED_METADATA_FIELDS) <= set(raw)
