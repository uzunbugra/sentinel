# =============================================================================
# SentinelFlow - Seed Admin (or demo) User
# =============================================================================
"""
Creates the initial admin user, or a demo analyst/viewer account.

Usage:
    python scripts/seed_admin.py [--role admin|analyst|viewer] [--no-generate]

Credentials are read from environment variables (or .env). The SEED_ADMIN_*
names are kept for every role so existing setups keep working:
    SEED_ADMIN_USERNAME  (default: the role name, e.g. "analyst")
    SEED_ADMIN_EMAIL     (default: <role>@example.com)
    SEED_ADMIN_PASSWORD  (REQUIRED, or auto-generated unless --no-generate)
    SEED_ADMIN_FULL_NAME (default: "SentinelFlow <Role>")

The script is idempotent: an existing username is never modified, even if
its role differs from --role (the difference is reported).
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from collections.abc import Mapping, Sequence

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from loguru import logger

from sentinelflow.auth.service import AuthService
from sentinelflow.contracts import UserCreate, UserRole
from sentinelflow.database.postgres import DatabaseSession, init_db

# Reserved documentation domain (RFC 2606): passes email validation, which
# rejects special-use domains such as ".local".
DEFAULT_ADMIN_EMAIL = "admin@example.com"

SEEDABLE_ROLES = (UserRole.ADMIN, UserRole.ANALYST, UserRole.VIEWER)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an admin or demo user.")
    parser.add_argument(
        "--role",
        choices=[role.value for role in SEEDABLE_ROLES],
        default=UserRole.ADMIN.value,
        help="Role of the account to create (default: admin).",
    )
    parser.add_argument(
        "--no-generate",
        action="store_true",
        help="Fail instead of generating a password when SEED_ADMIN_PASSWORD is unset.",
    )
    return parser.parse_args(argv)


def seed_identity(role: UserRole, env: Mapping[str, str]) -> dict[str, str]:
    """Username, e-mail and full name for ``role``, honouring SEED_ADMIN_*."""
    username = env.get("SEED_ADMIN_USERNAME") or role.value
    email = env.get("SEED_ADMIN_EMAIL") or f"{role.value}@example.com"
    full_name = env.get("SEED_ADMIN_FULL_NAME") or f"SentinelFlow {role.value.title()}"
    return {"username": username, "email": email, "full_name": full_name}


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    role = UserRole(args.role)
    identity = seed_identity(role, os.environ)
    username = identity["username"]
    password = os.getenv("SEED_ADMIN_PASSWORD", "")

    if not password:
        if args.no_generate:
            logger.error(
                "SEED_ADMIN_PASSWORD is not set. Set it in the environment "
                "or run without --no-generate to auto-generate a password."
            )
            return 1
        password = secrets.token_urlsafe(24)
        logger.warning(
            "SEED_ADMIN_PASSWORD was not set; generated a random password "
            f"for '{username}': {password}  (store it securely!)"
        )

    init_db()

    with DatabaseSession() as session:
        auth_service = AuthService(session)

        existing = auth_service._get_user_by_username(username)
        if existing:
            existing_role = getattr(existing.role, "value", existing.role)
            if existing_role != role.value:
                logger.warning(
                    f"User '{username}' already exists with role '{existing_role}' "
                    f"(requested '{role.value}'); not changing it"
                )
            else:
                logger.info(f"User '{username}' already exists, skipping seed")
            return 0

        user = auth_service.register(UserCreate(password=password, role=role, **identity))
        logger.info(f"{role.value.title()} user created: {user.username} ({user.user_id})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
