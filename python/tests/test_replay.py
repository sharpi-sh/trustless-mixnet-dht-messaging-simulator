from app.config import Config
from app.lab import Laboratory


def run_decisions():
    sim=Laboratory(Config(random_seed=773,payload_rate_per_minute=300,
               polling_interval_ms=150,base_transit_delay_ms=2,jitter_max_ms=2,
               mu_per_second=100,dht_nodes=3,storage_nodes=3,
               client_loop_rate_per_minute=.2,drop_cover_rate_per_minute=.2,mix_loop_rate_per_minute=.2))
    sim.lifecycle("run")
    for _ in sim.drain(15000):
        pass
    assert sim.status=="completed"
    return [(e.event_type,e.source_id,e.target_id,e.simulation_time_ms,e.payload.get("ordered_route"))
            for e in sim.events if e.event_type in {"mixnet_route_constructed","path_transit_failed",
            "path_transit_started","message_decrypted","poll_message_found"}]


def test_seed_reproduces_actual_routes_and_clock_with_fresh_keys():
    assert run_decisions()==run_decisions()
