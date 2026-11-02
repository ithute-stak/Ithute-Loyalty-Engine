"""Live signed FastAPI-client -> Rust -> restricted PostgreSQL smoke test.

Run only on a disposable migrated CI database with a running Rust service.
"""
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from loyalty_api.config import settings
from loyalty_api.ledger_client import LedgerCommand, submit_ledger_command
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_signed_service_two_company_isolation(monkeypatch):
    url = os.getenv("LEDGER_E2E_OWNER_DATABASE_URL")
    rust_url = os.getenv("LEDGER_E2E_SERVICE_URL")
    if not url or not rust_url:
        pytest.skip("live ledger CI fixture not enabled")
    a, b, programme_a, programme_b, account_a, account_b = [uuid.uuid4() for _ in range(6)]
    owner = create_async_engine(url)
    try:
        async with owner.begin() as conn:
            for tenant, programme, account in ((a, programme_a, account_a), (b, programme_b, account_b)):
                await conn.execute(text("""
                    INSERT INTO tenants (id,name,slug,status)
                    VALUES (:id,'Ledger E2E',:slug,'active')
                """), {"id": tenant, "slug": str(tenant)})
                await conn.execute(text("SELECT set_config('app.tenant_id',:id,true)"),
                                   {"id": str(tenant)})
                await conn.execute(text("""
                    INSERT INTO loyalty_programmes (id,tenant_id,code,name)
                    VALUES (:id,:tenant,'E2E','E2E')
                """), {"id": programme, "tenant": tenant})
                await conn.execute(text("""
                    INSERT INTO points_accounts(id,tenant_id,programme_id,customer_ref,balance)
                    VALUES (:id,:tenant,:programme,'test',0)
                """), {"id": account, "tenant": tenant, "programme": programme})

        monkeypatch.setattr(settings, "ledger_internal_url", rust_url)
        monkeypatch.setattr(settings, "ledger_internal_key", os.environ["LEDGER_E2E_KEY_SECRET"])
        monkeypatch.setattr(settings, "ledger_key_id", os.environ["LEDGER_E2E_KEY_ID"])
        cmd = LedgerCommand(account_id=account_a, event_id="e2e-earn", operation="earn", points=45)
        assert (await submit_ledger_command(a, cmd))["balance"] == 45
        assert (await submit_ledger_command(a, cmd))["balance"] == 45
        assert (await submit_ledger_command(a, LedgerCommand(
            account_id=account_a, event_id="e2e-redeem", operation="redeem", points=15
        )))["balance"] == 30

        # Even a correctly signed request may not switch to a tenant
        # outside the configured key's scope.
        with pytest.raises(HTTPException) as exc:
            await submit_ledger_command(b, LedgerCommand(
                account_id=account_b, event_id="unauthorized", operation="earn", points=100
            ))
        assert exc.value.status_code == 403

        async with owner.begin() as conn:
            await conn.execute(text("SELECT set_config('app.tenant_id',:id,true)"),
                               {"id": str(a)})
            balance = (await conn.execute(text("""
                SELECT balance FROM points_accounts WHERE id=:id
            """), {"id": account_a})).scalar_one()
            entries = (await conn.execute(text("""
                SELECT count(*),sum(delta) FROM points_entries WHERE account_id=:id
            """), {"id": account_a})).one()
            assert balance == 30
            assert entries == (2, 30)
            await conn.execute(text("SELECT set_config('app.tenant_id',:id,true)"),
                               {"id": str(b)})
            assert (await conn.execute(text("""
                SELECT balance FROM points_accounts WHERE id=:id
            """), {"id": account_b})).scalar_one() == 0
    finally:
        await owner.dispose()
