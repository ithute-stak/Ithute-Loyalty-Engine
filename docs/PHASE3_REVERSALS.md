# Phase 3 — Reversal and reconciliation

The Rust PostgreSQL module now exposes:
- `post(pool, tenant, account, event_id, operation, points)` for earn/redeem;
- `reverse(pool, tenant, account, event_id, original_event_id)` for full compensating entries;
- `reconcile(pool, tenant, account)` returning stored balance and sum of immutable entries.

All operations establish a transaction-local PostgreSQL tenant context. Mutations lock the points account before reading events and writing the new balance. Exact repeated reversal events return the originally recorded result; conflicting reuse of an event ID is rejected. The unique reversal index protects against two different refunds of the same entry. A reversal of previously earned points that have already been spent is rejected until a merchant policy for negative points/recovery is designed.

## Verification still required
- Integration tests with two real tenants and a dedicated non-owner PostgreSQL ledger role.
- Concurrent redemption/refund races, timeout and retry tests, and rollback checks.
- Append-only trigger tests and reconciliation drift alarms.
- Service transport and API integration, where the tenant is derived from authenticated credentials.
- OIDC integration and independent security review.
- Confirm actual green CI before deployment.

No actual reversal endpoint has been exposed to merchants. The ledger is still a library and not a deployable background service.
