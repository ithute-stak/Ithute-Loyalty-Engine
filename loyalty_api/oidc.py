"""Human authentication: verify external OIDC access token and tenant membership.

The issuer/audience/JWKS URL are operator configuration, never request inputs.
Only asymmetric RS256 is accepted; no unsigned or symmetric fallback.
"""
import uuid
from dataclasses import dataclass

import jwt
from fastapi import HTTPException
from jwt import PyJWKClient, PyJWTError
from sqlalchemy import text

from loyalty_api.config import settings
from loyalty_api.db import SessionLocal
from loyalty_api.tenant import tenant_transaction


@dataclass(frozen=True)
class HumanPrincipal:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    subject: str
    display_name: str


def decode_access_token(token: str) -> dict:
    if not (settings.oidc_issuer and settings.oidc_audience and settings.oidc_jwks_url):
        raise HTTPException(status_code=503, detail="human authentication not configured")
    try:
        key = PyJWKClient(settings.oidc_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, key.key, algorithms=["RS256"], issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            leeway=30,
        )
        if not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise ValueError("missing subject")
        return claims
    except (PyJWTError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="invalid access token") from exc


async def authenticate_human(token: str, tenant_id: uuid.UUID) -> HumanPrincipal:
    claims = decode_access_token(token)
    async with SessionLocal() as session:
        async with tenant_transaction(session, tenant_id):
            row = (await session.execute(text("""
                SELECT u.id, u.display_name FROM company_users u
                JOIN tenants t ON t.id = u.tenant_id
                WHERE u.tenant_id = :tenant AND u.external_subject = :subject
                AND u.status = 'active' AND t.status = 'active'
            """), {"tenant": tenant_id, "subject": claims["sub"]})).one_or_none()
            if row is None:
                raise HTTPException(status_code=403, detail="no active company membership")
            return HumanPrincipal(tenant_id, row.id, claims["sub"], row.display_name)
