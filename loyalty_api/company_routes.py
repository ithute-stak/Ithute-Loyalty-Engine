"""Read-only human administration endpoints; user writes remain disabled."""
import uuid

from fastapi import APIRouter, Header
from sqlalchemy import text

from loyalty_api.access import authorized_user, parse_bearer
from loyalty_api.db import SessionLocal
from loyalty_api.permissions import Permission
from loyalty_api.tenant import tenant_transaction

router = APIRouter(prefix="/v1/companies", tags=["company-access"])


@router.get("/{company_id}/users")
async def list_company_users(company_id: uuid.UUID, authorization: str | None = Header(default=None)):
    principal = await authorized_user(parse_bearer(authorization), company_id, Permission.USERS_MANAGE)
    async with SessionLocal() as session:
        async with tenant_transaction(session, principal.tenant_id):
            rows = (await session.execute(text("""
                SELECT id, display_name, status FROM company_users
                WHERE tenant_id=:tenant_id ORDER BY created_at, id LIMIT 100
            """), {"tenant_id": principal.tenant_id})).mappings().all()
    return {"items": [{"id": str(r["id"]), "display_name": r["display_name"],
                       "status": r["status"]} for r in rows]}


@router.get("/{company_id}/branches/{branch_id}")
async def branch_detail(company_id: uuid.UUID, branch_id: uuid.UUID,
                        authorization: str | None = Header(default=None)):
    principal = await authorized_user(
        parse_bearer(authorization), company_id, Permission.BRANCH_READ, branch_id
    )
    async with SessionLocal() as session:
        async with tenant_transaction(session, principal.tenant_id):
            row = (await session.execute(text("""
                SELECT id, code, name FROM branches
                WHERE tenant_id=:tenant_id AND id=:branch_id
            """), {"tenant_id": principal.tenant_id, "branch_id": branch_id})).mappings().one_or_none()
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="branch not found")
    return {"id": str(row["id"]), "code": row["code"], "name": row["name"]}
