# =============================================================================
# SentinelFlow - SAML-D Dataset Preparation Tests (ML-02)
# =============================================================================
"""
Fast tests for ``sentinelflow.ml.samld_dataset`` on a small synthetic SAML-D-shaped
CSV: the canonical transformation, chronological split invariants and determinism.
No quality metric is ever reported from this fixture.
"""

import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from sentinelflow.ml import samld_dataset as samld

HEADER = ",".join(samld.RAW_COLUMNS)

# 20 rows, 4 positives; rows 6-9 share one timestamp and rows 13-15 another, so
# several split fractions land inside a timestamp group.
ROWS = [
    "10:35:19,2022-10-07,8724731955,2769355426,1459.15,UK pounds,UK pounds,UK,UK,Cash Deposit,0,Normal_Cash_Deposits",
    "10:35:20,2022-10-07,1491989064,8401255335,6019.64,UK pounds,Dirham,UK,UAE,Cross-border,0,Normal_Fan_Out",
    "10:35:20,2022-10-07,287305149,4404767002,14328.44,UK pounds,UK pounds,UK,UK,Cheque,0,Normal_Small_Fan_Out",
    "10:35:21,2022-10-07,5376652437,9600420220,11895.0,UK pounds,UK pounds,UK,UK,ACH,0,Normal_Fan_In",
    "11:00:00,2022-10-07,8724731955,1491989064,250.5,Turkish lira,Turkish lira,Turkey,UK,Debit card,1,Structuring",
    "12:00:00,2022-10-08,1491989064,8724731955,99.99,Euro,Euro,Spain,Germany,Credit card,0,Normal_Group",
    "13:00:00,2022-10-08,287305149,8724731955,10.0,UK pounds,UK pounds,UK,UK,Cash Withdrawal,0,Normal_Cash_Withdrawal",
    "13:00:00,2022-10-08,5376652437,287305149,20.0,UK pounds,UK pounds,UK,UK,ACH,1,Fan_In",
    "13:00:00,2022-10-08,9600420220,287305149,30.0,UK pounds,UK pounds,UK,UK,ACH,0,Normal_Fan_In",
    "13:00:00,2022-10-08,4404767002,287305149,40.0,UK pounds,UK pounds,UK,UK,ACH,0,Normal_Fan_In",
    "14:00:00,2022-10-09,8401255335,2769355426,55.0,Yen,Yen,Japan,Japan,Cross-border,0,Normal_Foward",
    "15:00:00,2022-10-09,2769355426,8401255335,66.0,UK pounds,US dollar,UK,USA,Cross-border,1,Layered_Fan_Out",
    "16:00:00,2022-10-10,8724731955,2769355426,77.0,UK pounds,UK pounds,UK,UK,Cheque,0,Normal_Periodical",
    "17:00:00,2022-10-10,1491989064,287305149,88.0,UK pounds,UK pounds,UK,UK,ACH,0,Normal_Fan_In",
    "17:00:00,2022-10-10,287305149,1491989064,89.0,UK pounds,UK pounds,UK,UK,ACH,0,Normal_Fan_In",
    "17:00:00,2022-10-10,5376652437,1491989064,90.0,UK pounds,UK pounds,UK,UK,ACH,1,Cycle",
    "18:00:00,2022-10-11,9600420220,4404767002,101.0,Swiss franc,Swiss franc,Switzerland,Switzerland,Debit card,0,Normal_Mutual",
    "19:00:00,2022-10-11,4404767002,9600420220,102.0,UK pounds,UK pounds,UK,UK,Credit card,0,Normal_Mutual",
    "20:00:00,2022-10-12,8401255335,5376652437,103.0,UK pounds,UK pounds,UK,UK,Debit card,0,Normal_Group",
    "21:00:00,2022-10-12,2769355426,5376652437,104.0,UK pounds,UK pounds,UK,UK,Debit card,0,Normal_Group",
]


def _write_csv(path: Path, rows: list[str] = ROWS) -> Path:
    path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def source_csv(tmp_path: Path) -> Path:
    return _write_csv(tmp_path / "SAML-D.csv")


@pytest.fixture
def canonical(source_csv: Path) -> pd.DataFrame:
    return samld.transform(samld.read_source(source_csv))


# --- Transformation ------------------------------------------------------------


def test_transform_produces_contract_columns(canonical: pd.DataFrame) -> None:
    assert tuple(canonical.columns[: len(samld.CANONICAL_COLUMNS)]) == samld.CANONICAL_COLUMNS
    assert len(canonical) == len(ROWS)
    assert canonical.notna().all().all()


def test_timestamp_is_utc_and_ids_are_deterministic(canonical: pd.DataFrame) -> None:
    assert str(canonical["timestamp"].dt.tz) == "UTC"
    first = canonical.iloc[0]
    assert first["timestamp"] == pd.Timestamp("2022-10-07T10:35:19+00:00")
    assert first["transaction_id"] == "SAMLD-000000000"
    assert canonical["transaction_id"].is_unique
    assert canonical["transaction_id"].tolist() == sorted(canonical["transaction_id"])


def test_accounts_are_kept_unchanged_as_strings(canonical: pd.DataFrame) -> None:
    # 287305149 has no leading zero to lose, but must not become an int or be padded.
    assert canonical.loc[2, "sender_account"] == "287305149"
    assert canonical.loc[0, "receiver_account"] == "2769355426"
    assert all(isinstance(v, str) for v in canonical["sender_account"])


def test_amount_is_scaled_by_fixed_factor_on_every_row(canonical: pd.DataFrame) -> None:
    raw_amounts = [float(row.split(",")[4]) for row in ROWS]
    expected = [round(a * samld.AMOUNT_SCALE, 2) for a in raw_amounts]
    assert canonical["amount"].tolist() == pytest.approx(expected)
    assert canonical.loc[0, "amount"] == pytest.approx(72957.5)


def test_uk_and_turkey_swap_places(canonical: pd.DataFrame) -> None:
    uk_row = canonical.iloc[0]
    assert (uk_row["sender_country"], uk_row["payment_currency"]) == ("TR", "TRY")
    turkey_row = canonical.iloc[4]
    assert (turkey_row["sender_country"], turkey_row["receiver_country"]) == ("GB", "TR")
    assert (turkey_row["payment_currency"], turkey_row["received_currency"]) == ("GBP", "GBP")
    assert canonical.iloc[1]["receiver_country"] == "AE"
    assert canonical.iloc[1]["received_currency"] == "AED"


def test_categories_are_normalised(canonical: pd.DataFrame) -> None:
    assert set(canonical["payment_type"]) <= set(samld.PAYMENT_TYPES.values())
    assert canonical.iloc[0]["payment_type"] == "cash_deposit"
    assert canonical.iloc[1]["payment_type"] == "cross_border"


def test_unknown_categories_map_to_unknown(tmp_path: Path) -> None:
    row = "10:00:00,2022-10-07,1,2,5.0,Rouble,Rouble,Atlantis,UK,Barter,0,Normal_Group"
    df = samld.transform(samld.read_source(_write_csv(tmp_path / "x.csv", [row])))
    assert df.loc[0, "payment_currency"] == samld.UNKNOWN
    assert df.loc[0, "sender_country"] == samld.UNKNOWN
    assert df.loc[0, "receiver_country"] == "TR"
    assert df.loc[0, "payment_type"] == samld.UNKNOWN


def test_labels_are_copied(canonical: pd.DataFrame) -> None:
    assert canonical["is_laundering"].tolist() == [int(row.split(",")[10]) for row in ROWS]
    assert canonical.loc[4, "laundering_type"] == "Structuring"


def test_display_identities_are_valid_and_stable(canonical: pd.DataFrame) -> None:
    for iban in canonical["sender_iban"]:
        assert len(iban) == 26 and iban.startswith("TR") and iban[2:].isdigit()
        rearranged = iban[4:] + "2927" + iban[2:4]
        assert int(rearranged) % 97 == 1
    # Same account -> same IBAN and name, whichever side it appears on.
    by_account = {}
    for side in ("sender", "receiver"):
        for account, iban, name in canonical[
            [f"{side}_account", f"{side}_iban", f"{side}_name"]
        ].itertuples(index=False):
            assert by_account.setdefault(account, (iban, name)) == (iban, name)
    ibans = {iban for iban, _ in by_account.values()}
    assert len(ibans) == len(by_account)


def test_non_digit_account_is_rejected(tmp_path: Path) -> None:
    row = "10:00:00,2022-10-07,ACC1,2,5.0,UK pounds,UK pounds,UK,UK,ACH,0,Normal_Group"
    with pytest.raises(samld.SamldDatasetError, match="digit"):
        samld.transform(samld.read_source(_write_csv(tmp_path / "x.csv", [row])))


def test_unsorted_source_is_sorted_by_time_then_id(tmp_path: Path) -> None:
    rows = [ROWS[3], ROWS[0], ROWS[2], ROWS[1]]
    df = samld.transform(samld.read_source(_write_csv(tmp_path / "x.csv", rows)))
    assert df["timestamp"].is_monotonic_increasing
    # Rows 2 and 3 of the file share a timestamp: file order (id order) is kept.
    assert df["transaction_id"].tolist() == [
        "SAMLD-000000001",
        "SAMLD-000000002",
        "SAMLD-000000003",
        "SAMLD-000000000",
    ]


def test_zip_source_is_read_and_hashed_like_the_csv(tmp_path: Path, source_csv: Path) -> None:
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(source_csv, samld.SOURCE_MEMBER)
    assert (
        samld.source_fingerprint(archive)["csv_sha256"]
        == samld.source_fingerprint(source_csv)["csv_sha256"]
    )
    pd.testing.assert_frame_equal(
        samld.transform(samld.read_source(archive)),
        samld.transform(samld.read_source(source_csv)),
    )


# --- Chronological split ---------------------------------------------------------


def _split(df: pd.DataFrame, train: float, val: float) -> pd.DataFrame:
    boundaries = samld.compute_split_boundaries(df["timestamp"], train, val)
    out = df.copy()
    out["split"] = samld.assign_splits(df["timestamp"], boundaries).to_numpy()
    return out


@pytest.mark.parametrize(("train", "val"), [(0.7, 0.15), (0.3, 0.3), (0.35, 0.4), (0.5, 0.25)])
def test_split_is_time_disjoint_and_keeps_timestamp_groups(
    canonical: pd.DataFrame, train: float, val: float
) -> None:
    df = _split(canonical, train, val)
    samld.check_split_invariants(df)
    assert df.groupby("timestamp")["split"].nunique().max() == 1
    assert df["split"].tolist() == sorted(df["split"].tolist(), key=samld.SPLITS.index)


def test_cut_inside_timestamp_group_moves_past_the_group(canonical: pd.DataFrame) -> None:
    # 20 rows * 0.35 = row 7, which sits inside the 13:00:00 group (rows 6-9):
    # the cut moves to row 10 and the whole group stays in train.
    df = _split(canonical, 0.35, 0.4)
    assert (df["split"] == "train").sum() == 10
    assert set(df.loc[6:9, "split"]) == {"train"}


def test_split_validation_rejects_bad_input(canonical: pd.DataFrame) -> None:
    with pytest.raises(samld.SamldDatasetError):
        samld.compute_split_boundaries(canonical["timestamp"], 0.8, 0.2)
    with pytest.raises(samld.SamldDatasetError, match="sorted"):
        samld.compute_split_boundaries(canonical["timestamp"].iloc[::-1], 0.7, 0.15)
    same_time = pd.Series([canonical["timestamp"].iloc[0]] * 10)
    with pytest.raises(samld.SamldDatasetError, match="timestamp group"):
        samld.compute_split_boundaries(same_time, 0.7, 0.15)


def test_overlapping_splits_are_detected(canonical: pd.DataFrame) -> None:
    df = _split(canonical, 0.5, 0.25)
    df.loc[0, "split"] = "test"
    with pytest.raises(samld.SamldDatasetError, match="must be <"):
        samld.check_split_invariants(df)


# --- End to end: manifest and determinism ---------------------------------------


def test_prepare_writes_parquet_and_manifest(tmp_path: Path, source_csv: Path) -> None:
    manifest = samld.prepare(source_csv, tmp_path / "out", 0.5, 0.25)
    target = tmp_path / "out" / manifest["dataset_id"]
    df = pd.read_parquet(target / "transactions.parquet")
    on_disk = json.loads((target / "manifest.json").read_text(encoding="utf-8"))

    assert on_disk == manifest
    assert manifest["dataset_id"].startswith("samld-")
    assert manifest["transform_version"] == samld.TRANSFORM_VERSION
    assert manifest["rows"] == len(df) == len(ROWS)
    assert manifest["positives"] == int(df["is_laundering"].sum()) == 4
    assert sum(s["rows"] for s in manifest["splits"].values()) == len(ROWS)
    assert sum(s["positives"] for s in manifest["splits"].values()) == 4
    assert manifest["splits"]["train"]["timestamp_max"] < manifest["splits"]["val"]["timestamp_min"]
    assert manifest["splits"]["val"]["timestamp_max"] < manifest["splits"]["test"]["timestamp_min"]
    assert manifest["source"]["csv_sha256"] == samld.source_fingerprint(source_csv)["csv_sha256"]
    assert manifest["unknown_category_counts"] == dict.fromkeys(
        manifest["unknown_category_counts"], 0
    )
    assert list(df.columns) == list(samld.OUTPUT_COLUMNS)
    assert str(df["timestamp"].dt.tz) == "UTC"
    assert str(Path.cwd()) not in json.dumps(manifest)


def test_two_runs_give_the_same_manifest_and_rows(tmp_path: Path, source_csv: Path) -> None:
    first = samld.prepare(source_csv, tmp_path / "a")
    second = samld.prepare(source_csv, tmp_path / "b")
    assert first == second
    pd.testing.assert_frame_equal(
        pd.read_parquet(tmp_path / "a" / first["dataset_id"] / "transactions.parquet"),
        pd.read_parquet(tmp_path / "b" / second["dataset_id"] / "transactions.parquet"),
    )


def test_dataset_id_depends_on_source_and_parameters(tmp_path: Path, source_csv: Path) -> None:
    base = samld.prepare(source_csv, tmp_path / "a")["dataset_id"]
    other_split = samld.prepare(source_csv, tmp_path / "b", 0.6, 0.2)["dataset_id"]
    changed = _write_csv(tmp_path / "changed.csv", ROWS[:-1])
    other_source = samld.prepare(changed, tmp_path / "c")["dataset_id"]
    assert len({base, other_split, other_source}) == 3


def test_cli_reads_source_from_env(
    tmp_path: Path, source_csv: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setenv(samld.SOURCE_ENV_VAR, str(source_csv))
    assert samld.main(["--out", str(tmp_path / "out")]) == 0
    assert "dataset_id: samld-" in capsys.readouterr().out


def test_cli_requires_a_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(samld.SOURCE_ENV_VAR, raising=False)
    with pytest.raises(SystemExit):
        samld.main([])
