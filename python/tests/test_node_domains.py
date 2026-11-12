from random import Random

import pytest

from app.kademlia import DHTNetwork, ID_SPACE
from app.storage import StorageNetwork


def test_dht_identity_is_seeded_and_safe_to_display():
    first = DHTNetwork(Random(43))
    second = DHTNetwork(Random(43))
    assert first.add_node("dht-1") == second.add_node("dht-1")
    assert first.add_node("dht-2", 7).node_id == 7
    snapshot = first.inspect("dht-2", 21)
    assert snapshot["node_id"] == "0" * 39 + "7"
    assert snapshot["address"] == "sim://dht-2"
    assert snapshot["simulation_time_ms"] == 21
    assert snapshot["k"] == 20 and snapshot["alpha"] == 3


@pytest.mark.parametrize("peer,node_id", [("", 4), ("one", 4), ("two", 3), ("two", -1),
                                          ("two", ID_SPACE)])
def test_conflicting_and_invalid_dht_ids_are_rejected(peer, node_id):
    network = DHTNetwork(Random(43))
    network.add_node("one", 3)
    with pytest.raises(ValueError):
        network.add_node(peer, node_id)
    assert list(network.nodes) == ["one"]


def test_vaults_have_independent_storage_and_inspect_only_identifiers():
    network = StorageNetwork(["storage-1", "storage-2"])
    network.nodes["storage-2"].fragments["fragment"] = b"opaque"
    assert network.inspect("storage-1")["fragment_ids"] == []
    assert network.inspect("storage-2") == {
        "node_id": "storage-2", "address": "sim://storage-2", "fragment_ids": ["fragment"]
    }
    with pytest.raises(ValueError):
        StorageNetwork(["storage-1", "storage-1"])
