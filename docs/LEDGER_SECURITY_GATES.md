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

## Signed internal commands (2026-11-02)

The FastAPI ledger client now signs canonical JSON bytes with HMAC-SHA256 over
`<unix_timestamp>.<raw_body>`. Rust rejects requests lacking a valid MAC,
with an altered request body, or with timestamps outside a 60-second window.
The ledger internal secret is not transmitted in the request header anymore.

**Outstanding limitations:** HMAC identifies the shared client secret, not an
independently authorized merchant. A captured signed message can be replayed
within the allowed window. Ledger posting idempotency prevents duplicate
*effects* for the same event ID, but there is no nonce replay database yet.
The shared key must be rotated and protected, transports must have network
confidentiality, and public merchant writes remain disabled. The receiving
service still needs per-tenant authorization independently enforced via
authenticated service identity, signed scoped claims or equivalent.

## Independently enforced tenant allowlist

Rust now requires `LEDGER_ALLOWED_TENANTS`, a comma-separated list of UUIDs configured on the **ledger container**, and rejects commands and reconciliation requests for any unlisted company with HTTP 403. Empty/malformed config fails startup. FastAPI cannot add a company merely by setting `tenant_id` in the signed payload; enabling a new company requires an operational configuration change on Rust.

This is a **deployment-time allowlist, not a complete authenticated per-tenant identity system**. An actor possessing the shared HMAC key could still issue commands for any tenant included in that allowlist. A production multi-company SaaS must replace or augment this mechanism with separately scoped caller credentials or cryptographically verifiable tenant grants, reliable revocation and audit. Do not expose merchant mutation APIs yet.

## Scoped HTTP handler regression

The Rust internal command handler has a regression test for a *validly signed*
request from a key assigned to tenant A where the JSON body names tenant B.
The handler must return 403 before any PostgreSQL statement. A request without
signature headers must return 401. The reconciliation route has been fixed to
use the same key-ID authorization path as the posting route.

This is a **handler-level test**, not yet a complete FastAPI-to-running-Rust-to-
PostgreSQL end-to-end test. The latter remains a release gate.
