"""Anonymous service reads over forward Sphinx packets and client-created reply blocks."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from secrets import token_bytes
from struct import Struct
from typing import TYPE_CHECKING, Literal

import msgpack
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from .crypto import seal, unseal
from .engine import TransportFailure
from .sphinx import ReplyBlock, ReplySecret
from .steps import Action
from .topology import MixNode

if TYPE_CHECKING:
    from .storage_simulation import StorageSimulation

# The anonymous service adapter fragments bytes inside fixed-size Sphinx bodies.
_CHUNK = 896
_FRAME = Struct("!16sII")
Direction = Literal["request", "response"]


@dataclass(kw_only=True)
class RetrievalCallback(Action):
    data: bytes = field(default=b"", repr=False)
    ticket: str = field(default="", repr=False)


@dataclass(kw_only=True)
class RetrievalCell(Action):
    exchange: str
    direction: Direction
    index: int
    wire: bytes = field(repr=False)
    entry: str = ""
    reply_id: bytes = field(default=b"", repr=False)


@dataclass(kw_only=True)
class ReleaseRetrieval(Action):
    cell: RetrievalCell = field(repr=False)


@dataclass(kw_only=True)
class RetrievalFailure(TransportFailure):
    exchange: str
    reason: str = "Retrieval path unavailable"


@dataclass
class _Exchange:
    device: str
    service: str
    arrived: RetrievalCallback
    failed: Action
    tag: bytes = field(repr=False)
    expires: int
    client_secrets: list[ReplySecret] = field(default_factory=list, repr=False)
    # Populated only at the service from a received and authenticated request.
    service_blocks: list[ReplyBlock] = field(default_factory=list, repr=False)
    parts: dict[int, bytes] = field(default_factory=dict, repr=False)
    waiting: dict[str, str] = field(default_factory=dict)
    count: int = 0
    state: Literal["request", "service", "response"] = "request"


class RetrievalTransport:
    def __init__(self, sim: StorageSimulation):
        self.sim = sim
        self.routing = sim.packets.traffic.routing
        self.sphinx = sim.packets.traffic.sphinx
        self._service_keys = {
            node: X25519PrivateKey.generate()
            for node in [*sim.topology.storage_ids, *sim.topology.dht_ids]
        }
        self._exchanges: dict[str, _Exchange] = {}
        self._serial = 0

    def _event(self, name: str, ticket: str, ex: _Exchange, action: Action, **details: object) -> None:
        self.sim.emit(
            name,
            action,
            exchange_id=ticket,
            service_id=ex.service,
            operation="manifest" if self.sim.topology.nodes[ex.service].kind == "dht" else "fragment",
            **details,
        )

    def request(
        self,
        device: str,
        service: str,
        payload: bytes,
        reply_capacity: int,
        arrived: RetrievalCallback,
        failed: Action,
    ) -> str:
        if reply_capacity < 0:
            raise ValueError("Negative reply capacity")
        topo = self.sim.topology
        client_gateway = topo.provider_for(device)
        service_gateway = topo.service_gateways[service]
        self._serial += 1
        ticket = f"retrieval-{self._serial}"
        validity = max(3_600_000, 100 * self.sim.config.rpc_timeout_ms)
        ex = _Exchange(device, service, arrived, failed, token_bytes(16), self.sim.now + validity)
        blocks = []
        for _ in range(max(1, (reply_capacity + _CHUNK - 1) // _CHUNK)):
            route = self.routing.route(service_gateway, client_gateway)
            block, secret = self.sphinx.create_surb(
                route.nodes[1:], route.delays_ms[1:], destination=device
            )
            blocks.append(block.to_bytes())
            ex.client_secrets.append(secret)
        envelope = seal(
            self._service_keys[service].public_key().public_bytes_raw(),
            msgpack.packb([ex.tag, payload, blocks], use_bin_type=True),
            "retrieval",
        )
        ex.count = (len(envelope) + _CHUNK - 1) // _CHUNK
        self._exchanges[ticket] = ex
        self._event(
            "retrieval_request_created",
            ticket,
            ex,
            replace(arrived, source=device, target=client_gateway),
            cells=ex.count,
            reply_blocks=len(blocks),
            expires_ms=ex.expires,
        )
        for index in range(ex.count):
            part = (
                _FRAME.pack(ex.tag, index, ex.count) + envelope[index * _CHUNK : (index + 1) * _CHUNK]
            )
            route = self.routing.route(client_gateway, service_gateway)
            wire = self.sphinx.build(route.nodes, route.delays_ms, part)
            cell = RetrievalCell(
                exchange=ticket,
                token=f"{ticket}-q{index}",
                direction="request",
                index=index,
                entry=client_gateway,
                wire=wire,
                lane=arrived.lane,
                message_id=arrived.message_id,
            )
            self._move(cell, device, topo.channel_ids[device])
        self.sim.schedule(
            RetrievalFailure(exchange=ticket, reason="Reply block validity expired"), validity
        )
        return ticket

    def reply(self, ticket: str, payload: bytes, delivered: RetrievalCallback, failed: Action) -> None:
        ex = self._exchanges.get(ticket)
        if ex is None or ex.state != "service":
            return
        ex.failed, ex.arrived = failed, delivered
        count = max(1, (len(payload) + _CHUNK - 1) // _CHUNK)
        if count > len(ex.service_blocks) or self.sim.now >= ex.expires:
            self._fail(ticket, "Reply block capacity or lifetime exceeded")
            return
        ex.state, ex.count = "response", count
        gateway = self.sim.topology.service_gateways[ex.service]
        self._event(
            "retrieval_reply_sent",
            ticket,
            ex,
            replace(delivered, source=ex.service, target=gateway),
            cells=count,
        )
        for index, block in enumerate(ex.service_blocks[:count]):
            part = _FRAME.pack(ex.tag, index, count) + payload[index * _CHUNK : (index + 1) * _CHUNK]
            try:
                wire = self.sphinx.use_surb(block, part)
            except ValueError as error:
                self._fail(ticket, str(error))
                return
            cell = RetrievalCell(
                exchange=ticket,
                token=f"{ticket}-r{index}",
                direction="response",
                index=index,
                entry=block.first_node,
                wire=wire,
                lane=delivered.lane,
                message_id=delivered.message_id,
            )
            self._move(cell, ex.service, gateway)
        ex.service_blocks.clear()

    def _move(self, cell: RetrievalCell, source: str, target: str) -> None:
        arrival = replace(cell, source=source, target=target)
        miss = RetrievalFailure(
            exchange=cell.exchange,
            source=source,
            target=target,
            token=cell.token,
            lane=cell.lane,
            message_id=cell.message_id,
        )
        self.sim.transit(source, target, arrival, miss, token=cell.token, lane=cell.lane)

    def cancel(self, ticket: str) -> None:
        ex = self._exchanges.pop(ticket, None)
        if ex:
            for token, owner in ex.waiting.items():
                node = self.sim.topology.nodes[owner]
                if isinstance(node, MixNode):
                    node.delayed_packets.pop(token, None)
                    self.sim.emit(
                        "mix_packet_cancelled",
                        Action(
                            source=owner,
                            token=token,
                            lane=ex.arrived.lane,
                            message_id=ex.arrived.message_id,
                        ),
                        packet_id=token,
                        traffic="retrieval",
                    )

    def _fail(self, ticket: str, reason: str) -> None:
        ex = self._exchanges.get(ticket)
        if ex:
            self.cancel(ticket)
            self._event("retrieval_transport_failed", ticket, ex, ex.failed, reason=reason)
            self.sim.schedule(ex.failed)

    def _collect(self, ex: _Exchange, cell: RetrievalCell, frame: bytes) -> None:
        if len(frame) < _FRAME.size:
            raise ValueError("Truncated retrieval cell")
        tag, index, count = _FRAME.unpack_from(frame)
        if (
            tag != ex.tag
            or index != cell.index
            or count != ex.count
            or index >= count
            or index in ex.parts
        ):
            raise ValueError("Invalid retrieval frame association")
        ex.parts[index] = frame[_FRAME.size :]
        if len(ex.parts) != count:
            return
        data = b"".join(ex.parts[i] for i in range(count))
        ex.parts.clear()
        if cell.direction == "request":
            content = unseal(self._service_keys[cell.target], data, "retrieval")
            request_tag, payload, blocks = msgpack.unpackb(content, raw=False)
            if request_tag != tag or not isinstance(payload, bytes) or not isinstance(blocks, list):
                raise ValueError("Invalid retrieval request")
            ex.service_blocks = [ReplyBlock.from_bytes(block) for block in blocks]
            ex.state = "service"
            self._event("retrieval_request_delivered", cell.exchange, ex, cell, cells=count)
            self.sim.schedule(replace(ex.arrived, data=payload, ticket=cell.exchange))
        else:
            self.cancel(cell.exchange)
            self._event("retrieval_reply_received", cell.exchange, ex, cell, cells=count)
            self.sim.schedule(replace(ex.arrived, data=data))

    def _arrive(self, ex: _Exchange, cell: RetrievalCell) -> None:
        topo = self.sim.topology
        target = topo.nodes[cell.target]
        channel = topo.channel_ids[ex.device]
        if cell.target == channel:
            self.sim.channel_crossing(ex.device, cell, entering=True)
            self._move(cell, channel, cell.entry if cell.direction == "request" else ex.device)
            return
        if cell.source == channel:
            self.sim.channel_crossing(ex.device, cell, entering=False)
        if cell.direction == "response":
            if cell.source == ex.service:
                self._move(cell, target.id, cell.entry)
                return
            if cell.target == ex.device:
                data = ex.client_secrets[cell.index].open(cell.reply_id, cell.wire)
                self._collect(ex, cell, data)
                return
        elif cell.target == ex.service:
            self._collect(ex, cell, cell.wire)
            return
        hop = self.sphinx.peel(cell.target, cell.wire)
        target.last_activity = self.sim.now
        traffic = self.sim.packets.traffic
        traffic.observe(cell.source, target.id, self.sim.now, True)
        traffic.observe(target.id, cell.source, self.sim.now, True)
        self.sim.emit(
            "sphinx_layer_processed",
            cell,
            packet_id=cell.token,
            traffic="retrieval",
            replay_count=self.sphinx.replay_count(target.id),
            next_id=hop.next_id,
            delay_ms=hop.delay_ms,
            integrity="verified",
        )
        if hop.next_id is None:
            if hop.payload is None:
                raise ValueError("Missing retrieval packet payload")
            if cell.direction == "response":
                if hop.reply_destination != ex.device or not hop.reply_id:
                    raise ValueError("Unexpected anonymous reply destination")
                destination, reply_id = topo.channel_ids[hop.reply_destination], hop.reply_id
            else:
                destination, reply_id = ex.service, b""
            self._move(replace(cell, wire=hop.payload, reply_id=reply_id), target.id, destination)
        else:
            if hop.packet is None:
                raise ValueError("Missing retrieval forwarding packet")
            if isinstance(target, MixNode):
                target.delayed_packets[cell.token] = self.sim.now + hop.delay_ms
            ex.waiting[cell.token] = target.id
            onward = replace(cell, source=target.id, target=hop.next_id, wire=hop.packet)
            self.sim.emit(
                "mix_packet_queued",
                onward,
                packet_id=cell.token,
                traffic="retrieval",
                delay_ms=hop.delay_ms,
                release_at=self.sim.now + hop.delay_ms,
            )
            self.sim.schedule(ReleaseRetrieval(source=target.id, cell=onward), hop.delay_ms)

    def handle(self, action: Action) -> bool:
        if isinstance(action, RetrievalFailure):
            if (
                action.exchange in self._exchanges
                and action.origin is not None
                and action.origin.dispatched
                and self.sim.packets.traffic.observe(action.source, action.target, self.sim.now, False)
            ):
                self.sim.emit(
                    "mixnet_adjacency_updated",
                    action,
                    observation="unresponsive",
                    packet_id=action.token,
                )
            self._fail(action.exchange, action.reason)
        elif isinstance(action, (ReleaseRetrieval, RetrievalCell)):
            cell = action.cell if isinstance(action, ReleaseRetrieval) else action
            ex = self._exchanges.get(cell.exchange)
            if ex is None or cell.direction != ex.state:
                return True
            if isinstance(action, ReleaseRetrieval):
                node = self.sim.topology.nodes[action.source]
                if isinstance(node, MixNode):
                    node.delayed_packets.pop(cell.token, None)
                ex.waiting.pop(cell.token, None)
                self.sim.emit("mix_packet_released", cell, packet_id=cell.token, traffic="retrieval")
                self._move(cell, cell.source, cell.target)
            else:
                try:
                    self._arrive(ex, cell)
                except ValueError as error:
                    self._fail(cell.exchange, str(error))
        else:
            return False
        return True

    def cargo(self, action: Action) -> dict[str, object] | None:
        if isinstance(action, RetrievalCell):
            return {
                "kind": "Anonymous retrieval",
                "phase": action.direction,
                "exchange_id": action.exchange,
                "bytes": len(action.wire),
                "cell": action.index + 1,
            }
        return None
