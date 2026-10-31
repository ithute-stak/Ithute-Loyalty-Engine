"""Company invitation issuance and atomic acceptance.

Tokens are returned once for explicit delivery by the administrator; do not log
request/response bodies. Human identity comes from verified OIDC subject.
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from loyalty_api.access import authorized_user, parse_bearer
from loyalty_api.db import SessionLocal
from loyalty_api.invitations import create_invitation_token, hash_invitation_token, invitation_expires_at, validate_invitation_role
from loyalty_api.oidc import decode_access_token
from loyalty_api.permissions import Permission
from loyalty_api.tenant import tenant_transaction

router = APIRouter(prefix="/v1/companies", tags=["invitations"])


class InviteRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=200)
    role: str
    branch_id: uuid.UUID | None = None


class AcceptRequest(BaseModel):
    token: str = Field(min_length=30, max_length=256)


@router.post("/{company_id}/invitations", status_code=201)
async def issue_invitation(company_id: uuid.UUID, payload: InviteRequest,
                           authorization: str | None = Header(default=None)):
    principal = await authorized_user(parse_bearer(authorization), company_id, Permission.USERS_MANAGE)
    try:
        role = validate_invitation_role(payload.role)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid invitation role")
    secret, digest = create_invitation_token()
    invite_id = uuid.uuid4()
    async with SessionLocal() as session:
        async with tenant_transaction(session, company_id):
            # Company role must exist. Branch FK enforces tenant consistency.
            found = (await session.execute(text("""
                SELECT id FROM company_roles WHERE tenant_id=:tenant AND code=:code
            """), {"tenant": company_id, "code": role})).scalar_one_or_none()
            if found is None:
                raise HTTPException(status_code=422, detail="role not configured")
            if payload.branch_id is not None:
                branch_found = (await session.execute(text("""
                    SELECT 1 FROM branches WHERE tenant_id=:tenant AND id=:branch
                """), {"tenant": company_id, "branch": payload.branch_id})).scalar_one_or_none()
                if branch_found is None:
                    raise HTTPException(status_code=422, detail="branch not found")
            await session.execute(text("""
                INSERT INTO company_invitations
                (id,tenant_id,token_hash,subject,display_name,role_code,branch_id,created_by,expires_at)
                VALUES (:id,:tenant,:digest,:subject,:name,:role,:branch,:actor,:expires)
            """), {"id": invite_id, "tenant": company_id, "digest": digest,
                   "subject": payload.subject, "name": payload.display_name,
                   "role": role, "branch": payload.branch_id, "actor": principal.user_id,
                   "expires": invitation_expires_at()})
            await session.execute(text("""
                INSERT INTO company_audit_events (id,tenant_id,actor_id,event_type)
                VALUES (:id,:tenant,:actor,'invitation.issued')
            """), {"id": uuid.uuid4(), "tenant": company_id, "actor": principal.user_id})
    return {"invitation_id": str(invite_id), "token": secret, "expires_in_hours": 48}


@router.post("/{company_id}/invitations/accept")
async def accept_invitation(company_id: uuid.UUID, payload: AcceptRequest,
                            authorization: str | None = Header(default=None)):
    claims = decode_access_token(parse_bearer(authorization))
    try:
        digest = hash_invitation_token(payload.token)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid invitation")
    user_id = uuid.uuid4()
    try:
        async with SessionLocal() as session:
            async with tenant_transaction(session, company_id):
                invitation = (await session.execute(text("""
                    UPDATE company_invitations SET consumed_at=now()
                    WHERE tenant_id=:tenant AND token_hash=:digest AND subject=:subject
                      AND consumed_at IS NULL AND revoked_at IS NULL AND expires_at>now()
                    RETURNING id, display_name, role_code, branch_id
                """), {"tenant": company_id, "digest": digest,
                       "subject": claims["sub"]})).mappings().one_or_none()
                if invitation is None:
                    raise HTTPException(status_code=400, detail="invalid or expired invitation")
                role_id = (await session.execute(text("""
                    SELECT id FROM company_roles WHERE tenant_id=:tenant AND code=:code
                """), {"tenant": company_id, "code": invitation["role_code"]})).scalar_one_or_none()
                if role_id is None:
                    raise HTTPException(status_code=409, detail="invited role no longer exists")
                existing = (await session.execute(text("""
                    SELECT id, status FROM company_users
                    WHERE tenant_id=:tenant AND external_subject=:subject
                """), {"tenant": company_id, "subject": claims["sub"]})).scalar_one_or_none()
                if existing is None:
                    await session.execute(text("""
                        INSERT INTO company_users (id,tenant_id,external_subject,display_name,status)
                        VALUES (:id,:tenant,:subject,:name,'active')
                    """), {"id": user_id, "tenant": company_id,
                           "subject": claims["sub"], "name": invitation["display_name"]})
                else:
                    if existing.status != 'active':
                        raise HTTPException(status_code=403, detail='membership inactive')
                    user_id = existing.id
                await session.execute(text("""
                    INSERT INTO company_user_roles(id,tenant_id,user_id,role_id,branch_id)
                    VALUES (:id,:tenant,:user,:role,:branch)
                    ON CONFLICT DO NOTHING
                """), {"id": uuid.uuid4(), "tenant": company_id, "user": user_id,
                       "role": role_id, "branch": invitation["branch_id"]})
                await session.execute(text("""
                    INSERT INTO company_audit_events(id,tenant_id,actor_id,event_type,subject_id)
                    VALUES (:id,:tenant,:actor,'invitation.accepted',:subject)
                """), {"id": uuid.uuid4(), "tenant": company_id, "actor": user_id, "subject": user_id})
    except IntegrityError:
        raise HTTPException(status_code=409, detail="company membership conflict")
    return {"status": "accepted", "user_id": str(user_id)}
