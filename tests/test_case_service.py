# =============================================================================
# SentinelFlow - Case Workflow Service Tests (SF-304)
# =============================================================================
"""
Unit tests for CaseService and case rules against in-memory SQLite.
Contract: docs/contracts/sprint3-case-api.md.
"""

from datetime import datetime, timedelta, timezone

import pytest
from case_db import BASE_TIME, add_alert, make_engine, make_session

from sentinelflow.contracts import CaseCreate, CaseStatus, EventType
from sentinelflow.contracts.case import CaseUpdate
from sentinelflow.contracts.enums import CasePriority
from sentinelflow.database.models import AlertModel, CaseEventModel, CaseModel
from sentinelflow.services import (
    CaseConflictError,
    CaseNotFoundError,
    CaseRuleError,
    CaseService,
)
from sentinelflow.services import case_rules as rules

ACTOR = "analyst1"


@pytest.fixture()
def session():
    engine = make_engine()
    s = make_session(engine)
    add_alert(s, "A1", amount=1000.0, severity="high", minutes=0)
    add_alert(s, "A2", amount=500.0, severity="critical", minutes=5)
    add_alert(s, "A3", amount=250.0, severity="low", minutes=10)
    add_alert(s, "DISMISSED", dismissed=True)
    yield s
    s.close()
    engine.dispose()


@pytest.fixture()
def svc(session):
    return CaseService(session)


def _create(svc, *alert_ids, **kwargs):
    data = {"title": "Ring", "alert_ids": list(alert_ids), **kwargs}
    return svc.create_from_alerts(CaseCreate(**data), actor=ACTOR)


def _event_types(svc, case_id):
    return [e.event_type for e in svc.list_events(case_id).events]


# ----------------------------------------------------------------- rules


class TestRules:
    @pytest.mark.parametrize("status", sorted(rules.OPEN_STATUSES))
    def test_open_status_can_resolve_or_close(self, status):
        allowed = rules.allowed_transitions(status)
        assert allowed >= rules.RESOLVED_STATUSES
        assert CaseStatus.CLOSED in allowed
        assert status not in allowed

    @pytest.mark.parametrize("status", sorted(rules.RESOLVED_STATUSES))
    def test_resolved_can_close_or_reopen(self, status):
        assert rules.allowed_transitions(status) == {CaseStatus.CLOSED, CaseStatus.INVESTIGATING}

    def test_closed_is_terminal(self):
        assert rules.allowed_transitions(CaseStatus.CLOSED) == frozenset()
        assert not rules.is_valid_transition(CaseStatus.CLOSED, CaseStatus.INVESTIGATING)

    @pytest.mark.parametrize(
        ("priority", "hours"),
        [
            (CasePriority.P1_CRITICAL, 4),
            (CasePriority.P2_HIGH, 24),
            (CasePriority.P3_MEDIUM, 72),
            (CasePriority.P4_LOW, 168),
        ],
    )
    def test_sla(self, priority, hours):
        assert rules.sla_due_at(priority, BASE_TIME) == BASE_TIME + timedelta(hours=hours)


# ----------------------------------------------------------------- create


class TestCreateFromAlerts:
    def test_creates_case_with_aggregates_and_sla(self, svc):
        case = _create(svc, "A1", "A2", priority="P2")

        assert case.status == "new"
        assert case.alert_ids == ["A1", "A2"]
        assert case.alert_count == 2
        assert case.total_amount == 1500.0
        assert case.max_severity == "critical"
        assert case.first_alert_at == BASE_TIME
        assert case.last_alert_at == BASE_TIME + timedelta(minutes=5)
        assert case.sla_due_at - case.created_at == timedelta(hours=24)
        assert case.created_at.tzinfo is not None

    def test_writes_created_then_linked_events(self, svc):
        case = _create(svc, "A1", "A2")
        events = svc.list_events(case.case_id).events

        # newest first: links (request order reversed), then case_created last
        assert [e.event_type for e in events] == [
            "alert_linked_to_case",
            "alert_linked_to_case",
            "case_created",
        ]
        assert [e.alert_id for e in events[:2]] == ["A2", "A1"]
        assert {e.actor for e in events} == {ACTOR}
        assert {e.actor_type for e in events} == {"user"}
        assert events[0].created_at > events[1].created_at > events[2].created_at

    def test_duplicate_alert_ids_are_deduplicated(self, svc):
        case = _create(svc, "A1", "A1", "A2")
        assert case.alert_ids == ["A1", "A2"]
        assert _event_types(svc, case.case_id).count("alert_linked_to_case") == 2

    def test_missing_alert_is_404_and_nothing_written(self, svc, session):
        with pytest.raises(CaseNotFoundError, match="NOPE"):
            _create(svc, "A1", "NOPE")
        assert session.query(CaseModel).count() == 0
        assert session.query(CaseEventModel).count() == 0
        assert session.get(AlertModel, "A1").case_id is None

    def test_dismissed_alert_conflict(self, svc):
        with pytest.raises(CaseConflictError) as exc:
            _create(svc, "DISMISSED")
        assert exc.value.code == "alert_dismissed"
        assert exc.value.detail()["alert_id"] == "DISMISSED"

    def test_double_submit_returns_existing_case(self, svc, session):
        first = _create(svc, "A1")
        with pytest.raises(CaseConflictError) as exc:
            _create(svc, "A1")
        detail = exc.value.detail()
        assert detail["code"] == "alert_already_linked"
        assert detail["case_id"] == first.case_id
        assert session.query(CaseModel).count() == 1

    def test_alert_of_closed_case_can_be_relinked(self, svc):
        old = _create(svc, "A1")
        svc.update_case(old.case_id, CaseUpdate(status="closed"), actor=ACTOR)
        new = _create(svc, "A1")
        assert new.alert_ids == ["A1"]
        assert new.case_id != old.case_id

    def test_failure_after_writes_rolls_everything_back(self, svc, session, monkeypatch):
        def boom(case_id):
            raise RuntimeError("aggregate failure")

        monkeypatch.setattr(svc._cases, "refresh_aggregates", boom)
        with pytest.raises(RuntimeError):
            _create(svc, "A1", "A2")

        assert session.query(CaseModel).count() == 0
        assert session.query(CaseEventModel).count() == 0
        assert session.get(AlertModel, "A1").case_id is None
        assert session.get(AlertModel, "A2").case_id is None


# ----------------------------------------------------------------- link


class TestLinkAlert:
    def test_link_adds_alert_and_event(self, svc):
        case = _create(svc, "A1")
        updated = svc.link_alert(case.case_id, "A3", actor=ACTOR)

        assert updated.alert_ids == ["A1", "A3"]
        assert updated.alert_count == 2
        assert updated.total_amount == 1250.0
        events = svc.list_events(case.case_id).events
        assert events[0].event_type == "alert_linked_to_case"
        assert events[0].alert_id == "A3"

    def test_relink_same_case_is_idempotent(self, svc):
        case = _create(svc, "A1")
        before = svc.list_events(case.case_id).total
        again = svc.link_alert(case.case_id, "A1", actor=ACTOR)
        assert again.alert_ids == ["A1"]
        assert svc.list_events(case.case_id).total == before

    def test_alert_in_other_open_case(self, svc):
        _create(svc, "A1")
        other = _create(svc, "A2")
        with pytest.raises(CaseConflictError) as exc:
            svc.link_alert(other.case_id, "A1", actor=ACTOR)
        assert exc.value.code == "alert_already_linked"

    def test_closed_case_rejects_alerts(self, svc):
        case = _create(svc, "A1")
        svc.update_case(case.case_id, CaseUpdate(status="closed"), actor=ACTOR)
        with pytest.raises(CaseConflictError) as exc:
            svc.link_alert(case.case_id, "A2", actor=ACTOR)
        assert exc.value.code == "case_not_open"

    def test_dismissed_alert(self, svc):
        case = _create(svc, "A1")
        with pytest.raises(CaseConflictError, match="dismissed"):
            svc.link_alert(case.case_id, "DISMISSED", actor=ACTOR)

    @pytest.mark.parametrize(("case_id", "alert_id"), [("CASE-NOPE", "A1"), (None, "NOPE")])
    def test_not_found(self, svc, case_id, alert_id):
        target = case_id or _create(svc, "A1").case_id
        with pytest.raises(CaseNotFoundError):
            svc.link_alert(target, alert_id, actor=ACTOR)


# ----------------------------------------------------------------- update


class TestUpdateCase:
    def test_each_change_writes_one_event_in_fixed_order(self, svc):
        case = _create(svc, "A1")
        updated = svc.update_case(
            case.case_id,
            CaseUpdate(
                status="investigating",
                priority="P1",
                assigned_to="analyst2",
                assigned_team="AML",
                note="Hesap yeni açılmış",
            ),
            actor=ACTOR,
        )

        assert updated.status == "investigating"
        assert updated.priority == "P1"
        assert updated.sla_due_at - updated.created_at == timedelta(hours=4)
        assert (updated.assigned_to, updated.assigned_team) == ("analyst2", "AML")
        assert (updated.notes_count, updated.last_note) == (1, "Hesap yeni açılmış")
        events = svc.list_events(case.case_id).events
        assert [e.event_type for e in events[:4]] == [
            "note_added",
            "case_assigned",
            "case_priority_changed",
            "case_status_changed",
        ]
        status_event = events[3]
        assert (status_event.previous_value, status_event.new_value) == ("new", "investigating")

    def test_no_op_update_writes_nothing(self, svc):
        case = _create(svc, "A1", priority="P3")
        before = svc.list_events(case.case_id).total
        svc.update_case(case.case_id, CaseUpdate(status="new", priority="P3"), actor=ACTOR)
        svc.update_case(case.case_id, CaseUpdate(note="   "), actor=ACTOR)
        assert svc.list_events(case.case_id).total == before

    def test_resolve_requires_resolution(self, svc):
        case = _create(svc, "A1")
        with pytest.raises(CaseRuleError) as exc:
            svc.update_case(case.case_id, CaseUpdate(status="resolved_true_positive"), actor=ACTOR)
        assert exc.value.code == "resolution_required"

    def test_resolve_then_reopen(self, svc):
        case = _create(svc, "A1")
        resolved = svc.update_case(
            case.case_id,
            CaseUpdate(status="resolved_false_positive", resolution="Bilinen müşteri"),
            actor=ACTOR,
        )
        assert resolved.resolved_by == ACTOR
        assert resolved.resolved_at is not None
        assert resolved.resolution == "Bilinen müşteri"
        assert resolved.sla_breached is False

        reopened = svc.update_case(case.case_id, CaseUpdate(status="investigating"), actor=ACTOR)
        assert reopened.resolved_at is None
        assert reopened.resolved_by is None

    def test_invalid_transition_rolls_back_other_changes(self, svc):
        case = _create(svc, "A1")
        svc.update_case(case.case_id, CaseUpdate(status="closed"), actor=ACTOR)
        before = svc.list_events(case.case_id).total

        with pytest.raises(CaseConflictError) as exc:
            svc.update_case(case.case_id, CaseUpdate(status="investigating", note="x"), actor=ACTOR)
        detail = exc.value.detail()
        assert (detail["from_status"], detail["to_status"]) == ("closed", "investigating")
        assert svc.list_events(case.case_id).total == before

    def test_tags_are_rejected(self, svc):
        case = _create(svc, "A1")
        with pytest.raises(CaseRuleError) as exc:
            svc.update_case(case.case_id, CaseUpdate(tags=["x"]), actor=ACTOR)
        assert exc.value.detail() == {
            "code": "unsupported_field",
            "message": "Tags cannot be changed with this endpoint",
            "field": "tags",
        }

    def test_resolution_text_without_status_change(self, svc):
        case = _create(svc, "A1")
        updated = svc.update_case(
            case.case_id, CaseUpdate(resolution="Ön değerlendirme"), actor=ACTOR
        )
        assert updated.resolution == "Ön değerlendirme"

    def test_team_only_assignment(self, svc):
        case = _create(svc, "A1", assigned_to="analyst1")
        updated = svc.assign(case.case_id, "analyst1", "Fraud-2", actor=ACTOR)
        assert (updated.assigned_to, updated.assigned_team) == ("analyst1", "Fraud-2")
        assert svc.list_events(case.case_id).events[0].event_type == "case_assigned"

    def test_unknown_case(self, svc):
        with pytest.raises(CaseNotFoundError):
            svc.update_case("CASE-NOPE", CaseUpdate(note="x"), actor=ACTOR)


# ----------------------------------------------------------------- reads


class TestEventsAndSla:
    def test_events_of_unknown_case_is_404(self, svc):
        with pytest.raises(CaseNotFoundError):
            svc.list_events("CASE-NOPE")

    def test_filter_and_pagination(self, svc):
        case = _create(svc, "A1", "A2", "A3")
        linked = svc.list_events(
            case.case_id, event_type=EventType.ALERT_LINKED_TO_CASE, page=2, page_size=2
        )
        assert linked.total == 3
        assert [e.alert_id for e in linked.events] == ["A1"]

    def test_long_notes_are_kept_in_full(self, svc):
        case = _create(svc, "A1")
        note = "n" * 4000
        svc.update_case(case.case_id, CaseUpdate(note=note), actor=ACTOR)
        assert svc.list_events(case.case_id).events[0].description == note

    def test_overdue_open_case_is_breached(self, svc, session):
        case = _create(svc, "A1")
        model = session.get(CaseModel, case.case_id)
        model.sla_due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()
        assert svc.update_case(case.case_id, CaseUpdate(), actor=ACTOR).sla_breached is True
