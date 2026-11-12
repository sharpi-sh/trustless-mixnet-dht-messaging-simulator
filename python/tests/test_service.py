from fastapi.testclient import TestClient

from app.server import app


def test_connection_has_no_side_effect():
    with TestClient(app) as client:
        health = client.get("/health").json()
        assert health["simulation_active"] is False
        assert health["message_paced_playback"] is True
        assert client.get("/api/config").json()["exchanges"] == 1
        assert (
            "access-control-allow-origin"
            not in client.get("/health", headers={"origin": "https://other.example"}).headers
        )
