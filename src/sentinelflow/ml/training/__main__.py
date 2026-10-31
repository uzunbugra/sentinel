# =============================================================================
# SentinelFlow - ML-04 command line
# =============================================================================
"""``python -m sentinelflow.ml.training {features,select,evaluate-test,package}``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from sentinelflow.ml.training import artifact as tartifact
from sentinelflow.ml.training import data as tdata
from sentinelflow.ml.training import pipeline

DEFAULT_WORK_DIR = Path("data/ml04")
DEFAULT_REPORT_DIR = Path("reports/ml04")
DEFAULT_MODEL_ROOT = Path("models/fraud")


def _selection_is_committed(repo_dir: Path, selection: Path) -> str | None:
    """None when ``selection`` is tracked and identical to HEAD, else the reason."""
    if pipeline._git(repo_dir, "ls-files", "--error-unmatch", str(selection)) is None:
        return f"{selection} is not committed"
    if pipeline._git(repo_dir, "diff", "--quiet", "HEAD", "--", str(selection)) is None:
        return f"{selection} differs from HEAD"
    return None


def _summary(payload: dict, keys: Sequence[str]) -> str:
    return json.dumps({k: payload[k] for k in keys if k in payload}, indent=2, default=str)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train and evaluate the fraud model (ML-04)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("features", "select", "evaluate-test"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--dataset-dir", type=Path, required=True, help="data/samld/<id>")
        if name != "features":
            cmd.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
            cmd.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    sub.choices["features"].add_argument("--force", action="store_true")
    select = sub.choices["select"]
    select.add_argument(
        "--negative-rate", type=float, default=pipeline.TrainingConfig.negative_rate
    )
    select.add_argument("--num-threads", type=int, default=pipeline.TrainingConfig.num_threads)
    sub.choices["evaluate-test"].add_argument(
        "--skip-commit-check",
        action="store_true",
        help="do not require selection.json to be committed (local dry runs only)",
    )
    package = sub.add_parser("package", help="build the ML-05 artifact from a passed ML-04 run")
    package.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    package.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    package.add_argument("--out", type=Path, default=DEFAULT_MODEL_ROOT)
    args = parser.parse_args(argv)
    repo_dir = Path.cwd()

    try:
        if args.command == "features":
            info = tdata.build_feature_cache(args.dataset_dir, force=args.force)
            print(json.dumps(info, indent=2))
        elif args.command == "select":
            config = pipeline.TrainingConfig(
                negative_rate=args.negative_rate, num_threads=args.num_threads
            )
            result = pipeline.run_selection(
                args.dataset_dir, args.work_dir, args.report_dir, config, repo_dir
            )
            print(_summary(result, ("dataset_id", "selected", "git_sha", "git_dirty")))
            print(json.dumps(result["validation"]["lightgbm"]["at_threshold"], indent=2))
            print(f"commit {args.report_dir / pipeline.SELECTION_FILE} before evaluate-test")
        elif args.command == "package":
            path = tartifact.build_artifact(args.report_dir, args.work_dir, args.out)
            print(f"artifact: {path} ({tartifact.artifact_bytes(path)} bytes)")
        else:
            selection = args.report_dir / pipeline.SELECTION_FILE
            reason = (
                None if args.skip_commit_check else _selection_is_committed(repo_dir, selection)
            )
            if reason:
                print(f"refusing to open the test set: {reason}")
                return 2
            report = pipeline.run_test_evaluation(
                args.dataset_dir, args.work_dir, args.report_dir, repo_dir
            )
            for t in report["targets"]:
                print(f"{'PASS' if t['passed'] else 'FAIL'}  {t['target']}: {t['value']}")
            print(f"publishable: {report['publishable']}")
    except (
        tdata.TrainingDataError,
        pipeline.LockedTestError,
        tartifact.ArtifactBuildError,
    ) as exc:
        print(f"ML-04 failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
