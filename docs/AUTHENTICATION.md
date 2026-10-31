# Human authentication contract (initial implementation)

Human authentication is separate from machine-to-machine API keys. The external OIDC identity provider must issue RS256 JWT access tokens with exp/iat/iss/sub/aud, and publish its public signing keys at an operator-controlled JWKS URL.

Set `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL` through secure deployment settings. Blank settings disable all human authentication. No insecure development bypass is provided.

`GET /v1/companies/{company_id}/me` requires `Authorization: Bearer <access-token>`. The requested company UUID is used only as a membership selection; token verification and a tenant-scoped lookup of the authenticated subject must succeed before any information is returned. A user can be a member of multiple companies but cannot select a company in which the subject lacks an active membership.

The user membership is created only by a trusted operator/bootstrap process; public invitation and management endpoints are not provided yet.

**Not yet done:** establish the exact Ithute Auth issuer/keys/audience contract, verify the intended provider uses RS256 JWT access tokens, add company membership onboarding and branch-scoped RBAC enforcement, configure restricted database credentials, and run PostgreSQL RLS integration tests.

Security note: token validation currently instantiates a JWKS client per call; use a bounded cached client with operational timeout, error handling and refresh policy before exposing at scale.
