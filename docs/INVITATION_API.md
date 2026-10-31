# Invitation endpoints — initial implementation

- `POST /v1/companies/{company_id}/invitations` requires human OIDC token and a tenant-wide users:manage role. Body includes `subject`, `display_name`, `role`, optional `branch_id`. Returns an invitation token **once** to the authenticated administrator. An admin must deliver it using an independently verified secure channel.
- `POST /v1/companies/{company_id}/invitations/accept` requires human OIDC token for the intended `sub` and a valid unconsumed invitation token. The consume, user insert, role assignment and audit write happen in a single transaction; transaction rollback undoes consumption on errors.

Current restrictions: owner invitations are forbidden. An inactive existing membership cannot be reactivated through invitation acceptance. Tokens expire after 48 hours.

**Not production ready:** Requires configured RS256 OIDC provider, unprivileged database connection, migration execution and two-tenant integration testing. Credential responses must be redacted in proxies, analytics and observability. No delivery service, re-invite, suspension, role revoke, operator bootstrap or rate limiting is implemented. Do not expose these endpoints publicly until the deployment gates are satisfied.
