"""Live signed FastAPI-client -> Rust -> restricted PostgreSQL smoke test.

Run only on a disposable migrated CI database with a running Rust service.
"""
import os
import uuid
import hashlib
import hmac
import json
import time

import httpx

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
        if os.getenv("LEDGER_E2E_REQUIRED") == "1":
            pytest.fail("mandatory live Rust/PostgreSQL integration test is not configured")
        pytest.skip("live ledger CI fixture not enabled")
    a = uuid.UUID(os.environ["LEDGER_E2E_TENANT_A"])
    b, programme_a, programme_b, account_a, account_b = [uuid.uuid4() for _ in range(5)]
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

        # Reconciliation uses the same scoped signing contract as posting.
        query = json.dumps({"tenant_id": str(a), "account_id": str(account_a)},
                           sort_keys=True, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        key_id = os.environ["LEDGER_E2E_KEY_ID"]
        secret = os.environ["LEDGER_E2E_KEY_SECRET"].encode()
        signature = hmac.new(secret,
            key_id.encode() + b"." + timestamp.encode() + b"." + query,
            hashlib.sha256).hexdigest()
        headers = {
            "X-Ledger-Key-Id": key_id,
            "X-Ledger-Timestamp": timestamp,
            "X-Ledger-Signature": signature,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            checked = await client.post(rust_url + "/internal/v1/reconcile",
                                        content=query, headers=headers)
            assert checked.status_code == 200, checked.text
            assert checked.json() == {"stored": 30, "entries_total": 30}
            # A correctly signed cross-company read must be forbidden, not only tampering.
            foreign = json.dumps({"tenant_id": str(b), "account_id": str(account_b)},
                                 sort_keys=True, separators=(",", ":")).encode()
            foreign_sig = hmac.new(secret,
                key_id.encode() + b"." + timestamp.encode() + b"." + foreign,
                hashlib.sha256).hexdigest()
            forbidden = await client.post(rust_url + "/internal/v1/reconcile",
                content=foreign,
                headers={**headers, "X-Ledger-Signature": foreign_sig})
            assert forbidden.status_code == 403, forbidden.text
            forged = await client.post(rust_url + "/internal/v1/reconcile",
                content=query.replace(str(a).encode(), str(b).encode()), headers=headers)
            assert forged.status_code == 401, forged.text
            without_auth = await client.post(rust_url + "/internal/v1/reconcile",
                                             content=query)
            assert without_auth.status_code == 401, without_auth.text

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
