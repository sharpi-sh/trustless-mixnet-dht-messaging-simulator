"""Node identities in the simulator's Kademlia identifier space."""

from dataclasses import dataclass
from random import Random

ID_BITS = 160
ID_SPACE = 1 << ID_BITS
K = 20
ALPHA = 3


@dataclass
class DHTNode:
    peer_id: str
    node_id: int
    address: str


class DHTNetwork:
    def __init__(self, rng: Random) -> None:
        self.rng = rng
        self.nodes: dict[str, DHTNode] = {}
        self._allocated_ids: set[int] = set()

    def add_node(self, peer_id: str, node_id: int | None = None) -> DHTNode:
        if not peer_id or peer_id in self.nodes:
            raise ValueError("A DHT peer requires a unique non-empty name")
        if node_id is None:
            node_id = self.rng.getrandbits(ID_BITS)
            while node_id in self._allocated_ids:
                node_id = self.rng.getrandbits(ID_BITS)
        if not 0 <= node_id < ID_SPACE or node_id in self._allocated_ids:
            raise ValueError("Expected a unique unsigned 160-bit node ID")
        node = DHTNode(peer_id, node_id, f"sim://{peer_id}")
        self._allocated_ids.add(node_id)
        self.nodes[peer_id] = node
        return node

    def inspect(self, peer: str, now: int) -> dict[str, object]:
        node = self.nodes[peer]
        return {
            "peer_id": node.peer_id,
            "node_id": f"{node.node_id:040x}",
            "address": node.address,
            "simulation_time_ms": now,
            "k": K,
            "alpha": ALPHA,
        }
