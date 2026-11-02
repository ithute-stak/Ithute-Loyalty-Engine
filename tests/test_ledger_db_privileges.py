"""Validate least-privilege ledger role in a migrated disposable PostgreSQL database."""
import os
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_runtime_ledger_role_has_only_required_permissions():
    url = os.environ.get("TEST_LEDGER_DATABASE_URL")
    if not url:
        pytest.skip("TEST_LEDGER_DATABASE_URL not configured")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            row = (await conn.execute(text("""
                SELECT rolsuper, rolbypassrls, rolcreaterole
                FROM pg_roles WHERE rolname = current_user
            """))).one()
            assert not any(row), "ledger runtime cannot have privileged role flags"
            for table in ("points_accounts", "points_entries"):
                owner = (await conn.execute(text("""
                    SELECT pg_has_role(current_user, relowner, 'MEMBER')
                    FROM pg_class WHERE oid = CAST(:table AS regclass)
                """), {"table": "public." + table})).scalar_one()
                assert not owner, "ledger must never own its tables"
            for table in ("points_accounts", "points_entries"):
                assert (await conn.execute(text(
                    "SELECT has_table_privilege(current_user,:table,'SELECT')"
                ), {"table": "public." + table})).scalar_one()
                assert not (await conn.execute(text(
                    "SELECT has_table_privilege(current_user,:table,'DELETE')"
                ), {"table": "public." + table})).scalar_one()
            assert (await conn.execute(text(
                "SELECT has_column_privilege(current_user,'public.points_accounts','balance','UPDATE')"
            ))).scalar_one()
            assert not (await conn.execute(text(
                "SELECT has_column_privilege(current_user,'public.points_accounts','tenant_id','UPDATE')"
            ))).scalar_one()
            assert (await conn.execute(text(
                "SELECT has_table_privilege(current_user,'public.points_entries','INSERT')"
            ))).scalar_one()
            assert not (await conn.execute(text(
                "SELECT has_table_privilege(current_user,'public.tenants','INSERT')"
            ))).scalar_one()
    finally:
        await engine.dispose()
