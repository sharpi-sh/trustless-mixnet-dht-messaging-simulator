from random import Random

from app.config import Config
from app.participants import People
from app.topology import GlobalObserver, MixNode, NetworkPath, Topology


def test_default_six_mixes_form_three_equal_layers():
    config = Config()
    topology = Topology(config, Random(4), People(config, Random(3)))
    assert [len(layer) for layer in topology.mixnet.layers] == [2, 2, 2]


def test_three_west_providers_receive_reproducible_seeded_sender_associations():
    config = Config(sender_count=10, random_seed=921)
    people = People(config, Random(8))
    first = Topology(config, Random(9), people)
    second = Topology(config, Random(77), people)
    assert first.mixnet.west_providers == (
        "provider-west",
        "provider-west-2",
        "provider-west-3",
    )
    assert {first.nodes[provider].stage for provider in first.mixnet.west_providers} == {
        "West providers"
    }
    assert first.nodes["provider-east"].stage == "East providers"
    assert first.provider_by_person == second.provider_by_person
    assert {first.provider_by_person[f"sender-{index}"] for index in range(1, 11)} == set(
        first.mixnet.west_providers
    )
    assert first.provider_for("receiver-1") == "provider-east"
    for person_id, provider in first.provider_by_person.items():
        channel = first.channel_ids[person_id]
        assert first.path_id(channel, provider) in first.paths
        assert (
            sum(
                first.path_id(channel, candidate) in first.paths for candidate in first.mixnet.providers
            )
            == 1
        )


def test_complete_stratified_adjacency():
    c = Config(min_nodes=10)
    t = Topology(c, Random(4), People(c, Random(3)))
    assert [len(layer) for layer in t.mixnet.layers] == [4, 3, 3]
    node = t.nodes["mix-1"]
    assert isinstance(node, MixNode)
    assert set(node.adjacent_peers) == (
        set(t.mixnet.layers[1]) | set(t.mixnet.providers) | set(t.mixnet.service_providers)
    )
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
