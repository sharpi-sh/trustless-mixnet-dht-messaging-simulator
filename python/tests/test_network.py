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
