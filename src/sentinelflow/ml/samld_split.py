# =============================================================================
# SentinelFlow - SAML-D chronological split (ML-02)
# =============================================================================
"""
Train/val/test by time: row fractions, cuts never inside a timestamp group, splits
time-disjoint. Split out of ``samld_dataset``, which re-exports these names.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

DEFAULT_TRAIN_FRACTION = 0.70
DEFAULT_VAL_FRACTION = 0.15
SPLITS: tuple[str, ...] = ("train", "val", "test")
SPLIT_COLUMN = "split"


class SamldDatasetError(ValueError):
    """Raised when the source or the prepared dataset breaks an ML-02 invariant."""


@dataclass(frozen=True)
class SplitBoundary:
    """Rows with ``timestamp >= start`` belong to ``split`` (until the next boundary)."""

    split: str
    start: pd.Timestamp


# =============================================================================
# Chronological split
# =============================================================================


def compute_split_boundaries(
    timestamps: pd.Series,
    train_fraction: float = DEFAULT_TRAIN_FRACTION,
    val_fraction: float = DEFAULT_VAL_FRACTION,
) -> list[SplitBoundary]:
    """Cut a sorted timestamp series into train/val/test by row fraction.

    Each cut moves forward to the first row whose timestamp differs from the previous
    row, so equal timestamps never straddle a boundary.
    """
    if not 0 < train_fraction < 1 or not 0 < val_fraction < 1:
        raise SamldDatasetError("Split fractions must be in (0, 1).")
    if train_fraction + val_fraction >= 1:
        raise SamldDatasetError("train_fraction + val_fraction must be < 1 (test needs rows).")
    values = timestamps.to_numpy()
    if len(values) and not (values[1:] >= values[:-1]).all():
        raise SamldDatasetError("Timestamps must be sorted before splitting.")

    n = len(values)
    starts = [0]
    for fraction in (train_fraction, train_fraction + val_fraction):
        cut = min(int(n * fraction), n - 1)
        if cut > 0 and values[cut] == values[cut - 1]:
            # Inside a timestamp group: move the whole group to the later split.
            cut = int(np.searchsorted(values, values[cut], side="right"))
        starts.append(cut)
    if not (0 < starts[1] < starts[2] < n):
        raise SamldDatasetError(
            "Cannot split without breaking a timestamp group: each split needs at least "
            f"one distinct timestamp (row starts {starts}, {n} rows)."
        )
    return [
        SplitBoundary(split, pd.Timestamp(values[start]))
        for split, start in zip(SPLITS, starts, strict=True)
    ]


def assign_splits(timestamps: pd.Series, boundaries: Sequence[SplitBoundary]) -> pd.Series:
    """Label each row with its split from the boundaries' start timestamps."""
    codes = np.zeros(len(timestamps), dtype="int8")
    for boundary in boundaries[1:]:
        codes += (timestamps >= boundary.start).to_numpy(dtype="int8")
    return pd.Series(pd.Categorical.from_codes(codes, categories=list(SPLITS)), name=SPLIT_COLUMN)


def check_split_invariants(df: pd.DataFrame) -> None:
    """Raise unless splits are time-disjoint and in train < val < test order."""
    bounds = df.groupby(SPLIT_COLUMN, observed=False)["timestamp"].agg(["min", "max", "size"])
    for split in SPLITS:
        if bounds.loc[split, "size"] == 0:
            raise SamldDatasetError(f"Split '{split}' is empty.")
    for earlier, later in zip(SPLITS, SPLITS[1:], strict=False):
        if not bounds.loc[earlier, "max"] < bounds.loc[later, "min"]:
            raise SamldDatasetError(
                f"max({earlier})={bounds.loc[earlier, 'max']} must be < "
                f"min({later})={bounds.loc[later, 'min']}."
            )
