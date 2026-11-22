# SentinelFlow - scripts/seed_admin.py role option (SF-506)

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("sqlalchemy") is None,
    reason="sqlalchemy not installed",
)


@pytest.fixture()
def seed():
    path = Path(__file__).resolve().parents[1] / "scripts" / "seed_admin.py"
    spec = importlib.util.spec_from_file_location("seed_admin_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeAuthService:
    def __init__(self, users):
        self.users = users

    def __call__(self, _session):
        return self

    def _get_user_by_username(self, username):
        return self.users.get(username)

    def register(self, user_data):
        user = SimpleNamespace(
            username=user_data.username,
            user_id="USR-TEST",
            role=user_data.role,
            email=user_data.email,
            full_name=user_data.full_name,
        )
        self.users[user_data.username] = user
        return user


class _FakeSession:
    def __enter__(self):
        return object()

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def fake_db(seed, monkeypatch):
    users = {}
    monkeypatch.setattr(seed, "init_db", lambda: None)
    monkeypatch.setattr(seed, "DatabaseSession", _FakeSession)
    monkeypatch.setattr(seed, "AuthService", _FakeAuthService(users))
    for name in (
        "SEED_ADMIN_USERNAME",
        "SEED_ADMIN_EMAIL",
        "SEED_ADMIN_FULL_NAME",
        "SEED_ADMIN_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    return users


def test_default_role_is_admin_with_previous_defaults(seed):
    args = seed.parse_args([])
    assert args.role == "admin"
    assert not args.no_generate
    identity = seed.seed_identity(seed.UserRole.ADMIN, {})
    assert identity == {
        "username": "admin",
        "email": seed.DEFAULT_ADMIN_EMAIL,
        "full_name": "SentinelFlow Admin",
    }


def test_identity_defaults_follow_role(seed):
    identity = seed.seed_identity(seed.UserRole.ANALYST, {})
    assert identity == {
        "username": "analyst",
        "email": "analyst@example.com",
        "full_name": "SentinelFlow Analyst",
    }
    # The generated e-mail must pass the contract's validation.
    seed.UserCreate(password="Analyst123!", role=seed.UserRole.ANALYST, **identity)


def test_env_overrides_identity(seed):
    env = {
        "SEED_ADMIN_USERNAME": "demo-viewer",
        "SEED_ADMIN_EMAIL": "viewer@example.org",
        "SEED_ADMIN_FULL_NAME": "Demo Viewer",
    }
    assert seed.seed_identity(seed.UserRole.VIEWER, env) == {
        "username": "demo-viewer",
        "email": "viewer@example.org",
        "full_name": "Demo Viewer",
    }


@pytest.mark.parametrize("role", ["api", "root", ""])
def test_rejects_unseedable_roles(seed, role):
    with pytest.raises(SystemExit):
        seed.parse_args(["--role", role])


@pytest.mark.parametrize("role", ["admin", "analyst", "viewer"])
def test_main_creates_user_with_role(seed, fake_db, monkeypatch, role):
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "Seed12345!")
    assert seed.main(["--role", role, "--no-generate"]) == 0
    assert fake_db[role].role == seed.UserRole(role)


def test_main_never_changes_existing_user(seed, fake_db, monkeypatch):
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "Seed12345!")
    monkeypatch.setenv("SEED_ADMIN_USERNAME", "shared")
    assert seed.main(["--role", "viewer", "--no-generate"]) == 0
    assert seed.main(["--role", "admin", "--no-generate"]) == 0
    assert fake_db["shared"].role == seed.UserRole.VIEWER


def test_main_requires_password_with_no_generate(seed, fake_db):
    assert seed.main(["--role", "analyst", "--no-generate"]) == 1
    assert fake_db == {}
