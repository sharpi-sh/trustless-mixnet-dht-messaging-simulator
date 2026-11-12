from itertools import product

import pytest

from app.config import Config
from app.lab import Laboratory
from app.stream import snapshot


@pytest.mark.parametrize("sender,recipient", product(("tor", "shadowsocks", "direct"), repeat=2))
def test_per_side_channel_endpoints_and_ip_views_are_published_in_both_directions(sender, recipient):
    lab = Laboratory(Config(random_seed=42, sender_channel=sender, recipient_channel=recipient))
    state = snapshot(lab, 0)
    nodes = {n.id: n for n in state.topology.nodes}
    paths = {p.id: p for p in state.topology.paths}
    assert len(nodes) == len(snapshot(Laboratory(Config(random_seed=42)), 0).topology.nodes)
    for person, kind, provider, stage in (
        ("sender-1", sender, "provider-west", "Sender connection"),
        ("receiver-1", recipient, "provider-east", "Recipient connection"),
    ):
        device = next(d for d in state.devices if d.id == person)
        endpoint = nodes[f"{kind}-{person}"]
        assert (device.channel, device.channel_id, device.tor_id) == (kind, endpoint.id, endpoint.id)
        assert (endpoint.kind, endpoint.stage) == (kind, stage)
        assert lab.topology.channel_ids[person] == endpoint.id
        assert (
            lab.inspect(endpoint.id)["profile"]["id"]
            == {
                "tor": "tor-abstraction",
                "shadowsocks": "shadowsocks-abstraction",
                "direct": "direct-connection",
            }[kind]
        )
        participant_ip = nodes[person].simulated_address
        ingress, egress = endpoint.simulated_address, endpoint.egress_address
        assert egress
        assert (ingress == egress) == (kind != "tor")
        assert (participant_ip == ingress) == (kind == "direct")
        client_leg = paths[lab.topology.path_id(person, endpoint.id)]
        assert client_leg.local == (kind == "direct")
        if client_leg.local:
            assert (client_leg.base_transit_delay_ms, client_leg.jitter_max_ms) == (0, 0)
            assert nodes[person].operator_id == endpoint.operator_id
        forwards, backwards = client_leg.ip_hops[person], client_leg.ip_hops[endpoint.id]
        assert forwards.local == backwards.local == client_leg.local
        assert (forwards.source_ip, forwards.destination_ip, forwards.observer) == (
            participant_ip,
            ingress,
            endpoint.id,
        )
        assert (backwards.source_ip, backwards.destination_ip, backwards.observer) == (
            ingress,
            participant_ip,
            person,
        )
        for remote in (provider, "dht-1", "storage-1"):
            peer_ip = nodes[remote].simulated_address
            remote_leg = paths[lab.topology.path_id(endpoint.id, remote)]
            forwards, backwards = remote_leg.ip_hops[endpoint.id], remote_leg.ip_hops[remote]
            assert not remote_leg.local
            assert (forwards.source_ip, forwards.destination_ip, forwards.observed_source_ip) == (
                egress,
                peer_ip,
                egress,
            )
            assert (backwards.source_ip, backwards.destination_ip, backwards.observed_source_ip) == (
                peer_ip,
                egress,
                peer_ip,
            )


def test_default_channel_ids_and_mix_peer_visibility():
    lab = Laboratory(Config(random_seed=9))
    assert lab.config.sender_channel == lab.config.recipient_channel == "tor"
    assert lab.topology.channel_ids["sender-1"] == "tor-sender-1"
    mix = lab.topology.mixnet.layers[0][0]
    hop = lab.topology.paths[lab.topology.path_id("provider-west", mix)].ip_hops["provider-west"]
    assert hop.observer == mix
    assert (
        hop.source_ip == hop.observed_source_ip == lab.topology.nodes["provider-west"].simulated_address
    )
    assert hop.destination_ip == lab.topology.nodes[mix].simulated_address
