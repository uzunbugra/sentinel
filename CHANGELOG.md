# Changelog

All notable changes to this project are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Sprint 4 — ML pipeline v2 decision (ML-01).** ADR `docs/adr/0003-ml-pipeline-v2.md` (SAML-D source, time split with a locked test set, LightGBM + logistic baseline, threshold policy, numeric targets, budgets, artifact format, no-model behaviour) and the data/feature/artifact/API contract `docs/contracts/sprint4-ml-api.md`.
- **ML-06 — fraud model loader and service (#21).** `sentinelflow.ml.serving` validates a LightGBM artifact (files, `SHA256SUMS`, `metadata.json` schema, feature set version and order, objective, threshold) and `FraudModelService` scores one feature vector with log-odds contributions and top-5 features; a missing or invalid artifact leaves the service up in `not_loaded` / `invalid` state and never scores. New setting `SENTINELFLOW_MODEL_DIR` (default `models/fraud/current`).
- **ML-06 — fraud model in the API (#21).** The API loads the artifact at startup and serves it: `GET /api/v1/ml/models` returns the active model and its metrics (always `200`, `status` `loaded` / `not_loaded` / `invalid`); `POST /api/v1/risk/score` returns score, threshold, log-odds `base_value` and top-5 contributions and `history_cold_start`, or `503 model_not_loaded`; health gets an `ml_model` component (overall `degraded` without a model). `POST /api/v1/transactions` records the fs-1 account history (the only path that does), returns `model_version` and raises `ml_model` alerts whose evidence freezes model version, threshold and contributions. `TransactionCreate` accepts optional `received_currency`, `sender_country`, `receiver_country`, `payment_type`. Kafka detector still runs the old ensemble (follow-up).

### Changed
- **ML-07 — ML Pipeline workflow (#22).** `.github/workflows/ml-pipeline.yml` is rewritten on the ML-04/05 entry points. *Quality Gate* re-checks the committed locked-test report (`reports/ml04`) against the ADR 0003 targets in code and fails below target; *Training Pipeline* runs features → select → evaluate-test → package on a synthetic dataset (`python -m sentinelflow.ml.ci synthetic`, `fast` on push/PR, `full` weekly) and measures serving latency with real fs-1 vectors. Metrics go to the job summary; the artifact and reports are uploaded. The old inline-Python train/validate/benchmark/model-card jobs and the random-feature drift job are removed.
- `TransactionResponse.fraud_score` is `null` when no model is loaded (was a made-up `0.0`); new `model_version` field.
- `GET /api/v1/ml/models` and `GET /api/v1/ml/features` have new response shapes (contract §4.1, §4.6); health component `ml_ensemble` is now `ml_model`.
- `GET /api/v1/risk/stats` reports the account history counters (`history.recorded`, `duplicates`, `out_of_order`); `recorded` is 0 after a restart (ADR 0003 §4).

### Removed
- `POST /api/v1/ml/train` and `GET /api/v1/ml/train/status` (training is offline, ADR 0003 §10); `POST /api/v1/risk/batch` and `GET /api/v1/risk/features`; the five-model `RiskScoringEngine` behind `risk/score`.

### Fixed
- `AccountHistory` no longer keeps every transaction id for the life of the process: ids leave the duplicate set after the longest window (7 days of event time), and older duplicates are matched against the stored account events instead. Features are unchanged; memory no longer grows with the length of the stream.
- Ingesting the same transaction again returns its existing `ml_model` alert without broadcasting it or counting it again; an id the account history accepts as new is always scored against the current history, even if the duplicate-vector cache still holds it.
- Test artifacts are written with `\n` line endings so their checksums also match on Windows.

## [2.2.0] - 2026-10-29

### Added
- **Sprint 3 — alert-to-case analyst workflow.** `CaseService` creates a case from alerts, links alerts, and changes status / priority / assignment / notes, each as one transaction with audit events; status transition rules, priority-based SLA (`sla_due_at`, `sla_breached`), structured `409`/`422` error codes. New `POST /api/v1/cases/{case_id}/alerts`; typed `GET /api/v1/cases/{case_id}/events`. Contract: `docs/contracts/sprint3-case-api.md`.
- Frontend: case detail page with audit timeline, alert → new/existing case flow, role-aware actions, Europe/Istanbul timestamps; all protected requests go through the shared auth client (single shared refresh). Vitest + Testing Library suite runs in CI.
- `sentinelflow.ml.dataset_schema`: single source of truth for the labelled transaction dataset, used by the ML Pipeline's validation and training jobs.
- Optional `federated` extra (`pip install -e ".[federated]"`) for the Flower adapter.
- JWT/RBAC enforcement on all data routes (`viewer` / `analyst` / `admin`), incl. `X-API-Key` fallback for transaction ingestion (`tests/test_api_auth.py`).
- `POST /api/v1/kyc/screen` endpoint backed by `CombinedScreener`.
- CORS whitelist via `CORS_ORIGINS` (wildcard mode disables credentials).
- Frontend Docker image (multi-stage, standalone) + compose `frontend` profile fix.
- Team workflow: `CONTRIBUTING.md`, PR template, `CODEOWNERS`, `.editorconfig`, pre-commit hooks, API contract gate (`scripts/export_openapi.py`), coverage gate (`--cov-fail-under=45`), `tsc --noEmit` in CI.
- **SF-402 — PostgreSQL CI job.** Alembic migrations run on a real PostgreSQL 16 (upgrade, downgrade, re-upgrade, schema compared with the ORM models) and two independent sessions race to put the same alert into two cases: exactly one wins, the loser gets `409 alert_already_linked` and leaves no case or audit event (`tests/test_postgres_cases.py`, marker `postgres`).
- Integration smoke tests for Redis geo (impossible travel) and Neo4j ring detection (`tests/test_integration_services.py`, marker `integration`); the CI integration job now runs real tests instead of selecting zero.

### Changed
- JWT library: `python-jose` → `PyJWT` (token format unchanged). CI security scan passes with no exceptions.
- `POST /api/v1/cases` returns `201` and requires `alert_ids`; `/cases/{id}/add-alert/{alert_id}` and `/alerts/{id}/link-case/{case_id}` are deprecated aliases that apply the same rules.
- CI runs on pull requests into `develop`; ML Pipeline validates data on ML pull requests.
- `CODEOWNERS`: each PR is reviewed by the other team member.
- Required secrets are now fail-fast: `POSTGRES_PASSWORD`, `NEO4J_PASSWORD`, `JWT_SECRET_KEY` (no silent defaults in app, detector, or compose).
- Core modules split into ≤500-line packages for navigability (import paths unchanged): `processor/detector/` (types, checks, publishing, runtime, service, cli), `processor/graph_engine/` (types, cypher, engine), `api/risk_scoring/` (schemas, engine, routes). OpenAPI schema verified byte-identical.
- Dependencies pruned to what is actually imported (dropped spacy, geopy, haversine, pyvis, slowapi, asyncio-throttle, aiofiles, hyperopt, tensorboard and the unused `[mlops]` extra).
- Version unified at `2.1.0` across `pyproject.toml`, package `__version__`, the API and the Docker image.
- `docs/api.md` and `docs/architecture.md` rewritten from the real route table and module layout (previous drafts described non-existent modules and services).
- `seed_admin.py`: no default admin password; auto-generates unless `SEED_ADMIN_PASSWORD` or `--no-generate`.
- Alembic migration 002 no longer inserts a well-known admin user (use `seed_admin.py`).
- README synced with actual routes, roles, versions and test counts.

### Fixed
- Test suite no longer hangs or segfaults on macOS when the XGBoost and PyTorch tests share a process (two OpenMP runtimes); `tests/conftest.py` pins `OMP_NUM_THREADS=1` on macOS.
- Refresh tokens were always rejected (the revoked-token filter compiled to a constant).
- ML Pipeline: data validation required a `user_id` column the generator no longer produces; training fed raw strings and the `fraud_type` label to the model.
- Fresh installs on Python 3.11+ lacked `greenlet` for the async SQLAlchemy engine (`sqlalchemy[asyncio]` now declared).
- Case responses omitted `alert_ids`, SLA and resolution fields; PATCH ignored `priority`; events were attributed to `system`.
- Frontend auth was silently disabled in the browser (`NEXT_PUBLIC_*` read dynamically).
- Ingestion path works end-to-end again: `requests` is now a declared dependency (kafka ingestor / http generator / replay scripts crashed on clean installs), the Docker builder copies `README.md` (hatchling metadata), and ingestion clients send `X-API-Key` (the endpoint 401'd everything since RBAC).
- Compose passes `SENTINELFLOW_API_KEY` + `CORS_ORIGINS` to the api container and auto-creates the Neo4j schema on first boot (`init_neo4j_schema.cypher` mounted into `/docker-entrypoint-initdb.d`).
- CI: pin `bcrypt>=4.0.1,<4.1` (passlib 1.7.4 incompatible with bcrypt>=4.1 — broke JWT tests), coverage floor set to 45%.
- CI: pin black (`>=26.5,<27`) and ruff (`>=0.15.22,<0.16`) to same ranges in pyproject, CI and pre-commit — formatter minor versions changed formatting and caused lint drift; `tool.black.target-version` pinned to `py310` to silence the 3.11-runner AST safety warning.
- Frontend called non-existent endpoints (`/graph/nodes`, `/graph/edges`, `/ml/predict`, `/ml/info`); aligned with backend + generated contract snapshot.

### Removed
- `python-jose` / `ecdsa`; `flwr` from the core dependencies (now the `federated` extra).
- Unwired/broken feature modules parked for rebuild (working versions will be re-added one by one): `compliance/` (MASAK/audit, imported only by its own tests), `monitoring/` (Prometheus/OTel suite, nothing consumed it — `/metrics` is hand-rolled), `detectors/` CLI shim (passed `--topic`/`--group` flags the detector parser does not accept; advertised non-existent `graph`/`geo` subcommands), `ml/benchmark.py`, `ml/replay_producer.py`, `dashboard/competition_dashboard.py`, `generator/http_gen.py` (all zero external references). Sources preserved in the `archive/unwired-features-20261005` tag.
- Unused observability dependencies with the monitoring package: `prometheus-client`, `opentelemetry-api/sdk/exporter-otlp`.
- Dead CLI subcommands (`detectors graph|geo`) targeting non-existent entry points.
- Echo-only CI jobs (`model-version`, `deploy-staging`, `deploy-production`).
- Stray root launcher scripts (`*.bat`, `test_api.py`, `verify_kafka.py`, `scripts/live_test.py` — stale ports/paths), unused Next.js placeholder SVGs and the dead `src/sentinelflow/security/` duplicate-auth package with its tests.
- Dead CI/config options: ML pipeline `data/**`/`models/**` push triggers (gitignored), the `deploy` dispatch option, `MLFLOW_TRACKING_URI`, and the phantom `sentinelflow-detector` Prometheus target.

### Security
- Removed all hardcoded credentials from repo (incl. bcrypt hash of `Admin123!` in migration history and a Neo4j password in `init_neo4j_schema.cypher` comments).
- JWT: the silent insecure-key fallback is gone; `JWT_SECRET_KEY` unset now fails at startup and at every token operation.
- CI security scans are blocking gates (bandit + pip-audit, scanning the real dependency tree); MD5 fingerprinting/bucketing marked `usedforsecurity=False`; pickle/torch loads of self-saved artifacts annotated with justified `# nosec`.
