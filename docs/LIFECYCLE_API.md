# Lifecycle API — Phase 2

Human OIDC bearer token and tenant-wide `users:manage` permission required:

- `POST /v1/companies/{company_id}/users/{user_id}/suspend`
- `DELETE /v1/companies/{company_id}/users/{user_id}/roles/{role_id}`
- `POST /v1/companies/{company_id}/invitations/{invitation_id}/revoke`

All modifications are transactional and emit tenant-scoped audit events. Suspension blocks future authentication. Invitation revocation only applies to pending invitations. Owner suspension and revocation require the acting user to be an owner; the last active company owner cannot be removed. Tenant row locks serialize these owner-sensitive changes.

**Security/deployment gates:** Test concurrent owner mutations against real PostgreSQL under an unprivileged role; include cases where actor permissions are revoked concurrently, tenant access isolation and rollbacks. There is no guaranteed immediate invalidation of bearer tokens at the identity provider, though membership checks are performed for each new API operation. Add operational OIDC integration, request limits, audit retention, separate schema owner/runtime role, privilege audit and CI checks prior to exposure. No claim of production readiness is made.
