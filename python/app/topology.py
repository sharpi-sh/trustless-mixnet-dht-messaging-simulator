"""The simulator's explicit local connections. A path can carry traffic in either direction."""

import itertools
from dataclasses import dataclass, field
from random import Random
from typing import Any, Literal

from pydantic import Field

from .config import ChannelKind, Config, Model
from .participants import People

_CHANNEL_LABEL: dict[ChannelKind, str] = {
    "tor": "Tor abstraction",
    "shadowsocks": "Outline Shadowsocks proxy abstraction",
    "direct": "Direct interface",
}
_CHANNEL_ENTRY: dict[ChannelKind, str] = {
    "tor": "Tor guard connection",
    "shadowsocks": "Shadowsocks client to proxy",
    "direct": "Local interface handoff",
}
_CHANNEL_EGRESS: dict[ChannelKind, str] = {
    "tor": "Tor exit",
    "shadowsocks": "Shadowsocks proxy",
    "direct": "Direct connection",
}


class Node(Model):
    id: str
    label: str
    kind: Literal["person", "tor", "shadowsocks", "direct", "provider", "mix", "dht", "storage"]
    stage_index: int
    stage: str
    simulated_address: str
    egress_address: str | None = None
    operator_id: str
    online: bool = True
    history: list[tuple[int, bool]] = Field(default_factory=list)
    last_activity: int | None = None
    failure_count: int = 0


class Observation(Model):
    peer_id: str
    status: Literal["unknown", "online", "unresponsive"] = "unknown"
    last_contact: int | None = None
    last_failure: int | None = None
    failures: int = 0
    successes: int = 0


class MixNode(Node):
    adjacent_peers: dict[str, Observation] = Field(default_factory=dict)
    delayed_packets: dict[str, int] = Field(default_factory=dict)


class ProviderNode(Node):
    pass


class IPHop(Model):
    source_ip: str
    destination_ip: str
    observed_source_ip: str
    observer: str
    description: str
    local: bool

    @classmethod
    def from_nodes(cls, source: Node, target: Node, local: bool) -> "IPHop":
        # A channel faces the device on its ingress address and peers on its egress.
        source_ip = (
            source.simulated_address
            if target.kind == "person"
            else source.egress_address or source.simulated_address
        )
        destination_ip = (
            target.simulated_address
            if source.kind == "person"
            else target.egress_address or target.simulated_address
        )
        if local:
            description = (
                "The direct interface shares its device’s address. This handoff stays on the device."
            )
        elif target.kind == "tor":
            description = (
                "The Tor guard sees the device’s IP address."
                if source.kind == "person"
                else "The Tor exit receives a response from the remote peer’s IP address."
            )
        elif target.kind == "shadowsocks":
            description = (
                "The Shadowsocks server sees the device’s IP address."
                if source.kind == "person"
                else "The Shadowsocks server receives a response from the remote peer’s IP address."
            )
        elif source.kind == "tor":
            description = (
                "The device sees its Tor guard’s IP address."
                if target.kind == "person"
                else "The destination sees the Tor exit’s IP address."
            )
        elif source.kind == "shadowsocks":
            description = "The receiving peer sees the Shadowsocks server’s IP address."
        elif source.kind == "direct":
            description = "The destination sees the device’s own IP address."
        else:
            description = "The receiving peer sees the immediate sender’s IP address."
        return cls(
            source_ip=source_ip,
            destination_ip=destination_ip,
            observed_source_ip=source_ip,
            observer=target.id,
            description=description,
            local=local,
        )


class NetworkPath(Model):
    id: str
    source_id: str
    target_id: str
    boundary: str
    transport_label: str
    ip_hops: dict[str, IPHop]
    local: bool
    base_transit_delay_ms: int
    jitter_min_ms: int
    jitter_max_ms: int
    blocked: bool = False
    blocked_at: int | None = None
    blocked_by: str | None = None
    active: dict[str, dict[str, Any]] = Field(default_factory=dict)
    attempted: int = 0
    completed: int = 0
    failed: int = 0
    dropped: int = 0

    def delay(self, rng: Random) -> int:
        return self.base_transit_delay_ms + rng.randint(self.jitter_min_ms, self.jitter_max_ms)


@dataclass(frozen=True, slots=True)
class GlobalObserver:
    id: str
    lifecycle: str = "created"


@dataclass(slots=True)
class Mixnet:
    layers: list[list[str]] = field(default_factory=lambda: [[], [], []])
    providers: tuple[str, str] = ("provider-west", "provider-east")
    service_providers: tuple[str, ...] = ("provider-service",)


class Topology:
    def __init__(self, config: Config, rng: Random, people: People):
        self.config = config
        self.nodes: dict[str, Node] = {}
        self.paths: dict[str, NetworkPath] = {}
        self.mixnet = Mixnet()
        self.channel_ids = {uid: person.tor.id for uid, person in people.people.items()}
        for person in people.people.values():
            sender = person.role == "sender"
            device = self.add_node(
                person.id,
                person.label,
                "person",
                0 if sender else 10,
                "Sender" if sender else "Recipient",
            )
            kind = person.tor.kind
            channel = self.add_node(
                person.tor.id,
                _CHANNEL_LABEL[kind],
                kind,
                1 if sender else 9,
                "Sender connection" if sender else "Recipient connection",
            )
            if kind == "direct":
                channel.simulated_address = device.simulated_address
                channel.operator_id = device.operator_id
            channel.egress_address = (
                channel.simulated_address.replace("10.77.", "10.78.", 1)
                if kind == "tor"
                else channel.simulated_address
            )
            self.connect(person.id, channel.id, _CHANNEL_ENTRY[kind])
        for idx, provider in enumerate(self.mixnet.providers):
            self.add_node(
                provider,
                ["West provider", "East provider"][idx],
                "provider",
                2 + 4 * idx,
                ["West provider", "East provider"][idx],
            )
        for provider in self.mixnet.service_providers:
            self.add_node(
                provider,
                "Anonymous service gateway",
                "provider",
                6,
                "Service gateway",
            )
        count = (
            rng.randint(config.min_nodes, config.max_nodes)
            if config.randomise_count
            else config.min_nodes
        )
        for i in range(count):
            layer = i % 3
            name = f"mix-{i + 1}"
            self.add_node(name, f"Mix {i + 1}", "mix", 3 + layer, f"Layer {layer + 1}")
            self.mixnet.layers[layer].append(name)
        # Both client providers can act as ingress or egress. Provider wrap-around also supports mix loops.
        groups = [list(self.mixnet.providers), *self.mixnet.layers, list(self.mixnet.providers)]
        for left, right in itertools.pairwise(groups):
            for a in left:
                for b in right:
                    self.connect(a, b, "Loopix datagram")
        # Service gateways are independent egress/ingress providers. They attach to
        # both ends of the layered mixnet so retrieval requests and SURB replies
        # never reuse a participant-facing West/East provider as a vault endpoint.
        for provider in self.mixnet.service_providers:
            for mix in [*self.mixnet.layers[0], *self.mixnet.layers[-1]]:
                self.connect(provider, mix, "Loopix service datagram")
        self.dht_ids = [f"dht-{i + 1}" for i in range(config.dht_nodes)]
        self.storage_ids = [f"storage-{i + 1}" for i in range(config.storage_nodes)]
        self.service_gateways = {
            uid: self.mixnet.service_providers[i % len(self.mixnet.service_providers)]
            for ids in (self.dht_ids, self.storage_ids)
            for i, uid in enumerate(ids)
        }
        for i, dht in enumerate(self.dht_ids):
            self.add_node(dht, f"DHT {i + 1}", "dht", 7, "DHT")
            for peer in self.dht_ids[:i]:
                self.connect(dht, peer, "Kademlia RPC")
            for provider in self.mixnet.providers:
                self.connect(provider, dht, "opaque application handoff")
            self.connect(
                self.service_gateways[dht], dht, "post-mix anonymous DHT service delivery"
            )
        for i, store in enumerate(self.storage_ids):
            self.add_node(store, f"Vault {i + 1}", "storage", 8, "Vault")
            self.connect(
                self.service_gateways[store], store, "post-mix anonymous vault service delivery"
            )
            for dht in self.dht_ids:
                self.connect(dht, store, "encrypted fragment transfer")
        for person in people.people.values():
            provider = self.mixnet.providers[int(person.role == "receiver")]
            self.connect(
                person.tor.id, provider, f"{_CHANNEL_EGRESS[person.tor.kind]} → Loopix provider"
            )

    def add_node(self, uid: str, label: str, kind: Any, col: int, stage: str) -> Node:
        index = len(self.nodes)
        cls = {"mix": MixNode, "provider": ProviderNode}.get(kind, Node)
        node = cls(
            id=uid,
            label=label,
            kind=kind,
            stage_index=col,
            stage=stage,
            simulated_address=f"10.77.{index // 250}.{index % 250 + 1}",
            operator_id=f"operator-{index % self.config.operator_count + 1}",
        )
        self.nodes[uid] = node
        return node

    @staticmethod
    def path_id(a: str, b: str) -> str:
        return "~".join(sorted((a, b)))

    def connect(self, a: str, b: str, label: str) -> None:
        uid = self.path_id(a, b)
        left, right = sorted([self.nodes[a], self.nodes[b]], key=lambda n: (n.stage_index, n.id))
        local = {left.kind, right.kind} == {"person", "direct"}
        self.paths[uid] = NetworkPath(
            id=uid,
            source_id=left.id,
            target_id=right.id,
            boundary=f"{left.stage} ↔ {right.stage}",
            transport_label=label,
            ip_hops={
                left.id: IPHop.from_nodes(left, right, local),
                right.id: IPHop.from_nodes(right, left, local),
            },
            local=local,
            base_transit_delay_ms=0 if local else self.config.base_transit_delay_ms,
            jitter_min_ms=0 if local else self.config.jitter_min_ms,
            jitter_max_ms=0 if local else self.config.jitter_max_ms,
        )
        for node, peer in [(left, right), (right, left)]:
            if isinstance(node, MixNode):
                node.adjacent_peers[peer.id] = Observation(peer_id=peer.id)

    def snapshot(self) -> dict[str, Any]:
        return {
            "nodes": [n.model_dump() for n in self.nodes.values()],
            "paths": [p.model_dump() for p in self.paths.values()],
        }
