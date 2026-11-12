from collections import Counter

from app.config import Config
from app.engine import Engine
from app.packet_runtime import PacketDelivered, PacketFailed, PacketRuntime, TrafficClock
from app.steps import Action


class PacketEngine(Engine):
    def __init__(self):
        super().__init__(
            Config(
                random_seed=45,
                min_nodes=10,
                max_nodes=10,
                base_transit_delay_ms=8,
                jitter_min_ms=0,
                jitter_max_ms=0,
                mu_per_second=100,
                max_retries=1,
                ack_timeout_ms=25,
            )
        )
        self.runtime = PacketRuntime(self)
        self.terminal = []
        self.lifecycle("run")

    def handle(self, action: Action) -> bool:
        if isinstance(action, (PacketDelivered, PacketFailed)):
            self.terminal.append(action)
            return True
        return self.runtime.handle(action)

    def through(self, predicate):
        for _ in self.drain(1000):
            if predicate():
                assert all(e.event_type != "simulation_error" for e in self.events)
                return
        raise AssertionError("Logical clock did not reach the requested state")


def test_independent_clocks_start_once_and_stop_generating_at_completion():
    sim = PacketEngine()
    sim.runtime.start()
    sim.runtime.start()
    timers = [x[2].action for x in sim.queue if isinstance(x[2].action, TrafficClock)]
    assert Counter(t.kind for t in timers) == {
        "payload": 2,
        "drop": 2,
        "client_loop": 2,
        "mix_loop": 10,
    }
    assert all(x[0] > 0 for x in sim.queue)
    sim.status = "completed"
    size = len(sim.queue)
    assert sim.runtime.handle(timers[0])
    assert len(sim.queue) == size and not sim.runtime.traffic.packets
    assert not sim.runtime.handle(Action())


def test_large_encrypted_payload_uses_independent_packets_and_real_links():
    sim = PacketEngine()
    body = bytes(range(255)) * 8
    sim.runtime.outbox["sender-1"].append(("msg-1", "receiver-1", body, "forward"))
    sim.schedule(TrafficClock(source="sender-1", kind="payload"))
    sim.through(lambda: bool(sim.terminal))
    [result] = sim.terminal
    assert isinstance(result, PacketDelivered)
    assert (result.source, result.target, result.message_id, result.payload) == (
        "provider-east",
        "receiver-1",
        "msg-1",
        body,
    )
    routes = [
        e for e in sim.events if e.event_type == "mixnet_route_constructed" and e.message_id == "msg-1"
    ]
    assert len(routes) == 3 and len({e.payload["decision_seed"] for e in routes}) == 3
    for event in routes:
        token = event.payload["packet_id"]
        ordered = ["sender-1", "tor-sender-1", *event.payload["ordered_route"]]
        traversed = [
            (e.source_id, e.target_id)
            for e in sim.events
            if e.event_type == "path_transit_completed" and e.payload["token"] == token
        ]
        assert traversed == list(zip(ordered, ordered[1:]))
        accepted = [
            e
            for e in sim.events
            if e.event_type == "sphinx_layer_processed" and e.payload["token"] == token
        ]
        assert len(accepted) == 5 and all(e.payload["integrity"] == "verified" for e in accepted)
        queued = [
            e for e in sim.events if e.event_type == "mix_packet_queued" and e.payload["token"] == token
        ]
        released = [
            e
            for e in sim.events
            if e.event_type == "mix_packet_released" and e.payload["token"] == token
        ]
        assert len(queued) == len(released) == 4
        assert [e.payload["release_at"] for e in queued] == [e.simulation_time_ms for e in released]
    tor = sim.clients.people["sender-1"].tor
    assert tor.entry_count == tor.exit_count == 3
    assert sim.clients.people["receiver-1"].tor.entry_count == 0
    assert all("payload" not in e.payload for e in sim.events)


def test_egress_timeout_retries_fresh_at_the_sender_and_only_fails_once():
    sim = PacketEngine()
    path = sim.topology.paths[sim.topology.path_id("tor-sender-1", "provider-west")]
    path.blocked = True
    sim.runtime.outbox["sender-1"].append(("msg-1", "receiver-1", b"envelope", "forward"))
    sim.schedule(TrafficClock(source="sender-1", kind="payload"))
    sim.through(lambda: bool(sim.terminal))
    [failed] = sim.terminal
    assert isinstance(failed, PacketFailed) and failed.message_id == "msg-1"
    attempts = [p for p in sim.runtime.traffic.packets.values() if p.kind == "payload"]
    assert [p.attempt for p in attempts] == [1, 2] and all(p.status == "failed" for p in attempts)
    assert attempts[0].retry_id == attempts[1].id and attempts[0].route.seed != attempts[1].route.seed
    tor = sim.clients.people["sender-1"].tor
    assert tor.entry_count == 2 and tor.exit_count == 0
    failures = [e.simulation_time_ms for e in sim.events if e.event_type == "message_forward_failed"]
    blocks = [e.simulation_time_ms for e in sim.events if e.event_type == "path_transit_failed"]
    assert failures == [when + 25 for when in blocks]


def test_client_loop_reaches_own_polling_inbox_and_mix_loop_returns_over_links():
    sim = PacketEngine()
    sim.schedule(TrafficClock(source="receiver-1", kind="client_loop"))
    sim.schedule(TrafficClock(source="mix-1", kind="mix_loop"))
    sim.through(
        lambda: (
            len(sim.runtime.traffic.packets) >= 2
            and all(p.status == "completed" for p in sim.runtime.traffic.packets.values())
        )
    )
    assert sim.inboxes["receiver-1"].messages == [b""] and not sim.inboxes["sender-1"].messages
    assert not sim.terminal
    mix = next(p for p in sim.runtime.traffic.packets.values() if p.kind == "mix_loop")
    hops = [
        (e.source_id, e.target_id)
        for e in sim.events
        if e.event_type == "path_transit_completed" and e.payload["token"] == mix.id
    ]
    expected = ["mix-1", *mix.route.nodes]
    assert hops == list(zip(expected, expected[1:]))
    assert hops[-1][1] == "mix-1"
