# =============================================================================
# SentinelFlow - ML Pipeline CI helpers (ML-07)
# =============================================================================
"""
The quality gate passes the committed ML-04 report and fails a below-target one;
the synthetic dataset has the ML-02 layout; the benchmark runs the serving path.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from sentinelflow.ml import ci
from sentinelflow.ml.training.data import CANONICAL_COLUMNS

REPO_DIR = Path(__file__).resolve().parents[1]
COMMITTED_REPORTS = REPO_DIR / "reports" / "ml04"


@pytest.fixture()
def report_copy(tmp_path: Path) -> Path:
    target = tmp_path / "reports"
    target.mkdir()
    for name in (ci.SELECTION_FILE, ci.TEST_REPORT_FILE):
        shutil.copy(COMMITTED_REPORTS / name, target / name)
    return target


def _edit_report(report_dir: Path, edit) -> None:
    path = report_dir / ci.TEST_REPORT_FILE
    report = json.loads(path.read_text(encoding="utf-8"))
    edit(report)
    path.write_text(json.dumps(report), encoding="utf-8")


def test_committed_model_passes_the_gate(tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert ci.main(["gate", "--report-dir", str(COMMITTED_REPORTS)]) == 0
    text = summary.read_text(encoding="utf-8")
    assert "Quality gate — passed" in text
    assert "❌" not in text


def test_below_target_model_fails_the_gate(report_copy, tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    def below(report):
        report["test"]["lightgbm"]["pr_auc"] = 0.30
        report["publishable"] = True  # a stale flag must not hide the miss

    _edit_report(report_copy, below)
    assert ci.main(["gate", "--report-dir", str(report_copy)]) == 1
    assert "Quality gate — FAILED" in summary.read_text(encoding="utf-8")
    assert "PR-AUC (test)" in capsys.readouterr().err


def test_smoke_mode_reports_but_never_fails(report_copy, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    _edit_report(report_copy, lambda r: r["test"]["lightgbm"].update(pr_auc=0.1))
    assert ci.main(["gate", "--report-dir", str(report_copy), "--smoke"]) == 0


def test_report_for_another_model_is_rejected(report_copy):
    _edit_report(report_copy, lambda r: r.update(model_sha256="0" * 64))
    with pytest.raises(ci.GateError, match="frozen in selection"):
        ci.gate(report_copy)
    assert ci.main(["gate", "--report-dir", str(report_copy)]) == 1


def test_missing_report_fails(tmp_path):
    assert ci.main(["gate", "--report-dir", str(tmp_path)]) == 1


def test_selection_without_model_sha256_is_rejected(report_copy):
    """None == None must not pass as 'the report is for the frozen model'."""
    path = report_copy / ci.SELECTION_FILE
    selection = json.loads(path.read_text(encoding="utf-8"))
    selection["files"]["model.txt"].pop("sha256")
    path.write_text(json.dumps(selection), encoding="utf-8")
    _edit_report(report_copy, lambda r: r.pop("model_sha256"))
    with pytest.raises(ci.GateError, match="no model.txt sha256"):
        ci.gate(report_copy)


@pytest.mark.parametrize("key", ["test", "structure", "latency"])
def test_report_with_missing_keys_is_a_gate_error(report_copy, capsys, key):
    _edit_report(report_copy, lambda r: r.pop(key))
    with pytest.raises(ci.GateError, match="locked-test report is missing"):
        ci.gate(report_copy)
    assert ci.main(["gate", "--report-dir", str(report_copy)]) == 1
    assert "locked-test report is missing" in capsys.readouterr().err


def test_gate_markdown_reports_missing_keys():
    with pytest.raises(ci.GateError, match="locked-test report is missing"):
        ci.gate_markdown("t", [], {"dataset_id": "x"})


def test_synthetic_dataset_has_the_ml02_layout(tmp_path):
    manifest = ci.write_synthetic(tmp_path / "ds", "fast")
    frame = pd.read_parquet(tmp_path / "ds" / "transactions.parquet")
    assert set(CANONICAL_COLUMNS) <= set(frame.columns)
    assert {"is_laundering", "laundering_type", "split"} <= set(frame.columns)
    assert frame["timestamp"].is_monotonic_increasing
    assert str(frame["timestamp"].dt.tz) == "UTC"
    assert frame["transaction_id"].is_unique
    assert manifest["rows"] == len(frame)
    assert 0 < manifest["positives"] < len(frame)
    shares = frame["split"].value_counts(normalize=True)
    assert shares["train"] == pytest.approx(0.70, abs=0.01)
    # Deterministic for a seed: the CI run is reproducible.
    assert ci.synthetic_dataset(500).equals(ci.synthetic_dataset(500))


def test_benchmark_runs_the_serving_path(tmp_path):
    pytest.importorskip("lightgbm")
    from ml_artifacts import MODEL_VERSION, write_artifact

    ci.write_synthetic(tmp_path / "ds", "fast")
    model_dir = write_artifact(tmp_path / "model")
    result = ci.benchmark(tmp_path / "ds", model_dir, limit=300)
    assert result["model_version"] == MODEL_VERSION
    assert result["n"] > 0 and result["p95_ms"] >= result["p50_ms"] > 0
    assert "Serving latency" in ci.benchmark_markdown(result)


def test_benchmark_without_model_fails(tmp_path):
    ci.write_synthetic(tmp_path / "ds", "fast")
    with pytest.raises(ci.GateError, match="model not loaded"):
        ci.benchmark(tmp_path / "ds", tmp_path / "missing")
