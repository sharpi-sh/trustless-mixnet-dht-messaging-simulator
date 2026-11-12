import pytest

from app.config import Config
from app.dht_runtime import DHTRequest, DHTResult, Join, Maintenance
from app.engine import Engine
from app.kademlia import DAY
from app.profiles import profiles
from app.storage_simulation import StorageSimulation


class DHTLab(StorageSimulation):
    """Drive the production topology and availability hooks without unrelated traffic clocks."""

    def __init__(self, **config):
        super().__init__(Config(random_seed=8, dht_nodes=3, jitter_max_ms=0, **config))
        self.results = {}

    def initialise(self):
        Engine.initialise(self)
        self.rpc.start()

    def handle(self, action):
        if isinstance(action, DHTResult):
            self.results[action.token] = action.result
            return True
        return super().handle(action)

    def until(self, condition):
        for _ in self.drain(10_000):
            if condition():
                return
        raise AssertionError(f"Condition absent at {self.now} ms")


@pytest.mark.parametrize("unavailable", ["dht-1", "dht-3"])
def test_offline_join_recovers_through_normal_network_requests(unavailable):
    lab = DHTLab(base_transit_delay_ms=1200)
    lab.change_node(unavailable, False, "before start")
    lab.lifecycle("run")
    if unavailable == "dht-1":
        lab.until(lambda: any(e.event_type == "kademlia_join_retry_scheduled" for e in lab.events))
        assert not lab.rpc.joined
    else:
        lab.until(lambda: len(lab.rpc.joined) == 2)
    lab.change_node(unavailable, True, "restored")
    lab.until(lambda: len(lab.rpc.joined) == 3)
    successful = [
        e.payload["peer"]
        for e in lab.events
        if e.event_type == "kademlia_join_completed" and e.payload["success"]
    ]
    assert sorted(successful) == list(lab.dht.nodes)
    assert all(n.table.closest(0) for n in lab.dht.nodes.values())
    assert not any(isinstance(s.action, Join) for _, _, s in lab.queue)
    lab.schedule(DHTRequest(source="dht-1", token="pub", key=321, value=b"opaque handle"))
    lab.until(lambda: "pub" in lab.results)
    assert set(lab.results["pub"].peers) == set(lab.dht.nodes)
    lab.schedule(DHTRequest(source="dht-3", token="read", key=321))
    lab.until(lambda: "read" in lab.results)
    assert lab.results["read"].value == b"opaque handle"
    assert lab.dht.timeout_ms == lab.config.rpc_timeout_ms == 3400
    assert (
        next(p for p in profiles(lab.config) if p.id == "kademlia-2002").parameters["rpc_timeout_ms"]
        == 3400
    )
    assert Config().rpc_timeout_ms == 2000


def test_owner_recovers_expired_replicas_and_overdue_original_publication():
    lab = DHTLab(base_transit_delay_ms=2)
    lab.lifecycle("run")
    lab.until(lambda: len(lab.rpc.joined) == 3)
    key = 5
    lab.schedule(DHTRequest(source="dht-1", token="pub", key=key, value=b"manifest"))
    lab.until(lambda: "pub" in lab.results)
    expires = lab.dht.nodes["dht-2"].records[key].expires_at
    for uid in lab.dht.nodes:
        lab.change_node(uid, False, "long outage")
    lab.until(lambda: lab.now > expires)
    lab.change_node("dht-2", True, "replica recovery")
    lab.until(lambda: key not in lab.dht.nodes["dht-2"].records)
    assert "dht-2" in lab.rpc.joined
    # One periodic clock per peer survives recovery. Catch-up has no new period.
    assert sum(isinstance(s.action, Maintenance) and s.action.periodic for _, _, s in lab.queue) == 3
    lab.change_node("dht-1", True, "publisher recovery")
    lab.until(lambda: key in lab.dht.nodes["dht-2"].records)
    fresh = lab.dht.nodes["dht-2"].records[key]
    assert fresh.value == b"manifest"
    assert fresh.published_at >= expires and fresh.expires_at == fresh.published_at + DAY


def test_local_disconnect_cannot_succeed_via_its_own_timeout_or_blame_remote():
    lab = DHTLab(base_transit_delay_ms=3)
    lab.lifecycle("run")
    lab.until(lambda: len(lab.rpc.joined) == 3)
    origin = lab.dht.nodes["dht-2"]
    failures = sum(v["failures"] for v in origin.observations.values())
    lab.schedule(DHTRequest(source="dht-2", token="interrupted", key=9, value=b"in flight"))
    lab.until(lambda: "interrupted" in lab.rpc.pending)
    lab.change_node("dht-2", False, "during FIND_NODE")
    lab.until(lambda: "interrupted" in lab.results)
    assert not lab.results["interrupted"].success
    deadline = lab.now + lab.dht.timeout_ms
    lab.until(lambda: lab.now >= deadline)
    assert 9 not in origin.records
    assert sum(v["failures"] for v in origin.observations.values()) == failures
