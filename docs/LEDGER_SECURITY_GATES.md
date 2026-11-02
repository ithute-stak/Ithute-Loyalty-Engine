# Ledger network and tenant security gates

Current API->Rust transport is internal HTTP plus a shared service secret. This is not tenant-scoped service authorisation. **Do not enable public points mutation endpoints** until the internal caller's authorisation is cryptographically scoped to the requested tenant, enforced by Rust, and backed by a restricted PostgreSQL ledger role.

- Integration tests must establish that callers cannot substitute tenant IDs and that an invalid caller cannot issue commands.
- FastAPI's merchant/API-key route must verify operation-specific privileges, confirmed purchases and source-specific transaction ownership.
- Forwarding a tenant UUID from the trusted FastAPI principal is necessary but insufficient by itself; the receiving service must verify a scoped assertion or equivalent authenticated identity, not merely trust a bare ID.
- Keep the Rust ledger private; never publish its Docker port.
- Configure distinct DB roles for schema migration, FastAPI, and ledger, each with least privilege.
- Run two-tenant concurrency/idempotency tests against a real PostgreSQL instance.
- Introduce replay-bound signed messages or mutual TLS with authenticated service identity, secure key rotation and rate limiting before accepting external transaction requests.
- Verify CI, backup/restore and service health checks before production deployment.
