"""The selected access channel owns real forwards, replies, pull traffic and vault reads."""

from itertools import product

import pytest

from app.config import Config, Outage
from app.engine import Engine, Intervention
from app.lab import Laboratory
from app.steps import Action


def config(sender, recipient, **changes):
    return Config(
        sender_channel=sender,
        recipient_channel=recipient,
        random_seed=29,
        min_nodes=10,
        max_nodes=10,
        dht_nodes=3,
        storage_nodes=3,
        base_transit_delay_ms=5,
        jitter_min_ms=1,
        jitter_max_ms=2,
        payload_rate_per_minute=90,
        polling_interval_ms=500,
        mu_per_second=70,
        **changes,
    )


@pytest.mark.parametrize("sender,recipient", list(product(("tor", "shadowsocks", "direct"), repeat=2)))
def test_channels_carry_signed_messages_polls_lookups_and_vault_responses(sender, recipient):
    lab = Laboratory(config(sender, recipient))
    lab.lifecycle("run")
    for _ in lab.drain(15000):
        if lab.status != "running":
            break
    assert lab.status == "completed"
    assert lab.outcomes == {"msg-1": "received", "msg-2": "received"}
    starts = [e for e in lab.events if e.event_type == "path_transit_started"]
    received = {
        e.payload["transit_id"]: e for e in lab.events if e.event_type == "path_transit_completed"
    }
    for departure in starts:
        path = lab.topology.paths[departure.payload["path_id"]]
        a, b = departure.source_id, departure.target_id
        projection = path.ip_hops[a]
        expected = projection.model_dump()
        assert departure.payload["ip_hop"] == expected
        assert expected["observer"] == b and expected["observed_source_ip"] == expected["source_ip"]
        assert (expected["source_ip"], expected["destination_ip"]) == (
            path.ip_hops[b].destination_ip,
            path.ip_hops[b].source_ip,
        )
        if path.local:
            assert departure.payload["delay_ms"] == 0 and departure.payload["ip_observation"] == "local"
        else:
            assert (
                6 <= departure.payload["delay_ms"] <= 7
                and departure.payload["ip_observation"] == "in_transit"
            )
        arrival = received.get(departure.payload["transit_id"])
        if arrival:
            assert (arrival.source_id, arrival.target_id) == (a, b) and arrival.payload[
                "ip_hop"
            ] == expected
            assert arrival.payload["ip_observation"] == ("local" if path.local else "received")
    for msg in lab.clients.messages.values():
        payload = [
            e
            for e in starts
            if e.message_id == msg.id and e.payload.get("cargo", {}).get("kind") == "Sphinx packet"
        ]
        source = lab.clients.people[msg.sender_id]
        access = lab.topology.nodes[source.tor.id]
        person_ip = lab.topology.nodes[source.id].simulated_address
        assert (payload[0].source_id, payload[0].target_id) == (source.id, access.id)
        assert payload[0].payload["ip_hop"]["destination_ip"] == access.simulated_address
        assert payload[0].payload["ip_hop"]["source_ip"] == person_ip
        assert payload[1].source_id == access.id
        assert payload[1].payload["ip_hop"]["observed_source_ip"] == access.egress_address
        assert (access.egress_address == person_ip) == (source.tor.kind == "direct")
        if msg.direction == "forward":
            first = lab.events[lab.first_message_hop_sequence - 1]
            assert first.event_id == payload[int(source.tor.kind == "direct")].event_id
            assert not first.payload["ip_hop"]["local"]
        owner = lab.clients.people[msg.target_id]
        channel = lab.topology.nodes[owner.tor.id]
        retrieval = [
            e for e in starts if e.message_id == msg.id and channel.id in (e.source_id, e.target_id)
        ]
        gateway = lab.topology.mixnet.providers[int(owner.role == "receiver")]
        assert not any(
            uid.startswith(("storage-", "dht-"))
            for event in retrieval
            for uid in (event.source_id, event.target_id)
        )
        assert any(e.source_id == channel.id and e.target_id == gateway for e in retrieval)
        assert any(e.source_id == gateway and e.target_id == channel.id for e in retrieval)
        assert {
            e.payload["operation"]
            for e in lab.events
            if e.message_id == msg.id and e.event_type == "retrieval_reply_received"
        } == {"manifest", "fragment"}
        assert any(
            e.payload["token"].startswith("poll-")
            and e.source_id == channel.id
            and e.target_id == owner.id
            for e in starts
        )
        events = [
            e
            for e in lab.events
            if e.payload.get("owner") == owner.id
            and e.event_type in {owner.tor.kind + "_entry", owner.tor.kind + "_exit"}
        ]
        assert events
        assert sum(e.event_type.endswith("_entry") for e in events) == owner.tor.entry_count
        assert sum(e.event_type.endswith("_exit") for e in events) == owner.tor.exit_count
        assert all(e.payload["ip_hop"]["observer"] == e.target_id for e in events)


def test_unstarted_external_path_does_not_claim_the_remote_peer_saw_a_packet():
    sim = Engine(config("direct", "tor"))
    sim.lifecycle("run")
    source = "direct-sender-1"
    target = "provider-west"
    path = sim.topology.paths[sim.topology.path_id(source, target)]
    sim.intervene(Intervention(command="path", token="reject", target=path.id, enabled=False))
    sim.transit(source, target, Action(), Action(), token="blocked")
    sim.advance()
    [failure] = [e for e in sim.events if e.event_type == "path_transit_failed"]
    assert not failure.payload["dispatched"] and failure.payload["ip_observation"] == "not_received"
    assert failure.payload["ip_hop"]["source_ip"] == sim.topology.nodes["sender-1"].simulated_address
    assert not [e for e in sim.events if e.event_type == "path_transit_completed"]


def test_direct_interface_shares_outages_with_device_and_its_local_handoff_cannot_be_blocked():
    sim = Engine(
        config(
            "direct",
            "shadowsocks",
            pattern="scheduled",
            scheduled_outages=[
                Outage(node_id="direct-sender-1", start_ms=5, duration_ms=4),
                Outage(node_id="sender-1", start_ms=7, duration_ms=4),
            ],
        )
    )
    sim.lifecycle("run")
    list(sim.drain(20))
    device = sim.topology.nodes["sender-1"]
    local = sim.topology.nodes["direct-sender-1"]
    assert device.history == local.history == [(5, False), (11, True)]
    sim.intervene(Intervention(command="availability", token="off", target=local.id, enabled=False))
    assert not device.online and not local.online
    sim.intervene(Intervention(command="availability", token="on", target=device.id, enabled=True))
    assert device.online and local.online
    edge = sim.topology.paths[sim.topology.path_id(device.id, local.id)]
    result = sim.intervene(Intervention(command="path", token="block", target=edge.id, enabled=False))
    assert result.outcome == "failed" and not edge.blocked
