import uuid

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from loyalty_api.config import settings
from loyalty_api.db import SessionLocal, get_session
from loyalty_api.security import Principal, require_principal
from loyalty_api.tenant import tenant_transaction
from loyalty_api.oidc import authenticate_human
from loyalty_api.company_routes import router as company_router
from loyalty_api.invitation_routes import router as invitation_router
from loyalty_api.lifecycle_routes import router as lifecycle_router

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(company_router)
app.include_router(invitation_router)
app.include_router(lifecycle_router)


@app.get("/health/live", tags=["health"])
async def live():
    return {"status": "ok", "service": "ithute-loyalty-engine"}


@app.get("/health/ready", tags=["health"])
async def ready():
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ready"}



@app.get("/v1/merchant/branches", tags=["merchant"])
async def merchant_branches(
    principal: Principal = Depends(require_principal),
    session: AsyncSession = Depends(get_session),
):
    async with tenant_transaction(session, principal.tenant_id):
        rows = (await session.execute(
            text("SELECT id, code, name FROM branches ORDER BY code LIMIT 100")
        )).mappings().all()
        return {"items": [{"id": str(row["id"]), "code": row["code"], "name": row["name"]} for row in rows]}



@app.get("/v1/companies/{company_id}/me", tags=["human-access"])
async def company_membership_me(company_id: uuid.UUID, authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="bearer token required")
    token = authorization[7:]
    if not token or len(token) > 8192:
        raise HTTPException(status_code=401, detail="invalid access token")
    principal = await authenticate_human(token, company_id)
    return {"company_id": str(principal.tenant_id), "user_id": str(principal.user_id), "display_name": principal.display_name}
