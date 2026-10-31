from fastapi.testclient import TestClient
from loyalty_api.main import app


COMPANY = "11111111-1111-4111-8111-111111111111"
USER = "22222222-2222-4222-8222-222222222222"
ROLE = "33333333-3333-4333-8333-333333333333"
INVITATION = "44444444-4444-4444-8444-444444444444"


def test_lifecycle_endpoints_reject_unauthenticated_requests():
    routes = [
        ("post", f"/v1/companies/{COMPANY}/users/{USER}/suspend"),
        ("delete", f"/v1/companies/{COMPANY}/users/{USER}/roles/{ROLE}"),
        ("post", f"/v1/companies/{COMPANY}/invitations/{INVITATION}/revoke"),
    ]
    with TestClient(app) as client:
        for method, path in routes:
            assert getattr(client, method)(path).status_code == 401
