# Phase 2 — Tenant credentials and read isolation

This stage introduces offline tenant onboarding, SHA-256 fingerprints of high-entropy random API keys, explicit credential revocation storage, and authenticated tenant-scoped branch reads.

## Provisioning (trusted operator only)

After applying migrations, run this command only in an isolated operator environment with a schema-owner database credential:

```sh
python -m loyalty_api.provision --name "Demo Merchant" --slug demo-merchant
```

The command prints the initial API credential **once**. Store it in a secrets manager; never commit or log it. The CLI requires the operator role to have rights to insert into tenants/api_credentials.

## Request

```sh
curl -H 'X-API-Key: YOUR_SECRET' http://127.0.0.1:8085/v1/merchant/branches
```

The authenticated tenant is looked up from the key fingerprint; a tenant ID passed by the caller is never trusted.

## Database security / deployment gate

**IMPORTANT:** Existing Docker Compose uses the database owner for the API and **MUST NOT be publicly deployed as-is**. Create a separate LOGIN role (`loyalty_app`) that does not own tables and does not have BYPASSRLS, granting only SELECT on api_credentials and tenants plus SELECT on branches to begin with. Configure the API's DATABASE_URL for that role. Do not grant schema DDL or tenant write access to the API role. Run Alembic and offline onboarding with the migration/owner role only.

Tenant branch queries set `app.tenant_id` using PostgreSQL `set_config(..., true)` inside a transaction. PostgreSQL FORCE ROW LEVEL SECURITY on branches means an ordinary non-owner app role cannot inspect another company's branches.

Future milestones: platform users, RBAC, key rotation endpoint, privilege separation automation, tests with two real Postgres tenants, and wider company CRUD. No public tenant creation endpoint is enabled yet.
