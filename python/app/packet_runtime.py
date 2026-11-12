"""Execute Loopix source, access-channel, link and queue transitions on the logical clock."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from struct import Struct

from .engine import Engine, FailureOrigin, TransportFailure
from .loopix import Traffic
from .steps import Action
from .traffic import Lane, LoopixTraffic, Packet


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
class PacketLost(TransportFailure):
    pass


@dataclass(kw_only=True)
class SourceDeadline(Action):
    outage_version: int


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
        data = self.data[start : start + _CHUNK]
        if self.sent == self.count:
            self.data = b""
        return _PART.pack(index, self.count) + data

    def accept(self, body: bytes) -> bytes | None:
        if len(body) < _PART.size:
            raise ValueError("Truncated application fragment")
        index, count = _PART.unpack_from(body)
        if count != self.count or index >= count:
            raise ValueError("Invalid application fragment sequence")
        self.received.setdefault(index, body[_PART.size :])
        if len(self.received) == count:
            return b"".join(self.received[i] for i in range(count))
        return None


class PacketRuntime:
    def __init__(self, sim: Engine):
        self.sim = sim
        self.traffic = LoopixTraffic(sim.config, sim.topology, sim.rng)
        self.outbox: dict[str, deque[tuple[str, str, bytes, Lane]]] = {
            p: deque() for p in sim.clients.people
        }
        self._transfers: dict[str, _Transfer] = {}
        self._sending: dict[str, str] = {}
        self._retries: dict[str, deque[tuple[str, Packet]]] = {p: deque() for p in sim.clients.people}
        self._source_deadlines: dict[str, SourceDeadline] = {}
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        for node in self.sim.topology.nodes.values():
            if node.kind == "person":
                clocks: tuple[Traffic, ...] = ("payload", "client_loop", "drop")
                for kind in clocks:
                    self._schedule_clock(TrafficClock(source=node.id, kind=kind))
            elif node.kind == "mix":
                self._schedule_clock(TrafficClock(source=node.id, kind="mix_loop"))

    def _schedule_clock(self, action: TrafficClock) -> None:
        next_time = self.traffic.clock(action.kind, action.source, self.sim.now)
        self.sim.schedule(action, next_time - self.sim.now)

    def handle(self, action: Action) -> bool:
        if isinstance(action, TrafficClock):
            if self.sim.status not in {"completed", "failed", "stopped"}:
                self._schedule_clock(action)
                self._tick(action)
        elif isinstance(action, PacketArrival):
            self._arrive(action)
        elif isinstance(action, PacketRelease):
            self._release(action)
        elif isinstance(action, SourceDeadline):
            self._expire_source(action)
        elif isinstance(action, PacketLost):
            packet = self.traffic.packets[action.token]
            if packet.status == "active":
                origin = action.origin
                assert origin is not None
                observed = self.traffic.fail(
                    packet.id,
                    self.sim.now,
                    origin.value,
                    unresponsive=(
                        origin.dispatched
                        and action.source == packet.previous_node
                        and action.target == packet.expected_node
                    ),
                )
                if observed:
                    self.sim.emit(
                        "mixnet_adjacency_updated",
                        action,
                        observation="unresponsive",
                        packet_id=packet.id,
                    )
                self._failure(packet, action, origin.value)
        else:
            return False
        return True

    def _take_payload(self, source: str) -> tuple[str, Packet] | None:
        pending = self._retries[source]
        while pending:
            message_id, packet = pending.popleft()
            if message_id in self._transfers:
                if packet.status == "failed":
                    ctx = Action(
                        source=source,
                        target=packet.target_id,
                        message_id=message_id,
                        token=packet.id,
                        lane=packet.lane,
                    )
                    packet = self._make_retry(packet, ctx)
                return message_id, packet
            self.traffic.fail(packet.id, self.sim.now, "Application transfer already terminated")
            packet.original_payload = b""
        if source not in self._sending and self.outbox[source]:
            message_id, target, payload, lane = self.outbox[source].popleft()
            self._transfers[message_id] = _Transfer(target, lane, payload)
            self._sending[source] = message_id
        if source not in self._sending:
            return None
        message_id = self._sending[source]
        transfer = self._transfers[message_id]
        data = transfer.take()
        if transfer.sent == transfer.count:
            del self._sending[source]
        packet = self.traffic.fire("payload", source, transfer.target, data, transfer.lane)
        return message_id, packet

    def _wait_for_source(self, source: str) -> None:
        node = self.sim.topology.nodes[source]
        queued = {uid: (target, lane) for uid, target, _, lane in self.outbox[source]}
        for uid in [self._sending.get(source), *(uid for uid, _ in self._retries[source])]:
            if uid is not None and uid in self._transfers:
                transfer = self._transfers[uid]
                queued[uid] = (transfer.target, transfer.lane)
        for uid, (target, lane) in queued.items():
            pending = self._source_deadlines.get(uid)
            if pending is None or pending.outage_version != len(node.history):
                check = SourceDeadline(
                    source=source,
                    target=target,
                    message_id=uid,
                    lane=lane,
                    outage_version=len(node.history),
                )
                self._source_deadlines[uid] = check
                self.sim.schedule(
                    check, (self.sim.config.max_retries + 1) * self.sim.config.ack_timeout_ms
                )

    def _expire_source(self, action: SourceDeadline) -> None:
        uid, source = action.message_id, action.source
        if self._source_deadlines.get(uid) is not action:
            return
        del self._source_deadlines[uid]
        node = self.sim.topology.nodes[source]
        if node.online or len(node.history) != action.outage_version:
            return
        # The scheduler expires unavailable application work; the device never constructs a packet.
        for item in list(self.outbox[source]):
            if item[0] == uid:
                self.outbox[source].remove(item)
        for entry in list(self._retries[source]):
            if entry[0] == uid:
                self._retries[source].remove(entry)
                packet = entry[1]
                self.traffic.fail(packet.id, self.sim.now, "Source unavailable")
                packet.original_payload = b""
        self._transfers.pop(uid, None)
        if self._sending.get(source) == uid:
            del self._sending[source]
        self.sim.schedule(
            PacketFailed(
                source=source,
                target=action.target,
                message_id=uid,
                lane=action.lane,
                reason="Source unavailable",
            )
        )

    def _tick(self, action: TrafficClock) -> None:
        source = action.source
        if not self.sim.topology.nodes[source].online:
            if action.kind == "payload":
                self._wait_for_source(source)
            return
        item = self._take_payload(source) if action.kind == "payload" else None
        if item:
            message_id, packet = item
            self._source_deadlines.pop(message_id, None)
        else:
            cover_lane: Lane = (
                "reply"
                if source in self.sim.clients.people
                and self.sim.clients.people[source].role == "receiver"
                else "forward"
            )
            packet = self.traffic.fire(action.kind, source, lane=cover_lane)
            message_id = ""
        started = PacketArrival(
            source=source,
            target=packet.first_node,
            message_id=message_id,
            token=packet.id,
            lane=packet.lane,
        )
        self.sim.emit(
            "mixnet_route_constructed",
            started,
            packet_id=packet.id,
            traffic=packet.kind,
            attempt=packet.attempt,
            **packet.route.decision(),
        )
        if packet.kind != "payload":
            self.sim.emit("cover_packet_generated", started, packet_id=packet.id, traffic=packet.kind)
        first = (
            packet.first_node if packet.kind == "mix_loop" else self.sim.clients.people[source].tor.id
        )
        self._transit(packet, started, source, first)

    def _transit(self, packet: Packet, action: Action, source: str, target: str) -> None:
        success = PacketArrival(
            source=source,
            target=target,
            token=packet.id,
            lane=packet.lane,
            message_id=action.message_id,
        )
        failure = PacketLost(
            source=source,
            target=target,
            token=packet.id,
            lane=packet.lane,
            message_id=action.message_id,
        )
        self.sim.emit(
            "message_forward_attempt",
            success,
            packet_id=packet.id,
            traffic=packet.kind,
            attempt=packet.attempt,
        )
        self.sim.transit(source, target, success, failure, token=packet.id, lane=packet.lane)

    def _arrive(self, action: PacketArrival) -> None:
        packet = self.traffic.packets[action.token]
        if packet.status != "active":
            return
        node = self.sim.topology.nodes[action.target]
        if not node.online:
            self.sim.schedule(
                PacketLost(
                    source=action.source,
                    target=action.target,
                    token=action.token,
                    message_id=action.message_id,
                    lane=action.lane,
                    origin=FailureOrigin.TARGET_OFFLINE,
                ),
                self.sim.config.ack_timeout_ms,
            )
            return
        self.sim.emit(
            "message_forward_succeeded",
            action,
            packet_id=packet.id,
            traffic=packet.kind,
            attempt=packet.attempt,
        )
        channel = self.sim.topology.channel_ids.get(packet.source_id)
        if node.id == channel:
            self.sim.channel_crossing(packet.source_id, action, entering=True, packet_id=packet.id)
            self._transit(packet, action, node.id, packet.first_node)
            return
        if action.source == channel:
            self.sim.channel_crossing(packet.source_id, action, entering=False, packet_id=packet.id)
        try:
            hop = self.traffic.process(packet.id, node.id, self.sim.now)
        except ValueError as err:
            self.traffic.fail(packet.id, self.sim.now, str(err))
            self._failure(packet, action, str(err))
            return
        self.sim.emit(
            "sphinx_layer_processed",
            action,
            packet_id=packet.id,
            traffic=packet.kind,
            replay_count=self.traffic.sphinx.replay_count(node.id),
            next_id=hop.next_id,
            delay_ms=hop.delay_ms,
            integrity="verified",
        )
        if (
            self.traffic.local_observation(action.source, node.id) is not None
            or self.traffic.local_observation(node.id, action.source) is not None
        ):
            self.sim.emit("mixnet_adjacency_updated", action, observation="online", packet_id=packet.id)
        if hop.next_id is None:
            if packet.kind == "client_loop":
                self.sim.inboxes[packet.source_id].messages.append(b"")
            elif packet.kind == "payload" and action.message_id in self._transfers:
                transfer = self._transfers[action.message_id]
                assert hop.payload is not None
                payload = transfer.accept(hop.payload)
                if payload is not None:
                    del self._transfers[action.message_id]
                    self.sim.schedule(
                        PacketDelivered(
                            source=node.id,
                            target=packet.target_id,
                            token=packet.id,
                            lane=packet.lane,
                            message_id=action.message_id,
                            payload=payload,
                        )
                    )
            return
        release = PacketRelease(
            source=node.id,
            target=hop.next_id,
            token=packet.id,
            lane=packet.lane,
            message_id=action.message_id,
        )
        self.sim.emit(
            "mix_packet_queued",
            release,
            packet_id=packet.id,
            delay_ms=hop.delay_ms,
            release_at=packet.release_at,
            traffic=packet.kind,
        )
        self.sim.schedule(release, hop.delay_ms)

    def _release(self, action: PacketRelease) -> None:
        packet = self.traffic.packets[action.token]
        if packet.status != "active":
            return
        if not self.sim.topology.nodes[action.source].online:
            self.traffic.fail(packet.id, self.sim.now, "Queue owner unavailable")
            self._failure(packet, action, "Queue owner unavailable")
            return
        self.traffic.release(packet.id, action.source, self.sim.now)
        self.sim.emit("mix_packet_released", action, packet_id=packet.id, traffic=packet.kind)
        self._transit(packet, action, action.source, action.target)

    def _make_retry(self, failed: Packet, action: Action) -> Packet:
        retry = self.traffic.retry(failed.id)
        assert retry is not None
        self.sim.emit(
            "packet_retry_scheduled",
            action,
            previous_packet_id=failed.id,
            packet_id=retry.id,
            attempt=retry.attempt,
        )
        return retry

    def _failure(self, packet: Packet, action: Action, reason: str) -> None:
        self.sim.emit(
            "message_forward_failed",
            action,
            packet_id=packet.id,
            traffic=packet.kind,
            attempt=packet.attempt,
            reason=reason,
        )
        if packet.kind != "payload" or action.message_id not in self._transfers:
            packet.original_payload = b""
            return
        if packet.attempt <= self.sim.config.max_retries:
            retry = packet
            if self.sim.topology.nodes[packet.source_id].online:
                retry = self._make_retry(packet, action)
            self._retries[packet.source_id].append((action.message_id, retry))
            if retry is packet:
                self._wait_for_source(packet.source_id)
            return
        self._source_deadlines.pop(action.message_id, None)
        del self._transfers[action.message_id]
        if self._sending.get(packet.source_id) == action.message_id:
            del self._sending[packet.source_id]
        packet.original_payload = b""
        self.sim.schedule(
            PacketFailed(
                source=packet.source_id,
                target=packet.target_id,
                message_id=action.message_id,
                lane=packet.lane,
                token=packet.id,
                reason=reason,
            )
        )
