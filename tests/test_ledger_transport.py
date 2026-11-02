"""Transport contract tests; never require a running Rust service."""
import uuid
import httpx
import pytest
from fastapi import HTTPException
from loyalty_api import ledger_client
from loyalty_api.config import settings


@pytest.mark.asyncio
async def test_ledger_tenant_is_sourced_from_authenticated_context(monkeypatch):
    tenant = uuid.uuid4()
    account = uuid.uuid4()
    sent = {}
    async def handler(request: httpx.Request):
        sent.update(__import__("json").loads(request.content))
        assert request.headers["X-Internal-Ledger-Key"] == "x" * 40
        return httpx.Response(200, json={"balance": 23})
    original = httpx.AsyncClient
    def client_factory(*args, **kwargs):
        return original(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(ledger_client.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(settings, "ledger_internal_url", "http://ledger:8090")
    monkeypatch.setattr(settings, "ledger_internal_key", "x" * 40)
    command = ledger_client.LedgerCommand(
        account_id=account, event_id="confirmed-sale-1", operation="earn", points=23
    )
    result = await ledger_client.submit_ledger_command(tenant, command)
    assert result["balance"] == 23
    assert sent["tenant_id"] == str(tenant)
    assert sent["account_id"] == str(account)


@pytest.mark.asyncio
async def test_ledger_bad_operation_rejected_before_request(monkeypatch):
    monkeypatch.setattr(settings, "ledger_internal_url", "http://ledger:8090")
    monkeypatch.setattr(settings, "ledger_internal_key", "x" * 40)
    command = ledger_client.LedgerCommand(
        account_id=uuid.uuid4(), event_id="x", operation="transfer", points=1
    )
    with pytest.raises(HTTPException) as exc:
        await ledger_client.submit_ledger_command(uuid.uuid4(), command)
    assert exc.value.status_code == 422
