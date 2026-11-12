"""Source-generated Loopix traffic; the caller owns transit and the logical clock."""

from dataclasses import dataclass, field
from random import Random
from typing import Literal

from .config import Config
from .loopix import Loopix, Route, Traffic
from .sphinx import Hop, SphinxNetwork
from .topology import MixNode, Observation, Topology

Lane = Literal["forward", "reply"]


@dataclass(slots=True)
class Packet:
    id: str
    kind: Traffic
    source_id: str
    target_id: str
    lane: Lane
    route: Route
    attempt: int
    expected_node: str | None
    wire: bytes = field(repr=False)
    original_payload: bytes = field(repr=False)
    previous_node: str | None = None
    queued_at: str | None = None
    release_at: int | None = None
    status: Literal["active", "completed", "failed"] = "active"
    failure: str | None = None
    retry_id: str | None = None

    @property
    def first_node(self) -> str:
        return self.route.nodes[0]


class LoopixTraffic:
    def __init__(self, config: Config, topology: Topology, rng: Random):
        self.config = config
        self.topology = topology
        self.rng = rng
        self.routing = Loopix(topology.mixnet, config, rng)
        relay_ids = [n.id for n in topology.nodes.values() if n.kind in {"mix", "provider"}]
        self.sphinx = SphinxNetwork(relay_ids)
        self.packets: dict[str, Packet] = {}
        self._serial = 0
        self._clocks: dict[tuple[Traffic, str], Loopix] = {}
        for node in topology.nodes.values():
            kinds: tuple[Traffic, ...]
            if node.kind == "person":
                kinds = ("payload", "client_loop", "drop")
            elif node.kind == "mix":
                kinds = ("mix_loop",)
            else:
                continue
            for kind in kinds:
                self._clocks[kind, node.id] = Loopix(
                    topology.mixnet, config, Random(rng.getrandbits(128))
                )

    def clock(self, kind: Traffic, source_id: str, now: int) -> int:
        """Return the next firing time for one independent producer/process."""
        return now + self._clocks[kind, source_id].interval(kind)

    def fire(
        self,
        kind: Traffic,
        source_id: str,
        target_id: str | None = None,
        payload: bytes | None = None,
        lane: Lane = "forward",
    ) -> Packet:
        """An empty payload outbox consumes its tick by injecting drop cover."""
        if kind == "payload" and payload is None:
            kind = "drop"
        if kind in {"client_loop", "mix_loop"}:
            target_id = source_id
        elif kind == "drop":
            target_id = self.rng.choice(self.topology.mixnet.providers)
        if target_id is None:
            raise ValueError("Payload traffic requires a destination")
        return self.build_packet(kind, source_id, target_id, payload or b"", lane)

    def _provider(self, endpoint: str) -> str:
        if endpoint in self.topology.mixnet.providers:
            return endpoint
        if self.topology.nodes[endpoint].kind != "person":
            raise ValueError("Loopix endpoint must be a participant or provider")
        for provider in self.topology.mixnet.providers:
            if (
                self.topology.path_id(self.topology.channel_ids[endpoint], provider)
                in self.topology.paths
            ):
                return provider
        raise ValueError("Participant has no provider")

    def build_packet(
        self, kind: Traffic, source_id: str, target_id: str, payload: bytes, lane: Lane = "forward"
    ) -> Packet:
        if kind == "mix_loop":
            if self.topology.nodes[source_id].kind != "mix":
                raise ValueError("Mix loop must originate at a mix node")
            target_id = source_id
            route = self.routing.mix_loop(source_id)
        else:
            if kind == "client_loop":
                target_id = source_id
            route = self.routing.route(self._provider(source_id), self._provider(target_id))
        drop_at = len(route.nodes) - 1 if kind == "drop" else None
        wire = self.sphinx.build(route.nodes, route.delays_ms, payload, drop_at=drop_at)
        self._serial += 1
        packet = Packet(
            f"pkt-{self._serial}",
            kind,
            source_id,
            target_id,
            lane,
            route,
            1,
            route.nodes[0],
            wire,
            payload,
            previous_node=source_id if kind == "mix_loop" else None,
        )
        self.packets[packet.id] = packet
        return packet

    def local_observation(self, observer: str | None, peer: str) -> Observation | None:
        node = self.topology.nodes.get(observer) if observer is not None else None
        if isinstance(node, MixNode) and node.online:
            return node.adjacent_peers.get(peer)
        return None

    def observe(self, observer: str | None, peer: str, now: int, success: bool) -> bool:
        entry = self.local_observation(observer, peer)
        if entry is None:
            return False
        if success:
            entry.status = "online"
            entry.last_contact = now
            entry.successes += 1
            entry.failures = 0
        else:
            entry.status = "unresponsive"
            entry.failures += 1
            entry.last_failure = now
        return True

    def process(self, packet_id: str, node_id: str, now: int) -> Hop:
        packet = self.packets[packet_id]
        if packet.status != "active" or packet.expected_node != node_id or packet.queued_at is not None:
            raise ValueError("Packet is not awaiting reception at this node")
        node = self.topology.nodes[node_id]
        if not node.online:
            self.fail(packet_id, now, "Node unavailable", unresponsive=True)
            raise ValueError("Node unavailable")
        try:
            hop = self.sphinx.peel(node_id, packet.wire)
        except ValueError as error:
            self.fail(packet_id, now, str(error))
            raise

        self.observe(packet.previous_node, node_id, now, True)
        if packet.previous_node:
            self.observe(node_id, packet.previous_node, now, True)
        node.last_activity = now
        packet.expected_node = hop.next_id
        packet.previous_node = node_id
        packet.wire = hop.packet or b""
        if hop.next_id is None:
            packet.status = "completed"
            packet.original_payload = b""
        else:
            packet.queued_at = node_id
            packet.release_at = now + hop.delay_ms
            if isinstance(node, MixNode):
                node.delayed_packets[packet_id] = packet.release_at
        return hop

    def release(self, packet_id: str, node_id: str, now: int) -> None:
        packet = self.packets[packet_id]
        if packet.queued_at != node_id or packet.release_at is None or now < packet.release_at:
            raise ValueError("Packet cannot be released at this node and time")
        if not self.topology.nodes[node_id].online:
            raise ValueError("Queue owner unavailable")
        self._clear_queue(packet)

    def _clear_queue(self, packet: Packet) -> None:
        if packet.queued_at is not None:
            node = self.topology.nodes[packet.queued_at]
            if isinstance(node, MixNode):
                node.delayed_packets.pop(packet.id, None)
            packet.queued_at = None
            packet.release_at = None

    def fail(self, packet_id: str, now: int, reason: str, *, unresponsive: bool = False) -> bool:
        packet = self.packets[packet_id]
        if packet.status != "active":
            return False
        observed = (
            unresponsive
            and packet.expected_node is not None
            and self.observe(packet.previous_node, packet.expected_node, now, False)
        )
        self._clear_queue(packet)
        packet.status = "failed"
        packet.failure = reason
        packet.wire = b""
        return observed

    def retry(self, packet_id: str) -> Packet | None:
        packet = self.packets[packet_id]
        if packet.status != "failed":
            raise ValueError("Only failed packets may be retried")
        if packet.retry_id is not None:
            return self.packets[packet.retry_id]
        if packet.kind != "payload" or packet.attempt > self.config.max_retries:
            return None
        fresh = self.build_packet(
            packet.kind, packet.source_id, packet.target_id, packet.original_payload, packet.lane
        )
        fresh.attempt = packet.attempt + 1
        packet.retry_id = fresh.id
        packet.original_payload = b""
        return fresh
