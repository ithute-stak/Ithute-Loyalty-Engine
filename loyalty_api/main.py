from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from loyalty_api.config import settings
from loyalty_api.db import SessionLocal

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

# Merchant and platform endpoints are intentionally not exposed until
# authentication, tenant-scoped authorization and database RLS are implemented.
