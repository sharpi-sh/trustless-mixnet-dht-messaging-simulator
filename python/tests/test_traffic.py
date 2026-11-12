from random import Random

import pytest

from app.config import Config
from app.participants import People
from app.topology import MixNode, Topology
from app.traffic import LoopixTraffic, Packet


def traffic(*, retries=2):
    config = Config(max_retries=retries)
    rng = Random(23)
    return LoopixTraffic(config, Topology(config, rng, People(config, rng)), rng)


def deliver(network: LoopixTraffic, packet: Packet):
    now = 100
    for index, expected_node in enumerate(packet.route.nodes):
        assert packet.expected_node == expected_node
        hop = network.process(packet.id, expected_node, now)
        if hop.next_id is None:
            assert index == len(packet.route.nodes) - 1
            return hop
        assert hop.next_id == packet.route.nodes[index + 1]
        assert hop.payload is None and hop.packet
        assert hop.delay_ms == packet.route.delays_ms[index]
        assert packet.release_at == now + hop.delay_ms
        node = network.topology.nodes[expected_node]
        if isinstance(node, MixNode):
            assert node.delayed_packets[packet.id] == packet.release_at
        if hop.delay_ms:
            with pytest.raises(ValueError, match="cannot be released"):
                network.release(packet.id, expected_node, packet.release_at - 1)
        now = packet.release_at
        network.release(packet.id, expected_node, now)
        if isinstance(node, MixNode):
            assert packet.id not in node.delayed_packets
        now += 100
    pytest.fail("No terminal Sphinx layer")


@pytest.mark.parametrize(
    "direction,source,target",
    [
        ("forward", "sender-1", "receiver-1"),
        ("reply", "receiver-1", "sender-1"),
    ],
)
def test_payload_peels_and_queues_each_hop(direction, source, target):
    network = traffic()
    packet = network.build_packet("payload", source, target, b"sealed application envelope", direction)
    first, last = network.topology.provider_for(source), network.topology.provider_for(target)
    assert packet.first_node == first and packet.route.nodes[-1] == last
    assert deliver(network, packet).payload == b"sealed application envelope"
    assert packet.status == "completed"
    first_mix = network.topology.nodes[packet.route.nodes[1]]
    assert first_mix.adjacent_peers[first].status == "online"
    assert first_mix.adjacent_peers[first].successes == 1


def test_clocks_are_independent_and_empty_payload_ticks_become_drop_cover():
    original, replay = traffic(), traffic()
    for _ in range(100):
        original.clock("drop", "sender-1", 100)
    assert original.clock("payload", "sender-1", 200) == replay.clock("payload", "sender-1", 200)
    for kind in ("payload", "drop"):
        packet = original.fire(kind, "sender-1")
        assert packet.kind == "drop"
        assert packet.route.nodes[-1] in original.topology.mixnet.providers
        assert deliver(original, packet).drop


def test_client_loops_return_to_origin_provider_and_mix_loops_begin_on_adjacent_path():
    network = traffic()
    client = network.fire("client_loop", "sender-1")
    assert client.first_node == client.route.nodes[-1] == network.topology.provider_for("sender-1")
    assert client.target_id == client.source_id
    assert not deliver(network, client).drop
    mix = network.fire("mix_loop", "mix-3")
    assert network.topology.path_id(mix.source_id, mix.first_node) in network.topology.paths
    assert mix.route.nodes[-1] == mix.source_id == "mix-3"
    assert not deliver(network, mix).drop


def test_offline_hop_records_unresponsiveness_and_retries_are_bounded():
    network = traffic(retries=1)
    original = network.fire("payload", "sender-1", "receiver-1", b"safe")
    now = 0
    for node_id in original.route.nodes[:2]:
        hop = network.process(original.id, node_id, now)
        now += hop.delay_ms
        network.release(original.id, node_id, now)
    observing_id, unavailable = original.route.nodes[1:3]
    network.topology.nodes[unavailable].online = False
    with pytest.raises(ValueError, match="unavailable"):
        network.process(original.id, unavailable, now)
    entry = network.topology.nodes[observing_id].adjacent_peers[unavailable]
    assert entry.status == "unresponsive" and entry.last_failure == now and entry.failures == 1
    assert original.status == "failed"
    fresh = network.retry(original.id)
    assert fresh is not None and fresh.attempt == 2 and fresh.id != original.id
    assert fresh.route.seed != original.route.seed and fresh.original_payload == b"safe"
    assert network.retry(original.id) is fresh
    network.fail(fresh.id, now, "Timeout")
    assert network.retry(fresh.id) is None
    cover = network.fire("mix_loop", "mix-2")
    network.fail(cover.id, now, "Timeout")
    assert network.retry(cover.id) is None


def test_replayed_wire_is_rejected_by_receiving_node():
    network = traffic()
    first = network.fire("payload", "sender-1", "receiver-1", b"safe")
    replay = network.fire("payload", "sender-1", "receiver-1", b"safe")
    replay.wire = first.wire
    network.process(first.id, first.first_node, 0)
    with pytest.raises(ValueError, match="replay"):
        network.process(replay.id, replay.first_node, 1)
    assert replay.status == "failed" and network.sphinx.replay_count(first.first_node) == 1
