from random import Random

from app.config import Config
from app.participants import People
from app.topology import GlobalObserver, MixNode, NetworkPath, Topology


def test_complete_stratified_adjacency():
    c = Config(min_nodes=10)
    t = Topology(c, Random(4), People(c, Random(3)))
    assert [len(layer) for layer in t.mixnet.layers] == [4, 3, 3]
    node = t.nodes["mix-1"]
    assert isinstance(node, MixNode)
    assert set(node.adjacent_peers) == set(t.mixnet.layers[1]) | set(t.mixnet.providers)
    assert all(p.status == "unknown" for p in node.adjacent_peers.values())
    assert all(
        isinstance(p, NetworkPath) and p.source_id in t.nodes and p.target_id in t.nodes
        for p in t.paths.values()
    )
    assert all(p.attempted == 0 for p in t.paths.values())
    assert GlobalObserver.__slots__ == ("id", "lifecycle")


def test_created_simulation_owns_independent_idle_objects():
    from app.simulation import Simulation

    a, b = (Simulation(Config(random_seed=41)) for _ in range(2))
    assert a.id != b.id and a.observer != b.observer
    assert a.dht.nodes.keys() == set(a.topology.dht_ids)
    assert a.storage.nodes.keys() == set(a.topology.storage_ids)
    assert a.snapshot()["topology"] == b.snapshot()["topology"]
    assert a.status == "ready" and not a.events
