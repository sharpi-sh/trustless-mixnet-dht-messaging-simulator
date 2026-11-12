from app.config import Config
from app.dht_runtime import DHTRequest, DHTResult, DHTRuntime
from app.engine import Engine


class DhtExperiment(Engine):
    def __init__(self):
        super().__init__(Config(random_seed=35, dht_nodes=5, base_transit_delay_ms=4, jitter_max_ms=2))
        self.rpc = DHTRuntime(self)
        self.results = {}

    def handle(self, action):
        if isinstance(action, DHTResult):
            self.results[action.token] = action.result
            return True
        return self.rpc.handle(action)


def test_real_join_publish_and_lookup_over_paths():
    sim = DhtExperiment()
    sim.lifecycle("run")
    sim.rpc.start()
    for _ in sim.drain(5000):
        if sum(e.event_type == "kademlia_join_completed" for e in sim.events) == 5:
            break
    assert sim.now < 3600000
    sim.schedule(DHTRequest(source="dht-1", token="write", key=123, value=b"opaque"))
    for _ in sim.drain(5000):
        if "write" in sim.results:
            break
    assert sim.results["write"].success
    sim.schedule(DHTRequest(source="dht-5", token="read", key=123))
    for _ in sim.drain(5000):
        if "read" in sim.results:
            break
    assert sim.results["read"].value == b"opaque"
    assert any(p.completed for p in sim.topology.paths.values() if p.transport_label == "Kademlia RPC")
    assert not any(e.event_type == "simulation_error" for e in sim.events)
