# =============================================================================
# SentinelFlow - PostgreSQL migration and case concurrency tests (SF-402)
# =============================================================================
"""
Run against a real, disposable PostgreSQL database:

- Alembic migrations upgrade a clean database to head (and back) and the
  resulting schema matches the ORM models.
- Two requests with independent sessions racing to put the same alert into
  two cases: exactly one wins, the alert ends up in one open case and the
  loser rolls back without leaving a case or audit event behind.

The database named by ``SENTINELFLOW_TEST_POSTGRES_URL`` is wiped; never point
it at real data. Without the variable the module is skipped.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from case_db import add_alert
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from sentinelflow.contracts import CaseCreate, EventType
from sentinelflow.database.models import AlertModel, Base, CaseEventModel, CaseModel
from sentinelflow.services import CaseConflictError, CaseService

POSTGRES_URL = os.getenv("SENTINELFLOW_TEST_POSTGRES_URL", "")
REPO_ROOT = Path(__file__).resolve().parent.parent

# The CI job sets this so a missing URL fails loudly instead of skipping green.
if os.getenv("SENTINELFLOW_REQUIRE_POSTGRES") == "1" and not POSTGRES_URL:
    raise RuntimeError(
        "SENTINELFLOW_REQUIRE_POSTGRES=1 but SENTINELFLOW_TEST_POSTGRES_URL is unset"
    )

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not POSTGRES_URL, reason="SENTINELFLOW_TEST_POSTGRES_URL is not set"),
]

LOCK_WAIT_TIMEOUT_S = 10.0


def _alembic_config() -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return config


def _reset_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    # alembic/env.py reads DATABASE_URL; scope it to this module.
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", POSTGRES_URL)
        eng = create_engine(POSTGRES_URL, pool_size=5)
        _reset_schema(eng)
        command.upgrade(_alembic_config(), "head")
        yield eng
        eng.dispose()


@pytest.fixture()
def session_factory(engine: Engine) -> Iterator[sessionmaker[Session]]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE case_events, alerts, cases RESTART IDENTITY CASCADE"))


# =============================================================================
# Migrations
# =============================================================================


def test_migrations_reach_head_and_match_models(engine: Engine) -> None:
    with engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        assert context.get_current_revision() == "002"
        diff = compare_metadata(context, Base.metadata)

    # Known drift: models declare NOT NULL on columns the migrations left
    # nullable. Tables, columns, types and indexes must still match exactly.
    structural = [
        entry
        for entry in diff
        if not (isinstance(entry, list) and all(op[0] == "modify_nullable" for op in entry))
    ]
    assert structural == []


def test_migrations_downgrade_and_upgrade_again(engine: Engine) -> None:
    config = _alembic_config()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", POSTGRES_URL)
        command.downgrade(config, "base")
        with engine.connect() as conn:
            tables = conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
            assert set(tables) <= {"alembic_version"}
        command.upgrade(config, "head")

    with engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() == "002"


# =============================================================================
# Concurrency
# =============================================================================


def _lock_waiters(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )
        ).scalar_one()


def _race(
    engine: Engine,
    factory: sessionmaker[Session],
    alert_id: str,
    calls: list[Callable[[CaseService], Any]],
) -> list[Any]:
    """Run ``calls`` concurrently, each in its own session and transaction.

    A blocker transaction holds the alert's row lock until every call is
    waiting on it, so the requests really overlap instead of running one
    after another. Returns each call's result or raised exception.
    """
    results: list[Any] = [None] * len(calls)

    def worker(index: int, call: Callable[[CaseService], Any]) -> None:
        with factory() as session:
            try:
                results[index] = call(CaseService(session))
            except Exception as exc:  # noqa: BLE001 - asserted by the caller
                results[index] = exc

    with factory() as blocker:
        blocker.execute(select(AlertModel).where(AlertModel.alert_id == alert_id).with_for_update())
        threads = [
            threading.Thread(target=worker, args=(i, call), daemon=True)
            for i, call in enumerate(calls)
        ]
        for thread in threads:
            thread.start()

        deadline = time.monotonic() + LOCK_WAIT_TIMEOUT_S
        while _lock_waiters(engine) < len(calls):
            assert time.monotonic() < deadline, "requests never blocked on the alert lock"
            time.sleep(0.05)
        blocker.commit()

    for thread in threads:
        thread.join(LOCK_WAIT_TIMEOUT_S)
        assert not thread.is_alive(), "request did not finish after the lock was released"
    return results


def _split(results: list[Any]) -> tuple[Any, CaseConflictError]:
    winners = [r for r in results if not isinstance(r, Exception)]
    losers = [r for r in results if isinstance(r, Exception)]
    assert len(winners) == 1, results
    assert len(losers) == 1, results
    (loser,) = losers
    assert isinstance(loser, CaseConflictError), repr(loser)
    assert loser.code == "alert_already_linked"
    return winners[0], loser


def _linked_events(session: Session, alert_id: str) -> list[CaseEventModel]:
    stmt = select(CaseEventModel).where(
        CaseEventModel.alert_id == alert_id,
        CaseEventModel.event_type == EventType.ALERT_LINKED_TO_CASE.value,
    )
    return list(session.execute(stmt).scalars())


def test_concurrent_case_creation_links_alert_once(
    engine: Engine, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as setup:
        add_alert(setup, "RACE-1")

    def create(title: str) -> Callable[[CaseService], Any]:
        return lambda service: service.create_from_alerts(
            CaseCreate(title=title, alert_ids=["RACE-1"]), actor="analyst"
        )

    results = _race(engine, session_factory, "RACE-1", [create("first"), create("second")])
    winner, loser = _split(results)
    assert loser.context["case_id"] == winner.case_id

    with session_factory() as check:
        alert = check.get(AlertModel, "RACE-1")
        assert alert is not None and alert.case_id == winner.case_id
        # The losing request rolled back: no second case, no stray audit rows.
        assert check.execute(select(func.count()).select_from(CaseModel)).scalar_one() == 1
        events = check.execute(select(CaseEventModel)).scalars().all()
        assert {e.case_id for e in events} == {winner.case_id}
        assert len(_linked_events(check, "RACE-1")) == 1


def test_concurrent_link_to_two_open_cases_links_alert_once(
    engine: Engine, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as setup:
        for alert_id in ("SEED-X", "SEED-Y", "RACE-2"):
            add_alert(setup, alert_id)
        service = CaseService(setup)
        case_x = service.create_from_alerts(CaseCreate(title="X", alert_ids=["SEED-X"]), "a")
        case_y = service.create_from_alerts(CaseCreate(title="Y", alert_ids=["SEED-Y"]), "a")

    def link(case_id: str) -> Callable[[CaseService], Any]:
        return lambda service: service.link_alert(case_id, "RACE-2", actor="analyst")

    results = _race(engine, session_factory, "RACE-2", [link(case_x.case_id), link(case_y.case_id)])
    winner, loser = _split(results)
    loser_case_id = case_y.case_id if winner.case_id == case_x.case_id else case_x.case_id
    assert loser.context["case_id"] == winner.case_id

    with session_factory() as check:
        alert = check.get(AlertModel, "RACE-2")
        assert alert is not None and alert.case_id == winner.case_id
        assert winner.alert_count == 2
        loser_case = check.get(CaseModel, loser_case_id)
        assert loser_case is not None and loser_case.alert_count == 1
        events = _linked_events(check, "RACE-2")
        assert [e.case_id for e in events] == [winner.case_id]
