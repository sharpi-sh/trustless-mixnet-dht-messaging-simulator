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


def test_individual_channels_apply_to_participant_endpoints_and_selected_profiles():
    with TestClient(app) as client:
        assert client.get("/api/config").json()["participant_channels"] == {}
        labels = client.get("/health").json()["participant_labels"]
        payload = {
            "sender_count": 3,
            "receiver_count": 2,
            "recipient_channel": "shadowsocks",
            "participant_channels": {
                "sender-2": "shadowsocks",
                "sender-3": "direct",
                "receiver-2": "direct",
            },
        }
        data = client.post("/api/simulations", json=payload)
        assert data.status_code == 201
        state = data.json()
        expected = {
            "sender-1": "tor",
            "sender-2": "shadowsocks",
            "sender-3": "direct",
            "receiver-1": "shadowsocks",
            "receiver-2": "direct",
        }
        assert {d["id"]: d["channel"] for d in state["devices"]} == expected
        for device in state["devices"]:
            assert device["label"] == labels[device["id"]]
            endpoint = device["channel_id"]
            assert endpoint == f"{device['channel']}-{device['id']}"
            assert any(
                {p["source_id"], p["target_id"]} == {device["id"], endpoint}
                for p in state["topology"]["paths"]
            )
        assert {"tor-abstraction", "shadowsocks-abstraction", "direct-connection"} <= {
            profile["id"] for profile in state["profiles"]
        }
