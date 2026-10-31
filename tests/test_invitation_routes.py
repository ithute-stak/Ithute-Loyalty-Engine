from fastapi.testclient import TestClient
from loyalty_api.main import app


def test_issue_requires_authenticated_administrator():
    with TestClient(app) as client:
        result = client.post(
            "/v1/companies/11111111-1111-4111-8111-111111111111/invitations",
            json={"subject": "subject-1", "display_name": "Test", "role": "cashier"},
        )
    assert result.status_code == 401


def test_accept_requires_verified_identity():
    with TestClient(app) as client:
        result = client.post(
            "/v1/companies/11111111-1111-4111-8111-111111111111/invitations/accept",
            json={"token": "ili_" + "x" * 48},
        )
    assert result.status_code == 401
