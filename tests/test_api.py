from fastapi.testclient import TestClient

from rca_copilot.api import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_generate_incidents_returns_requested_count() -> None:
    response = client.post("/incidents", json={"count": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 5
    assert len(body["incidents"]) == 5


def test_generate_rejects_invalid_count() -> None:
    response = client.post("/incidents", json={"count": -1})
    assert response.status_code == 422


def test_generate_uses_default_when_count_omitted() -> None:
    response = client.post("/incidents", json={})
    assert response.status_code == 200
    assert response.json()["count"] == 10