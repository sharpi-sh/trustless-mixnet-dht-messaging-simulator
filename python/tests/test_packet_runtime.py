import itertools
from collections import Counter

import pytest

from app.config import Config
from app.engine import Engine, Intervention, Transit
from app.packet_runtime import PacketArrival, PacketDelivered, PacketFailed, PacketRuntime, TrafficClock
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
        assert traversed == list(itertools.pairwise(ordered))
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
    assert hops == list(itertools.pairwise(expected))
    assert hops[-1][1] == "mix-1"


def start_payload(sim):
    sim.runtime.outbox["sender-1"].append(("msg-1", "receiver-1", b"envelope", "forward"))
    sim.schedule(TrafficClock(source="sender-1", kind="payload"))


def set_online(sim, uid, online):
    sim.intervene(
        Intervention(
            command="availability", target=uid, enabled=online, token=f"availability-{uid}-{sim.serial}"
        )
    )


def event_rows(sim, kind, packet):
    return [e for e in sim.events if e.event_type == kind and e.payload.get("token") == packet.id]


@pytest.mark.parametrize("node_id", ["tor-sender-1", "provider-east"])
def test_offline_after_arrival_prevents_processing(node_id):
    sim = PacketEngine()
    start_payload(sim)
    sim.through(
        lambda: (
            isinstance(sim.queue[0][2].action, PacketArrival)
            and sim.queue[0][2].action.target == node_id
        )
    )
    packet = sim.runtime.traffic.packets[sim.queue[0][2].action.token]
    set_online(sim, node_id, False)
    sim.through(lambda: packet.status == "failed")
    assert not [
        e for e in event_rows(sim, "message_forward_succeeded", packet) if e.target_id == node_id
    ]
    assert not [e for e in event_rows(sim, "sphinx_layer_processed", packet) if e.target_id == node_id]
    if node_id.startswith("tor"):
        assert sim.clients.people["sender-1"].tor.entry_count == 0
    else:
        assert sim.runtime.traffic.sphinx.replay_count(node_id) == 0
    assert not sim.terminal


@pytest.mark.parametrize(
    "failure",
    [
        "queue owner offline",
        "offline before dispatch",
        "link blocked",
        "target offline",
        "drop in flight",
        "offline observer",
    ],
)
def test_only_dispatched_mix_hops_update_live_observer(failure):
    sim = PacketEngine()
    start_payload(sim)
    sim.through(
        lambda: any(
            p.queued_at and p.queued_at.startswith("mix-") for p in sim.runtime.traffic.packets.values()
        )
    )
    packet = next(
        p
        for p in sim.runtime.traffic.packets.values()
        if p.queued_at and p.queued_at.startswith("mix-")
    )
    source, target = packet.queued_at, packet.expected_node
    node = sim.topology.nodes[source]
    edge = sim.topology.paths[sim.topology.path_id(source, target)]
    if failure == "queue owner offline":
        set_online(sim, source, False)
    else:
        sim.through(
            lambda: (
                isinstance(sim.queue[0][2].action, Transit) and sim.queue[0][2].action.source == source
            )
        )
        if failure == "offline before dispatch":
            set_online(sim, source, False)
        elif failure == "link blocked":
            sim.intervene(Intervention(command="path", target=edge.id, enabled=False, token="block"))
        else:
            sim.advance()
            assert edge.active
            if failure == "drop in flight":
                sim.intervene(
                    Intervention(
                        command="path", target=edge.id, enabled=False, drop_in_flight=True, token="drop"
                    )
                )
            else:
                set_online(sim, target, False)
                if failure == "offline observer":
                    set_online(sim, source, False)
    sim.through(lambda: packet.status == "failed")
    assert packet.id not in node.delayed_packets and packet.queued_at is None
    assert edge.attempted == int(failure != "queue owner offline")
    assert sum(e.source_id == source for e in event_rows(sim, "mix_packet_released", packet)) == int(
        failure != "queue owner offline"
    )
    observed = failure in {"target offline", "drop in flight"}
    assert node.adjacent_peers[target].failures == int(observed)
    assert (
        bool(
            [
                e
                for e in event_rows(sim, "mixnet_adjacency_updated", packet)
                if e.payload["observation"] == "unresponsive"
            ]
        )
        == observed
    )
    if observations := event_rows(sim, "path_transit_failed", packet):
        assert observations[0].payload["dispatched"] == (observed or failure == "offline observer")
    assert event_rows(sim, "sphinx_layer_processed", packet)[-1].target_id != target


@pytest.mark.parametrize("recovery", [False, True])
def test_offline_source_wait_is_bounded_and_produces_no_packet(recovery):
    sim = PacketEngine()
    set_online(sim, "sender-1", False)
    start_payload(sim)
    sim.advance()
    assert not sim.runtime.traffic.packets and len(sim.runtime.outbox["sender-1"]) == 1
    if recovery:
        set_online(sim, "sender-1", True)
    sim.through(lambda: bool(sim.terminal))
    [result] = sim.terminal
    if recovery:
        assert isinstance(result, PacketDelivered) and result.payload == b"envelope"
    else:
        assert isinstance(result, PacketFailed) and result.reason == "Source unavailable"
        assert sim.now == (1 + sim.config.max_retries) * sim.config.ack_timeout_ms
        assert not sim.runtime.traffic.packets
    assert not sim.runtime.outbox["sender-1"]


@pytest.mark.parametrize("recovery", [False, True])
def test_retry_waits_for_live_source(recovery):
    sim = PacketEngine()
    start_payload(sim)
    sim.advance()
    packet = next(iter(sim.runtime.traffic.packets.values()))
    set_online(sim, "sender-1", False)
    sim.through(lambda: packet.status == "failed")
    assert packet.retry_id is None
    if recovery:
        set_online(sim, "sender-1", True)
    sim.through(lambda: bool(sim.terminal))
    [result] = sim.terminal
    if recovery:
        assert isinstance(result, PacketDelivered) and packet.retry_id is not None
        assert sim.runtime.traffic.packets[packet.retry_id].route.seed != packet.route.seed
    else:
        assert isinstance(result, PacketFailed) and packet.retry_id is None
    assert packet.original_payload == b""
