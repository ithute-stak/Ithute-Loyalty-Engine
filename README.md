# Ithute Loyalty Engine

Independent, multi-tenant loyalty-as-a-service platform for businesses in Lesotho and beyond.

## Product boundaries
- **Platform operator:** Ithute provisions tenants, plans, security policy and monitoring.
- **Merchant tenant:** each company independently owns its reward programmes, branches, memberships, rules and liabilities.
- **Integration neutral:** Khanya POS, IthutePay, third-party POS systems, commerce applications, and manual/admin channels integrate via documented APIs.
- **First release:** no inter-company points exchange or pooled balances; partnership settlement is a separate future capability.

## Initial technology proposal
- Python 3.12+ and FastAPI for API and administrative backend
- PostgreSQL for transactional state, append-only points ledger and auditing
- Redis for non-authoritative caching, rate limiting and background orchestration
- Transactional outbox for durable downstream notifications
- OpenAPI schemas and independently versioned client integrations
- Container-first deployment with Docker Compose initially

## Non-negotiable invariants
1. Tenant identification comes from authenticated credentials, not a caller-supplied tenant header or body field.
2. All tenant-owned records carry a tenant identifier; database authorization (including row-level security where applicable) must be enforced and tested.
3. All point mutations use an append-only, transactional ledger and immutable event identifiers.
4. Purchases are awarded once per tenant, source, external transaction ID, and rule application; retries return the original result.
5. Redemptions atomically check and reserve available points so concurrent requests cannot overspend.
6. Refunds and reversals post compensating ledger entries; historical entries are never silently modified.
7. Never award points for an unconfirmed payment. Payment providers remain external integrations.
8. Programme configuration changes are versioned, auditable and cannot retroactively change historical awards.
9. PII is minimised, permissioned and retained according to documented policy.
10. Financially meaningful amounts use fixed-precision decimal arithmetic; no floating point balances.

## Development roadmap
1. Tenant and company boundaries, identity, RBAC, audit
2. Branches, programmes, policy versions, customers and memberships
3. Ledger, earn transactions, reversals, idempotency and concurrency testing
4. Reward catalogues, redemption and expiry
5. POS and payment adapters, webhooks and outbox
6. Merchant administration and reports
7. Security, observability, backup/restore and deployment gates
8. Optional future multi-merchant networks and settlement

See [architecture](docs/ARCHITECTURE.md).

**Status:** foundational product specification; implementation and tests not yet completed.
