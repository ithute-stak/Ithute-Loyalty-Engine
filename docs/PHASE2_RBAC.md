# RBAC implementation slice

Added authenticated human, read-only routes:

- `GET /v1/companies/{company_id}/users`: an active human member with a company-wide `users:manage` role can see up to 100 user records.
- `GET /v1/companies/{company_id}/branches/{branch_id}`: a company-wide or matching branch-scoped `branch:read` grant is required.

Grant lookups occur in a tenant-scoped transaction using forced PostgreSQL RLS. Branch-specific grants do not authorize company-wide list operations. Unknown roles deny access.

No invitation, owner bootstrap, role write, or user activation endpoint exists yet. An API key does not grant human permissions. Owner/bootstrap workflows must be implemented by a trusted administrative process with audit logs, enforced company status and the correct unprivileged database role.

CI must still be exercised with a real non-owner PostgreSQL role and multi-tenant fixtures. Do not expose the API publicly before those tests and a reviewed OIDC/JWKS operational configuration.
