import uuid
import pytest
from fastapi import HTTPException
from loyalty_api.ledger_client import LedgerCommand, submit_ledger_command
from loyalty_api.config import settings


@pytest.mark.asyncio
async def test_ledger_fails_closed_without_configuration(monkeypatch):
    monkeypatch.setattr(settings, "ledger_internal_url", "")
    monkeypatch.setattr(settings, "ledger_internal_key", "")
    command = LedgerCommand(account_id=uuid.uuid4(), event_id="purchase-1", operation="earn", points=10)
    with pytest.raises(HTTPException) as exc:
        await submit_ledger_command(uuid.uuid4(), command)
    assert exc.value.status_code == 503
