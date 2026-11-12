from fastapi.testclient import TestClient

from app.server import app


def test_http_reads_writes_and_local_origin():
    with TestClient(app) as c:
        assert c.post("/api/simulations", json={"sender_count": 11}).status_code == 422
        assert (
            c.post(
                "/api/simulations", json={}, headers={"Origin": "https://external.example"}
            ).status_code
            == 403
        )
        created = c.post("/api/simulations", json={"random_seed": 21})
        assert created.status_code == 201, created.text
        state = created.json()
        url = "/api/simulations/" + state["simulation_id"]
        assert (
            state["status"] == "ready"
            and c.get("/health").json()["simulation_id"] == state["simulation_id"]
        )
        assert c.get(url + "/nodes/mix-1").json()["state"]["adjacent_peers"]
        assert c.get(url + "/topology").json() == state["topology"]
        assert (
            c.put(url + "/messages", json={"messages": {"msg-1": "Local test text"}}).status_code == 200
        )
        for command in ("step", "run", "pause", "resume", "stop"):
            assert c.post(url + "/" + command).status_code == 200
        assert c.put(url + "/messages", json={"messages": {"msg-1": "too late"}}).status_code == 409
        assert c.post(url + "/reset").status_code == 200
        assert c.get(url).json()["epoch"] == 1
        assert c.get(url + "/lineage").json() == {"lineage": []}


def test_websocket_reconnect_snapshot_and_live_delta():
    with TestClient(app) as c:
        sid = c.post("/api/simulations", json={"random_seed": 2}).json()["simulation_id"]
        sub = {"type": "subscribe", "command_id": "sub", "simulation_id": sid}
        with c.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "backend_ready"
            ws.send_json(sub)
            initial = ws.receive_json()
            assert initial["type"] == "snapshot"
            target = initial["state"]["topology"]["paths"][0]["id"]
            cmd = {
                "type": "block_network_path",
                "simulation_id": sid,
                "command_id": "block",
                "target": target,
            }
            ws.send_json(cmd)
            assert ws.receive_json()["type"] == "ack"
            change = ws.receive_json()["delta"]
            assert change["paths"][0]["blocked"] and change["sequence"] > initial["state"]["sequence"]
            ws.send_text("invalid-json")
            assert ws.receive_json()["type"] == "error"
        with c.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({**sub, "after_sequence": change["sequence"], "epoch": 0})
            restored = ws.receive_json()
            assert restored["events"] == []
            assert restored["state"]["topology"]["paths"][0]["blocked"]
            ws.send_json({"type": "reset", "command_id": "r", "simulation_id": sid})
            assert ws.receive_json()["type"] == "ack"
            assert ws.receive_json()["state"]["epoch"] == 1
