"""
ML-04 — train, select and evaluate the fraud model (ADR 0003, contract §2–§3).

Single entry point::

    python -m sentinelflow.ml.samld_dataset --source archive.zip --out data/samld   # ML-02
    python -m sentinelflow.ml.training features      --dataset-dir data/samld/<dataset_id>
    python -m sentinelflow.ml.training select        --dataset-dir data/samld/<dataset_id>
    git add reports/ml04/selection.json && git commit   # evidence before the test is opened
    python -m sentinelflow.ml.training evaluate-test --dataset-dir data/samld/<dataset_id>
"""

from sentinelflow.ml.training.pipeline import (
    LockedTestError,
    TrainingConfig,
    run_selection,
    run_test_evaluation,
)

__all__ = ["LockedTestError", "TrainingConfig", "run_selection", "run_test_evaluation"]
