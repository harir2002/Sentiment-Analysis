from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


client = TestClient(app)
AUTH = (
    get_settings().admin_username,
    get_settings().admin_password,
)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "providers" in data
    assert "models" in data
    assert "sarvam_stt" in data["models"]
    assert "openrouter_llm" in data["models"]
    assert "mock_mode" not in data


def test_list_calls_endpoint():
    response = client.get("/api/calls", auth=AUTH)
    assert response.status_code == 200
    data = response.json()
    assert "calls" in data
    assert "total" in data
    assert isinstance(data["calls"], list)


def test_list_calls_alias_endpoint():
    response = client.get("/calls", auth=AUTH)
    assert response.status_code == 200
    assert "calls" in response.json()
