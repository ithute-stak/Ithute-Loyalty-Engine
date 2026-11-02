"""FastAPI-side transport to the internal Rust ledger.

Only caller-authenticated tenant IDs may be forwarded; never take tenant_id from
the external JSON payload. Keep the internal key exclusively on the server.
"""
import uuid
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field

from loyalty_api.config import settings


class LedgerCommand(BaseModel):
    account_id: uuid.UUID
    event_id: str = Field(min_length=1, max_length=200)
    operation: str
    points: int | None = Field(default=None, gt=0)
    original_event_id: str | None = Field(default=None, min_length=1, max_length=200)


async def submit_ledger_command(tenant_id: uuid.UUID, command: LedgerCommand) -> dict:
    if not settings.ledger_internal_url or len(settings.ledger_internal_key) < 32:
        raise HTTPException(status_code=503, detail="ledger service not configured")
    if command.operation not in {"earn", "redeem", "reverse"}:
        raise HTTPException(status_code=422, detail="invalid ledger operation")
    if (command.operation == "reverse") != (command.original_event_id is not None):
        raise HTTPException(status_code=422, detail="invalid reversal fields")
    if (command.operation == "reverse") == (command.points is not None):
        raise HTTPException(status_code=422, detail="invalid points fields")
    payload = command.model_dump(mode="json")
    payload["tenant_id"] = str(tenant_id)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                settings.ledger_internal_url.rstrip("/") + "/internal/v1/commands",
                json=payload,
                headers={"X-Internal-Ledger-Key": settings.ledger_internal_key},
            )
        if response.status_code in (400, 404, 409, 422):
            raise HTTPException(status_code=response.status_code, detail="ledger command rejected")
        response.raise_for_status()
        return response.json()
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="ledger temporarily unavailable") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=503, detail="ledger temporarily unavailable") from exc
