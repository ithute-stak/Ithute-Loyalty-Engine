# Phase 3 — Rust loyalty ledger foundation

The Rust crate in `services/ledger-rust` defines deterministic, in-memory domain logic for point issuance, redemptions, exact idempotent retries and reversal events.

Run:
```sh
cd services/ledger-rust
cargo test
cargo clippy --all-targets -- -D warnings
```

This crate is **not** a production ledger database, service or public API. It does not yet persist entries, apply tenant-scoped PostgreSQL locking, enforce transaction ID uniqueness across process restarts, support expiry lots, solve negative balances on refunded spent points, or support partial reversals. The current policy rejects a refund reversal when awarded points have already been spent; future policy design must explicitly cover debt/negative points or delayed recovery without silently mutating history.

Next milestones: canonical SQL ledger schema (composite tenant keys and unique idempotency constraints); atomic transaction posting under PostgreSQL locks; audit/reconciliation and integration with the FastAPI boundary; property/concurrency tests.

No payment provider integration should be changed by ledger work.
