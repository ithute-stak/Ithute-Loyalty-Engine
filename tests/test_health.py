from fastapi.testclient import TestClient
from loyalty_api.main import app


def test_liveness():
    with TestClient(app) as client:
        res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
