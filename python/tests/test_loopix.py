from random import Random
from statistics import mean

from app.config import Config
from app.loopix import Loopix, ProviderInbox
from app.topology import Mixnet


def protocol():
    return Loopix(Mixnet([['a','b'],['c','d'],['e','f']]),Config(),Random(19))


def test_source_selections_match_reference_equations():
    loopix = protocol()
    first = loopix.route("ingress","egress")
    replica = Random(first.seed)
    assert first.nodes == ["ingress",*(replica.choice(layer) for layer in first.layers),"egress"]
    assert first.delays_ms[:-1] == [round(1000*replica.expovariate(1)) for _ in range(4)]
    assert loopix.route("ingress","egress").seed != first.seed


def test_mix_loop_wraps_via_provider():
    route=protocol().mix_loop("c")
    assert route.nodes[0] in ["e","f"] and route.nodes[1].startswith("provider")
    assert route.nodes[2] in ["a","b"] and route.nodes[-1] == "c"


def test_poisson_clocks_and_fixed_poll_cells():
    p=protocol()
    assert 19500 < mean(p.interval("payload") for _ in range(10000)) < 20500
    box=ProviderInbox([b"opaque"])
    batch=box.poll(3,256)
    assert tuple(map(len,batch)) == (256,256,256)
    assert batch[1:] == (bytes(256),)*2 and not box.messages
