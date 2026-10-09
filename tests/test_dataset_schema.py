# =============================================================================
# SentinelFlow - Transaction Dataset Contract Tests
# =============================================================================
"""
Fast tests for ``sentinelflow.ml.dataset_schema``: the generator must satisfy the
contract, and contract violations must fail with a clear message.
"""

import pandas as pd
import pytest

from sentinelflow.ml import dataset_schema as schema
from sentinelflow.ml.competition_dataset import CHANNELS as GENERATOR_CHANNELS
from sentinelflow.ml.competition_dataset import CompetitionDatasetGenerator


@pytest.fixture(scope="module")
def generated() -> pd.DataFrame:
    gen = CompetitionDatasetGenerator(seed=7, n_users=50)
    return gen.generate(n_transactions=300, fraud_ratio=0.1)


@pytest.fixture
def minimal() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "transaction_id": ["TX1", "TX2"],
            "timestamp": pd.to_datetime(["2026-10-01 10:00", "2026-10-01 23:30"]),
            "sender_iban": ["TR01", "TR02"],
            "receiver_iban": ["TR03", "TR01"],
            "amount": [150.0, 9800.5],
            "is_fraud": [False, True],
            "sender_city": ["İstanbul", "Ankara"],
            "receiver_city": ["İstanbul", "İzmir"],
            "description": ["Kira", ""],
            "channel": ["mobile", "unknown-channel"],
            "device_id": ["d1", "d2"],
        }
    )


class TestGeneratorSatisfiesContract:
    def test_generated_dataset_is_valid(self, generated):
        schema.validate_transaction_dataset(generated)

    def test_contract_covers_core_fields(self):
        names = {spec.name for spec in schema.REQUIRED_COLUMNS}
        assert names == {
            "transaction_id",
            "timestamp",
            "sender_iban",
            "receiver_iban",
            "amount",
            "is_fraud",
        }

    def test_generator_channels_are_known(self):
        unknown = set(GENERATOR_CHANNELS) - set(schema.CHANNELS)
        assert not unknown, f"Generator emits channels missing from the contract: {unknown}"

    def test_features_from_generated_data(self, generated):
        features = schema.build_feature_frame(generated)
        assert list(features.columns) == list(schema.FEATURE_COLUMNS)
        assert len(features) == len(generated)
        assert all(pd.api.types.is_numeric_dtype(features[c]) for c in features.columns)
        assert not features.isna().any().any()


class TestContractViolations:
    def test_empty_dataset(self, minimal):
        with pytest.raises(schema.DatasetSchemaError, match="empty"):
            schema.validate_transaction_dataset(minimal.iloc[0:0])

    def test_missing_column_names_the_column(self, minimal):
        with pytest.raises(
            schema.DatasetSchemaError, match=r"Missing required columns: \['sender_iban'\]"
        ):
            schema.validate_transaction_dataset(minimal.drop(columns=["sender_iban"]))

    def test_legacy_user_id_contract_is_not_enough(self, minimal):
        legacy = minimal.drop(columns=["sender_iban", "receiver_iban"]).assign(user_id=["U1", "U2"])
        with pytest.raises(schema.DatasetSchemaError, match="sender_iban"):
            schema.validate_transaction_dataset(legacy)

    def test_non_numeric_amount(self, minimal):
        bad = minimal.assign(amount=["150", "9800.5"])
        with pytest.raises(schema.DatasetSchemaError, match="'amount' must be numeric"):
            schema.validate_transaction_dataset(bad)

    def test_string_timestamp(self, minimal):
        bad = minimal.assign(timestamp=["2026-10-01", "2026-10-02"])
        with pytest.raises(schema.DatasetSchemaError, match="'timestamp' must be datetime"):
            schema.validate_transaction_dataset(bad)

    def test_label_outside_zero_one(self, minimal):
        bad = minimal.assign(is_fraud=[0, 2])
        with pytest.raises(schema.DatasetSchemaError, match="'is_fraud' must be label"):
            schema.validate_transaction_dataset(bad)

    def test_integer_label_is_accepted(self, minimal):
        schema.validate_transaction_dataset(minimal.assign(is_fraud=[0, 1]))

    def test_null_values_are_reported(self, minimal):
        bad = minimal.copy()
        bad.loc[0, "receiver_iban"] = None
        with pytest.raises(schema.DatasetSchemaError, match="'receiver_iban' has 1 null"):
            schema.validate_transaction_dataset(bad)

    def test_all_violations_reported_together(self, minimal):
        bad = minimal.assign(amount=["x", "y"], timestamp=["a", "b"])
        with pytest.raises(schema.DatasetSchemaError) as exc:
            schema.validate_transaction_dataset(bad)
        assert "amount" in str(exc.value) and "timestamp" in str(exc.value)

    def test_features_require_feature_source_columns(self, minimal):
        with pytest.raises(schema.DatasetSchemaError, match="channel"):
            schema.build_feature_frame(minimal.drop(columns=["channel"]))


class TestFeatureFrame:
    def test_no_identifier_label_or_leakage_columns(self, minimal):
        features = schema.build_feature_frame(minimal.assign(fraud_type=["none", "phishing"]))
        forbidden = {"transaction_id", "sender_iban", "receiver_iban", "is_fraud", "fraud_type"}
        assert forbidden.isdisjoint(features.columns)

    def test_derived_values(self, minimal):
        features = schema.build_feature_frame(minimal)
        assert features["hour"].tolist() == [10, 23]
        assert features["cross_city"].tolist() == [0, 1]
        assert features["description_length"].tolist() == [4, 0]
        assert features["channel_code"].tolist() == [schema.CHANNELS.index("mobile"), -1]
        assert features["sender_tx_count"].tolist() == [1, 1]

    def test_label_series_is_integer(self, minimal):
        assert schema.label_series(minimal).tolist() == [0, 1]


class TestCli:
    def test_main_passes_on_generated_sample(self, capsys):
        assert schema.main(["--sample-size", "200"]) == 0
        assert "Data validation passed!" in capsys.readouterr().out

    def test_main_reports_contract_failure(self, monkeypatch, capsys):
        def broken(self, n_transactions, fraud_ratio):
            return pd.DataFrame({"user_id": ["U1"], "amount": [1.0]})

        monkeypatch.setattr(CompetitionDatasetGenerator, "generate", broken)
        assert schema.main(["--sample-size", "10"]) == 1
        assert "Missing required columns" in capsys.readouterr().out
