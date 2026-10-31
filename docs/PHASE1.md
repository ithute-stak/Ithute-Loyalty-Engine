# Phase 1 developer guide

Copy `.env.example` to `.env` and replace BOTH example password occurrences with the same secure generated password (URL encode special characters in DATABASE_URL).

```sh
docker compose up -d --build
docker compose run --rm api alembic upgrade head
curl -fsS http://127.0.0.1:8085/health/live
curl -fsS http://127.0.0.1:8085/health/ready
```

The database is intentionally not published on a host port. The API is bound to local loopback. Do not expose the service to the internet before adding real authentication and trusted reverse proxy configuration.

**RLS caveat:** the initial Compose PostgreSQL user owns the schema, suitable only for local bootstrap. Production must use a separate unprivileged application database role with no BYPASSRLS and no ownership of protected tables, plus transaction-scoped `SET LOCAL app.tenant_id` from a verified identity. No tenant CRUD endpoints exist yet.

The service uses migrations, not automatic create_all. Run migrations as a separate deployment step. Never put development secrets into Git.
