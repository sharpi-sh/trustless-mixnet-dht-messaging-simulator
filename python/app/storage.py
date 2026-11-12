"""Replicated ciphertext fragments held by independent simulated storage nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from random import Random
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .config import Model

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Fragment(Model):
    id: Digest
    index: int = Field(ge=0)
    offset: int = Field(ge=0)
    size: int = Field(ge=0)
    digest: Digest
    replicas: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_replicas(self) -> Self:
        if len(set(self.replicas)) != len(self.replicas) or not all(self.replicas):
            raise ValueError("Fragment replicas must be distinct non-empty node IDs")
        return self

    def verify(self, data: bytes) -> None:
        if (
            not isinstance(data, bytes)
            or len(data) != self.size
            or sha256(data).hexdigest() != self.digest
        ):
            raise ValueError("Fragment ciphertext size or SHA-256 mismatch")


class MessageManifest(Model):
    id: Digest
    size: int = Field(ge=0)
    digest: Digest
    fragments: tuple[Fragment, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def complete_sequence(self) -> Self:
        offset = 0
        seen = set()
        for index, fragment in enumerate(self.fragments):
            if fragment.index != index or fragment.offset != offset or fragment.id in seen:
                raise ValueError("Manifest fragments must be ordered, unique and contiguous")
            seen.add(fragment.id)
            offset += fragment.size
        if offset != self.size:
            raise ValueError("Manifest size differs from its fragments")
        return self


@dataclass(slots=True)
class _Placement:
    fragment: Fragment
    write_attempts: int = 0
    retrieval_attempts: int = 0
    integrity: Literal["unchecked", "verified", "failed"] = "unchecked"
    last_failure: str | None = None
    used_in_reconstruction: bool = False


@dataclass
class StorageNode:
    node_id: str
    address: str
    fragments: dict[str, bytes] = field(default_factory=dict, repr=False)
    capacity_bytes: int = 16 * 1024 * 1024
    placements: dict[str, _Placement] = field(default_factory=dict, repr=False)

    @property
    def used_bytes(self) -> int:
        return sum(map(len, self.fragments.values()))


class StorageNetwork:
    def __init__(self, peers: list[str], *, capacity_bytes: int = 16 * 1024 * 1024) -> None:
        if len(set(peers)) != len(peers) or any(not peer for peer in peers):
            raise ValueError("Storage nodes require unique non-empty names")
        if capacity_bytes < 0:
            raise ValueError("Storage capacity must be non-negative")
        self.nodes = {
            peer: StorageNode(peer, f"sim://{peer}", capacity_bytes=capacity_bytes) for peer in peers
        }

    def plan(
        self, message_id: str, ciphertext: bytes, rng: Random, chunk_bytes: int, replicas: int
    ) -> MessageManifest:
        if not message_id or not isinstance(ciphertext, bytes):
            raise ValueError("A message ID and opaque ciphertext bytes are required")
        if chunk_bytes < 1 or not 1 <= replicas <= len(self.nodes):
            raise ValueError("Invalid chunk size or replica count")
        digest = sha256(ciphertext).hexdigest()
        # Bind fragment identifiers to the message, envelope and position without exposing the message ID.
        scope = sha256(b"vault-envelope\x00" + bytes.fromhex(digest) + message_id.encode()).digest()
        fragments = []
        locations = sorted(self.nodes)
        for i, offset in enumerate(range(0, max(1, len(ciphertext)), chunk_bytes)):
            part = ciphertext[offset : offset + chunk_bytes]
            fragment = Fragment(
                id=sha256(b"vault-fragment\x00" + scope + i.to_bytes(8, "big")).hexdigest(),
                index=i,
                offset=offset,
                size=len(part),
                digest=sha256(part).hexdigest(),
                replicas=tuple(rng.sample(locations, replicas)),
            )
            fragments.append(fragment)
        # A revised placement plan has its own manifest identifier.
        manifest_hash = sha256(b"vault-manifest\x00" + scope)
        for fragment in fragments:
            manifest_hash.update(fragment.model_dump_json().encode())
        manifest = MessageManifest(
            id=manifest_hash.hexdigest(),
            size=len(ciphertext),
            digest=digest,
            fragments=tuple(fragments),
        )
        for fragment in fragments:
            for peer in fragment.replicas:
                self._placement(peer, fragment)
        return manifest

    def _placement(self, node_id: str, fragment: Fragment) -> _Placement:
        if node_id not in self.nodes or node_id not in fragment.replicas:
            raise ValueError("Node is not an assigned storage replica")
        placements = self.nodes[node_id].placements
        if fragment.id not in placements:
            placements[fragment.id] = _Placement(fragment)
        return placements[fragment.id]

    def put(self, node_id: str, fragment: Fragment, data: bytes) -> None:
        placement = self._placement(node_id, fragment)
        placement.write_attempts += 1
        try:
            fragment.verify(data)
        except ValueError:
            placement.integrity = "failed"
            placement.last_failure = "integrity"
            raise
        node = self.nodes[node_id]
        previous = node.fragments.get(fragment.id, b"")
        if node.used_bytes - len(previous) + len(data) > node.capacity_bytes:
            placement.last_failure = "capacity"
            raise ValueError("Storage node capacity exceeded")
        node.fragments[fragment.id] = data
        placement.integrity = "verified"
        placement.last_failure = None

    def get(self, node_id: str, fragment: Fragment) -> bytes:
        placement = self._placement(node_id, fragment)
        placement.retrieval_attempts += 1
        data = self.nodes[node_id].fragments.get(fragment.id)
        if data is None:
            placement.last_failure = "missing"
            raise ValueError("Replica is missing the ciphertext fragment")
        try:
            fragment.verify(data)
        except ValueError:
            placement.integrity = "failed"
            placement.last_failure = "integrity"
            raise
        placement.integrity = "verified"
        placement.last_failure = None
        return data

    def record_unavailable(
        self, node_id: str, fragment: Fragment, operation: Literal["read", "write"] = "read"
    ) -> None:
        """Record a simulated transport failure without accessing the vault's ciphertext."""
        placement = self._placement(node_id, fragment)
        if operation == "read":
            placement.retrieval_attempts += 1
        elif operation == "write":
            placement.write_attempts += 1
        else:
            raise ValueError("Unknown storage operation")
        placement.last_failure = "unresponsive"

    def reconstruct(self, manifest: MessageManifest, parts: dict[str, bytes]) -> bytes:
        if set(parts) != {fragment.id for fragment in manifest.fragments}:
            raise ValueError("Reconstruction requires exactly the manifest's ciphertext fragments")
        ordered = []
        for fragment in manifest.fragments:
            part = parts[fragment.id]
            fragment.verify(part)
            ordered.append(part)
        data = b"".join(ordered)
        if len(data) != manifest.size or sha256(data).hexdigest() != manifest.digest:
            raise ValueError("Reconstructed ciphertext size or SHA-256 mismatch")
        for fragment in manifest.fragments:
            for peer in fragment.replicas:
                # The flag describes the logical fragment, independently of which replica supplied it.
                node = self.nodes.get(peer)
                if node and fragment.id in node.placements:
                    node.placements[fragment.id].used_in_reconstruction = True
        return data

    def inspect(self, peer: str) -> dict[str, object]:
        node = self.nodes[peer]
        return {
            "node_id": node.node_id,
            "address": node.address,
            "fragment_ids": sorted(node.fragments),
            "capacity_bytes": node.capacity_bytes,
            "used_bytes": node.used_bytes,
            "fragments": [
                {
                    **p.fragment.model_dump(mode="json"),
                    "placement": "stored" if fid in node.fragments else "planned",
                    "write_attempts": p.write_attempts,
                    "retrieval_attempts": p.retrieval_attempts,
                    "integrity": p.integrity,
                    "last_failure": p.last_failure,
                    "used_in_reconstruction": p.used_in_reconstruction,
                }
                for fid, p in sorted(node.placements.items())
            ],
        }
