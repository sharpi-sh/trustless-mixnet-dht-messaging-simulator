from app.network import Config, NetworkSimulation


def test_inspectors_and_scheduled_cover_transport():
    s = NetworkSimulation(Config(random_seed=733))
    assert s.inspect("mix-1")["state"]["replay_tags"] == 0
    assert s.inspect("dht-1")["state"]["k"] == 20
    assert s.inspect("storage-1")["state"]["fragment_ids"] == []
    assert s.inspect("tor-sender-1")["state"]["owner"] == "sender-1"
    s.lifecycle("run")
    for _ in s.drain(200):
        if any(e.event_type == "sphinx_layer_processed" for e in s.events):
            break
    kinds = {e.event_type for e in s.events}
    assert {
        "path_transit_started",
        "path_transit_completed",
        "sphinx_layer_processed",
        "cover_packet_generated",
    } <= kinds
    assert not any(e.event_type == "simulation_error" for e in s.events)


def test_provider_and_device_inspectors_count_only_their_local_queued_items():
    s = NetworkSimulation(Config(random_seed=733))
    s.inboxes["receiver-1"].messages.append(b"opaque receiver cell")
    s.packets.outbox["sender-1"].append(("message", "receiver-1", b"ciphertext", "forward"))
    assert s.inspect("provider-east")["state"]["queued_cells"] == 1
    assert s.inspect("provider-west")["state"]["queued_cells"] == 0
    assert s.inspect("provider-east")["state"]["inbound_queue"] == 1
    assert s.inspect("mix-1")["state"]["inbound_queue"] == 0
    assert s.inspect("sender-1")["state"]["outbound_queue"] == 1
    assert s.inspect("receiver-1")["state"]["outbound_queue"] == 0
    assert "opaque receiver cell" not in str(s.inspect("provider-east"))
    assert "ciphertext" not in str(s.inspect("sender-1"))
