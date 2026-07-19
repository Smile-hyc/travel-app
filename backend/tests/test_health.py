from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_endpoint() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to AI Travel API"}


def test_health_endpoint() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "message": "AI Travel backend is running",
        "status": "ok",
    }


def test_review_provider_health_does_not_expose_keys() -> None:
    response = client.get("/api/health/reviews")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "configured",
        "activeProvider",
        "rnoteConfigured",
        "tikhubConfigured",
    }
    assert "apiKey" not in payload
