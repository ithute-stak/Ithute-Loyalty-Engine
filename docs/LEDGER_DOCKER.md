# Private ledger deployment overlay

Optional `compose.ledger.yml` builds the Rust binary and attaches it to a dedicated internal Docker network. It does **not publish the Rust HTTP port**.

## Configuration
Generate `LEDGER_INTERNAL_KEY` using a cryptographically secure generator, store in an untracked secret manager or protected local env file, and configure `LEDGER_DATABASE_URL` for a **separate non-owner ledger DB role**. Run migrations using a migration-specific owner credential before enabling. Do not use the database schema owner in production.

## Local development
```sh
docker compose --env-file .env -f compose.yaml -f compose.ledger.yml config
docker compose --env-file .env -f compose.yaml -f compose.ledger.yml up --build -d
```

Do not expose merchant ledger writes yet. The Rust internal key authenticates the caller but does not independently scope tenant IDs. Production needs signed scoped service identity or mTLS and enforced caller authorisation before serving public points commands; add tests for this trust boundary. The initial API currently exposes no public ledger mutation endpoint.

Other deployment gates: restricted DB grants and RLS checks, explicit service health/ready checks, network egress review, secret rotation, end-to-end tests and confirmed green CI.
