"""Execute Loopix source, Tor, link and queue transitions on the logical clock."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from struct import Struct
from typing import TYPE_CHECKING

from .loopix import Traffic
from .steps import Action
from .traffic import Lane, LoopixTraffic, Packet

if TYPE_CHECKING:
    from .simulation import Simulation


@dataclass(kw_only=True)
class TrafficClock(Action):
    kind: Traffic


@dataclass(kw_only=True)
class PacketArrival(Action):
    pass


@dataclass(kw_only=True)
class PacketRelease(Action):
    pass


@dataclass(kw_only=True)
class PacketLost(Action):
    reason: str = "Path unresponsive"


@dataclass(kw_only=True)
class PacketDelivered(Action):
    payload: bytes = field(repr=False)


@dataclass(kw_only=True)
class PacketFailed(Action):
    reason: str


# Application transport framing inside the fixed Sphinx body. The egress owns
# reassembly. Sphinx relays never see the fragment fields or encrypted envelope.
_PART = Struct("!II")
_CHUNK = 896


@dataclass(slots=True)
class _Transfer:
    target: str
    lane: Lane
    data: bytes = field(repr=False)
    sent: int = 0
    count: int = field(init=False)
    received: dict[int, bytes] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.count = max(1, (len(self.data) + _CHUNK - 1) // _CHUNK)

    def take(self) -> bytes:
        index = self.sent
        self.sent += 1
        start = index * _CHUNK
        data = self.data[start:start+_CHUNK]
        if self.sent == self.count:
            self.data = b""
        return _PART.pack(index, self.count) + data

    def accept(self, body: bytes) -> bytes | None:
        if len(body) < _PART.size:
            raise ValueError("Truncated application fragment")
        index, count = _PART.unpack_from(body)
        if count != self.count or index >= count:
            raise ValueError("Invalid application fragment sequence")
        self.received.setdefault(index, body[_PART.size:])
        if len(self.received) == count:
            return b"".join(self.received[i] for i in range(count))
        return None


class PacketRuntime:
    def __init__(self, sim: Simulation):
        self.sim = sim
        self.traffic = LoopixTraffic(sim.config, sim.topology, sim.rng)
        self.outbox: dict[str, deque[tuple[str,str,bytes,Lane]]] = {p: deque() for p in sim.clients.people}
        self._transfers: dict[str,_Transfer] = {}
        self._sending: dict[str,str] = {}
        self._retries: dict[str,deque[tuple[str,Packet]]] = {p: deque() for p in sim.clients.people}
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        for node in self.sim.topology.nodes.values():
            if node.kind == "person":
                for kind in ("payload","client_loop","drop"):
                    self._schedule_clock(TrafficClock(source=node.id,kind=kind))
            elif node.kind == "mix":
                self._schedule_clock(TrafficClock(source=node.id,kind="mix_loop"))

    def _schedule_clock(self, action: TrafficClock) -> None:
        next_time = self.traffic.clock(action.kind,action.source,self.sim.now)
        self.sim.schedule(action,next_time-self.sim.now)

    def handle(self, action: Action) -> bool:
        if isinstance(action, TrafficClock):
            if self.sim.status not in {"completed","failed","stopped"}:
                self._schedule_clock(action)
                self._tick(action)
        elif isinstance(action, PacketArrival):
            self._arrive(action)
        elif isinstance(action, PacketRelease):
            self._release(action)
        elif isinstance(action, PacketLost):
            packet = self.traffic.packets[action.token]
            if packet.status == "active":
                self.traffic.fail(packet.id, self.sim.now,action.reason,unresponsive=True)
                self._failure(packet,action,action.reason)
        else:
            return False
        return True

    def _take_payload(self, source: str) -> tuple[str,Packet] | None:
        pending = self._retries[source]
        while pending:
            message_id, packet = pending.popleft()
            if message_id in self._transfers:
                return message_id,packet
            self.traffic.fail(packet.id,self.sim.now,"Application transfer already terminated")
            packet.original_payload = b""
        if source not in self._sending and self.outbox[source]:
            message_id, target, payload, lane = self.outbox[source].popleft()
            self._transfers[message_id] = _Transfer(target,lane,payload)
            self._sending[source] = message_id
        if source not in self._sending:
            return None
        message_id = self._sending[source]
        transfer = self._transfers[message_id]
        data = transfer.take()
        if transfer.sent == transfer.count:
            del self._sending[source]
        packet = self.traffic.fire("payload",source,transfer.target,data,transfer.lane)
        return message_id,packet

    def _tick(self, action: TrafficClock) -> None:
        source = action.source
        item = self._take_payload(source) if action.kind == "payload" else None
        if item:
            message_id,packet = item
        else:
            if not self.sim.topology.nodes[source].online:
                return
            cover_lane: Lane = "reply" if source in self.sim.clients.people and self.sim.clients.people[source].role == "receiver" else "forward"
            packet = self.traffic.fire(action.kind,source,lane=cover_lane)
            message_id = ""
        started = PacketArrival(source=source, target=packet.first_node, message_id=message_id,
                                token=packet.id,lane=packet.lane)
        self.sim.emit("mixnet_route_constructed",started,packet_id=packet.id,traffic=packet.kind,
                      attempt=packet.attempt,**packet.route.decision())
        if packet.kind != "payload":
            self.sim.emit("cover_packet_generated",started,packet_id=packet.id,traffic=packet.kind)
        first = packet.first_node if packet.kind == "mix_loop" else self.sim.clients.people[source].tor.id
        self._transit(packet,started,source,first)

    def _transit(self, packet: Packet, action: Action, source: str, target: str) -> None:
        success = PacketArrival(source=source,target=target,token=packet.id,lane=packet.lane,message_id=action.message_id)
        failure = PacketLost(source=source,target=target,token=packet.id,lane=packet.lane,message_id=action.message_id)
        self.sim.emit("message_forward_attempt",success,packet_id=packet.id,traffic=packet.kind,attempt=packet.attempt)
        self.sim.transit(source,target,success,failure,token=packet.id,lane=packet.lane)

    def _arrive(self, action: PacketArrival) -> None:
        packet = self.traffic.packets[action.token]
        if packet.status != "active":
            return
        node = self.sim.topology.nodes[action.target]
        self.sim.emit("message_forward_succeeded",action,packet_id=packet.id,traffic=packet.kind,attempt=packet.attempt)
        if node.kind == "tor":
            self.sim.clients.people[packet.source_id].tor.enter()
            self.sim.emit("tor_entry",action,packet_id=packet.id)
            self._transit(packet,action,node.id,packet.first_node)
            return
        if self.sim.topology.nodes[action.source].kind == "tor":
            self.sim.clients.people[packet.source_id].tor.exit()
            self.sim.emit("tor_exit",action,packet_id=packet.id)
        try:
            hop = self.traffic.process(packet.id,node.id,self.sim.now)
        except ValueError as err:
            self.traffic.fail(packet.id,self.sim.now,str(err))
            self._failure(packet, action,str(err))
            return
        self.sim.emit("sphinx_layer_processed",action,packet_id=packet.id,traffic=packet.kind,
                      replay_count=self.traffic.sphinx.replay_count(node.id),next_id=hop.next_id,
                      delay_ms=hop.delay_ms,integrity="verified")
        if self.sim.topology.nodes[action.source].kind == "mix" or node.kind == "mix":
            self.sim.emit("mixnet_adjacency_updated", action, observation="online",packet_id=packet.id)
        if hop.next_id is None:
            if packet.kind == "client_loop":
                self.sim.inboxes[packet.source_id].messages.append(b"")
            elif packet.kind == "payload" and action.message_id in self._transfers:
                transfer = self._transfers[action.message_id]
                assert hop.payload is not None
                payload = transfer.accept(hop.payload)
                if payload is not None:
                    del self._transfers[action.message_id]
                    self.sim.schedule(PacketDelivered(source=node.id,target=packet.target_id,token=packet.id,
                                          lane=packet.lane,message_id=action.message_id,payload=payload))
            return
        release = PacketRelease(source=node.id,target=hop.next_id,token=packet.id,lane=packet.lane,
                                message_id=action.message_id)
        self.sim.emit("mix_packet_queued",release,packet_id=packet.id,delay_ms=hop.delay_ms,
                      release_at=packet.release_at,traffic=packet.kind)
        self.sim.schedule(release,hop.delay_ms)

    def _release(self, action: PacketRelease) -> None:
        packet = self.traffic.packets[action.token]
        if packet.status != "active":
            return
        self.traffic.release(packet.id,action.source,self.sim.now)
        self.sim.emit("mix_packet_released",action,packet_id=packet.id,traffic=packet.kind)
        self._transit(packet,action,action.source,action.target)

    def _failure(self, packet: Packet, action: Action, reason: str) -> None:
        self.sim.emit("message_forward_failed",action,packet_id=packet.id,traffic=packet.kind,
                      attempt=packet.attempt,reason=reason)
        if self.sim.topology.nodes[action.source].kind == "mix":
            self.sim.emit("mixnet_adjacency_updated",action,observation="unresponsive",packet_id=packet.id)
        if packet.kind != "payload" or action.message_id not in self._transfers:
            packet.original_payload = b""
            return
        retry = self.traffic.retry(packet.id)
        if retry is not None:
            self._retries[packet.source_id].append((action.message_id,retry))
            self.sim.emit("packet_retry_scheduled", action,previous_packet_id=packet.id,packet_id=retry.id,
                          attempt=retry.attempt)
            return
        del self._transfers[action.message_id]
        if self._sending.get(packet.source_id) == action.message_id:
            del self._sending[packet.source_id]
        packet.original_payload = b""
        self.sim.schedule(PacketFailed(source=packet.source_id,target=packet.target_id,message_id=action.message_id,
                                     lane=packet.lane,token=packet.id,reason=reason))
