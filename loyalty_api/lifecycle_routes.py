"""Audited company account lifecycle operations.

These mutations re-check permissions under a tenant-scoped transaction.
Owner changes require an owner grant; the last active owner is protected.
"""
import uuid
from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import text

from loyalty_api.access import authorized_user, parse_bearer
from loyalty_api.db import SessionLocal
from loyalty_api.permissions import Permission
from loyalty_api.tenant import tenant_transaction

router = APIRouter(prefix="/v1/companies", tags=["company-lifecycle"])


async def _owner_role(session, tenant_id, user_id):
    return bool((await session.execute(text("""
        SELECT 1 FROM company_user_roles ur
        JOIN company_roles r ON r.id=ur.role_id AND r.tenant_id=ur.tenant_id
        WHERE ur.tenant_id=:tenant AND ur.user_id=:user AND r.code='owner'
          AND ur.branch_id IS NULL LIMIT 1
    """), {"tenant": tenant_id, "user": user_id})).scalar_one_or_none())


async def _assert_owner_survives(session, tenant_id, target_id, removing_owner):
    if not removing_owner:
        return
    # Serialize owner mutations, including concurrent requests to remove different owners.
    await session.execute(text("SELECT id FROM tenants WHERE id=:tenant FOR UPDATE"), {"tenant": tenant_id})
    remaining = (await session.execute(text("""
        SELECT count(DISTINCT u.id) FROM company_users u
        JOIN company_user_roles ur ON ur.user_id=u.id AND ur.tenant_id=u.tenant_id
        JOIN company_roles r ON r.id=ur.role_id AND r.tenant_id=ur.tenant_id
        WHERE u.tenant_id=:tenant AND u.status='active' AND u.id<>:target
          AND r.code='owner' AND ur.branch_id IS NULL
    """), {"tenant": tenant_id, "target": target_id})).scalar_one()
    if remaining < 1:
        raise HTTPException(status_code=409, detail="last active owner cannot be removed")


async def _audit(session, tenant, actor, event, subject=None):
    await session.execute(text("""
        INSERT INTO company_audit_events(id, tenant_id, actor_id, event_type, subject_id)
        VALUES (:id,:tenant,:actor,:event,:subject)
    """), {"id": uuid.uuid4(), "tenant": tenant, "actor": actor, "event": event, "subject": subject})


@router.post("/{company_id}/users/{user_id}/suspend")
async def suspend_user(company_id: uuid.UUID, user_id: uuid.UUID,
                       authorization: str | None = Header(default=None)):
    principal = await authorized_user(parse_bearer(authorization), company_id, Permission.USERS_MANAGE)
    if user_id == principal.user_id:
        raise HTTPException(status_code=409, detail="cannot suspend own account")
    async with SessionLocal() as session:
        async with tenant_transaction(session, company_id):
            # Serializes all owner-affecting mutations even if target role changes concurrently.
            await session.execute(text("SELECT id FROM tenants WHERE id=:tenant FOR UPDATE"), {"tenant": company_id})
            target = (await session.execute(text("""
                SELECT status FROM company_users WHERE tenant_id=:tenant AND id=:user FOR UPDATE
            """), {"tenant": company_id, "user": user_id})).scalar_one_or_none()
            if target is None:
                raise HTTPException(status_code=404, detail="user not found")
            target_owner = await _owner_role(session, company_id, user_id)
            if target_owner:
                if not await _owner_role(session, company_id, principal.user_id):
                    raise HTTPException(status_code=403, detail="only owners can suspend owners")
                await _assert_owner_survives(session, company_id, user_id, True)
            if target != 'suspended':
                await session.execute(text("""
                    UPDATE company_users SET status='suspended' WHERE tenant_id=:tenant AND id=:user
                """), {"tenant": company_id, "user": user_id})
                await _audit(session, company_id, principal.user_id, 'user.suspended', user_id)
    return {"status": "suspended"}


@router.delete("/{company_id}/users/{user_id}/roles/{role_id}", status_code=204)
async def revoke_role(company_id: uuid.UUID, user_id: uuid.UUID, role_id: uuid.UUID,
                      authorization: str | None = Header(default=None)):
    principal = await authorized_user(parse_bearer(authorization), company_id, Permission.USERS_MANAGE)
    async with SessionLocal() as session:
        async with tenant_transaction(session, company_id):
            await session.execute(text("SELECT id FROM tenants WHERE id=:tenant FOR UPDATE"), {"tenant": company_id})
            role = (await session.execute(text("""
                SELECT code FROM company_roles WHERE tenant_id=:tenant AND id=:role
            """), {"tenant": company_id, "role": role_id})).scalar_one_or_none()
            if role is None:
                raise HTTPException(status_code=404, detail="role not found")
            if role == 'owner':
                if not await _owner_role(session, company_id, principal.user_id):
                    raise HTTPException(status_code=403, detail="only owners can revoke owner roles")
                await _assert_owner_survives(session, company_id, user_id, True)
            result = await session.execute(text("""
                DELETE FROM company_user_roles
                WHERE tenant_id=:tenant AND user_id=:user AND role_id=:role
                RETURNING id
            """), {"tenant": company_id, "user": user_id, "role": role_id})
            if not result.first():
                raise HTTPException(status_code=404, detail="role assignment not found")
            await _audit(session, company_id, principal.user_id, 'user.role_revoked', user_id)


@router.post("/{company_id}/invitations/{invitation_id}/revoke")
async def revoke_invitation(company_id: uuid.UUID, invitation_id: uuid.UUID,
                            authorization: str | None = Header(default=None)):
    principal = await authorized_user(parse_bearer(authorization), company_id, Permission.USERS_MANAGE)
    async with SessionLocal() as session:
        async with tenant_transaction(session, company_id):
            result = await session.execute(text("""
                UPDATE company_invitations SET revoked_at=now()
                WHERE tenant_id=:tenant AND id=:invitation
                  AND revoked_at IS NULL AND consumed_at IS NULL
                RETURNING id
            """), {"tenant": company_id, "invitation": invitation_id})
            if not result.first():
                raise HTTPException(status_code=404, detail="active invitation not found")
            await _audit(session, company_id, principal.user_id, 'invitation.revoked')
    return {"status": "revoked"}
