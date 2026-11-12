"""Full three-conversation scenario, driven one ordinary logical step at a time."""

from collections import Counter

from app.config import Config, Outage
from app.engine import Intervention
from app.lab import Laboratory


def test_three_senders_five_exchanges_with_polling_outages_and_retry():
    config = Config(
        sender_count=3,
        receiver_count=1,
        exchanges=5,
        min_nodes=15,
        max_nodes=15,
        pairing_strategy="all_to_one",
        random_seed=254,
        step_delay_ms=500,
        polling_enabled=False,
        polling_interval_ms=600,
        poll_batch=6,
        payload_rate_per_minute=90,
        client_loop_rate_per_minute=0.15,
        drop_cover_rate_per_minute=0.15,
        mix_loop_rate_per_minute=0.15,
        base_transit_delay_ms=8,
        jitter_min_ms=0,
        jitter_max_ms=4,
        mu_per_second=45,
        dht_nodes=5,
        storage_nodes=5,
        replicas=2,
        max_retries=10,
        ack_timeout_ms=30,
        pattern="scheduled",
        scheduled_outages=[
            Outage(node_id="mix-5", start_ms=5, duration_ms=500),
            Outage(node_id="mix-15", start_ms=8, duration_ms=500000),
        ],
    )
    lab = Laboratory(config)
    initial = lab.snapshot()
    assert initial["status"] == "ready" and not initial["initialised"]
    assert initial["step_delay_ms"] == 500 and initial["random_seed"] == 254
    assert len({device["tor_id"] for device in initial["devices"]}) == 4
    kinds = Counter(n["kind"] for n in initial["topology"]["nodes"])
    assert kinds["person"] == 4 and kinds["mix"] == 15 and kinds["provider"] == 2
    assert kinds["dht"] == kinds["storage"] == 5
    profiles = {p["id"]: p for p in initial["profiles"]}
    assert profiles["loopix-usenix-2017"]["year"] == 2017
    assert profiles["kademlia-2002"]["parameters"] == {
        "k": 20,
        "alpha": 3,
        "id_bits": 160,
        "nodes": 5,
        "rpc_timeout_ms": 2000,
    }
    messages = {m["id"]: m for m in initial["messages"]}
    assert len(messages) == 30 and len({m["conversation_id"] for m in messages.values()}) == 3
    edited = "Bob, meet me at the east pier."
    msg_id = next(m["id"] for m in messages.values() if m["direction"] == "forward")
    lab.edit_messages({msg_id: edited})
    lab.lifecycle("run")
    cursor = 0
    first_packet = blocked = restored = published_at = enabled_at = None
    routes = {}
    for _ in lab.drain(50000):
        recent = lab.events[cursor:]
        cursor = len(lab.events)
        for event in recent:
            kind, data = event.event_type, event.payload
            assert kind != "simulation_error", event
            if kind == "mixnet_route_constructed":
                routes[data["packet_id"]] = event
                if first_packet is None and data["traffic"] == "payload":
                    first_packet = data["packet_id"]
                    blocked = lab.topology.path_id(event.source_id, f"tor-{event.source_id}")
                    result = lab.intervene(
                        Intervention(command="path", target=blocked, enabled=False, token="block-first")
                    )
                    assert result.outcome == "applied" and lab.topology.paths[blocked].blocked
            if (
                kind == "path_transit_failed"
                and data["token"] == first_packet
                and data["path_id"] == blocked
                and restored is None
            ):
                assert data["reason"] == "blocked"
                restored = event.sequence
                lab.intervene(
                    Intervention(command="path", target=blocked, enabled=True, token="restore-first")
                )
                assert not lab.topology.paths[blocked].blocked
            if kind == "manifest_published" and published_at is None:
                published_at = event.simulation_time_ms
        if (
            published_at is not None
            and enabled_at is None
            and lab.now >= published_at + config.polling_interval_ms
        ):
            bob = lab.clients.people["receiver-1"]
            assert not bob.polling_enabled
            assert not any(row.state == "received" for row in bob.logs)
            assert not any(e.event_type == "message_decrypted" for e in lab.events)
            lab.intervene(
                Intervention(command="polling", target=bob.id, enabled=True, token="enable-bob")
            )
            enabled_at = lab.now
        if lab.status in {"completed", "failed"}:
            break

    assert lab.status == "completed", (lab.status, lab.now, len(lab.events))
    assert restored is not None and enabled_at is not None
    events = lab.events
    retry = next(
        e
        for e in events
        if e.event_type == "packet_retry_scheduled" and e.payload["previous_packet_id"] == first_packet
    )
    original, next_route = routes[first_packet], routes[retry.payload["packet_id"]]
    assert original.message_id == next_route.message_id
    assert original.payload["decision_seed"] != next_route.payload["decision_seed"]
    assert next_route.payload["attempt"] == 2
    assert all(e.payload["attempt"] <= config.max_retries + 1 for e in routes.values())
    assert any(
        e.event_type == "path_transit_failed"
        and e.message_id
        and e.payload["reason"] == "unresponsive"
        and e.target_id in {"mix-5", "mix-15"}
        for e in events
    )
    assert lab.topology.nodes["mix-5"].history[:2] == [(5, False), (505, True)]
    assert lab.topology.nodes["mix-15"].history[0] == (8, False)
    # The run can complete while the long logical outage is still in progress.
    if lab.now < 500008:
        assert lab.availability.offline_until["mix-15"] == 500008
    else:
        assert lab.topology.nodes["mix-15"].history[1] == (500008, True)

    sent, received = {}, []
    for device in lab.snapshot()["devices"]:
        logs = device["logs"]
        assert [row["simulation_time_ms"] for row in logs] == sorted(
            row["simulation_time_ms"] for row in logs
        )
        for row in logs:
            message = messages[row["message_id"]]
            if row["state"] in {"sent", "replied"}:
                assert device["id"] == message["sender_id"]
                sent[row["message_id"]] = row
            if row["state"] == "received":
                assert device["id"] == message["target_id"] and row["direction"] == message["direction"]
                assert row["simulation_time_ms"] >= enabled_at
                assert row["text"] == (edited if message["id"] == msg_id else message["text"])
                received.append(row["message_id"])
    assert set(sent) == set(messages) and sent[msg_id]["text"] == edited
    assert Counter(received) == Counter(list(messages))
    assert Counter(messages[uid]["direction"] for uid in received) == {"forward": 15, "reply": 15}

    line = [row for row in lab.snapshot()["lineage"] if row["message_id"] == msg_id]
    ops = [row["operation"] for row in line]
    required = [
        "public_key_retrieved",
        "reply_key_encapsulated",
        "message_encrypted",
        "fragment_stored",
        "manifest_published",
        "fragment_retrieved",
        "message_reconstructed",
        "message_decrypted",
        "reply_key_learned",
    ]
    positions = [ops.index(operation) for operation in required]
    assert positions == sorted(positions)
    learned = line[positions[-1]]
    assert learned["location"] == "receiver-1" and "unverified" in learned["detail"].lower()
    assert all(edited not in str(e.payload) for e in events)
    assert lab.clients.people["sender-1"].public_key.hex() not in str(line)

    starts = {e.payload["transit_id"]: e for e in events if e.event_type == "path_transit_started"}
    ends = [e for e in events if e.event_type == "path_transit_completed" and e.message_id]
    assert ends
    for end in ends:
        start = starts[end.payload["transit_id"]]
        dt = end.simulation_time_ms - start.simulation_time_ms
        assert dt == start.payload["delay_ms"] and 8 <= dt <= 12
    queued = {
        (e.payload["packet_id"], e.source_id): e for e in events if e.event_type == "mix_packet_queued"
    }
    releases = [e for e in events if e.event_type == "mix_packet_released" and e.message_id]
    assert releases
    for release in releases:
        started = queued[release.payload["packet_id"], release.source_id]
        assert release.simulation_time_ms - started.simulation_time_ms == started.payload["delay_ms"]
