# Internal Rust ledger transport — initial draft implementation

A dedicated Rust HTTP binary is gated behind Cargo feature `service` and listens on 127.0.0.1:8090. It exposes POST /internal/v1/commands and /internal/v1/reconcile, requiring a secret header of at least 32 characters. The Python client accepts a verified tenant UUID as a function argument and adds it to the internal request.

This is **not yet a secure production service boundary**. The shared secret identifies the calling application, not a specific tenant. Therefore a compromised caller could submit any tenant ID. Production must enforce authenticated service identity and authorised tenant propagation (for example mTLS and signed, scoped assertions). The Rust ledger database role must be non-owner with enforced RLS and narrowly limited grants. Do not publish this listener to the public internet. A Dockerized isolated runtime topology, credential rotation and permission enforcement for earn/redeem/reverse still need implementation.

No public points mutation endpoint is introduced in FastAPI in this change. No changes have been made to IthutePay or merchant payment adapters. The Python client is prepared for later authenticated, permission-checked endpoint wiring.

Build: `cargo build --features service`. Run tests: `cargo test --features service`.
