# Multi-tenant architecture

## Hierarchy
Ithute platform -> merchant tenant/company -> branch -> loyalty programme -> membership -> points ledger.

A customer may hold memberships with different companies. Identity linking across companies requires explicit consent; no merchant may inspect another merchant's data.

## Initial domain entities
- Tenant, TenantUser, Role, Branch, ApiCredential
- Customer, CustomerContact, Membership
- LoyaltyProgramme, RuleVersion, Tier, Promotion
- EarnEvent, LedgerEntry, PointLot (expiry), BalanceProjection
- Reward, Redemption, Reservation, RefundEvent
- WebhookSubscription, OutboxEvent, AuditEvent, IdempotencyRecord

## Suggested API groups
- /v1/merchant/companies, /branches, /programmes, /rules, /rewards
- /v1/customers, /memberships, /balances
- /v1/transactions/earn, /reverse, /redemptions
- /v1/integrations/webhooks
- /v1/platform/tenants, /subscriptions

## Example transaction flow
1. Verify scoped merchant integration credential.
2. Validate programme/rule version and immutable external source ID.
3. Confirm sale/settlement status from trusted event or approved integration channel.
4. Lock membership balance and affected points lots in one database transaction.
5. Enforce unique idempotency key, record earn event and append ledger entries.
6. Atomically update a reconstructable balance projection.
7. Commit outbox event in same transaction.
8. Deliver notification or webhook asynchronously with replay protection.

## Isolation
Use scoped authorization at the service layer AND PostgreSQL tenant policy; workers must set and reset trusted tenant context per transaction. Each tenant-owned FK and uniqueness constraint should include tenant_id where needed to prevent cross-tenant association. Automated tests must attempt cross-tenant reads, writes, redemption, idempotency reuse and webhooks.

## Reward funding
Each company is responsible for rewards issued under its own programmes. Cross-merchant pooling is not part of phase one; future clearing would need contractual allocation, liabilities, settlement and reconciliation.

## Open questions before production
Legal data retention, message provider, authentication integration, subscription billing, preferred frontend and deployment environment.
