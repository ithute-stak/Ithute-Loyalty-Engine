"""The tenant setting is transaction-scoped, not connection-scoped."""
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def tenant_transaction(session: AsyncSession, tenant_id: UUID):
    if session.in_transaction():
        # Auth lookup may already have begun a transaction; close before tenant scope.
        await session.rollback()
    async with session.begin():
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        yield session
