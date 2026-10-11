# =============================================================================
# SentinelFlow - Case API Route Tests (SF-307)
# =============================================================================
"""
HTTP-level tests for the case workflow: status codes and error bodies from
docs/contracts/sprint3-case-api.md, the viewer/analyst/admin RBAC matrix,
audit timeline pagination/filtering and the published OpenAPI schema.
"""

import pytest
from case_db import add_alert, make_engine, make_session
from fastapi.testclient import TestClient

from sentinelflow.api.app import app
from sentinelflow.api.deps import get_db_session
from sentinelflow.auth.service import AuthService
from sentinelflow.contracts import UserCreate, UserRole
from sentinelflow.database.models import CaseEventModel, CaseModel

BASE = "/api/v1/cases"
ROLES = ("viewer", "analyst", "admin", "api")


@pytest.fixture()
def api():
    engine = make_engine()
    session = make_session(engine)
    auth = AuthService(session)
    tokens = {}
    for role in ROLES:
        auth.register(
            UserCreate(
                username=f"{role}1",
                email=f"{role}@example.com",
                password="Password123",
                full_name=f"{role.title()} User",
                role=UserRole(role),
            )
        )
        session.commit()
        tokens[role] = auth._create_access_token(auth._get_user_by_username(f"{role}1"))
    for i, alert_id in enumerate(("A1", "A2", "A3")):
        add_alert(session, alert_id, amount=100.0 * (i + 1), minutes=i)
    add_alert(session, "DISMISSED", dismissed=True)

    def _session():
        yield session

    app.dependency_overrides[get_db_session] = _session
    client = TestClient(app)
    client.session = session
    client.headers_for = lambda role: {"Authorization": f"Bearer {tokens[role]}"}
    yield client
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def _create(api, *alert_ids, role="analyst", **extra):
    body = {"title": "Ring", "alert_ids": list(alert_ids), **extra}
    return api.post(BASE, json=body, headers=api.headers_for(role))


# ----------------------------------------------------------------- create


class TestCreateCase:
    def test_201_with_full_case(self, api):
        res = _create(api, "A1", "A2", priority="P1")
        assert res.status_code == 201
        body = res.json()
        assert body["alert_ids"] == ["A1", "A2"]
        assert body["alert_count"] == 2
        assert body["total_amount"] == 300.0
        assert body["sla_due_at"].endswith("+00:00")
        assert body["created_at"].endswith("+00:00")

    def test_events_record_the_caller(self, api):
        case_id = _create(api, "A1", role="admin").json()["case_id"]
        res = api.get(f"{BASE}/{case_id}/events", headers=api.headers_for("viewer"))
        assert {e["actor"] for e in res.json()["events"]} == {"admin1"}

    def test_missing_alert_404_lists_ids(self, api):
        res = _create(api, "A1", "NOPE-1")
        assert res.status_code == 404
        assert res.json() == {"detail": "Alert(s) not found: NOPE-1"}
        assert api.session.query(CaseModel).count() == 0

    def test_double_submit_409_points_to_first_case(self, api):
        first = _create(api, "A1").json()["case_id"]
        res = _create(api, "A1")
        assert res.status_code == 409
        assert res.json()["detail"] == {
            "code": "alert_already_linked",
            "message": f"Alert A1 is already linked to open case {first}",
            "alert_id": "A1",
            "case_id": first,
        }
        assert api.session.query(CaseModel).count() == 1

    def test_dismissed_alert_409(self, api):
        res = _create(api, "DISMISSED")
        assert res.status_code == 409
        assert res.json()["detail"]["code"] == "alert_dismissed"

    @pytest.mark.parametrize(
        "body",
        [
            {"title": "", "alert_ids": ["A1"]},
            {"title": "x", "alert_ids": []},
            {"title": "x"},
            {"title": "x", "alert_ids": ["A1"], "priority": "P9"},
        ],
    )
    def test_body_validation_422(self, api, body):
        res = api.post(BASE, json=body, headers=api.headers_for("analyst"))
        assert res.status_code == 422


# ----------------------------------------------------------------- link


class TestLinkAlert:
    def test_link_and_idempotent_relink(self, api):
        case_id = _create(api, "A1").json()["case_id"]
        url = f"{BASE}/{case_id}/alerts"
        headers = api.headers_for("analyst")

        first = api.post(url, json={"alert_id": "A2"}, headers=headers)
        again = api.post(url, json={"alert_id": "A2"}, headers=headers)

        assert first.status_code == again.status_code == 200
        assert again.json()["alert_ids"] == ["A1", "A2"]
        linked = api.get(
            f"{BASE}/{case_id}/events",
            params={"event_type": "alert_linked_to_case"},
            headers=headers,
        ).json()
        assert linked["total"] == 2

    def test_deprecated_alias_uses_same_rules(self, api):
        case_id = _create(api, "A1").json()["case_id"]
        other = _create(api, "A2").json()["case_id"]
        res = api.post(f"{BASE}/{other}/add-alert/A1", headers=api.headers_for("analyst"))
        assert res.status_code == 409
        assert res.json()["detail"]["case_id"] == case_id

    def test_closed_case_409(self, api):
        case_id = _create(api, "A1").json()["case_id"]
        headers = api.headers_for("analyst")
        api.patch(f"{BASE}/{case_id}", json={"status": "closed"}, headers=headers)
        res = api.post(f"{BASE}/{case_id}/alerts", json={"alert_id": "A2"}, headers=headers)
        assert res.status_code == 409
        assert res.json()["detail"]["code"] == "case_not_open"

    @pytest.mark.parametrize(("case_id", "alert_id"), [("CASE-NOPE", "A1"), (None, "NOPE")])
    def test_404(self, api, case_id, alert_id):
        target = case_id or _create(api, "A1").json()["case_id"]
        res = api.post(
            f"{BASE}/{target}/alerts",
            json={"alert_id": alert_id},
            headers=api.headers_for("analyst"),
        )
        assert res.status_code == 404


# ----------------------------------------------------------------- update


class TestUpdateCase:
    def test_patch_changes_and_events(self, api):
        case_id = _create(api, "A1").json()["case_id"]
        headers = api.headers_for("analyst")
        res = api.patch(
            f"{BASE}/{case_id}",
            json={"status": "triage", "priority": "P2", "assigned_to": "analyst1", "note": "ok"},
            headers=headers,
        )
        assert res.status_code == 200
        body = res.json()
        assert (body["status"], body["priority"], body["assigned_to"]) == (
            "triage",
            "P2",
            "analyst1",
        )
        types = [
            e["event_type"]
            for e in api.get(f"{BASE}/{case_id}/events", headers=headers).json()["events"]
        ]
        assert types[:4] == [
            "note_added",
            "case_assigned",
            "case_priority_changed",
            "case_status_changed",
        ]

    def test_invalid_transition_409(self, api):
        case_id = _create(api, "A1").json()["case_id"]
        headers = api.headers_for("analyst")
        api.patch(f"{BASE}/{case_id}", json={"status": "closed"}, headers=headers)
        res = api.patch(f"{BASE}/{case_id}", json={"status": "new"}, headers=headers)
        assert res.status_code == 409
        assert res.json()["detail"]["code"] == "invalid_status_transition"

    @pytest.mark.parametrize(
        ("body", "code"),
        [
            ({"status": "resolved_true_positive"}, "resolution_required"),
            ({"tags": ["x"]}, "unsupported_field"),
        ],
    )
    def test_business_rule_422(self, api, body, code):
        case_id = _create(api, "A1").json()["case_id"]
        res = api.patch(f"{BASE}/{case_id}", json=body, headers=api.headers_for("analyst"))
        assert res.status_code == 422
        assert res.json()["detail"]["code"] == code

    def test_unknown_status_value_422(self, api):
        case_id = _create(api, "A1").json()["case_id"]
        res = api.patch(
            f"{BASE}/{case_id}", json={"status": "archived"}, headers=api.headers_for("analyst")
        )
        assert res.status_code == 422

    def test_assign_endpoint(self, api):
        case_id = _create(api, "A1").json()["case_id"]
        res = api.post(
            f"{BASE}/{case_id}/assign",
            params={"assigned_to": "analyst1", "assigned_team": "AML"},
            headers=api.headers_for("analyst"),
        )
        assert res.status_code == 200
        assert res.json()["assigned_team"] == "AML"

    def test_patch_unknown_case_404(self, api):
        res = api.patch(f"{BASE}/CASE-NOPE", json={"note": "x"}, headers=api.headers_for("admin"))
        assert res.status_code == 404


# ----------------------------------------------------------------- timeline


class TestTimeline:
    def test_pagination_newest_first(self, api):
        case_id = _create(api, "A1", "A2", "A3").json()["case_id"]
        headers = api.headers_for("viewer")
        url = f"{BASE}/{case_id}/events"

        page1 = api.get(url, params={"page": 1, "page_size": 3}, headers=headers).json()
        page2 = api.get(url, params={"page": 2, "page_size": 3}, headers=headers).json()

        assert (page1["total"], page1["page"], page1["page_size"]) == (4, 1, 3)
        assert [e["alert_id"] for e in page1["events"]] == ["A3", "A2", "A1"]
        assert [e["event_type"] for e in page2["events"]] == ["case_created"]
        stamps = [e["created_at"] for e in page1["events"] + page2["events"]]
        assert stamps == sorted(stamps, reverse=True)

    def test_event_fields_exclude_request_metadata(self, api):
        case_id = _create(api, "A1").json()["case_id"]
        event = api.get(f"{BASE}/{case_id}/events", headers=api.headers_for("viewer")).json()[
            "events"
        ][0]
        assert set(event) == {
            "event_id",
            "case_id",
            "event_type",
            "actor",
            "actor_type",
            "description",
            "previous_value",
            "new_value",
            "alert_id",
            "created_at",
        }

    @pytest.mark.parametrize("params", [{"event_type": "bogus"}, {"page": 0}, {"page_size": 101}])
    def test_invalid_query_422(self, api, params):
        case_id = _create(api, "A1").json()["case_id"]
        res = api.get(f"{BASE}/{case_id}/events", params=params, headers=api.headers_for("viewer"))
        assert res.status_code == 422

    def test_unknown_case_404(self, api):
        res = api.get(f"{BASE}/CASE-NOPE/events", headers=api.headers_for("viewer"))
        assert res.status_code == 404

    def test_events_survive_only_committed_requests(self, api):
        _create(api, "A1")
        _create(api, "A1")  # 409, must not leave events behind
        assert api.session.query(CaseEventModel).count() == 2


# ----------------------------------------------------------------- RBAC


WRITE_CALLS = [
    ("post", BASE, {"json": {"title": "x", "alert_ids": ["A2"]}}),
    ("patch", f"{BASE}/{{case_id}}", {"json": {"note": "x"}}),
    ("post", f"{BASE}/{{case_id}}/alerts", {"json": {"alert_id": "A2"}}),
    ("post", f"{BASE}/{{case_id}}/add-alert/A2", {}),
    ("post", f"{BASE}/{{case_id}}/assign", {"params": {"assigned_to": "analyst1"}}),
]
READ_CALLS = [
    ("get", BASE, {}),
    ("get", f"{BASE}/stats", {}),
    ("get", f"{BASE}/{{case_id}}", {}),
    ("get", f"{BASE}/{{case_id}}/events", {}),
]


class TestRbacMatrix:
    @pytest.fixture()
    def case_id(self, api):
        return _create(api, "A1").json()["case_id"]

    @pytest.mark.parametrize(("method", "url", "kwargs"), WRITE_CALLS + READ_CALLS)
    def test_unauthenticated_401(self, api, case_id, method, url, kwargs):
        res = getattr(api, method)(url.format(case_id=case_id), **kwargs)
        assert res.status_code == 401

    @pytest.mark.parametrize("role", ["viewer", "api"])
    @pytest.mark.parametrize(("method", "url", "kwargs"), WRITE_CALLS)
    def test_writes_forbidden(self, api, case_id, role, method, url, kwargs):
        res = getattr(api, method)(
            url.format(case_id=case_id), headers=api.headers_for(role), **kwargs
        )
        assert res.status_code == 403

    @pytest.mark.parametrize("role", ["analyst", "admin"])
    @pytest.mark.parametrize(("method", "url", "kwargs"), WRITE_CALLS)
    def test_writes_allowed(self, api, case_id, role, method, url, kwargs):
        res = getattr(api, method)(
            url.format(case_id=case_id), headers=api.headers_for(role), **kwargs
        )
        assert res.status_code in (200, 201)

    @pytest.mark.parametrize("role", ["viewer", "analyst", "admin"])
    @pytest.mark.parametrize(("method", "url", "kwargs"), READ_CALLS)
    def test_reads_allowed(self, api, case_id, role, method, url, kwargs):
        res = getattr(api, method)(
            url.format(case_id=case_id), headers=api.headers_for(role), **kwargs
        )
        assert res.status_code == 200

    def test_viewer_write_leaves_no_trace(self, api, case_id):
        before = api.session.query(CaseEventModel).count()
        api.patch(f"{BASE}/{case_id}", json={"note": "x"}, headers=api.headers_for("viewer"))
        assert api.session.query(CaseEventModel).count() == before


# ----------------------------------------------------------------- OpenAPI


class TestOpenApiContract:
    @pytest.fixture(scope="class")
    def spec(self):
        return app.openapi()

    def test_status_codes(self, spec):
        paths = spec["paths"]
        assert set(paths[BASE]["post"]["responses"]) >= {"201", "404", "409", "422"}
        assert set(paths[f"{BASE}/{{case_id}}"]["patch"]["responses"]) >= {
            "200",
            "404",
            "409",
            "422",
        }
        assert set(paths[f"{BASE}/{{case_id}}/alerts"]["post"]["responses"]) >= {
            "200",
            "404",
            "409",
        }
        assert set(paths[f"{BASE}/{{case_id}}/events"]["get"]["responses"]) >= {"200", "404"}

    def test_deprecated_alias(self, spec):
        assert spec["paths"][f"{BASE}/{{case_id}}/add-alert/{{alert_id}}"]["post"]["deprecated"]

    def test_response_models(self, spec):
        paths, schemas = spec["paths"], spec["components"]["schemas"]

        def ref(op, code):
            content = op["responses"][code]["content"]["application/json"]["schema"]
            return content["$ref"].rsplit("/", 1)[-1]

        assert ref(paths[f"{BASE}/{{case_id}}/events"]["get"], "200") == "CaseEventListResponse"
        assert ref(paths[BASE]["post"], "409") == "ApiErrorResponse"
        assert set(schemas["CaseEventOut"]["properties"]) == {
            "event_id",
            "case_id",
            "event_type",
            "actor",
            "actor_type",
            "description",
            "previous_value",
            "new_value",
            "alert_id",
            "created_at",
        }
        assert {"code", "message", "alert_id", "case_id"} <= set(
            schemas["ApiErrorDetail"]["properties"]
        )
        assert "alert_linked_to_case" in schemas["EventType"]["enum"]


class TestLegacyAlertLinkEndpoint:
    """POST /alerts/{alert_id}/link-case/{case_id} must follow the same case rules."""

    @staticmethod
    def _link(api, alert_id, case_id, role="analyst"):
        return api.post(
            f"/api/v1/alerts/{alert_id}/link-case/{case_id}", headers=api.headers_for(role)
        )

    def test_links_with_aggregates_and_real_actor(self, api):
        case_id = _create(api, "A1").json()["case_id"]
        res = self._link(api, "A2", case_id, role="admin")
        assert res.status_code == 200
        body = res.json()
        assert body["alert_ids"] == ["A1", "A2"]
        assert body["alert_count"] == 2
        assert body["total_amount"] == 300.0
        event = api.get(f"{BASE}/{case_id}/events", headers=api.headers_for("viewer")).json()[
            "events"
        ][0]
        assert (event["event_type"], event["alert_id"], event["actor"]) == (
            "alert_linked_to_case",
            "A2",
            "admin1",
        )

    def test_cannot_move_alert_out_of_open_case(self, api):
        first = _create(api, "A1").json()["case_id"]
        other = _create(api, "A2").json()["case_id"]
        res = self._link(api, "A1", other)
        assert res.status_code == 409
        assert res.json()["detail"]["code"] == "alert_already_linked"
        assert res.json()["detail"]["case_id"] == first

    def test_closed_case_and_dismissed_alert(self, api):
        case_id = _create(api, "A1").json()["case_id"]
        assert self._link(api, "DISMISSED", case_id).json()["detail"]["code"] == "alert_dismissed"
        api.patch(f"{BASE}/{case_id}", json={"status": "closed"}, headers=api.headers_for("admin"))
        assert self._link(api, "A2", case_id).json()["detail"]["code"] == "case_not_open"

    def test_unknown_case_is_404_not_fk_error(self, api):
        assert self._link(api, "A1", "CASE-NOPE").status_code == 404

    def test_viewer_forbidden(self, api):
        case_id = _create(api, "A1").json()["case_id"]
        assert self._link(api, "A2", case_id, role="viewer").status_code == 403

    def test_marked_deprecated_in_openapi(self):
        op = app.openapi()["paths"]["/api/v1/alerts/{alert_id}/link-case/{case_id}"]["post"]
        assert op["deprecated"] is True
