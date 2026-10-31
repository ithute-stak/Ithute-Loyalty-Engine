"""Schema-level RLS regression test against a migrated PostgreSQL database."""
import os
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from loyalty_api.config import settings


@pytest.mark.asyncio
async def test_all_tenant_tables_force_rls_with_tenant_policy():
    if not os.environ.get("TEST_RLS_DATABASE_URL"):
        pytest.skip("database integration test not configured")
    tables = (
        "branches", "loyalty_programmes", "company_users",
        "company_roles", "company_user_roles", "company_invitations",
        "company_audit_events",
    )
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            for table in tables:
                row = (await conn.execute(text("""
                    SELECT c.relrowsecurity, c.relforcerowsecurity,
                    EXISTS (
                        SELECT 1 FROM pg_policies p
                        WHERE p.schemaname = 'public'
                          AND p.tablename = :table
                          AND p.policyname = 'tenant_isolation'
                    )
                    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname='public' AND c.relname=:table
                """), {"table": table})).one_or_none()
                assert row is not None, f"missing tenant table: {table}"
                assert all(row), f"missing enforced RLS or tenant policy: {table}"
    finally:
        await engine.dispose()
