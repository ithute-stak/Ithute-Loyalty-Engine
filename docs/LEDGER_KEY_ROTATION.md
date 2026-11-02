# Scoped ledger signing keys (initial release)

The Rust ledger requires LEDGER_SIGNING_KEYS_JSON: an array of objects with
`id`, `secret` (at least 32 characters) and `tenants` (nonempty array of UUIDs).
Each credential's tenant allowlist is independently enforced by Rust.
The FastAPI caller sets LEDGER_KEY_ID and LEDGER_INTERNAL_KEY and signs
`key_id + "." + unix_timestamp + "." + raw_request_body` with HMAC-SHA256.
Rust verifies the MAC, timestamp and the tenant binding for that key ID before
calling PostgreSQL. Both command and reconciliation routes use this check.

Example configuration schema (placeholder strings only; never use in production):
```json
[{"id":"api-v1","secret":"REPLACE_WITH_32_PLUS_RANDOM_CHARACTERS","tenants":["00000000-0000-4000-8000-000000000001"]}]
```

## Rotation and revocation
1. Provision a fresh credential ID and high-entropy secret scoped only to the
   companies that caller should serve; store in a secret manager.
2. Deploy Rust with both previous and new credentials temporarily.
3. Switch FastAPI to the new key ID and secret.
4. Remove the previous credential from Rust configuration and restart or
   redeploy the service. Revocation takes effect after old instances stop.
5. Confirm old key returns 401, changed tenant returns 403, and new key works.

**Limitations:** Configuration and key changes are deployment based; no live
credential management API, audit sink, per-operation scopes, replay nonce store,
mutual TLS or automatic key rotation. Signed request replay is possible inside
the 60-second window, although idempotent ledger event IDs prevent repeated
posting effects. FastAPI must independently authorise every operation and source
transaction before public write endpoints are enabled. Do not use plaintext
environment secrets in production when mounted secrets are available.
