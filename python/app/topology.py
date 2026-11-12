"""The simulator's explicit local connections. A path can carry traffic in either direction."""

import itertools
from dataclasses import dataclass, field
from random import Random
from typing import Any, Literal

from pydantic import Field

from .config import Config, Model
from .participants import People


class Node(Model):
    id: str
    label: str
    kind: Literal["person", "tor", "provider", "mix", "dht", "storage"]
    stage_index: int
    stage: str
    simulated_address: str
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


class NetworkPath(Model):
    id: str
    source_id: str
    target_id: str
    boundary: str
    transport_label: str
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


class Topology:
    def __init__(self, config: Config, rng: Random, people: People):
        self.config = config
        self.nodes: dict[str, Node] = {}
        self.paths: dict[str, NetworkPath] = {}
        self.mixnet = Mixnet()
        for person in people.people.values():
            sender = person.role == "sender"
            self.add_node(
                person.id,
                person.label,
                "person",
                0 if sender else 10,
                "Sender" if sender else "Recipient",
            )
            self.add_node(
                person.tor.id,
                "Tor abstraction",
                "tor",
                1 if sender else 9,
                "Sender Tor" if sender else "Recipient Tor",
            )
            self.connect(person.id, person.tor.id, "local/TCP abstraction")
        for idx, provider in enumerate(self.mixnet.providers):
            self.add_node(
                provider,
                ["West provider", "East provider"][idx],
                "provider",
                2 + 4 * idx,
                ["West provider", "East provider"][idx],
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
        self.dht_ids = [f"dht-{i + 1}" for i in range(config.dht_nodes)]
        self.storage_ids = [f"storage-{i + 1}" for i in range(config.storage_nodes)]
        for i, dht in enumerate(self.dht_ids):
            self.add_node(dht, f"DHT {i + 1}", "dht", 7, "DHT")
            for peer in self.dht_ids[:i]:
                self.connect(dht, peer, "Kademlia RPC")
            for provider in self.mixnet.providers:
                self.connect(provider, dht, "opaque application handoff")
        for i, store in enumerate(self.storage_ids):
            self.add_node(store, f"Vault {i + 1}", "storage", 8, "Vault")
            for dht in self.dht_ids:
                self.connect(dht, store, "encrypted fragment transfer")
        for person in people.people.values():
            provider = self.mixnet.providers[int(person.role == "receiver")]
            self.connect(person.tor.id, provider, "Tor egress → Loopix provider")
            for dht in self.dht_ids:
                self.connect(person.tor.id, dht, "opaque mailbox lookup")
            for storage in self.storage_ids:
                self.connect(person.tor.id, storage, "encrypted fragment transfer")

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
        self.paths[uid] = NetworkPath(
            id=uid,
            source_id=left.id,
            target_id=right.id,
            boundary=f"{left.stage} ↔ {right.stage}",
            transport_label=label,
            base_transit_delay_ms=self.config.base_transit_delay_ms,
            jitter_min_ms=self.config.jitter_min_ms,
            jitter_max_ms=self.config.jitter_max_ms,
        )
        for node, peer in [(left, right), (right, left)]:
            if isinstance(node, MixNode):
                node.adjacent_peers[peer.id] = Observation(peer_id=peer.id)

    def snapshot(self) -> dict[str, Any]:
        return {
            "nodes": [n.model_dump() for n in self.nodes.values()],
            "paths": [p.model_dump() for p in self.paths.values()],
        }
