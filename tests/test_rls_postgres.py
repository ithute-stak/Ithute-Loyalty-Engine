"""Live PostgreSQL RLS tests, enabled by CI TEST_RLS_DATABASE_URL.

Run migrations with the schema owner first. Use a *different*, non-owner
database role for TEST_RLS_DATABASE_URL.
"""
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_two_tenant_branch_rls():
    url = os.environ.get("TEST_RLS_DATABASE_URL")
    if not url:
        pytest.skip("TEST_RLS_DATABASE_URL not configured")
    engine = create_async_engine(url)
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    branch_a, branch_b = uuid.uuid4(), uuid.uuid4()
    try:
        # Confirm runner isn't using privileged role. Test must fail, not skip.
        async with engine.connect() as conn:
            privileged = (await conn.execute(text("""
                SELECT rolsuper OR rolbypassrls OR
                    pg_has_role(current_user, (SELECT relowner FROM pg_class
                    WHERE oid='public.branches'::regclass), 'MEMBER')
                FROM pg_roles WHERE rolname=current_user
            """))).scalar_one()
            assert not privileged, "RLS tests must use an unprivileged non-owner role"
        # Test setup uses owner fixture connection, never application credentials.
        from loyalty_api.config import settings
        owner = create_async_engine(settings.database_url)
        try:
            async with owner.begin() as conn:
                for tid, slug in [(tenant_a, str(tenant_a)), (tenant_b, str(tenant_b))]:
                    await conn.execute(text("""
                        INSERT INTO tenants(id,name,slug,status)
                        VALUES (:id,'RLS test',:slug,'active')
                    """), {"id": tid, "slug": slug})
                for tid, bid in [(tenant_a, branch_a), (tenant_b, branch_b)]:
                    await conn.execute(text("""
                        SELECT set_config('app.tenant_id', :id, true)
                    """), {"id": str(tid)})
                    await conn.execute(text("""
                        INSERT INTO branches(id,tenant_id,code,name)
                        VALUES (:id,:tenant,'TEST','Test Branch')
                    """), {"id": bid, "tenant": tid})
            async with engine.begin() as conn:
                await conn.execute(text("SELECT set_config('app.tenant_id', :id, true)"), {"id": str(tenant_a)})
                visible = (await conn.execute(text("SELECT id FROM branches WHERE id IN (:a,:b)"),
                                              {"a": branch_a, "b": branch_b})).scalars().all()
                assert visible == [branch_a]
                await conn.execute(text("SELECT set_config('app.tenant_id', :id, true)"), {"id": str(tenant_b)})
                visible = (await conn.execute(text("SELECT id FROM branches WHERE id IN (:a,:b)"),
                                              {"a": branch_a, "b": branch_b})).scalars().all()
                assert visible == [branch_b]
            async with engine.begin() as conn:
                await conn.execute(text("SELECT set_config('app.tenant_id', :id, true)"), {"id": str(tenant_a)})
                with pytest.raises(Exception):
                    async with conn.begin_nested():
                        await conn.execute(text("""
                            INSERT INTO branches(id,tenant_id,code,name)
                            VALUES (:id,:tenant,'X','Forbidden')
                        """), {"id": uuid.uuid4(), "tenant": tenant_b})
        finally:
            async with owner.begin() as conn:
                for tid in (tenant_a, tenant_b):
                    await conn.execute(text("DELETE FROM branches WHERE tenant_id=:id"), {"id": tid})
                    await conn.execute(text("DELETE FROM tenants WHERE id=:id"), {"id": tid})
            await owner.dispose()
    finally:
        await engine.dispose()
