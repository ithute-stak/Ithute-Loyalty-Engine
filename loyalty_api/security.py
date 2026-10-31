"""Tenant-scoped API key authentication.

Credentials are provisioned offline by an authorised platform operator.
Never accept tenant identity from a caller-supplied header or request body.
"""
import hashlib
import secrets
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from loyalty_api.db import get_session

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass(frozen=True)
class Principal:
    tenant_id: uuid.UUID
    credential_id: uuid.UUID


async def require_principal(
    api_key: str | None = Security(api_key_header),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    if not api_key or len(api_key) > 256 or not api_key.startswith("ile_"):
        raise HTTPException(status_code=401, detail="invalid credentials")
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    result = await session.execute(
        text("""
          SELECT c.id, c.tenant_id
          FROM api_credentials AS c JOIN tenants AS t ON t.id = c.tenant_id
          WHERE c.key_hash = :digest AND c.revoked_at IS NULL AND t.status = 'active'
        """),
        {"digest": digest},
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return Principal(tenant_id=row.tenant_id, credential_id=row.id)


def generate_api_key() -> str:
    return "ile_" + secrets.token_urlsafe(36)
