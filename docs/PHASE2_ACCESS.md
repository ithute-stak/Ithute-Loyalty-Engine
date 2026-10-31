# Phase 2 continuation — company user and role foundations

## Implemented (schema and permission policy, not user login)
- `company_users` with a per-tenant external identity subject
- `company_roles` and tenant-scoped role assignment
- optional branch-scoped role assignments, validated with a composite tenant/branch foreign key
- PostgreSQL RLS policies on all new tenant-owned tables
- predefined permission policy: owner, administrator, branch_manager, cashier, auditor
- deny-by-default for unknown roles

## Not yet implemented
- Identity provider token validation (Ithute Auth or another trusted provider)
- Company user invitations, acceptance and verified lifecycle transitions
- Authentication-backed user management endpoints and live database authorization
- Company owner bootstrap and platform superadmin controls
- Tests that execute RLS policies as a non-owner database role
- Audit events for membership/permission changes

**Security gate:** no new user administration endpoints are exposed yet. The existing merchant API-key branch read remains integration-only. A merchant API key does not authenticate a human user or imply admin privilege.

## Next engineering sequence
1. Integrate a trusted OIDC provider with issuer, audience, expiry and JWKS verification.
2. Match validated subject and tenant against active company user membership.
3. Authorize each endpoint using role permission and optional verified branch scope.
4. Implement invitation and owner bootstrap flows through privileged operations.
5. Add PostgreSQL two-tenant tests that verify read/write isolation under an unprivileged database role.
