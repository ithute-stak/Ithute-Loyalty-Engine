"""PostgreSQL tenant-isolation integration tests.

Requires owner DATABASE_URL for fixtures and restricted TEST_RLS_DATABASE_URL.
Both connect to the same disposable CI database.
"""
import os
import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from loyalty_api.config import settings


@pytest.mark.asyncio
async def test_two_tenant_branch_rls():
    url = os.environ.get("TEST_RLS_DATABASE_URL")
    if not url:
        pytest.skip("restricted database URL not configured")
    owner = create_async_engine(settings.database_url)
    app = create_async_engine(url)
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    branch_a, branch_b = uuid.uuid4(), uuid.uuid4()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    programme_a, programme_b = uuid.uuid4(), uuid.uuid4()
    try:
        async with app.connect() as conn:
            restricted = (await conn.execute(text("""
                SELECT NOT (rolsuper OR rolbypassrls OR
                    pg_has_role(current_user,
                      (SELECT relowner FROM pg_class WHERE oid='public.branches'::regclass),
                      'MEMBER'))
                FROM pg_roles WHERE rolname=current_user
            """))).scalar_one()
            assert restricted, "RLS testing requires a non-owner non-BYPASSRLS user"
        async with owner.begin() as conn:
            for tenant, branch in ((tenant_a, branch_a), (tenant_b, branch_b)):
                await conn.execute(text("""
                    INSERT INTO tenants(id,name,slug,status)
                    VALUES (:id,'RLS fixture',:slug,'active')
                """), {"id":tenant, "slug":str(tenant)})
                await conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"),
                                   {"tenant":str(tenant)})
                await conn.execute(text("""
                    INSERT INTO branches(id,tenant_id,code,name)
                    VALUES (:id,:tenant,'TEST','RLS fixture')
                """), {"id":branch, "tenant":tenant})
                user = user_a if tenant == tenant_a else user_b
                programme = programme_a if tenant == tenant_a else programme_b
                await conn.execute(text("""
                    INSERT INTO company_users(id,tenant_id,external_subject,display_name,status)
                    VALUES (:id,:tenant,:subject,'Test user','active')
                """), {"id":user, "tenant":tenant, "subject":str(user)})
                await conn.execute(text("""
                    INSERT INTO loyalty_programmes(id,tenant_id,code,name)
                    VALUES (:id,:tenant,'TEST','Test programme')
                """), {"id":programme, "tenant":tenant})
        for current, own, other in ((tenant_a, branch_a, branch_b),
                                    (tenant_b, branch_b, branch_a)):
            async with app.begin() as conn:
                # Missing tenant context must never reveal another tenant's records.
                await conn.execute(text("SELECT set_config('app.tenant_id', '', true)"))
                assert (await conn.execute(text("SELECT count(*) FROM branches WHERE id IN (:a,:b)"),
                                           {"a":branch_a,"b":branch_b})).scalar_one()==0
                await conn.execute(text("SELECT set_config('app.tenant_id', :id, true)"),
                                   {"id":str(current)})
                visible=(await conn.execute(text("""
                    SELECT id FROM branches WHERE id IN (:a,:b)
                """), {"a":branch_a,"b":branch_b})).scalars().all()
                assert visible == [own]
                for table, ids in (
                    ("company_users", (user_a, user_b)),
                    ("loyalty_programmes", (programme_a, programme_b)),
                ):
                    result = (await conn.execute(
                        text(f"SELECT id FROM {table} WHERE id IN (:a,:b)"),
                        {"a":ids[0], "b":ids[1]},
                    )).scalars().all()
                    assert result == [ids[0] if current == tenant_a else ids[1]]
                # A tenant A connection cannot write into B, even if it has INSERT.
                with pytest.raises(Exception):
                    async with conn.begin_nested():
                        await conn.execute(text("""
                            INSERT INTO branches(id,tenant_id,code,name)
                            VALUES (:id,:tenant,'BLOCKED','Forbidden')
                        """), {"id":uuid.uuid4(),"tenant":(tenant_b if current==tenant_a else tenant_a)})
    finally:
        # FORCE RLS also applies to table owners; clean up with appropriate context.
        try:
            async with owner.begin() as conn:
                for tenant in (tenant_a,tenant_b):
                    await conn.execute(text("SELECT set_config('app.tenant_id', :id, true)"),
                                       {"id":str(tenant)})
                    await conn.execute(text("DELETE FROM branches WHERE tenant_id=:id"),{"id":tenant})
                    await conn.execute(text("DELETE FROM company_users WHERE tenant_id=:id"),{"id":tenant})
                    await conn.execute(text("DELETE FROM loyalty_programmes WHERE tenant_id=:id"),{"id":tenant})
                await conn.execute(text("DELETE FROM tenants WHERE id IN (:a,:b)"),
                                   {"a":tenant_a,"b":tenant_b})
        finally:
            await app.dispose()
            await owner.dispose()
