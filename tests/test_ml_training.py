# =============================================================================
# SentinelFlow - ML-04 training pipeline tests (synthetic fixture only)
# =============================================================================
"""
ADR 0003 §3, §5–§7. The data is a small deterministic synthetic stream with two
planted typologies; it checks the software (determinism, locked test, sampling,
threshold policy), not model quality. Full SAML-D never runs in CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("lightgbm")

from sentinelflow.ml.features import FEATURE_NAMES, build_features_batch
from sentinelflow.ml.training import data as tdata
from sentinelflow.ml.training import metrics as tmetrics
from sentinelflow.ml.training import models as tmodels
from sentinelflow.ml.training import pipeline
from sentinelflow.ml.training.__main__ import main as cli_main

T0 = pd.Timestamp("2022-10-01T00:00:00", tz="UTC")
SMALL_CONFIG = pipeline.TrainingConfig(
    negative_rate=0.5,
    num_threads=1,
    max_trees=40,
    grid=(
        {"num_leaves": 7, "learning_rate": 0.1, "scale_pos_weight": 1.0, "min_data_in_leaf": 10},
        {"num_leaves": 15, "learning_rate": 0.2, "scale_pos_weight": 2.0, "min_data_in_leaf": 10},
    ),
)


def synthetic_dataset(seed: int = 11, n_normal: int = 6000) -> pd.DataFrame:
    """Normal traffic plus fan-out bursts and near-limit cash deposits (positives)."""
    rng = np.random.default_rng(seed)
    accounts = [f"{1000 + i}" for i in range(300)]
    rows = []

    def add(ts, sender, receiver, amount, ptype, r_country, label, typology):
        rows.append(
            {
                "timestamp": ts,
                "sender_account": sender,
                "receiver_account": receiver,
                "amount": float(round(amount, 2)),
                "payment_currency": "TRY",
                "received_currency": "TRY" if r_country == "TR" else "AED",
                "sender_country": "TR",
                "receiver_country": r_country,
                "payment_type": ptype,
                "is_laundering": label,
                "laundering_type": typology,
            }
        )

    span = 60 * 86400
    for _ in range(n_normal):
        s, r = rng.choice(accounts, 2, replace=False)
        ts = T0 + pd.Timedelta(seconds=int(rng.integers(0, span)))
        ptype = str(rng.choice(["ach", "debit_card", "cheque", "cash_deposit"]))
        add(ts, s, r, rng.lognormal(9, 1), ptype, "TR", 0, "Normal")
    for burst in range(45):
        mule = f"9{burst:03d}"
        start = T0 + pd.Timedelta(seconds=int(rng.integers(0, span - 7200)))
        for k, r in enumerate(rng.choice(accounts, 8, replace=False)):
            add(start + pd.Timedelta(minutes=7 * k), mule, r, rng.uniform(2e4, 6e4),
                "cross_border", "AE", 1, "Fan_Out")  # fmt: skip
    for _ in range(80):
        s, r = rng.choice(accounts, 2, replace=False)
        ts = T0 + pd.Timedelta(seconds=int(rng.integers(0, span)))
        add(ts, s, r, rng.uniform(4.8e5, 4.99e5), "cash_deposit", "TR", 1, "Structuring")

    df = pd.DataFrame(rows).sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    df.insert(0, "transaction_id", [f"SYN-{i:06d}" for i in range(len(df))])
    cut1, cut2 = int(len(df) * 0.70), int(len(df) * 0.85)
    df["split"] = ["train"] * cut1 + ["val"] * (cut2 - cut1) + ["test"] * (len(df) - cut2)
    return df


@pytest.fixture()
def dataset_dir(tmp_path: Path) -> Path:
    target = tmp_path / "samld" / "synthetic-test"
    target.mkdir(parents=True)
    synthetic_dataset().to_parquet(target / tdata.DATASET_FILE, index=False)
    manifest = {"dataset_id": "synthetic-test", "output": {"content_sha256": "synthetic"}}
    (target / tdata.MANIFEST_FILE).write_text(json.dumps(manifest), encoding="utf-8")
    return target


def run_select(dataset_dir: Path, root: Path, config=SMALL_CONFIG) -> dict:
    return pipeline.run_selection(dataset_dir, root / "work", root / "reports", config)


# --- metrics and threshold policy (ADR §6) ------------------------------------
def test_threshold_is_highest_recall_with_precision_floor():
    label = np.array([1, 1, 0, 1, 0, 0, 0, 1, 0, 0])
    score = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.15, 0.1])
    # Precision >= 0.5 down to 0.2 (4 of 8); recall 1.0 there.
    assert tmetrics.select_threshold(label, score, 0.5) == pytest.approx(0.2)
    thr = tmetrics.select_threshold(label, score, 0.75)
    assert thr == pytest.approx(0.6)
    result = tmetrics.at_threshold(label, score, thr)
    assert result["precision"] == 0.75 and result["recall"] == 0.75
    assert result["confusion_matrix"] == {"tp": 3, "fp": 1, "fn": 1, "tn": 5}


def test_threshold_is_none_when_precision_floor_is_unreachable():
    label = np.array([0, 0, 0, 1])
    score = np.array([0.9, 0.8, 0.7, 0.1])
    assert tmetrics.select_threshold(label, score, 0.5) is None


def test_typology_recall_counts_support_per_type():
    label = np.array([1, 1, 1, 0])
    score = np.array([0.9, 0.1, 0.8, 0.95])
    types = np.array(["A", "A", "B", "Normal"])
    rows = tmetrics.typology_recall(label, score, types, 0.5)
    assert rows == [
        {"typology": "A", "support": 2, "detected": 1, "recall": 0.5},
        {"typology": "B", "support": 1, "detected": 1, "recall": 1.0},
    ]


# --- data -----------------------------------------------------------------------
def test_feature_cache_uses_the_full_event_stream(dataset_dir):
    tdata.build_feature_cache(dataset_dir)
    val = tdata.load_split(dataset_dir, ["val"])
    full = synthetic_dataset()
    expected = build_features_batch(full)[full["split"] == "val"].reset_index(drop=True)
    pd.testing.assert_frame_equal(val.features, expected)
    # Building on val rows alone would lose the train history.
    alone = build_features_batch(full[full["split"] == "val"]).reset_index(drop=True)
    assert not alone.equals(expected)


def test_load_split_reads_only_requested_splits(dataset_dir):
    tdata.build_feature_cache(dataset_dir)
    full = synthetic_dataset()
    train = tdata.load_split(dataset_dir, ["train"])
    assert len(train) == int((full["split"] == "train").sum())
    assert tuple(train.features.columns) == FEATURE_NAMES
    with pytest.raises(tdata.TrainingDataError):
        tdata.load_split(dataset_dir, ["holdout"])


def test_negative_sampling_keeps_positives_and_is_seeded(dataset_dir):
    tdata.build_feature_cache(dataset_dir)
    train = tdata.load_split(dataset_dir, ["train"])
    a, strategy = tdata.sample_train(train, 0.3, seed=5)
    b, _ = tdata.sample_train(train, 0.3, seed=5)
    assert a.positives == train.positives
    assert len(a) < len(train)
    pd.testing.assert_frame_equal(a.features, b.features)
    assert strategy["val"].startswith("natural") and strategy["test"].startswith("natural")
    with pytest.raises(tdata.TrainingDataError):
        tdata.sample_train(train, 0.0, seed=5)


# --- models ---------------------------------------------------------------------
def test_baseline_scores_from_json_parameters(dataset_dir):
    tdata.build_feature_cache(dataset_dir)
    train = tdata.load_split(dataset_dir, ["train"])
    params = tmodels.train_baseline(train.features, train.label)
    reloaded = json.loads(json.dumps(params))
    np.testing.assert_array_equal(
        tmodels.baseline_predict(params, train.features),
        tmodels.baseline_predict(reloaded, train.features),
    )
    assert len(params["coef"]) == len(tmodels.NUMERIC_FEATURES) + sum(
        tmodels.CATEGORY_SIZES.values()
    )


def test_lightgbm_limits_are_enforced(dataset_dir):
    tdata.build_feature_cache(dataset_dir)
    train = tdata.load_split(dataset_dir, ["train"])
    with pytest.raises(ValueError):
        tmodels.train_lightgbm_grid(
            train.features, train.label, train.features, train.label, max_trees=201
        )
    with pytest.raises(ValueError):
        tmodels.train_lightgbm_grid(
            train.features,
            train.label,
            train.features,
            train.label,
            [{"num_leaves": 7, "max_depth": 8}],
            max_trees=5,
        )


# --- validation stage -----------------------------------------------------------
def test_selection_is_deterministic(dataset_dir, tmp_path):
    first = run_select(dataset_dir, tmp_path / "a")
    second = run_select(dataset_dir, tmp_path / "b")
    assert first["files"] == second["files"]  # identical model and baseline bytes
    assert first["selected"]["threshold"] == second["selected"]["threshold"]
    for model in ("lightgbm", "baseline"):
        a, b = first["validation"][model], second["validation"][model]
        assert a["pr_auc"] == pytest.approx(b["pr_auc"], abs=1e-12)
        assert a["roc_auc"] == pytest.approx(b["roc_auc"], abs=1e-12)


def test_selection_never_reads_the_test_split(dataset_dir, tmp_path, monkeypatch):
    requested: list[str] = []
    original = tdata.load_split

    def spy(directory, splits):
        requested.extend(splits)
        return original(directory, splits)

    monkeypatch.setattr(tdata, "load_split", spy)
    selection = run_select(dataset_dir, tmp_path)
    assert set(requested) == {"train", "val"}
    assert selection["stage"] == "validation"
    assert selection["calibration"] is None
    assert selection["selected"]["structure"]["num_trees"] <= SMALL_CONFIG.max_trees
    assert selection["selected"]["structure"]["max_depth"] <= 6
    assert 0 < selection["selected"]["threshold"] < 1
    at_val = selection["validation"]["lightgbm"]["at_threshold"]
    assert at_val["precision"] >= tmetrics.MIN_VAL_PRECISION
    assert selection["sampling"]["applied"].startswith("after fs-1 features")
    assert (tmp_path / "reports" / pipeline.SELECTION_FILE).is_file()


# --- locked test stage ------------------------------------------------------------
def test_test_set_is_opened_once_with_frozen_models(dataset_dir, tmp_path):
    selection = run_select(dataset_dir, tmp_path)
    work, reports = tmp_path / "work", tmp_path / "reports"
    report = pipeline.run_test_evaluation(dataset_dir, work, reports)

    assert report["threshold"] == selection["selected"]["threshold"]
    assert report["model_sha256"] == selection["files"][pipeline.MODEL_FILE]["sha256"]
    names = [t["target"] for t in report["targets"]]
    assert len(names) == 9 and isinstance(report["publishable"], bool)
    test = report["test"]["lightgbm"]
    assert test["support_total"] == int((synthetic_dataset()["split"] == "test").sum())
    assert {r["typology"] for r in test["typology_recall"]} <= {"Fan_Out", "Structuring"}
    assert report["latency"]["p95_ms"] > 0
    markdown = (reports / pipeline.REPORT_MD_FILE).read_text(encoding="utf-8")
    assert "## Hedefler" in markdown and "Tipoloji" in markdown

    with pytest.raises(pipeline.LockedTestError, match="already opened"):
        pipeline.run_test_evaluation(dataset_dir, work, reports)
    with pytest.raises(pipeline.LockedTestError, match="already opened"):
        run_select(dataset_dir, tmp_path)


def test_test_stage_rejects_a_model_that_is_not_the_frozen_one(dataset_dir, tmp_path):
    run_select(dataset_dir, tmp_path)
    work, reports = tmp_path / "work", tmp_path / "reports"
    model = work / pipeline.MODEL_FILE
    model.write_text(model.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(pipeline.LockedTestError, match="frozen selection"):
        pipeline.run_test_evaluation(dataset_dir, work, reports)
    assert not (reports / pipeline.TEST_MARKER_FILE).exists()


def test_cli_refuses_to_open_test_when_selection_is_not_committed(
    dataset_dir, tmp_path, monkeypatch, capsys
):
    run_select(dataset_dir, tmp_path)
    monkeypatch.chdir(tmp_path)  # not a git repository
    code = cli_main(
        ["evaluate-test", "--dataset-dir", str(dataset_dir), "--work-dir", "work",
         "--report-dir", "reports"]  # fmt: skip
    )
    assert code == 2
    assert "refusing to open the test set" in capsys.readouterr().out
    assert not (tmp_path / "reports" / pipeline.TEST_MARKER_FILE).exists()
