# =============================================================================
# SentinelFlow - JWT & Refresh Token Lifecycle Tests
# =============================================================================
"""
Unit tests for AuthService token handling: creation, validation, expiry,
tampering and algorithm confusion. Runs against an
in-memory SQLite database; no external services.
"""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from sentinelflow.auth.config import auth_config
from sentinelflow.auth.service import AuthService
from sentinelflow.contracts import UserCreate, UserRole


@pytest.fixture()
def auth_service():
    from sqlalchemy import create_engine
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from sentinelflow.database.models import RefreshTokenModel, UserModel

    def _visit_jsonb(self, type_, **kw):
        return self.visit_JSON(type_, **kw)

    SQLiteTypeCompiler.visit_JSONB = _visit_jsonb  # UserModel uses PostgreSQL JSONB
    assert JSONB  # imported for the compiler patch above

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    UserModel.__table__.create(engine)
    RefreshTokenModel.__table__.create(engine)
    session = sessionmaker(bind=engine)()

    svc = AuthService(session)
    svc.register(
        UserCreate(
            username="analyst1",
            email="analyst@example.com",
            password="Analyst123",
            full_name="Analyst User",
            role=UserRole.ANALYST,
        )
    )
    session.commit()
    yield svc
    session.close()
    engine.dispose()


def _b64(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _encode(payload: dict) -> str:
    import jwt

    return jwt.encode(payload, auth_config.SECRET_KEY, algorithm=auth_config.ALGORITHM)


def _claims(**overrides) -> dict:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "user-1",
        "username": "analyst1",
        "role": "analyst",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "type": "access",
    }
    claims.update(overrides)
    return claims


class TestAccessToken:
    def test_login_issues_valid_access_token(self, auth_service):
        tokens = auth_service.login("analyst1", "Analyst123")
        payload = auth_service.validate_token(tokens.access_token)

        assert payload is not None
        assert payload.username == "analyst1"
        assert payload.role == "analyst"
        assert payload.type == "access"
        assert payload.exp - payload.iat == auth_config.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        assert tokens.expires_in == auth_config.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    def test_token_header_uses_configured_algorithm(self, auth_service):
        tokens = auth_service.login("analyst1", "Analyst123")
        header = json.loads(base64.urlsafe_b64decode(tokens.access_token.split(".")[0] + "=="))
        assert header["alg"] == auth_config.ALGORITHM

    def test_get_user_from_token(self, auth_service):
        tokens = auth_service.login("analyst1", "Analyst123")
        user = auth_service.get_user_from_token(tokens.access_token)
        assert user is not None and user.username == "analyst1"

    def test_expired_token_rejected(self, auth_service):
        past = datetime.now(timezone.utc) - timedelta(minutes=10)
        token = _encode(
            _claims(
                iat=int(past.timestamp()),
                exp=int((past + timedelta(minutes=1)).timestamp()),
            )
        )
        assert auth_service.validate_token(token) is None

    def test_tampered_payload_rejected(self, auth_service):
        token = auth_service.login("analyst1", "Analyst123").access_token
        header, _, signature = token.split(".")
        forged = f"{header}.{_b64(_claims(role='admin'))}.{signature}"
        assert auth_service.validate_token(forged) is None

    def test_wrong_secret_rejected(self, auth_service):
        import jwt

        token = jwt.encode(_claims(), "x" * 48, algorithm=auth_config.ALGORITHM)
        assert auth_service.validate_token(token) is None

    def test_unsigned_none_algorithm_rejected(self, auth_service):
        token = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(_claims(role='admin'))}."
        assert auth_service.validate_token(token) is None

    @pytest.mark.parametrize("garbage", ["", "not-a-jwt", "a.b.c", "a.b"])
    def test_malformed_token_rejected(self, auth_service, garbage):
        assert auth_service.validate_token(garbage) is None
