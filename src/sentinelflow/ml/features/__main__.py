"""
CLI for the shared fs-1 fixture (contract §5).

    python -m sentinelflow.ml.features expected tests/fixtures/ml

Reads ``transactions.jsonl`` from the directory, streams it through a fresh
:class:`AccountHistory` (``features_for`` then ``record``) and writes
``expected_features.jsonl`` next to it. ``--check`` only compares.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from sentinelflow.ml.features.engine import AccountHistory
from sentinelflow.ml.features.spec import FEATURE_DTYPES, FEATURE_NAMES, FEATURE_SET_VERSION

TRANSACTIONS_FILE = "transactions.jsonl"
EXPECTED_FILE = "expected_features.jsonl"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def expected_rows(transactions: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """One ``{transaction_id, features}`` row per input line, ints kept as ints."""
    history = AccountHistory()
    rows = []
    for tx in transactions:
        vec = history.features_for(tx)
        history.record(tx)
        features: list[float | int] = [
            int(v) if FEATURE_DTYPES[name].kind == "i" else float(v)
            for name, v in zip(FEATURE_NAMES, vec)
        ]
        rows.append({"transaction_id": tx["transaction_id"], "features": features})
    return rows


def render_jsonl(rows: Iterable[dict[str, Any]]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sentinelflow.ml.features")
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("expected", help=f"write {EXPECTED_FILE} for a fixture directory")
    exp.add_argument("directory", type=Path)
    exp.add_argument("--check", action="store_true", help="fail if the file is out of date")
    args = parser.parse_args(argv)

    text = render_jsonl(expected_rows(read_jsonl(args.directory / TRANSACTIONS_FILE)))
    target = args.directory / EXPECTED_FILE
    if args.check:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != text:
            print(f"{target} is out of date for {FEATURE_SET_VERSION}", file=sys.stderr)
            return 1
        print(f"{target} is up to date ({FEATURE_SET_VERSION})")
        return 0
    target.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {target} ({FEATURE_SET_VERSION})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
