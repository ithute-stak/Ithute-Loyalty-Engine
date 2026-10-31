"""Authenticated human RBAC with tenant- and branch-scoped grants."""
import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import text

from loyalty_api.db import SessionLocal
from loyalty_api.oidc import authenticate_human
from loyalty_api.permissions import Permission, has_permission
from loyalty_api.tenant import tenant_transaction


@dataclass(frozen=True)
class RoleGrant:
    code: str
    branch_id: uuid.UUID | None


async def authorized_user(token: str, company_id: uuid.UUID, permission: Permission,
                          branch_id: uuid.UUID | None = None):
    principal = await authenticate_human(token, company_id)
    async with SessionLocal() as session:
        async with tenant_transaction(session, company_id):
            result = await session.execute(text("""
                SELECT r.code, ur.branch_id FROM company_user_roles ur
                JOIN company_roles r ON r.id=ur.role_id AND r.tenant_id=ur.tenant_id
                WHERE ur.tenant_id=:tenant_id AND ur.user_id=:user_id
            """), {"tenant_id": company_id, "user_id": principal.user_id})
            grants = [RoleGrant(r.code, r.branch_id) for r in result]
    if not authorized_grants(grants, permission, branch_id):
        raise HTTPException(status_code=403, detail="insufficient permission")
    return principal


def authorized_grants(grants: list[RoleGrant], permission: Permission,
                      branch_id: uuid.UUID | None = None) -> bool:
    """Unscoped operations require an explicitly company-wide grant.

    For branch operations, company-wide OR a matching branch grant is accepted.
    """
    return any(
        has_permission({grant.code}, permission)
        and (grant.branch_id is None or (branch_id is not None and grant.branch_id == branch_id))
        for grant in grants
    )


def parse_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="bearer token required")
    token = authorization[7:]
    if not token or len(token) > 8192 or token.strip() != token:
        raise HTTPException(status_code=401, detail="invalid access token")
    return token
