from fastapi.testclient import TestClient

from app.server import app


def test_connection_has_no_side_effect():
    with TestClient(app) as client:
        assert client.get("/health").json()["simulation_active"] is False
        assert client.get("/api/config").json()["exchanges"] == 1
        assert "access-control-allow-origin" not in client.get(
            "/health", headers={"origin": "https://other.example"}
        ).headers
