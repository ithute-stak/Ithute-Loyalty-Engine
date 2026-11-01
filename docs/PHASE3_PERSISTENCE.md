# Phase 3 — Persistent ledger slice

## Added
- PostgreSQL tables `points_accounts` and `points_entries`, tenant-scoped RLS, unique event idempotency constraints, nonnegative balance checks, reversible-reference uniqueness.
- Database trigger rejecting UPDATE/DELETE on ledger entries.
- Optional Rust `postgres` crate feature using sqlx and transaction-scoped tenant context.
- PostgreSQL row lock on accounts, atomic earn/redeem entry + balance projection updates.
- Exact retries return the originally committed `balance_after`; conflicting retries are rejected.

## Scope boundaries
`post()` is a Rust library function, **not a running service or integrated HTTP endpoint**. It receives a tenant UUID from a trusted calling layer; do not expose tenant selection from request fields. Operations currently support **earn and redeem only**. Persistent reversal is not implemented, although the schema reserves the reversal reference field. Production rollback/refund policy, point expiration lots, signed payment confirmation and network API are outstanding.

## Important invariants / release gates
1. The Rust ledger backend must run with a dedicated, non-owner database role; generic API credentials must not have ledger table mutation privileges.
2. Use `cargo test --features postgres` and `cargo clippy --features postgres --all-targets -- -D warnings` to verify Rust. GitHub Actions defines these checks, but actual passing results must be confirmed.
3. Apply migrations through a privileged migrator before starting a dedicated service.
4. Conduct live two-tenant RLS tests, concurrent redemption and idempotent retry races against PostgreSQL, not only unit tests.
5. Ledger history is immutable. Updates happen only to the reconstructable `points_accounts.balance` projection in the same transaction as a new entry.
6. Do not alter IthutePay payment integrations. Loyalty points are awarded only after a trusted confirmed sale/payment event.
