# =============================================================================
# SentinelFlow - ML-05 artifact packaging tests
# =============================================================================
"""
Contract §3 / ADR 0003 §9. Builds the artifact from a synthetic ML-04 run and
checks layout, checksums, metadata, size and save/load prediction equality. The
round trip through the service loader (ML-06 ``load_artifact``) runs once that
loader is on the branch; until then it is skipped.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pytest

lgb = pytest.importorskip("lightgbm")

from test_ml_training import SMALL_CONFIG, synthetic_dataset  # noqa: E402

from sentinelflow.ml.features import FEATURE_NAMES, FEATURE_SET_VERSION  # noqa: E402
from sentinelflow.ml.training import artifact as tartifact  # noqa: E402
from sentinelflow.ml.training import data as tdata  # noqa: E402
from sentinelflow.ml.training import pipeline  # noqa: E402
from sentinelflow.ml.training.__main__ import main as cli_main  # noqa: E402

REPO_DIR = Path(__file__).resolve().parents[1]
FIXTURE_METADATA = REPO_DIR / "tests" / "fixtures" / "ml" / "metadata.example.json"


@pytest.fixture(scope="module")
def ml04_run(tmp_path_factory) -> dict[str, Path]:
    """A complete synthetic ML-04 run: dataset, frozen models, selection and test report."""
    root = tmp_path_factory.mktemp("ml05")
    dataset = root / "samld" / "synthetic-test"
    dataset.mkdir(parents=True)
    synthetic_dataset().to_parquet(dataset / tdata.DATASET_FILE, index=False)
    manifest = {"dataset_id": "synthetic-test", "output": {"content_sha256": "synthetic"}}
    (dataset / tdata.MANIFEST_FILE).write_text(json.dumps(manifest), encoding="utf-8")
    work, reports = root / "work", root / "reports"
    pipeline.run_selection(dataset, work, reports, SMALL_CONFIG, repo_dir=REPO_DIR)
    pipeline.run_test_evaluation(dataset, work, reports, repo_dir=REPO_DIR)
    return {"root": root, "dataset": dataset, "work": work, "reports": reports}


@pytest.fixture()
def built(ml04_run, tmp_path) -> Path:
    return tartifact.build_artifact(
        ml04_run["reports"], ml04_run["work"], tmp_path / "models" / "fraud",
        require_publishable=False,
    )  # fmt: skip


def _test_features(ml04_run):
    return tdata.load_split(ml04_run["dataset"], ["test"]).features


def test_layout_checksums_and_size(built):
    assert sorted(p.name for p in built.iterdir()) == sorted(
        ["model.txt", "metadata.json", "model_card.md", "SHA256SUMS"]
    )
    for line in (built / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split()
        assert hashlib.sha256((built / name).read_bytes()).hexdigest() == digest
    names = {line.split()[1] for line in (built / "SHA256SUMS").read_text().splitlines()}
    assert names == {"model.txt", "metadata.json"}
    assert tartifact.artifact_bytes(built) <= 5 * 1024 * 1024


def test_metadata_matches_contract_and_frozen_selection(built, ml04_run):
    metadata = json.loads((built / "metadata.json").read_text(encoding="utf-8"))
    example = json.loads(FIXTURE_METADATA.read_text(encoding="utf-8"))
    assert set(metadata) == set(example)
    assert set(metadata["metrics"]) == set(example["metrics"])
    selection = json.loads((ml04_run["reports"] / "selection.json").read_text(encoding="utf-8"))
    report = json.loads((ml04_run["reports"] / "test-report.json").read_text(encoding="utf-8"))

    assert re.fullmatch(r"fraud-lgbm-\d{8}-[0-9a-f]{7}", metadata["model_version"])
    assert built.name == metadata["model_version"]
    assert metadata["feature_set_version"] == FEATURE_SET_VERSION
    assert tuple(metadata["feature_names"]) == FEATURE_NAMES
    assert metadata["threshold"] == selection["selected"]["threshold"]
    assert metadata["calibration"] is None and metadata["objective"] == "binary"
    assert metadata["metrics"]["split"] == "test"
    assert metadata["metrics"]["pr_auc"] == report["test"]["lightgbm"]["pr_auc"]
    assert metadata["metrics"]["baseline_pr_auc"] == report["test"]["baseline"]["pr_auc"]
    assert metadata["model_sha256"] == selection["files"]["model.txt"]["sha256"]
    assert metadata["git_sha"] == selection["git_sha"]
    card = (built / "model_card.md").read_text(encoding="utf-8")
    assert metadata["model_version"] in card and "sentetik" in card


def test_saved_model_predicts_like_the_frozen_model(built, ml04_run):
    frozen = lgb.Booster(model_file=str(ml04_run["work"] / "model.txt"))
    saved = lgb.Booster(model_str=(built / "model.txt").read_text(encoding="utf-8"))
    x = _test_features(ml04_run).to_numpy(dtype=np.float64)
    np.testing.assert_array_equal(saved.predict(x), frozen.predict(x))
    assert tuple(saved.feature_name()) == FEATURE_NAMES
    # Contributions are log-odds: base + sum == logit(score) (contract §4.2).
    contrib = saved.predict(x[:20], pred_contrib=True)
    np.testing.assert_allclose(contrib.sum(axis=1), saved.predict(x[:20], raw_score=True))


def test_round_trip_through_the_service_loader(built, ml04_run):
    serving = pytest.importorskip(
        "sentinelflow.ml.serving.artifact", reason="ML-06 loader not on this branch yet"
    )
    loaded = serving.load_artifact(
        built, feature_set_version=FEATURE_SET_VERSION, feature_names=FEATURE_NAMES
    )
    x = _test_features(ml04_run).to_numpy(dtype=np.float64)
    frozen = lgb.Booster(model_file=str(ml04_run["work"] / "model.txt"))
    np.testing.assert_array_equal(loaded.booster.predict(x), frozen.predict(x))
    assert loaded.metadata.model_version == built.name
    assert (
        loaded.metadata.threshold == json.loads((built / "metadata.json").read_text())["threshold"]
    )


def test_unpublishable_result_is_not_packaged(ml04_run, tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    for name in ("selection.json", "test-report.json"):
        (reports / name).write_bytes((ml04_run["reports"] / name).read_bytes())
    report = json.loads((reports / "test-report.json").read_text(encoding="utf-8"))
    report["publishable"] = False
    report["targets"][0]["passed"] = False
    (reports / "test-report.json").write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(tartifact.ArtifactBuildError, match="not published"):
        tartifact.build_artifact(reports, ml04_run["work"], tmp_path / "models")
    assert not (tmp_path / "models").exists()


def test_refuses_a_model_that_differs_from_the_evaluated_one(ml04_run, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    text = (ml04_run["work"] / "model.txt").read_text(encoding="utf-8")
    (work / "model.txt").write_text(text + "\n", encoding="utf-8")
    with pytest.raises(tartifact.ArtifactBuildError, match="frozen selection"):
        tartifact.build_artifact(
            ml04_run["reports"], work, tmp_path / "models", require_publishable=False
        )


def test_existing_artifact_is_not_overwritten(built, ml04_run):
    with pytest.raises(tartifact.ArtifactBuildError, match="already exists"):
        tartifact.build_artifact(
            ml04_run["reports"], ml04_run["work"], built.parent, require_publishable=False
        )


def test_cli_package_refuses_failed_targets_by_default(ml04_run, tmp_path, capsys):
    report = json.loads((ml04_run["reports"] / "test-report.json").read_text(encoding="utf-8"))
    out = tmp_path / "models"
    code = cli_main(
        ["package", "--work-dir", str(ml04_run["work"]), "--report-dir",
         str(ml04_run["reports"]), "--out", str(out)]  # fmt: skip
    )
    if report["publishable"]:
        assert code == 0 and len(list(out.iterdir())) == 1
    else:
        assert code == 1 and "not published" in capsys.readouterr().out
