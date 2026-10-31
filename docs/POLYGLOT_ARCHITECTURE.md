# Polyglot engineering architecture

## Language responsibilities

| Language | Planned responsibility | Deployment approach |
| --- | --- | --- |
| Python / FastAPI | Public REST API, tenant administration, integration orchestration, merchant onboarding | `api` container |
| Rust | High-assurance ledger command handling, redemption concurrency, point expiry and accounting invariants | `ledger` service (later phase) |
| Go | High-throughput webhooks, outbox delivery, ingestion adapters and workers | `events` service (later phase) |
| Java (Spring Boot) | Optional enterprise integrations, large ERP adapters and batch processing | `enterprise-adapters` service when justified |
| C# (.NET) | Optional Microsoft ecosystem integrations, Windows-based merchant and ERP connectors | `dotnet-adapters` service when justified |
| C++ | Optional isolated native hardware/terminal connector or optimized library after benchmarks | native library or edge agent, not a network-facing core by default |
| PostgreSQL | Canonical point ledger, balances, programme and membership data | `postgres` service |
| Redis | Cache and rate-limiting, never canonical point balances | optional `redis` service |

## Avoid accidental microservice complexity
Start with a deployable FastAPI modular monolith and PostgreSQL; establish typed interfaces for ledger and event processing. Introduce Rust and Go services with independently measurable performance/security requirements, and add Java, C# or C++ only for concrete integrations. Supporting a language means having a designated place for it, not rewriting the same operation six times.

## Contract and messaging
- Public integration contracts: OpenAPI 3.x with explicit versioning.
- Internal synchronous interfaces: versioned gRPC/Protocol Buffers or HTTP when simpler.
- Asynchronous delivery: transactional PostgreSQL outbox and durable worker processing. Introduce a broker only when needed.
- Use canonical transaction and monetary/point types; fixed precision, no native floating point for rewards.
- No service may mutate a points balance outside the canonical ledger command boundary.
- Sign webhooks; enforce replay protection, idempotency, retries, delivery logs and dead-letter handling.
- Integration credentials authenticate tenant scope; user-provided tenant IDs never override that scope.

## Proposed layout
```text
apps/
  api-python/             # FastAPI API and admin backend
services/
  ledger-rust/            # future ledger command processor
  event-worker-go/        # future event/webhook processor
  enterprise-java/        # optional enterprise adapters
  connectors-dotnet/      # optional Microsoft/Windows adapters
native/
  device-bridge-cpp/      # optional hardware connector
contracts/
  openapi/
  proto/
infra/
  docker/
  migrations/
docs/
tests/
  contract/
  integration/
  security/
```

## Data and deployment constraints
One canonical PostgreSQL database initially. No simultaneous ownership of the ledger tables by multiple services. Database transactions enforce ledger invariants; outbox rows are written with ledger events in the same transaction. Every company, branch and membership reference must be verified within its tenant boundary. Start on a resource-limited VPS with only necessary containers; reserve CPU/RAM for database stability.

## Release gates
Tenant isolation tests, double-spend concurrency tests, reversal consistency, idempotency replay, webhook signature verification, backup/restore rehearsal, data retention and observability. Add performance tests before extracting services.
