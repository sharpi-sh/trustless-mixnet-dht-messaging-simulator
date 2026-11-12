from random import Random

from app.config import Config
from app.participants import People
from app.topology import GlobalObserver, MixNode, NetworkPath, Topology


def test_complete_stratified_adjacency():
    c = Config(min_nodes=10)
    t = Topology(c,Random(4),People(c,Random(3)))
    assert [len(layer) for layer in t.mixnet.layers] == [4,3,3]
    node = t.nodes["mix-1"]
    assert isinstance(node,MixNode)
    assert set(node.adjacent_peers) == set(t.mixnet.layers[1]) | set(t.mixnet.providers)
    assert all(p.status=="unknown" for p in node.adjacent_peers.values())
    assert all(isinstance(p,NetworkPath) and p.source_id in t.nodes and p.target_id in t.nodes for p in t.paths.values())
    assert all(p.attempted==0 for p in t.paths.values())
    assert GlobalObserver.__slots__ == ("id","lifecycle")
