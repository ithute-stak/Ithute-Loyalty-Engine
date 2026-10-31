"""Invitation token creation and validation helpers.

Invitation endpoints remain disabled until provider-specific subject binding,
restricted DB grants, and two-tenant tests are complete.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from loyalty_api.permissions import ROLE_PERMISSIONS

INVITABLE_ROLES = frozenset({"administrator", "branch_manager", "cashier", "auditor"})


def create_invitation_token() -> tuple[str, str]:
    token = "ili_" + secrets.token_urlsafe(36)
    return token, hash_invitation_token(token)


def hash_invitation_token(token: str) -> str:
    if not isinstance(token, str) or len(token) > 256 or not token.startswith("ili_"):
        raise ValueError("invalid invitation token")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def invitation_expires_at(hours: int = 48) -> datetime:
    if not 1 <= hours <= 168:
        raise ValueError("invitation lifetime out of range")
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def validate_invitation_role(role: str) -> str:
    if role not in INVITABLE_ROLES or role not in ROLE_PERMISSIONS:
        raise ValueError("role not allowed for invitation")
    return role
