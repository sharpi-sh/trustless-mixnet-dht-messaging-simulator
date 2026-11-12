"""Locally simulated encrypted fragment vault identities."""

from dataclasses import dataclass, field


@dataclass
class StorageNode:
    node_id: str
    address: str
    fragments: dict[str, bytes] = field(default_factory=dict, repr=False)


class StorageNetwork:
    def __init__(self, peers: list[str]) -> None:
        if len(set(peers)) != len(peers) or any(not peer for peer in peers):
            raise ValueError("Storage nodes require unique non-empty names")
        self.nodes = {peer: StorageNode(peer, f"sim://{peer}") for peer in peers}

    def inspect(self, peer: str) -> dict[str, object]:
        node = self.nodes[peer]
        return {
            "node_id": node.node_id,
            "address": node.address,
            "fragment_ids": sorted(node.fragments),
        }
