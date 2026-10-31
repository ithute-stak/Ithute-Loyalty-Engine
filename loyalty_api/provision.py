"""Offline CLI: create one tenant and issue its initial credential.

Run only with trusted schema-owner database credentials, never inside the public API.
Prints the credential once; store it in a secrets manager.
"""
import argparse
import asyncio
import hashlib
import uuid

from sqlalchemy import text

from loyalty_api.db import SessionLocal
from loyalty_api.security import generate_api_key


async def provision(name: str, slug: str):
    key = generate_api_key()
    tenant_id = uuid.uuid4()
    credential_id = uuid.uuid4()
    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(
                text("INSERT INTO tenants (id,name,slug,status) VALUES (:id,:name,:slug,'active')"),
                {"id": tenant_id, "name": name, "slug": slug},
            )
            await session.execute(
                text("INSERT INTO api_credentials (id,tenant_id,name,key_hash) VALUES (:id,:tenant_id,:name,:key_hash)"),
                {"id": credential_id, "tenant_id": tenant_id, "name": "initial integration", "key_hash": hashlib.sha256(key.encode()).hexdigest()},
            )
    print(f"Tenant: {tenant_id}")
    print(f"Credential (shown once): {key}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--slug", required=True)
    args = parser.parse_args()
    asyncio.run(provision(args.name, args.slug))


if __name__ == "__main__":
    main()
