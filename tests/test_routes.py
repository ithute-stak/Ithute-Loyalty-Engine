from fastapi.testclient import TestClient
from loyalty_api.main import app


def test_branches_without_credentials_rejected():
    with TestClient(app) as client:
        response = client.get("/v1/merchant/branches")
    assert response.status_code == 401
