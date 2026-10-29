# =============================================================================
# SentinelFlow - Case & Event Repository Tests (SF-307)
# =============================================================================
"""
Repository-level tests for case listing (filters, pagination, ordering),
statistics, aggregates and event listing against in-memory SQLite.
"""

from datetime import timedelta

import pytest
from case_db import BASE_TIME, add_alert, make_engine, make_session

from sentinelflow.contracts import CaseCreate
from sentinelflow.contracts.case import CaseUpdate
from sentinelflow.repository import CaseRepository, EventRepository
from sentinelflow.services import CaseService


@pytest.fixture()
def seeded():
    engine = make_engine()
    session = make_session(engine)
    for i in range(1, 6):
        add_alert(session, f"A{i}", amount=100.0 * i, minutes=i)
    svc = CaseService(session)
    created = []
    for i, (priority, status, assignee) in enumerate(
        [
            ("P1", None, "analyst1"),
            ("P2", "investigating", "analyst2"),
            ("P3", "closed", None),
            ("P1", "resolved_true_positive", "analyst1"),
            ("P4", None, None),
        ],
        start=1,
    ):
        case = svc.create_from_alerts(
            CaseCreate(
                title=f"Case {i}", alert_ids=[f"A{i}"], priority=priority, assigned_to=assignee
            ),
            actor="analyst1",
        )
        if status:
            svc.update_case(
                case.case_id,
                CaseUpdate(status=status, resolution="done" if "resolved" in status else None),
                actor="analyst1",
            )
        created.append(case.case_id)
    yield session, created
    session.close()
    engine.dispose()


class TestCaseRepositoryList:
    def test_newest_first_with_pagination(self, seeded):
        session, created = seeded
        repo = CaseRepository(session)
        page1, total = repo.list(page=1, page_size=2)
        page3, _ = repo.list(page=3, page_size=2)
        assert total == 5
        assert [c.case_id for c in page1] == created[::-1][:2]
        assert [c.case_id for c in page3] == [created[0]]

    @pytest.mark.parametrize(
        ("filters", "expected_titles"),
        [
            ({"status": "investigating"}, {"Case 2"}),
            ({"priority": "P1"}, {"Case 1", "Case 4"}),
            ({"assigned_to": "analyst1"}, {"Case 1", "Case 4"}),
            ({"is_open": True}, {"Case 1", "Case 2", "Case 5"}),
            ({"is_open": False}, {"Case 3", "Case 4"}),
        ],
    )
    def test_filters(self, seeded, filters, expected_titles):
        session, _ = seeded
        cases, total = CaseRepository(session).list(**filters)
        assert {c.title for c in cases} == expected_titles
        assert total == len(expected_titles)

    def test_stats(self, seeded):
        session, _ = seeded
        stats = CaseRepository(session).get_stats()
        assert (stats["total"], stats["open"], stats["closed"]) == (5, 3, 2)
        assert stats["by_priority"] == {"P1": 2, "P2": 1, "P3": 1, "P4": 1}
        assert stats["by_status"]["new"] == 2

    def test_get_by_id(self, seeded):
        session, created = seeded
        repo = CaseRepository(session)
        case = repo.get_by_id(created[0])
        assert case.alert_ids == ["A1"]
        assert case.first_alert_at == BASE_TIME + timedelta(minutes=1)
        assert repo.get_by_id("CASE-NOPE") is None


class TestEagerLoading:
    def test_list_and_get_do_not_lazy_load_alerts(self, seeded):
        from sqlalchemy import event

        session, created = seeded
        session.expunge_all()
        engine = session.get_bind()
        statements = []

        def count(*args):
            statements.append(args[2])

        event.listen(engine, "before_cursor_execute", count)
        try:
            cases, _ = CaseRepository(session).list(page_size=20)
            listed = len(statements)
            CaseRepository(session).get_by_id(created[0])
        finally:
            event.remove(engine, "before_cursor_execute", count)

        assert all(case.alert_ids for case in cases)
        assert listed == 3  # count + cases + one selectin query for all alerts
        assert len(statements) - listed == 2  # case + its alerts


class TestEventRepository:
    def test_list_by_case_orders_and_filters(self, seeded):
        session, created = seeded
        repo = EventRepository(session)
        events, total = repo.list_by_case(created[1])
        assert total == 3
        assert [e.event_type for e in events] == [
            "case_status_changed",
            "alert_linked_to_case",
            "case_created",
        ]
        only_status, count = repo.list_by_case(created[1], event_type="case_status_changed")
        assert count == 1 and only_status[0].new_value == "investigating"

    def test_list_is_scoped_to_case(self, seeded):
        session, created = seeded
        events, total = EventRepository(session).list_by_case(created[0])
        assert total == 2
        assert {e.case_id for e in events} == {created[0]}
