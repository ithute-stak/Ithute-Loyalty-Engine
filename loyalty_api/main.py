from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from loyalty_api.config import settings
from loyalty_api.db import SessionLocal, get_session
from loyalty_api.security import Principal, require_principal
from loyalty_api.tenant import tenant_transaction

app = FastAPI(title=settings.app_name, version="0.1.0")


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

