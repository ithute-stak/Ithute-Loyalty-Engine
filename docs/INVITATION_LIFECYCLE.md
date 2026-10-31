# Company invitations — foundational schema and security contract

This change adds hashed, random, one-time invitation token storage, expiry and revoke/consume columns, actor and role/branch metadata, tenant policies and an append-only audit event table. No public invitations or acceptance endpoints exist yet.

Invitation issuance in the next increment must require an active human administrator and `users:manage`. The actor cannot invite an owner. Verify the target subject with the identity provider before activation; never accept a subject claimed solely in an untrusted HTTP request. Invitation consumption must be atomic (`UPDATE ... WHERE consumed_at IS NULL AND revoked_at IS NULL AND expires_at > now() RETURNING ...`) and must check that the authenticated token subject matches the intended subject. Use transactional inserts into users, roles and audit events; reject duplicate membership cleanly. Deliver tokens over a verified out-of-band channel, never in logs.

Only an owner should be able to manage other owners. Suspensions and role changes must be audited, and removal of the last active owner prohibited.

**Deployment gate:** the existing API Docker role still needs separation from the schema owner. Migrations, restricted-role grants, actual OIDC integration and two-tenant RLS tests are required before exposing invitation endpoints.
