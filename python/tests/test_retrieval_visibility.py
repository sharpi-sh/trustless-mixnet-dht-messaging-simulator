from app.config import Config
from app.lab import Laboratory


def test_exported_retrieval_transits_show_only_safe_cargo_and_physical_hops():
    lab = Laboratory(Config(random_seed=29, dht_nodes=3, storage_nodes=3, step_delay_ms=0))
    lab.lifecycle("run")
    for _ in range(50000):
        if lab.status != "running":
            break
        lab.step()
    assert lab.outcomes == {"msg-1": "received", "msg-2": "received"}
    phases = {}
    for event in lab.events:
        if event.event_type != "path_transit_started":
            continue
        cargo = event.payload.get("cargo", {})
        if cargo.get("kind") != "Anonymous retrieval":
            continue
        assert set(cargo) == {"kind", "phase", "exchange_id", "bytes", "cell"}
        assert cargo["bytes"] > 0
        if lab.topology.nodes[event.target_id].kind == "mix":
            phases.setdefault((event.message_id, cargo["phase"]), set()).add(
                lab.topology.nodes[event.target_id].stage_index
            )
    assert phases == {
        (mid, phase): {3, 4, 5} for mid in ("msg-1", "msg-2") for phase in ("request", "response")
    }
