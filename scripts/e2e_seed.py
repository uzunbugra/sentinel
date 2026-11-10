# =============================================================================
# SentinelFlow - Browser test data (SF-404)
# =============================================================================
"""
Prepares and removes the data the Playwright tests use, straight in the database.

Usage:
    python scripts/e2e_seed.py users            # e2e_analyst and e2e_viewer
    python scripts/e2e_seed.py alert --tag T    # one rule alert, prints {"alert_id": ...}
    python scripts/e2e_seed.py cleanup --tag T  # removes T's alerts, cases and events

The database name must contain ``e2e`` (e.g. ``sentinelflow_e2e``), so a ``.env`` that
points at the development database is refused instead of filled with test accounts.

The users' password is read from ``E2E_PASSWORD`` (required). Running ``users`` again
resets the password, role and lockout, so a test run never depends on an earlier one.

Every alert carries its tag in the transaction id (``TX-E2E-<tag>``) and the sender
name, so a test finds only its own alert and ``cleanup`` removes only its own data.
The alert is a ``structuring`` rule alert: the browser tests cover the analyst
workflow, not the model (the model is covered by the ML tests and the SF-403 demo).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from sqlalchemy import delete, select
from sqlalchemy.engine import make_url

from sentinelflow.auth.password import hash_password
from sentinelflow.auth.service import AuthService
from sentinelflow.contracts import UserCreate, UserRole
from sentinelflow.database.models import AlertModel, CaseEventModel, CaseModel
from sentinelflow.database.postgres import DatabaseSession, get_database_url, init_db
from sentinelflow.processor.alert_writer import create_alert_from_detection
from sentinelflow.repository import AlertRepository

USERS = {"e2e_analyst": UserRole.ANALYST, "e2e_viewer": UserRole.VIEWER}
TAG_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,40}$")


def _require_test_database() -> None:
    """Refuse to write e2e users and alerts into a database not named for tests."""
    database = make_url(get_database_url()).database or ""
    if "e2e" not in database.lower():
        raise SystemExit(
            f"refusing to seed database {database!r}: its name must contain 'e2e' "
            "(see sentinelflow-web/e2e/README.md)"
        )


def _password() -> str:
    password = os.getenv("E2E_PASSWORD", "")
    if not password:
        raise SystemExit("E2E_PASSWORD is not set")
    return password


def ensure_users() -> None:
    password = _password()
    with DatabaseSession() as session:
        service = AuthService(session)
        for username, role in USERS.items():
            user = service._get_user_by_username(username)
            if user is None:
                service.register(
                    UserCreate(
                        username=username,
                        email=f"{username}@example.com",
                        password=password,
                        full_name=f"E2E {role.value}",
                        role=role,
                    )
                )
            else:
                user.password_hash = hash_password(password)
                user.role = role.value
                user.status = "active"
                user.failed_login_attempts = 0
                user.locked_until = None
        session.commit()
    print(json.dumps({"users": sorted(USERS)}))


def create_alert(tag: str) -> None:
    tx = {
        "transaction_id": f"TX-E2E-{tag}",
        "sender_iban": "TR000000000000000000000001",
        "sender_name": f"E2E Gonderen {tag}",
        "receiver_iban": "TR000000000000000000000002",
        "receiver_name": "E2E Alici",
        "amount": 49500,
        "currency": "TRY",
    }
    with DatabaseSession() as session:
        alert = AlertRepository(session).create(
            create_alert_from_detection(
                "structuring", "high", 0.9, tx, f"SF-404 tarayici testi alarmi ({tag})"
            )
        )
        session.commit()
        print(json.dumps({"alert_id": alert.alert_id, "sender_name": tx["sender_name"]}))


def cleanup(tag: str) -> None:
    with DatabaseSession() as session:
        alerts = session.scalars(
            select(AlertModel).where(AlertModel.transaction_id == f"TX-E2E-{tag}")
        ).all()
        alert_ids = [a.alert_id for a in alerts]
        case_ids = sorted({a.case_id for a in alerts if a.case_id})
        if case_ids:
            session.execute(delete(CaseEventModel).where(CaseEventModel.case_id.in_(case_ids)))
        if alert_ids:
            session.execute(delete(AlertModel).where(AlertModel.alert_id.in_(alert_ids)))
        if case_ids:
            session.execute(delete(CaseModel).where(CaseModel.case_id.in_(case_ids)))
        session.commit()
    print(json.dumps({"alerts": len(alert_ids), "cases": len(case_ids)}))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("users")
    for name in ("alert", "cleanup"):
        sub.add_parser(name).add_argument("--tag", required=True)
    args = parser.parse_args(argv)

    if getattr(args, "tag", None) is not None and not TAG_PATTERN.match(args.tag):
        parser.error("--tag: letters, digits and '-' only, at most 40 characters")

    _require_test_database()
    init_db()
    if args.command == "users":
        ensure_users()
    elif args.command == "alert":
        create_alert(args.tag)
    else:
        cleanup(args.tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
