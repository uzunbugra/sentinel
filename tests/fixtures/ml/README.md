# ML shared fixture (contract §5, feature set `fs-1`)

Shared by the feature engine tests (ML-03), the service loader/API tests (ML-06)
and the SF-405 UI fixture. If a file changes, both sides update their tests in
the same PR.

| File | Content |
|---|---|
| `transactions.jsonl` | 23 canonical transactions (contract §1) in stream order `(timestamp, transaction_id)` |
| `expected_features.jsonl` | One `{transaction_id, features}` row per line of `transactions.jsonl`, 15 values in `FEATURE_NAMES` order |
| `metadata.example.json` | Artifact metadata example (contract §3); not tied to a real model, metrics are `null` |

The expected vectors come from streaming the transactions through a fresh
`AccountHistory` (`features_for`, then `record`). The tests also check them
against a naive implementation of the contract text and against
`build_features_batch`.

Cases covered: cold start, three events at the same timestamp, missing optional
fields (defaults), currency mismatch and cross-border, events exactly 24 h and
7 d back (inclusive lower edge) and one second past them, a duplicate
`transaction_id` (scored, recorded once), unknown payment type and country,
lower-case codes, a gap longer than 7 d (`sender_seconds_since_prev` still set),
fan-in to one receiver, a self transfer and a `+03:00` timestamp offset.

Regenerate after a deliberate change to `transactions.jsonl` or the feature set:

```bash
python -m sentinelflow.ml.features expected tests/fixtures/ml
```

`--check` only verifies the file is current.
