from fastapi.testclient import TestClient

from app.server import app


def test_connection_has_no_side_effect():
    with TestClient(app) as client:
        health = client.get("/health").json()
        assert health["simulation_active"] is False
        assert health["message_paced_playback"] is True
        assert health["first_departure_playback"] is True
        assert client.get("/api/config").json()["exchanges"] == 1
        assert (
            "access-control-allow-origin"
            not in client.get("/health", headers={"origin": "https://other.example"}).headers
        )


def test_info_advertises_all_channels_while_a_snapshot_lists_only_the_selected_channels():
    with TestClient(app) as client:
        supported = {p["id"]: p for p in client.get("/api/info").json()["protocols"]}
        assert "tor-abstraction" in supported and "direct-connection" in supported
        assert supported["shadowsocks-abstraction"]["name"] == "Outline Shadowsocks proxy abstraction"
        response = client.post(
            "/api/simulations", json={"sender_channel": "shadowsocks", "recipient_channel": "direct"}
        )
        assert response.is_success
        snapshot = response.json()
        configured = {p["id"] for p in snapshot["profiles"]}
        assert {"shadowsocks-abstraction", "direct-connection"} <= configured
        assert "tor-abstraction" not in configured
        proxy = next(n for n in snapshot["topology"]["nodes"] if n["kind"] == "shadowsocks")
        assert proxy["label"] == supported["shadowsocks-abstraction"]["name"]
