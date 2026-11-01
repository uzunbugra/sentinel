# =============================================================================
# SentinelFlow - ML Pipeline CI helpers (ML-07)
# =============================================================================
"""
What the ML Pipeline workflow runs besides the ML-02/04/05 entry points::

    python -m sentinelflow.ml.ci synthetic --out data/samld/synthetic-ci [--size fast|full]
    python -m sentinelflow.ml.ci gate --report-dir reports/ml04 [--smoke]
    python -m sentinelflow.ml.ci benchmark --dataset-dir DIR --model-dir DIR

* ``synthetic`` writes a small labelled dataset in the ML-02 layout so CI can run
  the real training chain (features → select → evaluate-test → package) without
  the SAML-D source. Its positives need non-linear rules (an amount band, bursts
  that only history features see), so the LR baseline is clearly weaker, as on
  SAML-D. It is a smoke fixture, not evidence about the model.
* ``gate`` re-checks a locked-test report against the ADR 0003 §7–§8 targets in
  code (``TARGETS``) and fails when one is missed. On ``reports/ml04`` this is
  the quality gate of the model that ships; ``--smoke`` only reports.
* ``benchmark`` replays dataset rows through the serving path (fs-1 history +
  ``FraudModelService``) and measures the per-transaction latency.

Tables are appended to ``$GITHUB_STEP_SUMMARY`` when it is set.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sentinelflow.ml.training.metrics import TARGETS, check_targets, latency_summary

SIZES = {"fast": 6_000, "full": 60_000}
T0 = pd.Timestamp("2026-01-05T00:00:00Z")
SELECTION_FILE = "selection.json"
TEST_REPORT_FILE = "test-report.json"


class GateError(RuntimeError):
    """The report is missing, inconsistent or misses a target."""


# --- synthetic dataset -----------------------------------------------------------


def synthetic_dataset(n_normal: int, seed: int = 7) -> pd.DataFrame:
    """Canonical ML-02 rows with ``is_laundering``, ``laundering_type`` and ``split``."""
    rng = np.random.default_rng(seed)
    accounts = [f"{1000 + i}" for i in range(max(300, n_normal // 20))]
    span = 90 * 86400
    rows: list[dict[str, Any]] = []

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

    def at(seconds: int) -> pd.Timestamp:
        return T0 + pd.Timedelta(seconds=int(seconds))

    for _ in range(n_normal):
        s, r = rng.choice(accounts, 2, replace=False)
        ptype = str(rng.choice(["ach", "debit_card", "cheque", "cash_deposit", "cross_border"]))
        country = "AE" if ptype == "cross_border" else "TR"
        # Cash on both sides of the structuring band, cross-border in the fan-out range.
        amount = rng.uniform(2e5, 9e5) if ptype == "cash_deposit" else rng.lognormal(9.5, 1.2)
        add(at(rng.integers(0, span)), s, r, amount, ptype, country, 0, "Normal")
    n_bursts = max(12, n_normal // 400)
    # Domestic payroll bursts: same shape as fan-out, legitimate.
    for burst in range(n_bursts):
        payer = f"8{burst:04d}"
        start = int(rng.integers(0, span - 7200))
        for k, r in enumerate(rng.choice(accounts, 8, replace=False)):
            add(at(start + 420 * k), payer, r, rng.uniform(2e4, 6e4), "ach", "TR", 0, "Normal")
    for burst in range(n_bursts):
        mule = f"9{burst:04d}"
        start = int(rng.integers(0, span - 7200))
        for k, r in enumerate(rng.choice(accounts, 8, replace=False)):
            amount = rng.uniform(2e4, 6e4)
            add(at(start + 420 * k), mule, r, amount, "cross_border", "AE", 1, "Fan_Out")
    for _ in range(max(60, n_normal // 25)):
        s, r = rng.choice(accounts, 2, replace=False)
        amount = rng.uniform(4.8e5, 4.99e5)
        add(at(rng.integers(0, span)), s, r, amount, "cash_deposit", "TR", 1, "Structuring")

    df = pd.DataFrame(rows).sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    df.insert(0, "transaction_id", [f"CI-{i:07d}" for i in range(len(df))])
    cut1, cut2 = int(len(df) * 0.70), int(len(df) * 0.85)
    df["split"] = ["train"] * cut1 + ["val"] * (cut2 - cut1) + ["test"] * (len(df) - cut2)
    return df


def write_synthetic(out_dir: Path, size: str = "fast", seed: int = 7) -> dict[str, Any]:
    """Write ``transactions.parquet`` and ``manifest.json`` (ML-02 layout)."""
    df = synthetic_dataset(SIZES[size], seed=seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_dir / "transactions.parquet", index=False)
    manifest = {
        "dataset_id": f"synthetic-ci-{size}-{seed}",
        "source": "sentinelflow.ml.ci synthetic (CI smoke fixture, not SAML-D)",
        "rows": len(df),
        "positives": int(df["is_laundering"].sum()),
        "output": {"content_sha256": "synthetic"},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")
    return manifest


# --- quality gate ------------------------------------------------------------------


def recheck_targets(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The ADR targets recomputed from the report's metrics with today's ``TARGETS``."""
    try:
        return check_targets(
            report["test"]["lightgbm"],
            report["test"]["baseline"],
            report["structure"],
            report["artifact_bytes_model_txt"],
            report["latency"],
        )
    except (KeyError, TypeError) as exc:
        raise GateError(f"locked-test report is missing {exc}") from exc


def gate(report_dir: Path) -> tuple[bool, list[dict[str, Any]], dict[str, Any]]:
    """Return (passed, targets, report). Raises ``GateError`` for a broken report."""
    try:
        report = json.loads((report_dir / TEST_REPORT_FILE).read_text(encoding="utf-8"))
        selection = json.loads((report_dir / SELECTION_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateError(f"locked-test report missing: {exc.filename}") from exc
    frozen = selection.get("files", {}).get("model.txt", {}).get("sha256")
    if not frozen:
        raise GateError("selection.json has no model.txt sha256")
    if frozen != report.get("model_sha256"):
        raise GateError("test report is not for the model frozen in selection.json")
    if report.get("dataset_id") != selection.get("dataset_id"):
        raise GateError("test report and selection.json name different datasets")
    targets = recheck_targets(report)
    passed = all(t["passed"] for t in targets)
    return passed, targets, report


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return "—" if value is None else str(value)


def gate_markdown(title: str, targets: Sequence[Mapping[str, Any]], report: Mapping) -> str:
    try:
        return _gate_markdown(title, targets, report)
    except (KeyError, TypeError) as exc:
        raise GateError(f"locked-test report is missing {exc}") from exc


def _gate_markdown(title: str, targets: Sequence[Mapping[str, Any]], report: Mapping) -> str:
    lgbm = report["test"]["lightgbm"]
    lines = [
        f"### {title}",
        "",
        f"`dataset_id` `{report['dataset_id']}` · model SHA-256 `{report['model_sha256'][:12]}` "
        f"· threshold `{report['threshold']:.6f}`",
        "",
        "| Target | Value | Goal | Result |",
        "|---|---:|---|---|",
    ]
    for t in targets:
        lines.append(
            f"| {t['target']} | {_fmt(t['value'])} | {t['goal']} | "
            f"{'✅ pass' if t['passed'] else '❌ fail'} |"
        )
    thr = lgbm["at_threshold"]
    lines += [
        "",
        f"Test PR-AUC {lgbm['pr_auc']:.4f} · ROC-AUC {lgbm['roc_auc']:.4f} · precision "
        f"{thr['precision']:.4f} · recall {thr['recall']:.4f} · F1 {thr['f1']:.4f}",
        "",
    ]
    return "\n".join(lines)


# --- serving benchmark ---------------------------------------------------------------


def benchmark(dataset_dir: Path, model_dir: Path, limit: int = 2000) -> dict[str, Any]:
    """Latency of features + score + record per transaction, rows in time order."""
    from sentinelflow.ml.features import FEATURE_NAMES, FEATURE_SET_VERSION, AccountHistory
    from sentinelflow.ml.serving import FraudModelService

    service = FraudModelService(
        model_dir, feature_set_version=FEATURE_SET_VERSION, feature_names=FEATURE_NAMES
    )
    service.load()
    if not service.is_loaded:
        raise GateError(f"model not loaded from {model_dir}: {service.error}")
    frame = pd.read_parquet(dataset_dir / "transactions.parquet")
    frame = frame.drop(columns=["is_laundering", "laundering_type", "split"], errors="ignore")
    rows = frame.head(limit).to_dict("records")

    history = AccountHistory()
    samples: list[int] = []
    for row in rows:
        start = time.perf_counter_ns()
        service.score(history.features_for(row))
        history.record(row)
        samples.append(time.perf_counter_ns() - start)
    warm = samples[min(100, len(samples) // 10) :]
    return {
        **latency_summary(warm),
        "scope": "fs-1 features + predict + contributions + record, one transaction",
        "model_version": service.metadata.model_version if service.metadata else None,
        "target_p95_ms": TARGETS["predict_p95_ms"],
    }


def benchmark_markdown(result: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "### Serving latency (CI runner)",
            "",
            f"{result['scope']} · {result['n']} transactions · `{result['model_version']}`",
            "",
            "| p50 | p95 | p99 | max |",
            "|---:|---:|---:|---:|",
            f"| {result['p50_ms']:.3f} ms | {result['p95_ms']:.3f} ms | "
            f"{result['p99_ms']:.3f} ms | {result['max_ms']:.3f} ms |",
            "",
        ]
    )


# --- command line ----------------------------------------------------------------------


def _summarize(markdown: str) -> None:
    print(markdown)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ML Pipeline CI helpers (ML-07)")
    sub = parser.add_subparsers(dest="command", required=True)
    syn = sub.add_parser("synthetic", help="write the CI smoke dataset (ML-02 layout)")
    syn.add_argument("--out", type=Path, required=True)
    syn.add_argument("--size", choices=sorted(SIZES), default="fast")
    syn.add_argument("--seed", type=int, default=7)
    gat = sub.add_parser("gate", help="re-check a locked-test report against the targets")
    gat.add_argument("--report-dir", type=Path, default=Path("reports/ml04"))
    gat.add_argument("--smoke", action="store_true", help="report only, never fail")
    ben = sub.add_parser("benchmark", help="serving latency with real feature vectors")
    ben.add_argument("--dataset-dir", type=Path, required=True)
    ben.add_argument("--model-dir", type=Path, required=True)
    ben.add_argument("--limit", type=int, default=2000)
    args = parser.parse_args(argv)

    try:
        if args.command == "synthetic":
            print(json.dumps(write_synthetic(args.out, args.size, args.seed), indent=2))
        elif args.command == "gate":
            passed, targets, report = gate(args.report_dir)
            if args.smoke:
                title = "Synthetic smoke run (pipeline check, not a quality gate)"
            else:
                title = f"Quality gate — {'passed' if passed else 'FAILED'}"
            _summarize(gate_markdown(title, targets, report))
            if not passed and not args.smoke:
                failed = [t["target"] for t in targets if not t["passed"]]
                print(f"quality gate failed: {failed}", file=sys.stderr)
                return 1
        else:
            _summarize(benchmark_markdown(benchmark(args.dataset_dir, args.model_dir, args.limit)))
    except GateError as exc:
        print(f"ML CI failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
